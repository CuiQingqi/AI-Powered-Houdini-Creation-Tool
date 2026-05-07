"""
JSON-RPC handler for Houdini Bridge.

Maps incoming JSON-RPC method names (e.g. "tool.create_node") to the
corresponding functions in hou_wrappers. Validates parameters and handles
errors.
"""

import json
import logging
from typing import Any, Dict, Callable

from . import hou_wrappers as hou
from .thread_safety import run_on_main_thread

logger = logging.getLogger("houdini_bridge.handler")

# ── Method Dispatch Table ───────────────────────────────────────────

DISPATCH_TABLE: Dict[str, Callable] = {
    # Node operations
    "tool.create_node":          hou.create_node,
    "tool.delete_node":          hou.delete_node,
    "tool.connect_nodes":        hou.connect_nodes,
    "tool.set_parameter":        hou.set_parameter,
    "tool.get_parameter":        hou.get_parameter,
    "tool.set_display_flag":     hou.set_display_flag,
    "tool.copy_node":            hou.copy_node,
    "tool.create_nodes_batch":   hou.create_nodes_batch,

    # Scene query
    "tool.get_node_info":        hou.get_node_info,
    "tool.get_node_details":     hou.get_node_details,
    "tool.get_network_structure": hou.get_network_structure,
    "tool.list_children":        hou.list_children,
    "tool.check_errors":         hou.check_errors,
    "tool.get_selected_nodes":   hou.get_selected_nodes,
    "tool.get_geometry_info":    hou.get_geometry_info,

    # Layout
    "tool.layout_nodes":         hou.layout_nodes,
    "tool.get_node_positions":   hou.get_node_positions,
    "tool.create_network_box":   hou.create_network_box,
    "tool.list_network_boxes":   hou.list_network_boxes,

    # Scene I/O
    "tool.save_hip":             hou.save_hip,
    "tool.undo_redo":            hou.undo_redo,

    # Search / code
    "tool.search_node_types":    hou.search_node_types,
    "tool.execute_python":       hou.execute_python,
}

# Methods that should trigger a viewport capture after execution
_CAPTURE_AFTER = {
    "tool.create_node", "tool.delete_node", "tool.set_parameter",
    "tool.set_display_flag", "tool.connect_nodes", "tool.create_nodes_batch",
    "tool.copy_node", "tool.undo_redo",
}

# Methods that should trigger a network structure push
_NETWORK_CHANGE_AFTER = {
    "tool.create_node", "tool.delete_node", "tool.connect_nodes",
    "tool.create_nodes_batch", "tool.copy_node", "tool.undo_redo",
    "tool.layout_nodes", "tool.create_network_box", "tool.set_display_flag",
}


class BridgeHandler:
    """Handles JSON-RPC requests by dispatching to hou_wrappers."""

    def __init__(self, on_event=None, hou_available=False):
        """Initialize with an optional event callback.

        Args:
            on_event: Callable(event_method, event_params) for push events.
            hou_available: Pre-cached hou availability (must be checked on main thread).
        """
        self._on_event = on_event
        self._hou_available = hou_available

    def handle_request(self, request: dict) -> dict:
        """Process a JSON-RPC request and return a JSON-RPC response.

        Args:
            request: JSON-RPC request dict with jsonrpc, id, method, params keys.

        Returns:
            JSON-RPC response dict with jsonrpc, id, result/error keys.
        """
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        # Health check (uses cached value, no hou access from asyncio thread)
        if method == "ping":
            return self._response(req_id, {"pong": True, "hou_available": self._hou_available})

        # Handle tool calls
        if method.startswith("tool."):
            return self._handle_tool_call(req_id, method, params)

        return self._error(req_id, -32601, f"Method not found: {method}")

    def _handle_tool_call(self, req_id: str, method: str, params: dict) -> dict:
        """Dispatch a tool.* method to the appropriate hou_wrappers function."""
        func = DISPATCH_TABLE.get(method)
        if func is None:
            return self._error(req_id, -32601, f"Unknown tool method: {method}")

        logger.info(f"Tool call: {method}({json.dumps(params, default=str)[:200]})")

        try:
            result = run_on_main_thread(func, **params)
        except TimeoutError as e:
            logger.error(f"Timeout: {method}")
            return self._error(req_id, -32000, f"Operation timed out: {e}")
        except Exception as e:
            logger.error(f"Execution error: {method} - {e}")
            return self._error(req_id, -32000, f"Execution error: {e}")

        # Fire events for state changes
        if self._on_event:
            if method in _CAPTURE_AFTER:
                self._on_event("event.viewport_capture_requested", {})
            if method in _NETWORK_CHANGE_AFTER:
                self._on_event("event.network_changed", {"method": method})

        return self._response(req_id, result)

    def _response(self, req_id: str, result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _error(self, req_id: str, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def get_dispatch_table_info() -> list:
    """Get list of available tool methods for documentation."""
    return list(DISPATCH_TABLE.keys())
