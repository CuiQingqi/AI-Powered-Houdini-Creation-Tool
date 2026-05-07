"""
Workflow Engine for structured Houdini asset creation.

Pipeline:
  1. OPTIMIZE: User's casual prompt -> AI optimizes to detailed requirement
  2. MODULES: Detailed requirement -> AI splits into named modules
  3. OPERATIONS: For each module -> AI splits into operations
  4. COMPILE: All operations -> unified todo list
  5. EXECUTE: Execute operations one-by-one in Houdini, marking progress

State machine: IDLE -> OPTIMIZING -> MODULE_PLANNING -> OPERATION_PLANNING -> COMPILING -> EXECUTING -> DONE
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("mcp_server.workflow")


class WorkflowPhase(Enum):
    IDLE = "idle"
    OPTIMIZING = "optimizing"
    MODULE_PLANNING = "modules"
    OPERATION_PLANNING = "operations"
    COMPILING = "compiling"
    EXECUTING = "executing"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class WorkflowTask:
    """A single executable Houdini operation."""
    task_id: str
    module_name: str
    operation_name: str
    action_type: str
    node_type: str = ""
    node_name: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    parent_path: str = "/obj/geo1"
    comment: str = ""
    status: str = "pending"
    message: str = ""


@dataclass
class WorkflowModule:
    """A module containing multiple operations."""
    module_id: str
    module_name: str
    description: str
    operations: List[dict] = field(default_factory=list)


@dataclass
class WorkflowState:
    """Full workflow state."""
    phase: WorkflowPhase = WorkflowPhase.IDLE
    user_prompt: str = ""
    detailed_requirement: str = ""
    modules: List[WorkflowModule] = field(default_factory=list)
    tasks: List[WorkflowTask] = field(default_factory=list)
    current_task_index: int = 0
    current_module_index: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0


OPTIMIZE_PROMPT = """You are a Houdini procedural design expert. Transform the user's casual description into a detailed, technical requirement for a Houdini procedural asset.

User said: "{user_prompt}"

Output a detailed requirement covering:
1. What geometry to generate
2. Key parameters (sizes, counts, spacing, etc.)
3. Any control inputs (curves, points, etc.)
4. Desired visual style
5. Technical constraints

Write in clear technical English. Keep it to 3-5 paragraphs. NO markdown headers."""


MODULE_PROMPT = """Based on this detailed requirement, break the procedural asset into logical modules. Each module handles one part of the asset.

Requirement:
{requirement}

Output as JSON array of modules:
```json
[
  {{
    "module_id": "M01",
    "module_name": "Short descriptive name",
    "description": "What this module does"
  }}
]
```

Rules:
- 3-7 modules total
- Each module should be independently testable
- Order from upstream (inputs) to downstream (final output)
- Return ONLY the JSON array, no other text."""


OPERATION_PROMPT = """Break down this module into detailed Houdini operations.

Module: {module_name}
Description: {module_description}

Full requirement context: {requirement}

Output as JSON array of operations. Each operation is an atomic Houdini action:
```json
[
  {{
    "operation_name": "Descriptive name",
    "action_type": "create_node|set_parameter|connect_nodes|create_nodes_batch|set_display_flag",
    "node_type": "Houdini node type (only for create_node)",
    "node_name": "Unique descriptive name for the node",
    "parameters": {{"param_name": value}},
    "inputs": [{{"input_index": 0, "source_node": "node_name"}}],
    "comment": "What this step does"
  }}
]
```

Rules:
- 3-8 operations per module
- First operation creates the primary node
- Use UNIQUE node_name values within this module
- For set_parameter, omit node_type (the target node was created earlier)
- For connect_nodes, use source_node to reference previously created nodes
- Parameters should use actual Houdini parameter names
- parent_path should be "/obj/geo1" for all nodes
- Return ONLY the JSON array, no other text."""


COMPILE_PROMPT = """Compile all module operations into a unified numbered todo list.

Modules and their operations:
{all_operations}

Output a numbered todo list. Each item should be:
- Numbered sequentially (1, 2, 3, ...)
- Show which module it belongs to
- Show what action to take
- Show all necessary parameters

Format:
```
1. [Module Name] Create node 'node_type' named 'node_name' with params {{...}}
2. [Module Name] Set parameter 'param' on 'node_name' to value
3. [Module Name] Connect 'node_a' to input 0 of 'node_b'
...
```

Return the numbered list as plain text. Number EVERY operation from all modules."""


class WorkflowEngine:
    """Manages the structured creation pipeline."""

    def __init__(self, ai_provider, dispatcher, event_bus=None):
        self.provider = ai_provider
        self.dispatcher = dispatcher
        self.event_bus = event_bus
        self.state = WorkflowState()
        self._cancelled = False

        self.on_phase_change: Optional[Callable] = None
        self.on_progress: Optional[Callable] = None
        self.on_task_complete: Optional[Callable] = None
        self.on_log: Optional[Callable] = None

    def reset(self):
        self.state = WorkflowState()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    async def run(self, user_prompt: str):
        """Run the full workflow pipeline. Yields events at each step."""
        self.reset()
        self.state.user_prompt = user_prompt
        self.state.phase = WorkflowPhase.OPTIMIZING
        self._emit_phase()

        project_name = user_prompt.strip()[:60]
        if len(user_prompt) > 60:
            project_name += "..."

        try:
            yield {"type": "phase", "phase": "optimizing", "message": "Optimizing your prompt..."}
            self.state.detailed_requirement = await self._optimize(user_prompt)
            yield {"type": "phase_done", "phase": "optimizing"}

            yield {"type": "phase", "phase": "modules", "message": "Breaking down into modules..."}
            modules = await self._plan_modules(self.state.detailed_requirement)
            self.state.modules = [WorkflowModule(**m) for m in modules]
            yield {
                "type": "phase_done",
                "phase": "modules",
                "project_name": project_name,
                "project_description": self.state.detailed_requirement[:200],
                "modules": [
                    {"module_id": m.module_id, "module_name": m.module_name, "description": m.description}
                    for m in self.state.modules
                ],
            }

            all_ops_text = ""
            for i, module in enumerate(self.state.modules):
                self.state.current_module_index = i
                yield {
                    "type": "phase",
                    "phase": "operations",
                    "message": f"Breaking down Module {module.module_id}: {module.module_name}...",
                }
                operations = await self._plan_operations(module, self.state.detailed_requirement)
                module.operations = operations
                ops_text = json.dumps(operations, indent=2)
                all_ops_text += f"\n### {module.module_id}: {module.module_name}\n{ops_text}\n"
                yield {
                    "type": "phase_done",
                    "phase": "operations",
                    "module_id": module.module_id,
                    "op_count": len(operations),
                }

            self.state.phase = WorkflowPhase.COMPILING
            yield {"type": "phase", "phase": "compiling", "message": "Compiling todo list..."}
            todo_text = await self._compile(all_ops_text)
            self._parse_todo_to_tasks(todo_text)
            self.state.total_tasks = len(self.state.tasks)
            yield {
                "type": "phase_done",
                "phase": "compiling",
                "total_tasks": self.state.total_tasks,
                "tasks": [
                    {
                        "task_id": t.task_id,
                        "module_name": t.module_name,
                        "operation_name": t.operation_name,
                        "action_type": t.action_type,
                    }
                    for t in self.state.tasks
                ],
            }

            self.state.phase = WorkflowPhase.EXECUTING
            yield {
                "type": "phase",
                "phase": "executing",
                "message": f"Executing {self.state.total_tasks} operations in Houdini...",
            }

            for i, task in enumerate(self.state.tasks):
                if self._cancelled:
                    break

                self.state.current_task_index = i
                task.status = "running"
                self._emit_progress()

                yield {
                    "type": "task_start",
                    "task_id": task.task_id,
                    "module_name": task.module_name,
                    "operation": task.operation_name,
                    "action": task.action_type,
                }

                try:
                    result = await self._execute_task(task)
                    task.status = "done" if result else "failed"
                    task.message = result.get("message", "") if result else "Failed"
                    self.state.completed_tasks += 1
                except Exception as e:
                    task.status = "failed"
                    task.message = str(e)
                    self.state.failed_tasks += 1

                self._emit_progress()
                self._emit_task_complete(task)
                yield {
                    "type": "task_done",
                    "task_id": task.task_id,
                    "status": task.status,
                    "message": task.message,
                }

            self.state.phase = WorkflowPhase.DONE
            self._emit_phase()
            yield {
                "type": "workflow_done",
                "completed": self.state.completed_tasks,
                "failed": self.state.failed_tasks,
                "total": self.state.total_tasks,
            }

        except Exception as e:
            logger.error(f"Workflow error: {e}")
            self.state.phase = WorkflowPhase.CANCELLED
            yield {"type": "error", "message": str(e)}
            yield {
                "type": "workflow_done",
                "completed": self.state.completed_tasks,
                "failed": self.state.failed_tasks,
                "total": self.state.total_tasks,
                "error": str(e),
            }

    async def _call_ai(self, prompt: str, tools: List[dict] = None) -> str:
        """Call the AI with a prompt and return the text response."""
        from .ai_provider import ChatMessage

        messages = [ChatMessage(role="user", content=prompt)]
        full_text = ""

        async for chunk in self.provider.chat(messages, tools or [], stream=True):
            if chunk.content:
                full_text += chunk.content
                self._emit_log_chunk(chunk.content)

        return full_text.strip()

    async def _optimize(self, user_prompt: str) -> str:
        prompt = OPTIMIZE_PROMPT.format(user_prompt=user_prompt)
        self._emit_log("AI optimizing prompt...")
        result = await self._call_ai(prompt)
        self._emit_log(f"Requirement: {result[:200]}...")
        return result

    async def _plan_modules(self, requirement: str) -> List[dict]:
        prompt = MODULE_PROMPT.format(requirement=requirement)
        self._emit_log("AI planning modules...")
        result = await self._call_ai(prompt)
        self._emit_log(f"Module response: {result[:200]}...")
        return self._parse_json(result)

    async def _plan_operations(self, module: WorkflowModule, requirement: str) -> List[dict]:
        prompt = OPERATION_PROMPT.format(
            module_name=module.module_name,
            module_description=module.description,
            requirement=requirement,
        )
        self._emit_log(f"AI planning operations for {module.module_id}...")
        result = await self._call_ai(prompt)
        self._emit_log(f"Operations response: {result[:200]}...")
        return self._parse_json(result)

    async def _compile(self, all_ops_text: str) -> str:
        prompt = COMPILE_PROMPT.format(all_operations=all_ops_text)
        self._emit_log("AI compiling todo list...")
        return await self._call_ai(prompt)

    async def _execute_task(self, task: WorkflowTask) -> Optional[dict]:
        if task.action_type == "create_node":
            return await self._exec_create_node(task)
        if task.action_type == "set_parameter":
            return await self._exec_set_param(task)
        if task.action_type == "connect_nodes":
            return await self._exec_connect(task)
        if task.action_type == "set_display_flag":
            return await self._exec_display_flag(task)
        if task.action_type == "create_nodes_batch":
            return await self._exec_batch(task)
        self._emit_log(f"Unknown action_type: {task.action_type}")
        return None

    async def _exec_create_node(self, task: WorkflowTask) -> dict:
        result = await self.dispatcher.execute("houdini_create_node", {
            "parent_path": task.parent_path,
            "node_type": task.node_type,
            "node_name": task.node_name,
        })
        if not result.get("isError") and task.parameters:
            node_path = f"{task.parent_path}/{task.node_name}"
            for pname, pval in task.parameters.items():
                await self.dispatcher.execute("houdini_set_parameter", {
                    "node_path": node_path,
                    "param_name": pname,
                    "value": pval,
                })
        return result

    async def _exec_set_param(self, task: WorkflowTask) -> dict:
        node_path = task.parameters.pop("_node_path", f"{task.parent_path}/{task.node_name}")
        param_name = task.parameters.pop("_param_name", list(task.parameters.keys())[0] if task.parameters else "")
        value = task.parameters.pop("_value", list(task.parameters.values())[0] if task.parameters else None)

        if not param_name and task.parameters:
            param_name = list(task.parameters.keys())[0]
            value = task.parameters[param_name]

        return await self.dispatcher.execute("houdini_set_parameter", {
            "node_path": node_path,
            "param_name": param_name,
            "value": value,
        })

    async def _exec_connect(self, task: WorkflowTask) -> dict:
        input_idx = task.parameters.get("input_index", 0)
        source_node = task.parameters.get("source_node", "")
        if not source_node and task.inputs:
            source_node = task.inputs[0].get("source_node", "")
        return await self.dispatcher.execute("houdini_connect_nodes", {
            "output_path": f"{task.parent_path}/{source_node}",
            "input_path": f"{task.parent_path}/{task.node_name}",
            "input_index": input_idx,
        })

    async def _exec_display_flag(self, task: WorkflowTask) -> dict:
        return await self.dispatcher.execute("houdini_set_display_flag", {
            "node_path": f"{task.parent_path}/{task.node_name}",
        })

    async def _exec_batch(self, task: WorkflowTask) -> dict:
        return await self.dispatcher.execute("houdini_create_nodes_batch", {
            "parent_path": task.parent_path,
            "nodes_config": task.parameters.get("nodes_config", []),
            "connections_config": task.parameters.get("connections_config", []),
        })

    def _parse_json(self, text: str) -> List[dict]:
        """Extract JSON from AI response."""
        text = text.strip()
        if "```" in text:
            lines = text.split("\n")
            in_block = False
            json_lines = []
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block or not line.startswith("```"):
                    json_lines.append(line)
            text = "\n".join(json_lines)

        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
        except json.JSONDecodeError:
            pass

        import re
        match = re.search(r'\[[\s\S]*\]', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        logger.warning(f"Could not parse JSON from: {text[:300]}")
        return [{"error": "Could not parse AI response", "raw": text[:500]}]

    def _parse_todo_to_tasks(self, todo_text: str):
        """Parse the compiled todo list into WorkflowTask objects."""
        self.state.tasks = []
        lines = todo_text.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line or not line[0].isdigit():
                continue

            import re
            match = re.match(r'(\d+)\.\s*\[([^\]]+)\]\s*(.+)', line)
            if not match:
                continue

            task_num, module_name, description = match.groups()
            desc_lower = description.lower()
            if "create node" in desc_lower or ("create " in desc_lower and "node" in desc_lower):
                action_type = "create_node"
                node_match = re.search(r"node\s+'(\w+)'\s+named\s+'(\w+)'", description)
                node_type = node_match.group(1) if node_match else ""
                node_name = node_match.group(2) if node_match else f"node_{task_num}"
            elif "set parameter" in desc_lower or ("set " in desc_lower and "param" in desc_lower):
                action_type = "set_parameter"
                node_type = ""
                node_name = ""
            elif "connect" in desc_lower:
                action_type = "connect_nodes"
                node_type = ""
                node_name = ""
            elif "display flag" in desc_lower or "display" in desc_lower:
                action_type = "set_display_flag"
                node_type = ""
                node_name = ""
            else:
                action_type = "create_node"
                node_type = ""
                node_name = f"node_{task_num}"

            self.state.tasks.append(WorkflowTask(
                task_id=f"T{task_num}",
                module_name=module_name,
                operation_name=description[:80],
                action_type=action_type,
                node_type=node_type,
                node_name=node_name,
                parameters={},
                comment=description,
            ))

    def _emit_phase(self):
        if self.on_phase_change:
            self.on_phase_change(self.state.phase.value, {
                "phase": self.state.phase.value,
                "module_index": self.state.current_module_index,
                "total_modules": len(self.state.modules),
            })

    def _emit_progress(self):
        if self.on_progress:
            self.on_progress({
                "current": self.state.current_task_index,
                "total": self.state.total_tasks,
                "completed": self.state.completed_tasks,
                "failed": self.state.failed_tasks,
                "phase": self.state.phase.value,
            })

    def _emit_task_complete(self, task: WorkflowTask):
        if self.on_task_complete:
            self.on_task_complete({
                "task_id": task.task_id,
                "status": task.status,
                "message": task.message,
            })

    def _emit_log(self, message: str):
        if self.on_log:
            self.on_log(message)
        logger.info(f"[Workflow] {message}")

    def _emit_log_chunk(self, chunk: str):
        if self.on_log:
            self.on_log("__CHUNK__" + chunk)
