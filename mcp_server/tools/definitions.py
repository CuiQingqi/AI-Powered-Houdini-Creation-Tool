"""
MCP tool definitions for Houdini AI.

Each tool has:
- name: Unique tool identifier (prefix: houdini_)
- description: What it does, when to use it
- inputSchema: JSON Schema for parameters
- annotations: Hints for Claude Code (readOnly, destructive, etc.)
"""

HOUDINI_TOOLS = [
    # ═══ Node Operations ═══
    {
        "name": "houdini_create_node",
        "description": (
            "Create a new node in a Houdini network. Use this to add any SOP, "
            "DOP, VOP, or other node type. The node is created inside the "
            "specified parent network."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "parent_path": {
                    "type": "string",
                    "description": "Parent network path, e.g. /obj/geo1. Use houdini_list_children to discover networks.",
                },
                "node_type": {
                    "type": "string",
                    "description": "Houdini node type name, e.g. box, grid, scatter, attribwrangle. Use houdini_search_node_types to discover available types.",
                },
                "node_name": {
                    "type": "string",
                    "description": "Optional custom node name. Auto-generated if omitted.",
                },
            },
            "required": ["parent_path", "node_type"],
        },
    },
    {
        "name": "houdini_delete_node",
        "description": (
            "Delete a node from the Houdini scene by its full path. "
            "This is destructive and cannot be undone via the tool (use houdini_undo_redo to revert)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_path": {
                    "type": "string",
                    "description": "Full path to the node to delete, e.g. /obj/geo1/box1",
                },
            },
            "required": ["node_path"],
        },
    },
    {
        "name": "houdini_connect_nodes",
        "description": (
            "Connect the output of one node to the input of another. "
            "Specify which input index on the target node to connect to."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_path": {
                    "type": "string",
                    "description": "Path of the node providing the output connection.",
                },
                "input_path": {
                    "type": "string",
                    "description": "Path of the node receiving the input connection.",
                },
                "input_index": {
                    "type": "integer",
                    "description": "Input index on the receiving node (0 = first input). Default: 0.",
                    "default": 0,
                },
            },
            "required": ["output_path", "input_path"],
        },
    },
    {
        "name": "houdini_set_parameter",
        "description": (
            "Set a parameter value on a node. Use this to configure node behavior — "
            "sizes, counts, modes, toggles, etc. After setting parameters, check "
            "for errors with houdini_check_errors."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_path": {
                    "type": "string",
                    "description": "Full path to the node.",
                },
                "param_name": {
                    "type": "string",
                    "description": "Parameter name, e.g. 'radx', 'scale', 'groupname'. Use houdini_get_node_info to see available parameters.",
                },
                "value": {
                    "description": "Value to set. Can be a number, string, boolean, or list for vector/tuple parameters.",
                },
            },
            "required": ["node_path", "param_name", "value"],
        },
    },
    {
        "name": "houdini_create_nodes_batch",
        "description": (
            "Create multiple nodes at once and optionally connect them. "
            "More efficient than calling houdini_create_node repeatedly. "
            "Provide a list of node specs and a list of connections."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "parent_path": {
                    "type": "string",
                    "description": "Parent network where nodes will be created.",
                },
                "nodes_config": {
                    "type": "array",
                    "description": "List of {node_type, node_name} dicts to create.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "node_type": {"type": "string"},
                            "node_name": {"type": "string"},
                        },
                        "required": ["node_type"],
                    },
                },
                "connections_config": {
                    "type": "array",
                    "description": "List of {from_node_name, to_node_name, input_index} dicts. Node names reference the node_name in nodes_config.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from_node_name": {"type": "string"},
                            "to_node_name": {"type": "string"},
                            "input_index": {"type": "integer", "default": 0},
                        },
                        "required": ["from_node_name", "to_node_name"],
                    },
                },
            },
            "required": ["parent_path", "nodes_config"],
        },
    },
    {
        "name": "houdini_copy_node",
        "description": "Copy a node to a destination network, optionally with a new name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_path": {
                    "type": "string",
                    "description": "Path of the node to copy.",
                },
                "dest_network": {
                    "type": "string",
                    "description": "Destination network path. Default: same as source.",
                },
                "new_name": {
                    "type": "string",
                    "description": "Optional new name for the copied node.",
                },
            },
            "required": ["source_path"],
        },
    },
    {
        "name": "houdini_set_display_flag",
        "description": "Set the display and render flags on a node, making it the visible output of its network.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_path": {
                    "type": "string",
                    "description": "Path of the node to set as display.",
                },
            },
            "required": ["node_path"],
        },
    },
    {
        "name": "houdini_undo_redo",
        "description": "Undo or redo the last operation in Houdini.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Either 'undo' or 'redo'.",
                    "enum": ["undo", "redo"],
                },
            },
            "required": ["action"],
        },
    },

    # ═══ Scene Query ═══
    {
        "name": "houdini_get_network_structure",
        "description": (
            "Get the full structure of a Houdini network: all nodes, their connections, "
            "positions, types, flags, and NetworkBoxes. Use this BEFORE making changes "
            "to understand the current state of the scene."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "network_path": {
                    "type": "string",
                    "description": "Path to the network to inspect. Default: /obj.",
                    "default": "/obj",
                },
            },
            "required": [],
        },
    },
    {
        "name": "houdini_get_node_info",
        "description": (
            "Get detailed information about a specific node, including all non-default "
            "parameters, input/output connections, flags, and any errors or warnings."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_path": {
                    "type": "string",
                    "description": "Full path to the node to inspect.",
                },
            },
            "required": ["node_path"],
        },
    },
    {
        "name": "houdini_list_children",
        "description": "List all direct child nodes in a network.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "parent_path": {
                    "type": "string",
                    "description": "Path to the parent network, e.g. /obj/geo1.",
                },
            },
            "required": ["parent_path"],
        },
    },
    {
        "name": "houdini_check_errors",
        "description": (
            "Check for Houdini errors and warnings. Call this after making changes "
            "to verify everything is working. Can check a specific node or the entire scene."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_path": {
                    "type": "string",
                    "description": "Specific node to check. Omit to scan the entire scene.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "houdini_read_selection",
        "description": "Get information about the currently selected nodes in Houdini.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    # ═══ Layout and Organization ═══
    {
        "name": "houdini_layout_nodes",
        "description": (
            "Auto-arrange nodes in a network. Methods: 'auto' (grid-based), "
            "'grid' (square grid), 'columns' (topological depth-based)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "parent_path": {
                    "type": "string",
                    "description": "Path to the network to layout. Default: current network editor path.",
                },
                "method": {
                    "type": "string",
                    "description": "Layout method.",
                    "enum": ["auto", "grid", "columns"],
                    "default": "auto",
                },
                "spacing": {
                    "type": "number",
                    "description": "Spacing multiplier. Default: 1.0.",
                    "default": 1.0,
                },
            },
            "required": [],
        },
    },
    {
        "name": "houdini_get_node_positions",
        "description": "Get the position (x, y) of every node in a network. Useful before manual layout adjustments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "parent_path": {
                    "type": "string",
                    "description": "Path to the network. Default: current network editor path.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "houdini_create_network_box",
        "description": (
            "Create a NetworkBox to visually group related nodes. "
            "Color presets: input (blue), processing (green), deform (orange), "
            "output (red), simulation (purple), utility (gray)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "parent_path": {
                    "type": "string",
                    "description": "Parent network path.",
                },
                "name": {
                    "type": "string",
                    "description": "Box title/name.",
                },
                "comment": {
                    "type": "string",
                    "description": "Comment displayed in the box header.",
                },
                "color_preset": {
                    "type": "string",
                    "description": "Color preset name.",
                    "enum": ["input", "processing", "deform", "output", "simulation", "utility"],
                },
                "node_paths": {
                    "type": "array",
                    "description": "List of node paths to include in the box.",
                    "items": {"type": "string"},
                },
            },
            "required": ["parent_path"],
        },
    },

    # ═══ Visualization and Export ═══
    {
        "name": "houdini_capture_viewport",
        "description": "Capture a screenshot of the current Houdini viewport. Returns a base64-encoded PNG image URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "resolution": {
                    "type": "string",
                    "description": "Screenshot resolution: 'low' (400x300), 'medium' (800x600), 'high' (1600x1200). Default: 'medium'.",
                    "enum": ["low", "medium", "high"],
                    "default": "medium",
                },
            },
            "required": [],
        },
    },
    {
        "name": "houdini_save_hip",
        "description": "Save the current Houdini scene file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File path to save to. Saves to current file if omitted.",
                },
            },
            "required": [],
        },
    },

    # ═══ Search and Code ═══
    {
        "name": "houdini_search_node_types",
        "description": (
            "Search Houdini node types by keyword. Use this to find the right node "
            "for a task when you don't know the exact type name."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Search keyword, e.g. 'scatter', 'noise', 'voronoi'.",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by node category. Common: Sop, Dop, Vop, Top, Cop2, Lop. Leave empty to search all.",
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "houdini_execute_python",
        "description": (
            "Execute Python code in Houdini's context. The code has access to the 'hou' module. "
            "SECURITY: Code is sandboxed — file deletion, network access, subprocess calls, "
            "and module manipulation are blocked. Use for custom geometry operations, "
            "automation, or operations not covered by other tools."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute. The 'hou' module is pre-imported. Keep it focused and minimal.",
                },
            },
            "required": ["code"],
        },
    },
]
