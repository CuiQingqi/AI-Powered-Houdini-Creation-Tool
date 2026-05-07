"""
Tests for MCP tool definitions and registry.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.tools.definitions import HOUDINI_TOOLS
from mcp_server.tools.registry import ToolRegistry


def test_all_tools_loaded():
    """Verify we have exactly 20 tools."""
    assert len(HOUDINI_TOOLS) == 20, f"Expected 20 tools, got {len(HOUDINI_TOOLS)}"


def test_all_tools_have_required_fields():
    """Every tool must have name, description, and inputSchema."""
    for tool in HOUDINI_TOOLS:
        assert "name" in tool, f"Missing 'name' in tool"
        assert "description" in tool, f"Missing 'description' in {tool.get('name', '?')}"
        assert "inputSchema" in tool, f"Missing 'inputSchema' in {tool['name']}"
        assert tool["name"].startswith("houdini_"), f"Tool name must start with houdini_: {tool['name']}"


def test_all_tools_unique_names():
    """No duplicate tool names."""
    names = [t["name"] for t in HOUDINI_TOOLS]
    assert len(names) == len(set(names)), f"Duplicate tool names: {names}"


def test_required_tools_present():
    """Core tools that must exist."""
    tool_names = {t["name"] for t in HOUDINI_TOOLS}
    required = [
        "houdini_create_node",
        "houdini_delete_node",
        "houdini_connect_nodes",
        "houdini_set_parameter",
        "houdini_get_network_structure",
        "houdini_get_node_info",
        "houdini_check_errors",
        "houdini_capture_viewport",
        "houdini_layout_nodes",
        "houdini_execute_python",
    ]
    for name in required:
        assert name in tool_names, f"Required tool missing: {name}"


def test_registry_loads_all_tools():
    reg = ToolRegistry()
    assert reg.tool_count == 20
    assert reg.enabled_count == 20


def test_registry_enable_disable():
    reg = ToolRegistry()
    name = "houdini_create_node"
    assert reg.is_enabled(name)

    reg.disable(name)
    assert not reg.is_enabled(name)
    assert reg.enabled_count == 19

    reg.enable(name)
    assert reg.is_enabled(name)
    assert reg.enabled_count == 20

    # Invalid tool names
    assert not reg.disable("nonexistent_tool")
    assert not reg.enable("nonexistent_tool")


def test_registry_list_enabled():
    reg = ToolRegistry()
    tools = reg.list_enabled()
    assert len(tools) == 20

    # All have valid schemas
    for tool in tools:
        assert "inputSchema" in tool
        assert "name" in tool
        assert "description" in tool
