"""
Houdini core operations layer.

Adapted from V1's battle-tested hou_core.py. All functions operate on the
`hou` module and return a unified dict: {"status": "success"|"error",
"message": str, "data": any}.

These functions MUST be called via run_on_main_thread() from bridge/thread_safety.py
since they access the hou module directly.
"""

from typing import Any, Dict, List, Optional, Tuple

try:
    import hou
except ImportError:
    hou = None


def is_houdini_available() -> bool:
    """Check if running inside Houdini with hou module available."""
    return hou is not None


def _ok(message: str, data: Any = None) -> dict:
    return {"status": "success", "message": message, "data": data}


def _err(message: str, data: Any = None) -> dict:
    return {"status": "error", "message": message, "data": data}


def _check_hou() -> Optional[dict]:
    if hou is None:
        return _err("Houdini environment not available")
    return None


# ── NetworkBox color presets ────────────────────────────────────────

_BOX_COLORS: Dict[str, Tuple[float, float, float]] = {
    "input":      (0.2, 0.4, 0.8),
    "processing": (0.3, 0.7, 0.3),
    "deform":     (0.8, 0.6, 0.2),
    "output":     (0.7, 0.2, 0.3),
    "simulation": (0.6, 0.3, 0.7),
    "utility":    (0.5, 0.5, 0.5),
}

# ── Node Operations ─────────────────────────────────────────────────

def create_node(parent_path: str, node_type: str, node_name: str = "") -> dict:
    """Create a node in the specified parent network."""
    if err := _check_hou():
        return err
    parent = hou.node(parent_path)
    if not parent:
        return _err(f"Parent node '{parent_path}' not found")
    try:
        node = parent.createNode(node_type, node_name or None)
        return _ok(f"Created node {node.path()}", {
            "node_path": node.path(),
            "node_name": node.name(),
            "node_type": node.type().name(),
        })
    except Exception as e:
        return _err(f"Failed to create node: {e}")


def delete_node(node_path: str) -> dict:
    """Delete a node by path."""
    if err := _check_hou():
        return err
    node = hou.node(node_path)
    if not node:
        return _err(f"Node '{node_path}' not found")
    try:
        node.destroy()
        return _ok(f"Deleted node '{node_path}'")
    except Exception as e:
        return _err(f"Failed to delete: {e}")


def connect_nodes(output_path: str, input_path: str, input_index: int = 0) -> dict:
    """Connect output of one node to input of another."""
    if err := _check_hou():
        return err
    output_node = hou.node(output_path)
    input_node = hou.node(input_path)
    if not output_node:
        return _err(f"Output node '{output_path}' not found")
    if not input_node:
        return _err(f"Input node '{input_path}' not found")
    max_inputs = input_node.type().maxNumInputs()
    if input_index < 0 or input_index >= max_inputs:
        return _err(f"Input index {input_index} invalid (range 0-{max_inputs - 1})")
    try:
        input_node.setInput(input_index, output_node, 0)
        return _ok(f"Connected {output_path} -> {input_path}[{input_index}]")
    except Exception as e:
        return _err(f"Connection failed: {e}")


def set_parameter(node_path: str, param_name: str, value: Any) -> dict:
    """Set a parameter value on a node."""
    if err := _check_hou():
        return err
    node = hou.node(node_path)
    if not node:
        return _err(f"Node '{node_path}' not found")
    parm = node.parm(param_name)
    if parm is not None:
        try:
            parm.set(value)
            return _ok(f"Set {node_path}/{param_name} = {value}")
        except Exception as e:
            return _err(f"Failed to set parameter: {e}")
    pt = node.parmTuple(param_name)
    if pt is not None:
        try:
            pt.set(value)
            return _ok(f"Set {node_path}/{param_name} = {value}")
        except Exception as e:
            return _err(f"Failed to set parameter tuple: {e}")
    return _err(f"Parameter '{param_name}' not found on '{node_path}'")


def get_parameter(node_path: str, param_name: str) -> dict:
    """Get a parameter value from a node."""
    if err := _check_hou():
        return err
    node = hou.node(node_path)
    if not node:
        return _err(f"Node '{node_path}' not found")
    parm = node.parm(param_name)
    if parm is not None:
        return _ok(f"Got {node_path}/{param_name}", {"value": parm.eval()})
    pt = node.parmTuple(param_name)
    if pt is not None:
        return _ok(f"Got {node_path}/{param_name}", {"value": [p.eval() for p in pt]})
    return _err(f"Parameter '{param_name}' not found on '{node_path}'")


def set_display_flag(node_path: str) -> dict:
    """Set display and render flags on a node."""
    if err := _check_hou():
        return err
    node = hou.node(node_path)
    if not node:
        return _err(f"Node '{node_path}' not found")
    try:
        node.setDisplayFlag(True)
        node.setRenderFlag(True)
        return _ok(f"Set display/render flag on {node_path}")
    except Exception as e:
        return _err(f"Failed to set display flag: {e}")


# ── Scene Query ─────────────────────────────────────────────────────

def get_node_info(node_path: str) -> dict:
    """Get basic node type, path, inputs, and outputs."""
    if err := _check_hou():
        return err
    node = hou.node(node_path)
    if not node:
        return _err(f"Node '{node_path}' not found")
    info = {
        "name": node.name(),
        "type": node.type().name(),
        "category": node.type().category().name(),
        "path": node.path(),
        "parent_path": node.parent().path() if node.parent() else "",
        "inputs": [i.path() for i in node.inputs() if i],
        "outputs": [o.path() for o in node.outputs() if o],
        "is_display": node.isDisplayFlagSet(),
        "is_render": node.isRenderFlagSet(),
        "is_bypass": node.isBypassed(),
        "is_locked": node.isLocked(),
    }
    return _ok(f"Info for {node_path}", info)


def get_node_details(node_path: str) -> dict:
    """Get detailed node info including all parameters."""
    if err := _check_hou():
        return err
    node = hou.node(node_path)
    if not node:
        return _err(f"Node '{node_path}' not found")

    # Collect non-default parameters
    parms = []
    for p in node.parms():
        if p.isAtDefault():
            continue
        parms.append({
            "name": p.name(),
            "label": p.description(),
            "value": p.eval(),
            "raw_value": p.rawValue(),
        })

    info = {
        "name": node.name(),
        "type": node.type().name(),
        "category": node.type().category().name(),
        "path": node.path(),
        "parent_path": node.parent().path() if node.parent() else "",
        "inputs": [i.path() for i in node.inputs() if i],
        "outputs": [o.path() for o in node.outputs() if o],
        "parameters": parms,
        "total_params": len(node.parms()),
        "non_default_params": len(parms),
        "is_display": node.isDisplayFlagSet(),
        "is_render": node.isRenderFlagSet(),
        "is_bypass": node.isBypassed(),
        "is_locked": node.isLocked(),
        "errors": list(node.errors() or []),
        "warnings": list(node.warnings() or []),
    }
    return _ok(f"Details for {node_path}", info)


def get_network_structure(network_path: str = "/obj") -> dict:
    """Get full network topology: nodes, connections, positions, NetworkBoxes."""
    if err := _check_hou():
        return err
    root = hou.node(network_path)
    if not root:
        return _err(f"Network '{network_path}' not found")

    nodes_list = []
    connections = []
    for node in root.allSubChildren():
        nodes_list.append({
            "name": node.name(),
            "path": node.path(),
            "type": node.type().name(),
            "category": node.type().category().name(),
            "position": list(node.position()),
            "is_display": node.isDisplayFlagSet(),
            "is_render": node.isRenderFlagSet(),
            "is_bypass": node.isBypassed(),
        })
        for i, inp in enumerate(node.inputs()):
            if inp:
                connections.append({
                    "from_path": inp.path(),
                    "to_path": node.path(),
                    "input_index": i,
                })

    boxes = []
    for box in root.networkBoxes():
        boxes.append({
            "name": box.name(),
            "comment": box.comment() or "",
            "nodes": [n.path() for n in box.nodes()],
            "minimized": box.isMinimized(),
        })

    return _ok(f"Network structure for {network_path}", {
        "network_path": network_path,
        "node_count": len(nodes_list),
        "nodes": nodes_list,
        "connections": connections,
        "network_boxes": boxes,
    })


def list_children(parent_path: str) -> dict:
    """List direct children of a network."""
    if err := _check_hou():
        return err
    parent = hou.node(parent_path)
    if not parent:
        return _err(f"Parent '{parent_path}' not found")
    children = []
    for c in parent.children():
        children.append({
            "name": c.name(),
            "path": c.path(),
            "type": c.type().name(),
            "is_display": c.isDisplayFlagSet(),
            "is_bypass": c.isBypassed(),
        })
    return _ok(f"{len(children)} children in {parent_path}", {"children": children})


def check_errors(node_path: str = None) -> dict:
    """Check for errors on a specific node or all nodes."""
    if err := _check_hou():
        return err
    if node_path:
        node = hou.node(node_path)
        if not node:
            return _err(f"Node '{node_path}' not found")
        errors = list(node.errors() or [])
        warnings = list(node.warnings() or [])
        return _ok(
            f"Node has {len(errors)} error(s), {len(warnings)} warning(s)",
            {"node_path": node_path, "errors": errors, "warnings": warnings},
        )
    else:
        error_nodes = []
        warning_nodes = []
        for n in hou.node('/').allSubChildren():
            try:
                if n.errors():
                    error_nodes.append({
                        "path": n.path(),
                        "errors": list(n.errors()),
                    })
                if n.warnings():
                    warning_nodes.append({
                        "path": n.path(),
                        "warnings": list(n.warnings()),
                    })
            except Exception:
                continue
        return _ok(
            f"Found {len(error_nodes)} error node(s), {len(warning_nodes)} warning node(s)",
            {"error_nodes": error_nodes, "warning_nodes": warning_nodes},
        )


def get_selected_nodes() -> dict:
    """Get paths of currently selected nodes."""
    if err := _check_hou():
        return err
    selected = hou.selectedNodes()
    paths = [n.path() for n in selected]
    return _ok(f"{len(paths)} node(s) selected", {"selected_paths": paths})


def get_geometry_info(node_path: str, output_index: int = 0) -> dict:
    """Get geometry statistics for a node's output."""
    if err := _check_hou():
        return err
    node = hou.node(node_path)
    if not node:
        return _err(f"Node '{node_path}' not found")
    try:
        geo = node.geometry(output_index)
        if geo is None:
            return _err(f"No geometry at output {output_index} of '{node_path}'")

        # Point attributes
        point_attrs = []
        for attr in geo.pointAttribs():
            point_attrs.append({
                "name": attr.name(),
                "type": str(attr.dataType()),
                "size": attr.size(),
            })

        # Primitive attributes
        prim_attrs = []
        for attr in geo.primAttribs():
            prim_attrs.append({
                "name": attr.name(),
                "type": str(attr.dataType()),
                "size": attr.size(),
            })

        bbox = geo.boundingBox()
        info = {
            "num_points": geo.intrinsicValue("pointcount") if hasattr(geo, 'intrinsicValue') else len(geo.iterPoints()),
            "num_prims": geo.intrinsicValue("primitivecount") if hasattr(geo, 'intrinsicValue') else len(geo.iterPrims()),
            "num_vertices": geo.intrinsicValue("vertexcount") if hasattr(geo, 'intrinsicValue') else 0,
            "bounding_box": {
                "min": list(bbox.minvec()) if bbox else [],
                "max": list(bbox.maxvec()) if bbox else [],
                "center": list(bbox.center()) if bbox else [],
                "size": list(bbox.sizevec()) if bbox else [],
            },
            "point_attributes": point_attrs,
            "primitive_attributes": prim_attrs,
        }
        return _ok(f"Geometry info for {node_path}", info)
    except Exception as e:
        return _err(f"Failed to get geometry info: {e}")


# ── Layout and Organization ─────────────────────────────────────────

def layout_nodes(parent_path: str = "", method: str = "auto", spacing: float = 1.0) -> dict:
    """Auto-layout nodes in a network using the specified method."""
    if err := _check_hou():
        return err
    parent = hou.node(parent_path) if parent_path else None
    if parent is None:
        try:
            editor = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
            if editor:
                parent = editor.pwd()
        except Exception:
            pass
    if parent is None:
        return _err("Could not find target network")

    nodes = list(parent.children())
    if not nodes:
        return _err(f"No children in {parent.path()}")

    used_method = method
    try:
        if method == "auto":
            try:
                import math
                cols = max(1, int(math.ceil(math.sqrt(len(nodes)))))
                for idx, n in enumerate(nodes):
                    col = idx % cols
                    row = idx // cols
                    n.setPosition(hou.Vector2(col * 3.5 * spacing, -row * 1.5 * spacing))
                used_method = "auto-grid"
            except Exception:
                for n in nodes:
                    try:
                        n.moveToGoodPosition()
                    except Exception:
                        pass
                used_method = "moveToGoodPosition"
        elif method == "grid":
            import math
            cols = max(1, int(math.ceil(math.sqrt(len(nodes)))))
            for idx, n in enumerate(nodes):
                col = idx % cols
                row = idx // cols
                n.setPosition(hou.Vector2(col * 3.5 * spacing, -row * 1.5 * spacing))
            used_method = "grid"
        elif method == "columns":
            # Topological depth-based column layout
            node_set = set(id(n) for n in nodes)
            depth_map = {}
            def calc_depth(n):
                nid = id(n)
                if nid in depth_map:
                    return depth_map[nid]
                inputs = [i for i in (n.inputs() or []) if i and id(i) in node_set]
                d = max(calc_depth(i) for i in inputs) + 1 if inputs else 0
                depth_map[nid] = d
                return d
            for n in nodes:
                calc_depth(n)
            layers = {}
            for n in nodes:
                d = depth_map.get(id(n), 0)
                layers.setdefault(d, []).append(n)
            for d in sorted(layers):
                for idx, n in enumerate(layers[d]):
                    x = (idx - len(layers[d]) / 2.0 + 0.5) * 3.5 * spacing
                    y = -d * 2.0 * spacing
                    n.setPosition(hou.Vector2(x, y))
            used_method = "columns"
        else:
            return _err(f"Unknown layout method: {method}")

        positions = []
        for n in nodes:
            pos = n.position()
            positions.append({
                "name": n.name(), "path": n.path(),
                "x": round(pos[0], 3), "y": round(pos[1], 3),
            })

        return _ok(f"Laid out {len(nodes)} nodes ({used_method})", {"positions": positions})
    except Exception as e:
        return _err(f"Layout failed: {e}")


def get_node_positions(parent_path: str = "") -> dict:
    """Get positions of all children in a network."""
    if err := _check_hou():
        return err
    parent = hou.node(parent_path) if parent_path else None
    if parent is None:
        try:
            editor = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
            if editor:
                parent = editor.pwd()
        except Exception:
            pass
    if parent is None:
        return _err("Could not find target network")

    positions = []
    for n in parent.children():
        pos = n.position()
        positions.append({
            "name": n.name(), "path": n.path(),
            "x": round(pos[0], 3), "y": round(pos[1], 3),
            "type": n.type().name(),
        })
    return _ok(f"Got {len(positions)} node positions", {"positions": positions})


def create_network_box(parent_path: str, name: str = "", comment: str = "",
                       color_preset: str = "", node_paths: List[str] = None) -> dict:
    """Create a NetworkBox and optionally add nodes to it."""
    if err := _check_hou():
        return err
    parent = hou.node(parent_path)
    if not parent:
        return _err(f"Parent '{parent_path}' not found")

    try:
        box = parent.createNetworkBox(name or None)
        if comment:
            box.setComment(comment)
        if color_preset and color_preset in _BOX_COLORS:
            r, g, b = _BOX_COLORS[color_preset]
            box.setColor(hou.Color((r, g, b)))

        added = []
        if node_paths:
            for np in node_paths:
                node = hou.node(np)
                if node:
                    box.addNode(node)
                    added.append(np)
            if added:
                box.fitAroundContents()

        msg = f"Created NetworkBox '{box.name()}'"
        if comment:
            msg += f" ({comment})"
        if added:
            msg += f" with {len(added)} nodes"
        return _ok(msg, {"box_name": box.name(), "nodes": added})
    except Exception as e:
        return _err(f"Failed to create NetworkBox: {e}")


def list_network_boxes(parent_path: str) -> dict:
    """List all NetworkBoxes in a network."""
    if err := _check_hou():
        return err
    parent = hou.node(parent_path)
    if not parent:
        return _err(f"Parent '{parent_path}' not found")

    boxes = []
    for box in parent.networkBoxes():
        boxes.append({
            "name": box.name(),
            "comment": box.comment() or "",
            "node_count": len(box.nodes()),
            "nodes": [n.path() for n in box.nodes()],
            "minimized": box.isMinimized(),
        })
    return _ok(f"Found {len(boxes)} NetworkBox(es)", {"network_boxes": boxes})


# ── Scene I/O ───────────────────────────────────────────────────────

def save_hip(file_path: str = "") -> dict:
    """Save the current .hip file."""
    if err := _check_hou():
        return err
    try:
        if file_path:
            hou.hipFile.save(file_path)
            return _ok(f"Saved to {file_path}", {"file_path": file_path})
        else:
            current = hou.hipFile.path()
            hou.hipFile.save()
            return _ok(f"Saved {current}", {"file_path": current})
    except Exception as e:
        return _err(f"Failed to save: {e}")


def undo_redo(action: str) -> dict:
    """Perform undo or redo.

    Args:
        action: "undo" or "redo"
    """
    if err := _check_hou():
        return err
    try:
        if action == "undo":
            hou.undos.undo()
            return _ok("Undo performed")
        elif action == "redo":
            hou.undos.redo()
            return _ok("Redo performed")
        else:
            return _err(f"Unknown action: {action}. Use 'undo' or 'redo'.")
    except Exception as e:
        return _err(f"Failed: {e}")


def copy_node(source_path: str, dest_network: str = "", new_name: str = "") -> dict:
    """Copy a node to a destination network."""
    if err := _check_hou():
        return err
    source = hou.node(source_path)
    if not source:
        return _err(f"Source node '{source_path}' not found")

    dest_parent = hou.node(dest_network) if dest_network else source.parent()
    if not dest_parent:
        return _err(f"Destination network '{dest_network}' not found")

    try:
        nodes = hou.copyNodesTo([source], dest_parent)
        if nodes:
            copied = nodes[0]
            if new_name:
                copied.setName(new_name, unique_name=True)
            return _ok(f"Copied to {copied.path()}", {
                "node_path": copied.path(),
                "node_name": copied.name(),
            })
        return _err("Copy produced no nodes")
    except Exception as e:
        return _err(f"Copy failed: {e}")


# ── Code Execution ──────────────────────────────────────────────────

def execute_python(code: str) -> dict:
    """Execute Python code in the Houdini context.

    WARNING: Code should be pre-validated by the sandbox before calling this.
    """
    if err := _check_hou():
        return err
    try:
        exec_globals = {"hou": hou}
        exec(compile(code, "<houdini_bridge>", "exec"), exec_globals)
        return _ok("Python code executed successfully")
    except Exception as e:
        return _err(f"Python execution failed: {e}")


# ── Node Search ─────────────────────────────────────────────────────

# Cache for node type search
_NODE_TYPE_CACHE: Optional[List[Dict[str, str]]] = None


def search_node_types(keyword: str, category: str = "") -> dict:
    """Search Houdini node types by keyword."""
    if err := _check_hou():
        return err

    global _NODE_TYPE_CACHE
    if _NODE_TYPE_CACHE is None:
        _NODE_TYPE_CACHE = []
        for cat in hou.nodeTypeCategories().values():
            for nt in cat.nodeTypes().values():
                _NODE_TYPE_CACHE.append({
                    "name": nt.name(),
                    "category": nt.category().name(),
                    "description": nt.description() or "",
                })

    keyword_lower = keyword.lower()
    results = []
    for nt in _NODE_TYPE_CACHE:
        if category and nt["category"].lower() != category.lower():
            continue
        if keyword_lower in nt["name"].lower() or keyword_lower in nt["description"].lower():
            results.append(nt)

    results = results[:20]
    return _ok(f"Found {len(results)} matching node type(s)", {"results": results})


def create_nodes_batch(parent_path: str, nodes_config: List[dict],
                       connections_config: List[dict] = None) -> dict:
    """Create multiple nodes and optionally connect them.

    Args:
        parent_path: Parent network path.
        nodes_config: List of {node_type, node_name} dicts.
        connections_config: List of {from_node_name, to_node_name, input_index} dicts.
            Node names reference the node_name from nodes_config.
    """
    if err := _check_hou():
        return err
    parent = hou.node(parent_path)
    if not parent:
        return _err(f"Parent '{parent_path}' not found")

    created = {}
    errors = []

    # Create all nodes
    for cfg in nodes_config:
        node_type = cfg["node_type"]
        node_name = cfg.get("node_name", "")
        result = create_node(parent_path, node_type, node_name)
        if result["status"] == "success":
            created[node_name or result["data"]["node_name"]] = result["data"]
        else:
            errors.append(result["message"])
            # Rollback: delete all created nodes
            for info in created.values():
                try:
                    n = hou.node(info["node_path"])
                    if n:
                        n.destroy()
                except Exception:
                    pass
            return _err(f"Batch creation failed: {'; '.join(errors)}")

    # Connect
    if connections_config:
        for conn in connections_config:
            from_name = conn["from_node_name"]
            to_name = conn["to_node_name"]
            input_idx = conn.get("input_index", 0)

            if from_name not in created or to_name not in created:
                continue
            from_path = created[from_name]["node_path"]
            to_path = created[to_name]["node_path"]

            result = connect_nodes(from_path, to_path, input_idx)
            if result["status"] == "error":
                errors.append(result["message"])

    return _ok(
        f"Created {len(created)} node(s)" + (f", {len(errors)} connection error(s)" if errors else ""),
        {"created_nodes": list(created.values()), "connection_errors": errors},
    )
