"""
AI Provider module for standalone chat mode.

Supports OpenAI-compatible APIs (DeepSeek, OpenAI, GLM, OpenRouter),
Anthropic Claude, and Ollama local models.

Adapted from Houdini Agent V2's provider pattern.
"""

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional
from dataclasses import dataclass, field

import aiohttp

logger = logging.getLogger("mcp_server.ai_provider")


@dataclass
class ChatMessage:
    role: str  # "system", "user", "assistant", "tool"
    content: str = ""
    tool_calls: Optional[List[dict]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


@dataclass
class AIResponse:
    content: str = ""
    tool_calls: Optional[List[dict]] = None
    finish_reason: str = "stop"


class AIProvider:
    """Base class for AI providers."""

    async def chat(
        self,
        messages: List[ChatMessage],
        tools: List[dict],
        stream: bool = True,
    ) -> AsyncIterator[AIResponse]:
        raise NotImplementedError


class OpenAICompatibleProvider(AIProvider):
    """Provider for OpenAI, DeepSeek, GLM, OpenRouter, Ollama, etc."""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1",
                 model: str = "gpt-4o", temperature: float = 0.7):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature

    async def chat(self, messages: List[ChatMessage], tools: List[dict],
                   stream: bool = True) -> AsyncIterator[AIResponse]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        # Convert to OpenAI format
        openai_msgs = []
        for m in messages:
            msg = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            if m.name:
                msg["name"] = m.name
            openai_msgs.append(msg)

        # Convert tools to OpenAI function format
        openai_tools = []
        for t in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("inputSchema", t.get("parameters", {})),
                },
            })

        body = {
            "model": self.model,
            "messages": openai_msgs,
            "tools": openai_tools,
            "temperature": self.temperature,
            "stream": stream,
        }

        # DeepSeek-specific: add thinking if enabled
        # body["stream_options"] = {"include_usage": True}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"API error ({resp.status}): {error_text}")

                if stream:
                    async for chunk in self._parse_stream(resp):
                        yield chunk
                else:
                    data = await resp.json()
                    yield self._parse_response(data)

    async def _parse_stream(self, resp) -> AsyncIterator[AIResponse]:
        """Parse SSE streaming response."""
        tool_calls_acc: Dict[int, dict] = {}
        content_parts = []

        async for line in resp.content:
            line = line.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                if tool_calls_acc:
                    tc_list = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc.get("arguments", ""),
                            },
                        }
                        for tc in sorted(tool_calls_acc.values(), key=lambda x: x["index"])
                    ]
                    yield AIResponse(
                        content="",
                        tool_calls=tc_list,
                        finish_reason="tool_calls",
                    )
                break

            try:
                data = json.loads(data_str)
                choice = data.get("choices", [{}])[0]
                delta = choice.get("delta", {})

                # Text content
                if "content" in delta and delta["content"]:
                    content_parts.append(delta["content"])
                    yield AIResponse(content=delta["content"])

                # Tool calls
                if "tool_calls" in delta:
                    for tc_delta in delta["tool_calls"]:
                        idx = tc_delta.get("index", 0)
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "index": idx,
                                "id": tc_delta.get("id", ""),
                                "name": "",
                                "arguments": "",
                            }
                        tc = tool_calls_acc[idx]
                        if "id" in tc_delta:
                            tc["id"] = tc_delta["id"]
                        if "function" in tc_delta:
                            fn = tc_delta["function"]
                            if "name" in fn:
                                tc["name"] += fn["name"]
                            if "arguments" in fn:
                                tc["arguments"] += fn["arguments"]

                # Finish
                if choice.get("finish_reason") == "tool_calls" and tool_calls_acc:
                    pass  # Wait for [DONE]

            except json.JSONDecodeError:
                continue

    def _parse_response(self, data: dict) -> AIResponse:
        """Parse non-streaming response."""
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls")
        return AIResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
        )


class AnthropicProvider(AIProvider):
    """Provider for Anthropic Claude API."""

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com",
                 model: str = "claude-sonnet-4-20250514", temperature: float = 0.7):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature

    async def chat(self, messages: List[ChatMessage], tools: List[dict],
                   stream: bool = True) -> AsyncIterator[AIResponse]:
        url = f"{self.base_url}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        # Separate system messages
        system_msgs = [m.content for m in messages if m.role == "system"]
        chat_msgs = []
        for m in messages:
            if m.role == "system":
                continue
            msg = {"role": m.role, "content": m.content}
            if m.tool_calls:
                # Assistant message with tool_use blocks
                content_blocks = []
                if m.content:
                    content_blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": tc.get("function", {}).get("name", tc.get("name", "")),
                        "input": json.loads(tc.get("function", {}).get("arguments", "{}")) if isinstance(tc.get("function", {}).get("arguments"), str) else tc.get("function", {}).get("arguments", {}),
                    })
                msg["content"] = content_blocks
            if m.tool_call_id:
                msg["content"] = [
                    {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                ]
            chat_msgs.append(msg)

        # Convert tools to Anthropic format
        anthropic_tools = []
        for t in tools:
            anthropic_tools.append({
                "name": t["name"],
                "description": t["description"],
                "input_schema": t.get("inputSchema", t.get("parameters", {})),
            })

        body = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": chat_msgs,
            "tools": anthropic_tools,
            "temperature": self.temperature,
            "stream": stream,
        }
        if system_msgs:
            body["system"] = "\n\n".join(system_msgs)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"Anthropic API error ({resp.status}): {error_text}")

                if stream:
                    async for chunk in self._parse_stream(resp):
                        yield chunk

    async def _parse_stream(self, resp) -> AsyncIterator[AIResponse]:
        """Parse Anthropic SSE streaming."""
        async for line in resp.content:
            line = line.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            event_type = data.get("type", "")

            if event_type == "content_block_start":
                block = data.get("content_block", {})
                if block.get("type") == "tool_use":
                    yield AIResponse(
                        content="",
                        tool_calls=[{
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": "",
                            },
                        }],
                    )

            elif event_type == "content_block_delta":
                delta = data.get("delta", {})
                delta_type = delta.get("type", "")
                if delta_type == "text_delta":
                    yield AIResponse(content=delta.get("text", ""))
                elif delta_type == "input_json_delta":
                    yield AIResponse(content=delta.get("partial_json", ""))

            elif event_type == "content_block_stop":
                yield AIResponse(finish_reason="tool_calls")

            elif event_type == "message_delta":
                if data.get("delta", {}).get("stop_reason") == "end_turn":
                    yield AIResponse(finish_reason="stop")


def create_provider(config) -> AIProvider:
    """Create an AI provider from configuration.

    Args:
        config: An object with AI-related attributes (from config.py).
    """
    return create_provider_from_dict({
        "provider": getattr(config, "ai_provider", "deepseek"),
        "openai_api_key": getattr(config, "openai_api_key", ""),
        "openai_base_url": getattr(config, "openai_base_url", "https://api.deepseek.com/v1"),
        "openai_model": getattr(config, "openai_model", "deepseek-chat"),
        "anthropic_api_key": getattr(config, "anthropic_api_key", ""),
        "anthropic_base_url": getattr(config, "anthropic_base_url", "https://api.anthropic.com"),
        "anthropic_model": getattr(config, "anthropic_model", "claude-sonnet-4-20250514"),
        "ollama_base_url": getattr(config, "ollama_base_url", "http://localhost:11434/v1"),
        "ollama_model": getattr(config, "ollama_model", "llama3"),
        "temperature": getattr(config, "ai_temperature", 0.7),
    })


def create_provider_from_dict(settings: dict) -> AIProvider:
    """Create an AI provider from settings dict."""
    provider_name = settings.get("provider", "deepseek").lower()
    temperature = settings.get("temperature", 0.7)

    if provider_name == "anthropic":
        api_key = settings.get("anthropic_api_key", "")
        if not api_key:
            raise ValueError("Anthropic API key is required. Set anthropic_api_key in config.")
        return AnthropicProvider(
            api_key=api_key,
            base_url=settings.get("anthropic_base_url", "https://api.anthropic.com"),
            model=settings.get("anthropic_model", "claude-sonnet-4-20250514"),
            temperature=temperature,
        )
    elif provider_name == "ollama":
        return OpenAICompatibleProvider(
            api_key="ollama",
            base_url=settings.get("ollama_base_url", "http://localhost:11434/v1"),
            model=settings.get("ollama_model", "llama3"),
            temperature=temperature,
        )
    else:
        # OpenAI-compatible (openai, deepseek, glm, openrouter, custom)
        api_key = settings.get("openai_api_key", "")
        if not api_key:
            raise ValueError(
                f"API key is required for provider '{provider_name}'. "
                f"Set openai_api_key in config/houdini_ai.ini"
            )
        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url=settings.get("openai_base_url", "https://api.deepseek.com/v1"),
            model=settings.get("openai_model", "deepseek-chat"),
            temperature=temperature,
        )
