"""
MCP Server + Chat + Web UI entry point.

Starts FastMCP HTTP server, chat WebSocket, Web UI push WebSocket,
and manages the connection to Houdini Bridge.

Usage:
    python -m mcp_server.main
    # Double-click: start_server.bat
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set

# Ensure the project root is on the path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from mcp_server.config import read_config, find_web_ui_dir, find_config_dir
from mcp_server.event_bus import EventBus
from mcp_server.tools.registry import get_registry
from mcp_server.tools.dispatch import ToolDispatcher
from mcp_server.tools.definitions import HOUDINI_TOOLS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mcp_server.main")


class HoudiniMCPApp:
    """Main application tying together MCP Server, Chat, Bridge, and Web UI."""

    def __init__(self):
        self.config = read_config()
        self.event_bus = EventBus()
        self.tool_registry = get_registry(
            str(find_config_dir() / "tools.json")
        )
        self.dispatcher = ToolDispatcher(event_bus=self.event_bus)

        self.bridge = None
        self._bridge_connected = False
        self._start_time = time.time()
        self._ui_clients: Set[Any] = set()
        self._ai_provider = None
        self._chat_task: Optional[asyncio.Task] = None
        self._current_workflow = None
        self._last_workflow_state: Optional[dict] = None
        self._last_workflow_name: str = ""

        self.mcp = None

    @property
    def has_ai_provider(self) -> bool:
        return getattr(self, '_ai_provider', None) is not None

    def _status_dict(self) -> dict:
        """Build the standard connection_status payload."""
        return {
            "houdini_connected": self._bridge_connected,
            "ai_configured": self.has_ai_provider,
            "ai_provider": self.config.ai.provider if self.has_ai_provider else "",
            "ai_model": self.config.ai.model if self.has_ai_provider else "",
            "context_limit": self.config.ai.context_limit if self.has_ai_provider else 0,
            "uptime_seconds": int(time.time() - self._start_time),
        }

    def setup_ai_provider(self) -> str:
        """Try to set up the AI provider from config. Returns error message or empty string."""
        try:
            from mcp_server.ai_provider import create_provider_from_dict

            settings = self.config.ai.as_dict()
            provider = create_provider_from_dict(settings)

            self._ai_provider = provider
            logger.info(f"AI provider ready: {self.config.ai.provider} / {self.config.ai.model}")
            return ""
        except ValueError as e:
            msg = str(e)
            logger.warning(f"AI provider not configured: {msg}")
            return msg
        except Exception as e:
            msg = str(e)
            logger.error(f"AI provider setup failed: {msg}")
            return msg

    def setup_mcp(self):
        """Create FastMCP instance and register all Houdini tools."""
        from mcp.server.fastmcp import FastMCP

        self.mcp = FastMCP(
            name="Houdini AI MCP Server",
            instructions=(
                "You are a Houdini procedural artist assistant. "
                "You have access to tools that can create, modify, and inspect "
                "Houdini scenes."
            ),
        )

        # Register tools from definitions using dynamically-built functions
        # FastMCP generates inputSchema from function signatures + type hints.

        TYPE_MAP = {
            "string": "str", "integer": "int", "number": "float",
            "boolean": "bool", "array": "list", "object": "dict",
        }

        for tool_def in HOUDINI_TOOLS:
            tool_name = tool_def["name"]
            schema = tool_def["inputSchema"]
            props = schema.get("properties", {})
            required = set(schema.get("required", []))

            param_parts = []
            type_imports = set()
            for pname, pinfo in props.items():
                ptype = TYPE_MAP.get(pinfo.get("type", "string"), "str")
                if ptype == "list":
                    type_imports.add("List")
                if ptype == "dict":
                    type_imports.add("Dict")

                if pname in required:
                    param_parts.append(f"{pname}: {ptype}")
                else:
                    default = pinfo.get("default")
                    if default is None:
                        param_parts.append(f"{pname}: {ptype} = None")
                    elif isinstance(default, str):
                        param_parts.append(f'{pname}: {ptype} = "{default}"')
                    elif isinstance(default, bool):
                        param_parts.append(f'{pname}: {ptype} = {str(default)}')
                    else:
                        param_parts.append(f"{pname}: {ptype} = {default}")

            params_str = ", ".join(param_parts) if param_parts else ""

            desc_clean = tool_def["description"].replace('"', '\\"').replace('\n', ' ')[:200]

            func_source = (
                f"async def {tool_name}({params_str}) -> str:\n"
                f'    """{desc_clean}"""\n'
                f'    if not app_inst._bridge_connected:\n'
                f'        return "Error: Not connected to Houdini."\n'
                f'    if not app_inst.tool_registry.is_enabled("{tool_name}"):\n'
                f'        return "Error: Tool is disabled."\n'
                f'    kwargs = {{k: v for k, v in locals().items() if v is not None and k != "self"}}\n'
                f'    result = await app_inst.dispatcher.execute("{tool_name}", kwargs)\n'
                f'    if result.get("isError"):\n'
                f'        return result["content"][0]["text"]\n'
                f'    return result["content"][0]["text"] if result.get("content") else str(result)\n'
            )

            namespace = {"app_inst": self}
            exec(func_source, namespace)
            fn = namespace[tool_name]
            self.mcp.tool(name=tool_name, description=tool_def["description"])(fn)

        self._register_resources()

    def _register_resources(self):
        if self.mcp is None:
            return
        rules_dir = _PROJECT_ROOT / "rules"

        @self.mcp.resource("houdini://skills/effect-breakdown")
        def effect_breakdown_resource() -> str:
            breakdown_path = _PROJECT_ROOT.parent / "houdini-effect-breakdown.md"
            if breakdown_path.exists():
                return breakdown_path.read_text(encoding="utf-8")
            return "Effect breakdown skill not found."

        @self.mcp.resource("houdini://rules/system-prompt")
        def system_prompt_resource() -> str:
            prompt_path = rules_dir / "houdini_system_prompt.md"
            if prompt_path.exists():
                return prompt_path.read_text(encoding="utf-8")
            return "System prompt not found."

    # ── Web UI WebSocket ──────────────────────────────────────────

    async def _handle_ui_connection(self, websocket):
        """Handle a Web UI browser connection (monitoring/state push)."""
        self._ui_clients.add(websocket)
        logger.info(f"Web UI client connected (total: {len(self._ui_clients)})")

        await self._send_ui(websocket, "connection_status", self._status_dict())

        try:
            while True:
                try:
                    raw_message = await websocket.receive_text()
                except Exception:
                    break
                try:
                    msg = json.loads(raw_message)
                    msg_type = msg.get("type", "")

                    if msg_type == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
                    elif msg_type == "reload_ai":
                        self.config = read_config()
                        err = self.setup_ai_provider()
                        status = self._status_dict()
                        status["ai_error"] = err if err else ""
                        await self._send_ui(websocket, "connection_status", status)
                    elif msg_type == "request_viewport":
                        if self._bridge_connected and self.bridge:
                            await self.bridge.call_tool("tool.capture_viewport", {})
                    elif msg_type == "get_node_info":
                        node_path = msg.get("node_path", "")
                        if self._bridge_connected and self.bridge:
                            result = await self.bridge.call_tool(
                                "tool.get_node_details", {"node_path": node_path})
                            await self._send_ui(websocket, "node_info", result)
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    logger.error(f"UI msg error: {e}")
        except Exception:
            pass
        finally:
            self._ui_clients.discard(websocket)

    # ── Chat WebSocket ────────────────────────────────────────────

    async def _handle_chat_connection(self, websocket):
        """Handle a chat WebSocket connection (AI conversation)."""
        logger.info("Chat client connected")

        # Send initial state — try to configure AI on connect
        if not self.has_ai_provider:
            self.config = read_config()
            self.setup_ai_provider()
        await self._send_ws(websocket, "chat_status", {
            "ai_configured": self.has_ai_provider,
            "ai_provider": self.config.ai.provider if self.has_ai_provider else "",
            "bridge_connected": self._bridge_connected,
        })

        try:
            while True:
                try:
                    raw_message = await websocket.receive_text()
                except Exception:
                    break

                if self._chat_task and not self._chat_task.done():
                    # Cancel previous workflow before starting new one
                    self._chat_task.cancel()
                    if self._current_workflow:
                        self._current_workflow.cancel()

                try:
                    msg = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "chat_message":
                    user_text = msg.get("content", "")
                    image_b64 = msg.get("image_base64", "")

                    if not user_text.strip():
                        await self._send_ws(websocket, "error", {"message": "Empty message"})
                        continue

                    if not self.has_ai_provider:
                        self.config = read_config()
                        ai_error = self.setup_ai_provider()
                        if ai_error:
                            await self._send_ws(websocket, "error", {"message": ai_error})
                            continue

                    # Run workflow engine (planning works without Houdini;
                    # execution phase will fail gracefully if bridge is offline)
                    from mcp_server.workflow_engine import WorkflowEngine
                    workflow = WorkflowEngine(
                        ai_provider=self._ai_provider,
                        dispatcher=self.dispatcher,
                        event_bus=self.event_bus,
                    )
                    self._chat_task = asyncio.create_task(
                        self._run_workflow(websocket, workflow, user_text)
                    )

                elif msg_type == "cancel_chat":
                    if self._current_workflow:
                        self._current_workflow.cancel()
                    if self._chat_task:
                        self._chat_task.cancel()
                    await self._send_ws(websocket, "chat_done", {})

                elif msg_type == "reset_chat":
                    if self._current_workflow:
                        self._current_workflow.reset()
                    if self._chat_task:
                        self._chat_task.cancel()
                    await self._send_ws(websocket, "chat_reset", {})

        except Exception as e:
            logger.error(f"Chat handler error: {e}")
        finally:
            if self._chat_task:
                self._chat_task.cancel()
            if self._current_workflow:
                self._current_workflow.cancel()
            logger.info("Chat client disconnected")

    async def _run_workflow(self, websocket, workflow, user_text: str):
        """Run the full workflow pipeline and stream events to WebSocket."""
        self._current_workflow = workflow

        # Queue for streaming text chunks from AI calls
        chunk_queue = asyncio.Queue()

        def on_log(msg):
            if msg.startswith("__CHUNK__"):
                chunk_queue.put_nowait(msg[9:])  # Strip prefix
            # Regular log messages could also be forwarded

        workflow.on_log = on_log

        async def forward_chunks():
            """Forward streaming chunks from the queue to WebSocket."""
            while True:
                try:
                    chunk = await asyncio.wait_for(chunk_queue.get(), timeout=0.1)
                    await self._send_ws(websocket, "text_chunk", {"content": chunk})
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break

        chunk_task = asyncio.create_task(forward_chunks())

        try:
            async for event in workflow.run(user_text):
                await self._send_ws(websocket, event["type"], event)
        except asyncio.CancelledError:
            await self._send_ws(websocket, "chat_done", {"cancelled": True})
        except Exception as e:
            logger.error(f"Workflow error: {e}")
            await self._send_ws(websocket, "error", {"message": str(e)})
            await self._send_ws(websocket, "chat_done", {})
        finally:
            chunk_task.cancel()
            # Cache workflow state for save/load after completion
            from mcp_server.workflow_store import workflow_state_to_dict
            if workflow.state and workflow.state.modules:
                self._last_workflow_state = workflow_state_to_dict(workflow.state)
                self._last_workflow_state["name"] = self._last_workflow_name
                self._last_workflow_state["user_prompt"] = workflow.state.user_prompt
            self._current_workflow = None

    async def _send_ws(self, websocket, event_type: str, data: dict):
        """Send a typed event to a WebSocket client."""
        try:
            # Forward all data fields, add type
            payload = json.dumps({"type": event_type, **data}, default=str)
            await websocket.send_text(payload)
        except Exception as e:
            logger.error(f"WS send error ({event_type}): {e}")

    # ── Event handlers ────────────────────────────────────────────

    async def _send_ui(self, websocket, event_type: str, data: dict):
        try:
            payload = json.dumps({"type": event_type, "data": data}, default=str)
            await websocket.send_text(payload)
        except Exception:
            self._ui_clients.discard(websocket)

    async def _broadcast_ui_event(self, event_type: str, data: dict):
        dead = set()
        for ws in self._ui_clients:
            try:
                await self._send_ui(ws, event_type, data)
            except Exception:
                dead.add(ws)
        self._ui_clients -= dead

    async def _on_bridge_event(self, method: str, params: dict):
        if method == "event.viewport_capture_requested":
            from bridge.screenshot import capture_viewport_base64, capture_viewport_simple
            img = capture_viewport_base64() or capture_viewport_simple()
            if img:
                await self._broadcast_ui_event("viewport_update", {
                    "image_base64": img, "timestamp": time.time()})
        elif method == "event.network_changed":
            if self._bridge_connected and self.bridge:
                try:
                    result = await self.bridge.call_tool(
                        "tool.get_network_structure", {"network_path": "/obj"})
                    await self._broadcast_ui_event("node_graph_update", result)
                except Exception:
                    pass

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(self):
        logger.info("=" * 50)
        logger.info("Houdini AI Server starting...")
        logger.info(f"  MCP:    {self.config.mcp_url}")
        logger.info(f"  Web UI: {self.config.web_ui_url}")
        logger.info(f"  Bridge: {self.config.bridge_url}")
        logger.info(f"  Tools:  {self.tool_registry.enabled_count}")
        logger.info("=" * 50)

        self.setup_mcp()

        # Setup AI provider for chat
        ai_error = self.setup_ai_provider()
        if ai_error:
            logger.info(f"Chat mode: {ai_error}")
        else:
            logger.info("Chat mode: ready (type in browser)")

        # Connect to Houdini Bridge
        self._bridge_connected = await self._connect_bridge()
        self.event_bus.on_event(self._broadcast_ui_event)

        asyncio.create_task(self._health_check_loop())
        logger.info("Server ready!")

    async def _connect_bridge(self) -> bool:
        from mcp_server.bridge_client import BridgeClient
        self.bridge = BridgeClient(self.config.bridge_url)
        self.bridge.on_event(self._on_bridge_event)
        connected = await self.bridge.connect()
        self._bridge_connected = connected
        self.dispatcher.set_bridge(self.bridge)
        if connected:
            logger.info("Connected to Houdini Bridge")
        else:
            logger.warning("Houdini Bridge not available — start it in Houdini")
        await self._broadcast_ui_event("connection_status", self._status_dict())
        return connected

    async def _health_check_loop(self):
        while True:
            await asyncio.sleep(10)
            prev = self._bridge_connected
            self._bridge_connected = self.bridge is not None and self.bridge.is_connected
            if prev != self._bridge_connected:
                logger.info(f"Bridge: {'connected' if self._bridge_connected else 'disconnected'}")
                await self._broadcast_ui_event("connection_status", self._status_dict())
                if self._bridge_connected:
                    self.dispatcher.set_bridge(self.bridge)

    async def stop(self):
        logger.info("Shutting down...")
        if self.bridge:
            await self.bridge.disconnect()
        self._bridge_connected = False


# ── Entry Point ────────────────────────────────────────────────────

def main():
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import Route, WebSocketRoute, Mount
    from starlette.staticfiles import StaticFiles
    from starlette.responses import HTMLResponse, JSONResponse
    from starlette.websockets import WebSocketDisconnect

    app_inst = HoudiniMCPApp()
    app_inst.setup_mcp()

    fastmcp_app = app_inst.mcp.streamable_http_app()

    # ── Settings API ───────────────────────────────────────────

    async def get_settings(request):
        return JSONResponse({
            "provider": app_inst.config.ai.provider,
            "model": app_inst.config.ai.model,
            "context_limit": app_inst.config.ai.context_limit,
            "openai_api_key": app_inst.config.ai.openai_api_key[:8] + "***" if app_inst.config.ai.openai_api_key else "",
            "openai_base_url": app_inst.config.ai.openai_base_url,
            "openai_model": app_inst.config.ai.openai_model,
            "obsidian_vault_path": app_inst.config.obsidian.vault_path,
        })

    async def save_settings(request):
        try:
            data = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)

        # Update config in memory
        app_inst.config.ai.provider = data.get("provider", app_inst.config.ai.provider)
        app_inst.config.ai.model = data.get("model", app_inst.config.ai.model)
        app_inst.config.ai.context_limit = data.get("context_limit", app_inst.config.ai.context_limit)
        app_inst.config.ai.openai_api_key = data.get("openai_api_key", app_inst.config.ai.openai_api_key)
        app_inst.config.ai.openai_base_url = data.get("openai_base_url", app_inst.config.ai.openai_base_url)
        app_inst.config.ai.openai_model = data.get("openai_model", app_inst.config.ai.openai_model)
        app_inst.config.obsidian.vault_path = data.get("obsidian_vault_path", app_inst.config.obsidian.vault_path)

        # Save to INI file
        ini_path = find_config_dir() / "houdini_ai.ini"
        try:
            lines = ini_path.read_text(encoding="utf-8").split("\n")
            new_lines = []
            in_ai = False
            in_obs = False
            for line in lines:
                if line.startswith("[ai]"):
                    in_ai = True; in_obs = False; new_lines.append(line); continue
                if line.startswith("[obsidian]"):
                    in_obs = True; in_ai = False; new_lines.append(line); continue
                if line.startswith("[") and not line.startswith("[ai]") and not line.startswith("[obsidian]"):
                    in_ai = False; in_obs = False
                if in_ai:
                    if line.startswith("provider"):
                        new_lines.append(f"provider = {app_inst.config.ai.provider}")
                    elif line.startswith("model"):
                        new_lines.append(f"model = {app_inst.config.ai.model}")
                    elif line.startswith("context_limit"):
                        new_lines.append(f"context_limit = {app_inst.config.ai.context_limit}")
                    elif line.startswith("openai_api_key"):
                        new_lines.append(f"openai_api_key = {app_inst.config.ai.openai_api_key}")
                    elif line.startswith("openai_base_url"):
                        new_lines.append(f"openai_base_url = {app_inst.config.ai.openai_base_url}")
                    elif line.startswith("openai_model"):
                        new_lines.append(f"openai_model = {app_inst.config.ai.openai_model}")
                    else:
                        new_lines.append(line)
                elif in_obs:
                    if line.startswith("vault_path"):
                        new_lines.append(f"vault_path = {app_inst.config.obsidian.vault_path}")
                    elif line.startswith("auto_save"):
                        new_lines.append(f"auto_save = {str(app_inst.config.obsidian.auto_save).lower()}")
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            ini_path.write_text("\n".join(new_lines), encoding="utf-8")
        except Exception as e:
            return JSONResponse({"ok": False, "error": f"Failed to save: {e}"})

        return JSONResponse({"ok": True})

    # ── Workflow API ──────────────────────────────────────────

    async def list_workflows_api(request):
        from mcp_server.workflow_store import list_workflows
        return JSONResponse(list_workflows())

    async def save_workflow_api(request):
        try:
            data = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)

        from mcp_server.workflow_store import save_workflow, workflow_state_to_dict

        # Use active workflow state, or fall back to last completed workflow
        wf = app_inst._current_workflow
        if wf:
            state_dict = workflow_state_to_dict(wf.state)
            state_dict["user_prompt"] = wf.state.user_prompt
            name = data.get("name", wf.state.user_prompt[:40])
        elif app_inst._last_workflow_state:
            state_dict = dict(app_inst._last_workflow_state)
            name = data.get("name", state_dict.get("name", "workflow"))
        else:
            return JSONResponse({"ok": False, "error": "No workflow to save. Run a workflow first."}, status_code=400)
        wid = save_workflow(name, state_dict)

        # Also save to Obsidian if configured
        obsidian_path = ""
        if app_inst.config.obsidian.vault_path and app_inst.config.obsidian.auto_save:
            try:
                from mcp_server.rag import get_rag
                rag = get_rag(app_inst.config.obsidian.vault_path)
                md_content = rag.workflow_to_markdown(state_dict)
                obsidian_path = rag.save_workflow_note(name, md_content)
            except Exception:
                pass

        return JSONResponse({"ok": True, "id": wid, "obsidian_path": obsidian_path})

    async def load_workflow_api(request):
        try:
            data = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)

        from mcp_server.workflow_store import load_workflow
        state_dict = load_workflow(data.get("id", ""))
        if not state_dict:
            return JSONResponse({"ok": False, "error": "Workflow not found"}, status_code=404)

        await app_inst._broadcast_ui_event("workflow_loaded", state_dict)
        return JSONResponse({"ok": True, "workflow": state_dict})

    async def delete_workflow_api(request):
        try:
            data = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)

        from mcp_server.workflow_store import delete_workflow
        ok = delete_workflow(data.get("id", ""))
        return JSONResponse({"ok": ok})

    # ── RAG API ───────────────────────────────────────────────

    async def rag_search_api(request):
        query = request.query_params.get("q", "")
        if not query:
            return JSONResponse({"results": []})
        from mcp_server.rag import get_rag
        rag = get_rag(app_inst.config.obsidian.vault_path)
        results = rag.search(query, limit=10)
        return JSONResponse({"results": results})

    # ── Web UI routes ──────────────────────────────────────────

    async def serve_index(request):
        index_path = find_web_ui_dir() / "index.html"
        if index_path.exists():
            return HTMLResponse(index_path.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Web UI not found</h1>", status_code=404)

    async def ws_ui_endpoint(websocket):
        await websocket.accept()
        try:
            await app_inst._handle_ui_connection(websocket)
        except WebSocketDisconnect:
            pass

    async def ws_chat_endpoint(websocket):
        await websocket.accept()
        try:
            await app_inst._handle_chat_connection(websocket)
        except WebSocketDisconnect:
            pass

    async def health_check(request):
        return JSONResponse({
            "status": "running",
            "houdini_connected": app_inst._bridge_connected,
            "ai_configured": app_inst.has_ai_provider,
            "tools_count": app_inst.tool_registry.enabled_count,
            "uptime_seconds": int(time.time() - app_inst._start_time),
        })

    # Build Starlette app
    web_ui_dir = find_web_ui_dir()
    routes = [
        Route("/", serve_index),
        Route("/health", health_check),
        Route("/api/settings", get_settings, methods=["GET"]),
        Route("/api/settings", save_settings, methods=["POST"]),
        Route("/api/workflows", list_workflows_api, methods=["GET"]),
        Route("/api/workflow/save", save_workflow_api, methods=["POST"]),
        Route("/api/workflow/load", load_workflow_api, methods=["POST"]),
        Route("/api/workflow/delete", delete_workflow_api, methods=["POST"]),
        Route("/api/rag/search", rag_search_api, methods=["GET"]),
        WebSocketRoute("/ws/ui", ws_ui_endpoint),
        WebSocketRoute("/ws/chat", ws_chat_endpoint),
    ]
    if web_ui_dir.exists():
        routes.append(Mount("/static", StaticFiles(directory=str(web_ui_dir)), name="static"))

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        # Startup — connect bridge in background so server starts immediately
        asyncio.create_task(app_inst._connect_bridge())
        app_inst.event_bus.on_event(app_inst._broadcast_ui_event)
        try:
            app_inst.setup_ai_provider()
        except Exception:
            pass
        asyncio.create_task(app_inst._health_check_loop())
        yield
        # Shutdown
        await app_inst.stop()

    starlette_app = Starlette(routes=routes, lifespan=lifespan)
    starlette_app.mount("/mcp", fastmcp_app)

    if app_inst.config.web_ui.auto_open:
        import webbrowser
        webbrowser.open(app_inst.config.web_ui_url)

    print(f"""
╔══════════════════════════════════════════════════╗
║       Houdini AI Server                          ║
╠══════════════════════════════════════════════════╣
║  Web UI:  {app_inst.config.web_ui_url}             ║
║  MCP:     {app_inst.config.mcp_url}/    ║
║  Bridge:  {app_inst.config.bridge_url}              ║
╠══════════════════════════════════════════════════╣
║  Open browser → type prompt → control Houdini    ║
╚══════════════════════════════════════════════════╝
""")

    uvicorn.run(
        starlette_app,
        host=app_inst.config.mcp_server.host,
        port=app_inst.config.mcp_server.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
