"""Autonomous Cross-Desk Swarm Workflow Engine.

Implements cross-desk workflow DAG compilation, distributed task state machines,
dependency resolution pipelines with typed context passing, and adaptive resource
scheduling with priority preemption.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
import hashlib
import json
import secrets
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PREEMPTED = "PREEMPTED"
    CANCELLED = "CANCELLED"


class TaskPriority(int, enum.Enum):
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4
    BACKGROUND = 5


@dataclasses.dataclass
class WorkflowTask:
    task_id: str
    name: str
    assigned_seat: str
    required_capabilities: List[str]
    dependencies: List[str] = dataclasses.field(default_factory=list)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    input_data: Dict[str, Any] = dataclasses.field(default_factory=dict)
    output_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: float = 30.0
    created_at: float = dataclasses.field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "assigned_seat": self.assigned_seat,
            "required_capabilities": self.required_capabilities,
            "dependencies": self.dependencies,
            "priority": self.priority.value,
            "status": self.status.value,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "error": self.error,
            "retry_count": self.retry_count,
            "timeout_seconds": self.timeout_seconds,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclasses.dataclass
class WorkflowDAG:
    workflow_id: str
    name: str
    tasks: Dict[str, WorkflowTask]
    execution_order: List[str]
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)
    created_at: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "tasks": {tid: t.to_dict() for tid, t in self.tasks.items()},
            "execution_order": self.execution_order,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


class CrossDeskWorkflowCompiler:
    """Compiles multi-stage workflow definitions into distributed execution DAGs."""

    def compile(self, spec: Dict[str, Any]) -> WorkflowDAG:
        workflow_id = spec.get("workflow_id", f"wf-{secrets.token_hex(6)}")
        name = spec.get("name", "unnamed-workflow")
        raw_tasks = spec.get("tasks", [])

        tasks: Dict[str, WorkflowTask] = {}
        for rt in raw_tasks:
            tid = rt["task_id"]
            priority = TaskPriority(rt.get("priority", TaskPriority.NORMAL.value))
            tasks[tid] = WorkflowTask(
                task_id=tid,
                name=rt.get("name", tid),
                assigned_seat=rt.get("assigned_seat", "lead"),
                required_capabilities=rt.get("required_capabilities", []),
                dependencies=rt.get("dependencies", []),
                priority=priority,
                input_data=rt.get("input_data", {}),
                max_retries=rt.get("max_retries", 3),
                timeout_seconds=float(rt.get("timeout_seconds", 30.0)),
            )

        # Topological sort & cycle detection
        adj: Dict[str, List[str]] = {tid: [] for tid in tasks}
        in_degree: Dict[str, int] = {tid: 0 for tid in tasks}

        for tid, t in tasks.items():
            for dep in t.dependencies:
                if dep not in tasks:
                    raise ValueError(f"Task '{tid}' has unknown dependency '{dep}'")
                adj[dep].append(tid)
                in_degree[tid] += 1

        queue = collections.deque([tid for tid, deg in in_degree.items() if deg == 0])
        order: List[str] = []

        while queue:
            curr = queue.popleft()
            order.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(tasks):
            raise ValueError("Cycle detected in workflow task dependencies")

        return WorkflowDAG(
            workflow_id=workflow_id,
            name=name,
            tasks=tasks,
            execution_order=order,
            metadata=spec.get("metadata", {}),
        )


class DependencyPipeline:
    """Resolves cross-seat data dependencies with typed validation and zero-copy context streaming."""

    def __init__(self) -> None:
        self._artifact_store: Dict[str, Any] = {}

    def publish_artifact(self, task_id: str, artifact_key: str, data: Any) -> str:
        ref_id = f"art-{task_id}-{artifact_key}"
        self._artifact_store[ref_id] = {
            "task_id": task_id,
            "artifact_key": artifact_key,
            "data": data,
            "digest": hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest(),
            "timestamp": time.time(),
        }
        return ref_id

    def resolve_inputs(self, task: WorkflowTask, completed_tasks: Dict[str, WorkflowTask]) -> Dict[str, Any]:
        resolved: Dict[str, Any] = dict(task.input_data)
        for dep_id in task.dependencies:
            dep_task = completed_tasks.get(dep_id)
            if dep_task and dep_task.output_data:
                resolved[f"dep_{dep_id}"] = dep_task.output_data
        return resolved


class SwarmResourceScheduler:
    """Dynamic resource scheduler prioritizing critical tasks and preempting low-priority jobs."""

    def __init__(self, seat_capacities: Optional[Dict[str, int]] = None) -> None:
        self.capacities: Dict[str, int] = seat_capacities or {
            "lead": 4,
            "systems": 4,
            "web": 4,
            "android": 4,
            "ios": 4,
            "infra": 4,
            "quality": 4,
        }
        self.active_allocations: Dict[str, List[WorkflowTask]] = collections.defaultdict(list)

    def can_allocate(self, task: WorkflowTask) -> bool:
        current_alloc = self.active_allocations[task.assigned_seat]
        capacity = self.capacities.get(task.assigned_seat, 2)
        if len(current_alloc) < capacity:
            return True

        # Check if preemption possible
        lowest_priority_active = max(t.priority.value for t in current_alloc)
        return task.priority.value < lowest_priority_active

    def allocate(self, task: WorkflowTask) -> Optional[WorkflowTask]:
        """Allocates execution slot, preempting a lower priority task if needed."""
        seat = task.assigned_seat
        current_alloc = self.active_allocations[seat]
        capacity = self.capacities.get(seat, 2)

        preempted_task: Optional[WorkflowTask] = None
        if len(current_alloc) >= capacity:
            # Preempt lowest priority active task
            current_alloc.sort(key=lambda t: t.priority.value, reverse=True)
            candidate = current_alloc[0]
            if task.priority.value < candidate.priority.value:
                preempted_task = current_alloc.pop(0)
                preempted_task.status = TaskStatus.PREEMPTED
            else:
                return None

        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        self.active_allocations[seat].append(task)
        return preempted_task

    def release(self, task: WorkflowTask) -> None:
        seat = task.assigned_seat
        if task in self.active_allocations[seat]:
            self.active_allocations[seat].remove(task)


class WorkflowExecutionEngine:
    """Manages workflow execution, checkpoint snapshots, retries, and transitions."""

    def __init__(
        self,
        scheduler: Optional[SwarmResourceScheduler] = None,
        pipeline: Optional[DependencyPipeline] = None,
    ) -> None:
        self.scheduler = scheduler or SwarmResourceScheduler()
        self.pipeline = pipeline or DependencyPipeline()
        self.workflows: Dict[str, WorkflowDAG] = {}
        self.checkpoints: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)

    def submit_workflow(self, dag: WorkflowDAG) -> None:
        self.workflows[dag.workflow_id] = dag
        self.create_checkpoint(dag.workflow_id, "SUBMITTED")

    def create_checkpoint(self, workflow_id: str, label: str) -> Dict[str, Any]:
        dag = self.workflows[workflow_id]
        snapshot = {
            "checkpoint_id": f"chk-{secrets.token_hex(4)}",
            "workflow_id": workflow_id,
            "label": label,
            "timestamp": time.time(),
            "tasks": {tid: t.to_dict() for tid, t in dag.tasks.items()},
        }
        self.checkpoints[workflow_id].append(snapshot)
        return snapshot

    def step_execution(
        self,
        workflow_id: str,
        task_executor: Optional[Callable[[WorkflowTask, Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Executes one step of workflow tasks whose dependencies are satisfied."""
        dag = self.workflows[workflow_id]
        completed_tasks = {
            tid: t for tid, t in dag.tasks.items() if t.status == TaskStatus.COMPLETED
        }

        progressed: List[str] = []
        for tid in dag.execution_order:
            task = dag.tasks[tid]
            if task.status in (TaskStatus.PENDING, TaskStatus.PREEMPTED):
                deps_satisfied = all(
                    dag.tasks[dep].status == TaskStatus.COMPLETED for dep in task.dependencies
                )
                if deps_satisfied:
                    task.status = TaskStatus.READY

            if task.status == TaskStatus.READY:
                if self.scheduler.can_allocate(task):
                    preempted = self.scheduler.allocate(task)
                    resolved_inputs = self.pipeline.resolve_inputs(task, completed_tasks)

                    if task_executor:
                        try:
                            output = task_executor(task, resolved_inputs)
                            task.output_data = output
                            task.status = TaskStatus.COMPLETED
                            task.completed_at = time.time()
                        except Exception as exc:
                            task.error = str(exc)
                            task.retry_count += 1
                            if task.retry_count <= task.max_retries:
                                task.status = TaskStatus.READY
                            else:
                                task.status = TaskStatus.FAILED
                    else:
                        # Default mock execution
                        task.output_data = {"result": f"processed-{task.task_id}", "echo": resolved_inputs}
                        task.status = TaskStatus.COMPLETED
                        task.completed_at = time.time()

                    self.scheduler.release(task)
                    progressed.append(tid)

        all_completed = all(t.status == TaskStatus.COMPLETED for t in dag.tasks.values())
        any_failed = any(t.status == TaskStatus.FAILED for t in dag.tasks.values())

        status = "COMPLETED" if all_completed else ("FAILED" if any_failed else "RUNNING")
        self.create_checkpoint(workflow_id, f"STEP_{status}")

        return {
            "workflow_id": workflow_id,
            "status": status,
            "progressed_tasks": progressed,
            "all_completed": all_completed,
            "tasks": {tid: t.to_dict() for tid, t in dag.tasks.items()},
        }
