"""
Tool Registry for MCP Server.

Manages tool enable/disable state and provides filtered tool lists
for the MCP protocol. Tool definitions are loaded from definitions.py.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .definitions import HOUDINI_TOOLS


class ToolRegistry:
    """Manages tool availability and metadata."""

    def __init__(self, tools_json_path: str = ""):
        """
        Args:
            tools_json_path: Path to tools.json config file.
        """
        self._tools: Dict[str, dict] = {}
        self._disabled: set = set()
        self._tools_json_path = tools_json_path

        # Load all tools from definitions
        for tool in HOUDINI_TOOLS:
            self._tools[tool["name"]] = tool

        # Load disabled state
        self._load_disabled()

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def enabled_count(self) -> int:
        return self.tool_count - len(self._disabled)

    def list_all(self) -> List[dict]:
        """Get all tool definitions."""
        return list(self._tools.values())

    def list_enabled(self) -> List[dict]:
        """Get enabled tool definitions (for MCP tools/list)."""
        return [
            tool for name, tool in self._tools.items()
            if name not in self._disabled
        ]

    def list_disabled(self) -> List[str]:
        """Get list of disabled tool names."""
        return sorted(self._disabled)

    def get_tool(self, name: str) -> Optional[dict]:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def is_enabled(self, name: str) -> bool:
        return name in self._tools and name not in self._disabled

    def enable(self, name: str) -> bool:
        if name not in self._tools:
            return False
        self._disabled.discard(name)
        self._save_disabled()
        return True

    def disable(self, name: str) -> bool:
        if name not in self._tools:
            return False
        self._disabled.add(name)
        self._save_disabled()
        return True

    def toggle(self, name: str) -> Optional[bool]:
        """Toggle a tool's enabled state. Returns new state or None if unknown."""
        if name not in self._tools:
            return None
        if name in self._disabled:
            self._disabled.discard(name)
        else:
            self._disabled.add(name)
        self._save_disabled()
        return name not in self._disabled

    def _load_disabled(self):
        if not self._tools_json_path:
            return
        try:
            path = Path(self._tools_json_path)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._disabled = set(data.get("disabled_tools", []))
        except Exception:
            self._disabled = set()

    def _save_disabled(self):
        if not self._tools_json_path:
            return
        try:
            path = Path(self._tools_json_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"disabled_tools": sorted(self._disabled)}, f, indent=2)
        except Exception:
            pass


# ── Singleton ───────────────────────────────────────────────────────

_registry: Optional[ToolRegistry] = None


def get_registry(tools_json_path: str = "") -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry(tools_json_path)
    return _registry
