"""
Workflow persistence - save/load workflow state to disk.

Workflows are stored as JSON files in selfHoudiniAgent/workflows/
"""

import json
import time
from pathlib import Path
from typing import List, Optional


def _workflows_dir() -> Path:
    """Get the workflows storage directory."""
    d = Path(__file__).resolve().parent.parent / "workflows"
    d.mkdir(exist_ok=True)
    return d


def list_workflows() -> List[dict]:
    """List all saved workflows with metadata."""
    result = []
    for f in sorted(_workflows_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            result.append({
                "id": f.stem,
                "name": data.get("name", f.stem),
                "user_prompt": data.get("user_prompt", "")[:100],
                "total_tasks": data.get("total_tasks", 0),
                "completed_tasks": data.get("completed_tasks", 0),
                "failed_tasks": data.get("failed_tasks", 0),
                "modules_count": len(data.get("modules", [])),
                "phase": data.get("phase", "idle"),
                "saved_at": data.get("saved_at", ""),
            })
        except Exception:
            pass
    return result


def save_workflow(name: str, state: dict) -> str:
    """Save a workflow state. Returns the workflow ID."""
    import uuid
    wid = name.replace(" ", "_").replace("/", "_")[:40] or uuid.uuid4().hex[:8]
    state["id"] = wid
    state["name"] = name
    state["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    path = _workflows_dir() / f"{wid}.json"
    path.write_text(json.dumps(state, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    return wid


def load_workflow(wid: str) -> Optional[dict]:
    """Load a saved workflow by ID."""
    path = _workflows_dir() / f"{wid}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def delete_workflow(wid: str) -> bool:
    """Delete a saved workflow."""
    path = _workflows_dir() / f"{wid}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def workflow_state_to_dict(state) -> dict:
    """Convert WorkflowState to a serializable dict."""
    return {
        "phase": state.phase.value if hasattr(state.phase, 'value') else str(state.phase),
        "user_prompt": state.user_prompt,
        "detailed_requirement": state.detailed_requirement,
        "modules": [
            {
                "module_id": m.module_id,
                "module_name": m.module_name,
                "description": m.description,
                "operations": [
                    {
                        "operation_name": op.get("operation_name", "") if isinstance(op, dict) else getattr(op, "operation_name", ""),
                        "tasks": op.get("tasks", []) if isinstance(op, dict) else [],
                    }
                    for op in m.operations
                ] if m.operations else [],
            }
            for m in state.modules
        ],
        "tasks": [
            {
                "task_id": t.task_id,
                "module_name": t.module_name,
                "operation_name": t.operation_name,
                "action_type": t.action_type,
                "node_type": t.node_type,
                "node_name": t.node_name,
                "parameters": t.parameters,
                "parent_path": t.parent_path,
                "comment": t.comment,
                "status": t.status,
                "message": t.message,
            }
            for t in state.tasks
        ],
        "current_task_index": state.current_task_index,
        "current_module_index": state.current_module_index,
        "total_tasks": state.total_tasks,
        "completed_tasks": state.completed_tasks,
        "failed_tasks": state.failed_tasks,
    }


def workflow_state_from_dict(data: dict, state):
    """Restore WorkflowState from a dict."""
    from .workflow_engine import WorkflowModule, WorkflowTask

    state.phase = data.get("phase", "idle")
    state.user_prompt = data.get("user_prompt", "")
    state.detailed_requirement = data.get("detailed_requirement", "")
    state.total_tasks = data.get("total_tasks", 0)
    state.completed_tasks = data.get("completed_tasks", 0)
    state.failed_tasks = data.get("failed_tasks", 0)
    state.current_task_index = data.get("current_task_index", 0)
    state.current_module_index = data.get("current_module_index", 0)

    state.modules = []
    for m in data.get("modules", []):
        ops = []
        for o in m.get("operations", []):
            ops.append({"operation_name": o.get("operation_name", ""), "tasks": o.get("tasks", [])})
        state.modules.append(WorkflowModule(
            module_id=m.get("module_id", ""),
            module_name=m.get("module_name", ""),
            description=m.get("description", ""),
            operations=ops,
        ))

    state.tasks = []
    for t in data.get("tasks", []):
        state.tasks.append(WorkflowTask(
            task_id=t.get("task_id", ""),
            module_name=t.get("module_name", ""),
            operation_name=t.get("operation_name", ""),
            action_type=t.get("action_type", ""),
            node_type=t.get("node_type", ""),
            node_name=t.get("node_name", ""),
            parameters=t.get("parameters", {}),
            parent_path=t.get("parent_path", "/obj/geo1"),
            comment=t.get("comment", ""),
            status=t.get("status", "pending"),
            message=t.get("message", ""),
        ))

    return state
