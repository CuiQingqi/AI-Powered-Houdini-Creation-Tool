"""
Chat Agent Loop — handles multi-turn AI conversations with tool calling.

Runs when the user chats directly through the Web UI (standalone mode).
Streams text responses and tool call events to the Web UI via EventBus.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from .ai_provider import ChatMessage, AIProvider, create_provider_from_dict
from .tools.dispatch import ToolDispatcher

logger = logging.getLogger("mcp_server.chat_agent")

SYSTEM_PROMPT = """You are a Houdini procedural artist assistant with direct control over SideFX Houdini. You can create, modify, and inspect nodes in real-time.

## Core Rules
1. Before creating nodes, check the current network state using houdini_get_network_structure.
2. After making changes, check for errors with houdini_check_errors.
3. Work inside geometry containers like /obj/geo1.
4. Use houdini_search_node_types if you don't know the exact node name.
5. Set display flags on final output nodes with houdini_set_display_flag.
6. Use houdini_create_nodes_batch for creating 3+ nodes at once.
7. After finishing, use houdini_capture_viewport to show the result.

## Communication
- Be concise. State what you're doing and why.
- Report any errors clearly.
- Summarize what was created when done."""


class ChatAgent:
    """Manages a single AI chat conversation with tool calling."""

    def __init__(self, provider: AIProvider, dispatcher: ToolDispatcher,
                 event_bus=None, max_iterations: int = 20):
        self.provider = provider
        self.dispatcher = dispatcher
        self.event_bus = event_bus
        self.max_iterations = max_iterations
        self.messages: List[ChatMessage] = []
        self._cancelled = False

    def reset(self):
        self.messages = []
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    async def send_message(self, user_text: str, tools: List[dict],
                           image_base64: str = ""):
        """Send a user message and process the AI response stream.

        Yields events:
            {"type": "text_chunk", "content": "..."}
            {"type": "thinking_chunk", "content": "..."}
            {"type": "tool_start", "tool_name": "...", "arguments": {...}}
            {"type": "tool_result", "tool_name": "...", "result": {...}}
            {"type": "error", "message": "..."}
            {"type": "done"}
        """
        self._cancelled = False

        # Build user message
        user_content = user_text
        if image_base64:
            # For providers that support vision
            user_content = [
                {"type": "text", "text": user_text},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_base64 if image_base64.startswith("data:") else f"data:image/png;base64,{image_base64}",
                    },
                },
            ]

        self.messages.append(ChatMessage(role="user", content=user_content))

        iteration = 0
        while iteration < self.max_iterations and not self._cancelled:
            iteration += 1

            # Stream text chunks to caller via queue
            text_queue = []

            async def on_text(chunk_text):
                text_queue.append(chunk_text)

            try:
                response = await self._call_ai(tools, on_text=on_text)
            except Exception as e:
                yield {"type": "error", "message": f"AI API error: {e}"}
                yield {"type": "done"}
                return

            # Yield accumulated text as a single chunk (or per-chunk if streamed)
            for text in text_queue:
                yield {"type": "text_chunk", "content": text}

            if response.tool_calls:
                # Execute tool calls
                for tc in response.tool_calls:
                    if self._cancelled:
                        yield {"type": "done"}
                        return

                    fn = tc.get("function", tc)
                    tool_name = fn.get("name", "")
                    try:
                        arguments = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        arguments = {}

                    yield {
                        "type": "tool_start",
                        "tool_name": tool_name,
                        "arguments": arguments,
                    }

                    # Execute
                    try:
                        result = await self.dispatcher.execute(tool_name, arguments)
                    except Exception as e:
                        result = {
                            "content": [{"type": "text", "text": f"Tool error: {e}"}],
                            "isError": True,
                        }

                    yield {
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "result": result,
                    }

                    # Add tool result to conversation
                    result_text = result.get("content", [{}])[0].get("text", str(result))
                    self.messages.append(ChatMessage(
                        role="assistant",
                        content="",
                        tool_calls=[tc],
                    ))
                    self.messages.append(ChatMessage(
                        role="tool",
                        content=result_text,
                        tool_call_id=tc.get("id", ""),
                    ))

            else:
                # Text response — conversation complete
                if response.content:
                    self.messages.append(ChatMessage(
                        role="assistant",
                        content=response.content,
                    ))
                yield {"type": "done"}
                return

        if iteration >= self.max_iterations:
            yield {"type": "error", "message": f"Reached max iterations ({self.max_iterations})"}
        yield {"type": "done"}

    async def _call_ai(self, tools: List[dict], on_text = None):
        """Call the AI provider and accumulate the full response.

        Args:
            tools: List of tool definitions.
            on_text: Optional async callback(text_chunk) for streaming.

        Returns:
            AIResponse with accumulated content and tool_calls.
        """
        accumulated_content = ""
        tool_calls_acc: Dict[int, dict] = {}
        last_response = None

        async for chunk in self.provider.chat(
            messages=self.messages,
            tools=tools,
            stream=True,
        ):
            if self._cancelled:
                break

            if chunk.content:
                accumulated_content += chunk.content
                if on_text:
                    await on_text(chunk.content)

            if chunk.tool_calls:
                for tc in chunk.tool_calls:
                    fn = tc.get("function", tc)
                    idx = fn.get("index", 0)
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = tc
                    else:
                        fn_acc = tool_calls_acc[idx].get("function", tool_calls_acc[idx])
                        fn_acc["arguments"] = (fn_acc.get("arguments", "") +
                                                fn.get("arguments", ""))
                        tool_calls_acc[idx]["function"] = fn_acc

            last_response = chunk

        if last_response is None:
            last_response = type('AIResponse', (), {'content': '', 'tool_calls': None})()

        if tool_calls_acc:
            last_response.tool_calls = [
                tool_calls_acc[i] for i in sorted(tool_calls_acc.keys())
            ]
            last_response.content = ""
        elif accumulated_content:
            last_response.content = accumulated_content

        return last_response


# ── Global agent manager ────────────────────────────────────────────

class AgentManager:
    """Manages chat agents for the Web UI."""

    def __init__(self):
        self._agent: Optional[ChatAgent] = None
        self._provider: Optional[AIProvider] = None

    @property
    def has_provider(self) -> bool:
        return self._provider is not None

    def setup_provider(self, settings: dict):
        """Initialize the AI provider from settings."""
        self._provider = create_provider_from_dict(settings)

    def get_agent(self, dispatcher: ToolDispatcher, event_bus=None) -> ChatAgent:
        """Get or create a chat agent."""
        if self._agent is None:
            if self._provider is None:
                raise RuntimeError("AI provider not configured. Set API key in config/houdini_ai.ini")
            self._agent = ChatAgent(
                provider=self._provider,
                dispatcher=dispatcher,
                event_bus=event_bus,
            )
        return self._agent

    def reset(self):
        """Reset the agent conversation."""
        if self._agent:
            self._agent.reset()

    def cancel(self):
        """Cancel the current agent response."""
        if self._agent:
            self._agent.cancel()


# Singleton
_agent_manager = AgentManager()


def get_agent_manager() -> AgentManager:
    return _agent_manager
