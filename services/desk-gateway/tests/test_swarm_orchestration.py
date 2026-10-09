"""Unit tests for Phase 46: Autonomous Cross-Desk Swarm Workflow Engine."""

import pytest
from desk_gateway.swarm_orchestration import (
    CrossDeskWorkflowCompiler,
    WorkflowDAG,
    WorkflowTask,
    TaskStatus,
    TaskPriority,
    DependencyPipeline,
    SwarmResourceScheduler,
    WorkflowExecutionEngine,
)


def test_workflow_compiler_topological_sort_and_cycle_detection():
    compiler = CrossDeskWorkflowCompiler()

    # Valid DAG
    spec = {
        "workflow_id": "wf-compile-test",
        "name": "Compile Test Workflow",
        "tasks": [
            {"task_id": "step_a", "dependencies": []},
            {"task_id": "step_b", "dependencies": ["step_a"]},
            {"task_id": "step_c", "dependencies": ["step_a"]},
            {"task_id": "step_d", "dependencies": ["step_b", "step_c"]},
        ],
    }
    dag = compiler.compile(spec)
    assert dag.workflow_id == "wf-compile-test"
    assert dag.execution_order[0] == "step_a"
    assert dag.execution_order[-1] == "step_d"

    # Cycle detection
    cyclic_spec = {
        "tasks": [
            {"task_id": "node_x", "dependencies": ["node_y"]},
            {"task_id": "node_y", "dependencies": ["node_x"]},
        ]
    }
    with pytest.raises(ValueError, match="Cycle detected"):
        compiler.compile(cyclic_spec)


def test_dependency_pipeline_context_resolution():
    pipeline = DependencyPipeline()
    ref = pipeline.publish_artifact("t1", "report_json", {"status": "ok", "lines": 42})
    assert "t1-report_json" in ref

    task_a = WorkflowTask(
        task_id="t1",
        name="Task A",
        assigned_seat="lead",
        required_capabilities=[],
        status=TaskStatus.COMPLETED,
        output_data={"metrics": {"coverage": 95.0}},
    )
    task_b = WorkflowTask(
        task_id="t2",
        name="Task B",
        assigned_seat="systems",
        required_capabilities=[],
        dependencies=["t1"],
        input_data={"mode": "strict"},
    )

    resolved = pipeline.resolve_inputs(task_b, {"t1": task_a})
    assert resolved["mode"] == "strict"
    assert resolved["dep_t1"]["metrics"]["coverage"] == 95.0


def test_swarm_resource_scheduler_preemption():
    scheduler = SwarmResourceScheduler(seat_capacities={"lead": 1})

    low_task = WorkflowTask(
        task_id="bg_task",
        name="Background",
        assigned_seat="lead",
        required_capabilities=[],
        priority=TaskPriority.LOW,
    )
    crit_task = WorkflowTask(
        task_id="crit_task",
        name="Critical hotfix",
        assigned_seat="lead",
        required_capabilities=[],
        priority=TaskPriority.CRITICAL,
    )

    # Allocate low task
    preempted = scheduler.allocate(low_task)
    assert preempted is None
    assert low_task.status == TaskStatus.RUNNING

    # Allocate critical task -> preempts low task
    assert scheduler.can_allocate(crit_task) is True
    preempted = scheduler.allocate(crit_task)
    assert preempted is not None
    assert preempted.task_id == "bg_task"
    assert preempted.status == TaskStatus.PREEMPTED
    assert crit_task.status == TaskStatus.RUNNING
