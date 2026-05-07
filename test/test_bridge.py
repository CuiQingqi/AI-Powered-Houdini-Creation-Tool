"""
Tests for Houdini Bridge JSON-RPC protocol (no Houdini required).

Tests the handler dispatch logic and request/response formatting.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_handler_dispatch_table():
    """Verify all tool methods have handlers."""
    from bridge.handler import DISPATCH_TABLE

    assert len(DISPATCH_TABLE) >= 20, f"Expected at least 20 handlers, got {len(DISPATCH_TABLE)}"

    # All handlers should be callable
    for method, func in DISPATCH_TABLE.items():
        assert callable(func), f"Handler for {method} is not callable"
        assert method.startswith("tool."), f"Method {method} should start with 'tool.'"


def test_handler_ping_response():
    """Ping should return a valid JSON-RPC response."""
    from bridge.handler import BridgeHandler

    handler = BridgeHandler()
    request = {"jsonrpc": "2.0", "id": "test-1", "method": "ping", "params": {}}
    response = handler.handle_request(request)

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "test-1"
    assert "result" in response
    assert "pong" in response["result"]


def test_handler_unknown_method():
    """Unknown methods should return an error."""
    from bridge.handler import BridgeHandler

    handler = BridgeHandler()
    request = {"jsonrpc": "2.0", "id": "test-2", "method": "tool.nonexistent", "params": {}}
    response = handler.handle_request(request)

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "test-2"
    assert "error" in response
    assert response["error"]["code"] == -32601


def test_hou_wrappers_helpers():
    """Test the _ok/_err helpers work correctly."""
    from bridge.hou_wrappers import _ok, _err

    result = _ok("Success!", {"key": "value"})
    assert result["status"] == "success"
    assert result["message"] == "Success!"
    assert result["data"]["key"] == "value"

    result = _err("Failed!")
    assert result["status"] == "error"
    assert result["message"] == "Failed!"
