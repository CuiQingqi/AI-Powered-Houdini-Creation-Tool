"""
Tool dispatch layer.

Bridges MCP tool calls to the Houdini Bridge WebSocket connection.
Handles sandbox validation for code execution tools and formats results
for Claude Code consumption.
"""

import json
import logging
from typing import Any, Dict, Optional
from datetime import datetime

from .sandbox import get_sandbox

logger = logging.getLogger("mcp_server.dispatch")


class ToolDispatcher:
    """Dispatches MCP tool calls to the Houdini Bridge."""

    def __init__(self, bridge_client=None, event_bus=None):
        """
        Args:
            bridge_client: BridgeClient instance for WebSocket calls to Houdini.
            event_bus: EventBus for pushing events to Web UI.
        """
        self._bridge = bridge_client
        self._event_bus = event_bus

    def set_bridge(self, bridge_client):
        self._bridge = bridge_client

    def set_event_bus(self, event_bus):
        self._event_bus = event_bus

    # ── MCP tool name → Bridge JSON-RPC method mapping ──────────

    TOOL_TO_METHOD = {
        "houdini_create_node":          "tool.create_node",
        "houdini_delete_node":          "tool.delete_node",
        "houdini_connect_nodes":        "tool.connect_nodes",
        "houdini_set_parameter":        "tool.set_parameter",
        "houdini_create_nodes_batch":   "tool.create_nodes_batch",
        "houdini_copy_node":            "tool.copy_node",
        "houdini_set_display_flag":     "tool.set_display_flag",
        "houdini_undo_redo":            "tool.undo_redo",
        "houdini_get_network_structure":"tool.get_network_structure",
        "houdini_get_node_info":        "tool.get_node_details",
        "houdini_list_children":        "tool.list_children",
        "houdini_check_errors":         "tool.check_errors",
        "houdini_read_selection":       "tool.get_selected_nodes",
        "houdini_layout_nodes":         "tool.layout_nodes",
        "houdini_get_node_positions":   "tool.get_node_positions",
        "houdini_create_network_box":   "tool.create_network_box",
        "houdini_capture_viewport":     "tool.capture_viewport",
        "houdini_save_hip":             "tool.save_hip",
        "houdini_search_node_types":    "tool.search_node_types",
        "houdini_execute_python":       "tool.execute_python",
    }

    async def execute(self, tool_name: str, arguments: dict) -> dict:
        """Execute a tool call and return the MCP-formatted result.

        Returns:
            MCP tool result dict: {"content": [...], "isError": bool}
        """
        start_time = datetime.now()

        if tool_name not in self.TOOL_TO_METHOD:
            return self._error_result(f"Unknown tool: {tool_name}")

        # Security: validate code execution tools
        if tool_name == "houdini_execute_python":
            code = arguments.get("code", "")
            sandbox = get_sandbox()
            if not sandbox.is_python_safe(code):
                violations = sandbox.get_python_violations(code)
                return self._error_result(
                    f"Python code blocked by security sandbox. Violations: {', '.join(violations)}"
                )

        if self._bridge is None:
            return self._error_result("Not connected to Houdini. Start the Houdini Bridge first.")

        # Handle viewport capture specially (resolution mapping)
        if tool_name == "houdini_capture_viewport":
            return await self._execute_capture(arguments, start_time)

        # Standard tool execution via Bridge WebSocket
        bridge_method = self.TOOL_TO_METHOD[tool_name]

        try:
            response = await self._bridge.call_tool(bridge_method, arguments)
        except Exception as e:
            logger.error(f"Bridge call failed: {tool_name} - {e}")
            self._emit_event("error", {
                "tool": tool_name,
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            })
            return self._error_result(f"Failed to communicate with Houdini: {e}")

        elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        status = response.get("status", "error")

        # Emit tool execution event for Web UI
        self._emit_event("tool_executed", {
            "tool": tool_name,
            "status": status,
            "message": response.get("message", ""),
            "timestamp": datetime.now().isoformat(),
            "elapsed_ms": elapsed_ms,
        })

        if status == "error":
            self._emit_event("error", {
                "tool": tool_name,
                "message": response.get("message", "Unknown error"),
                "timestamp": datetime.now().isoformat(),
            })
            return self._error_result(response.get("message", "Tool execution failed"))

        return self._success_result(tool_name, response)

    async def _execute_capture(self, arguments: dict, start_time: datetime) -> dict:
        """Execute viewport capture with resolution mapping and screenshot push."""
        from bridge.screenshot import capture_viewport_base64, capture_viewport_simple

        res_map = {"low": (400, 300), "medium": (800, 600), "high": (1600, 1200)}
        resolution = res_map.get(arguments.get("resolution", "medium"), (800, 600))

        img_data = capture_viewport_base64(resolution)
        if not img_data:
            img_data = capture_viewport_simple()

        if img_data:
            self._emit_event("viewport_update", {
                "image_base64": img_data,
                "timestamp": datetime.now().isoformat(),
            })
            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            self._emit_event("tool_executed", {
                "tool": "houdini_capture_viewport",
                "status": "success",
                "message": f"Captured viewport ({resolution[0]}x{resolution[1]})",
                "timestamp": datetime.now().isoformat(),
                "elapsed_ms": elapsed_ms,
            })
            return {
                "content": [
                    {"type": "text", "text": f"Viewport captured ({resolution[0]}x{resolution[1]})."},
                    {"type": "image", "data": img_data.split(",", 1)[1] if "," in img_data else img_data, "mimeType": "image/png"},
                ],
            }
        else:
            return self._error_result("Failed to capture viewport. Make sure Houdini is running and a viewport is visible.")

    def _success_result(self, tool_name: str, response: dict) -> dict:
        """Format a successful tool result for MCP response."""
        message = response.get("message", f"{tool_name} executed successfully")
        data = response.get("data")

        # Include structured data as JSON if present
        if data:
            content = f"{message}\n\n```json\n{json.dumps(data, indent=2, default=str)}\n```"
        else:
            content = message

        return {"content": [{"type": "text", "text": content}]}

    def _error_result(self, message: str) -> dict:
        """Format an error tool result for MCP response."""
        return {
            "content": [{"type": "text", "text": f"Error: {message}"}],
            "isError": True,
        }

    def _emit_event(self, event_type: str, data: dict):
        """Emit an event to the Web UI via EventBus."""
        if self._event_bus:
            try:
                self._event_bus.publish(event_type, data)
            except Exception:
                pass
