from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import json
import logging

from .plan_and_solve import _invoke

logger = logging.getLogger(__name__)


class DeadlockPlanError(Exception):
    """Raised when a sub-task plan contains a cyclic dependency, causing a deadlock."""
    pass


@dataclass
class SubTask:
    id: str
    description: str
    task_type: str = "general"
    depends_on: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    status: str = "pending"  # pending, completed, failed


@dataclass
class PlanDAG:
    tasks: dict[str, SubTask] = field(default_factory=dict)

    def add_task(self, task: SubTask) -> None:
        self.tasks[task.id] = task

    def validate_acyclic(self) -> list[str]:
        """
        Enforce acyclicity using Kahn's algorithm.
        Returns the topological ordering of task IDs if acyclic.
        Raises DeadlockPlanError if a cycle (deadlock) is detected.
        """
        in_degree = {task_id: 0 for task_id in self.tasks}
        adj_list: dict[str, list[str]] = {task_id: [] for task_id in self.tasks}

        for task_id, task in self.tasks.items():
            for dep in task.depends_on:
                if dep in self.tasks:
                    adj_list[dep].append(task_id)
                    in_degree[task_id] += 1
                else:
                    logger.warning("Dependency %s not found in plan tasks, ignoring.", dep)

        queue = [task_id for task_id, deg in in_degree.items() if deg == 0]
        topological_order = []

        while queue:
            current = queue.pop(0)
            topological_order.append(current)
            for neighbor in adj_list[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(topological_order) != len(self.tasks):
            cycle_tasks = [t for t, deg in in_degree.items() if deg > 0]
            raise DeadlockPlanError(
                f"Cyclic dependency (deadlock) detected among tasks: {cycle_tasks}"
            )

        return topological_order


class DecompositionFirst:
    """
    Decomposition-First: The entire plan is generated upfront as a DAG in one shot.
    Acyclicity is verified at construction time. Tasks are executed in topological order.
    """

    def __init__(self, llm_client: Any, router_fn: Callable[[SubTask], Any] | None = None):
        self.llm = llm_client
        self.router_fn = router_fn
        self.metrics = {"llm_calls": 0, "tokens": 0}

    def decompose(self, complex_request: str, context: Any = None) -> PlanDAG:
        """Generate the complete DAG upfront in one shot."""
        prompt = (
            "You are the Lead Planning Decomposition Agent for Sterling Vance Bank Card Disputes.\n"
            "Decompose the following complex dispute remediation request into a structured Directed Acyclic Graph (DAG) of sub-tasks.\n"
            "Return a clean JSON object with a 'tasks' list. Each task must have:\n"
            "- 'id': unique string (e.g. 'task_1', 'task_2')\n"
            "- 'description': clear actionable goal\n"
            "- 'task_type': one of ['evidence_aggregation', 'timeline_generation', 'fee_calculation', 'rank_recovery', 'sort_priority', 'process_refund', 'escalate_dispute', 'notification_draft']\n"
            "- 'depends_on': list of task IDs that must complete BEFORE this task\n"
            "- 'context': specific parameters (dispute_id, merchant_id, etc.)\n\n"
            f"Request: {complex_request}\nContext: {context}\n"
            "JSON Output:"
        )

        response = self._call(prompt)
        dag = PlanDAG()

        try:
            raw = response.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            parsed = json.loads(raw)
            task_list = parsed.get("tasks", [])
            for item in task_list:
                task = SubTask(
                    id=str(item.get("id")),
                    description=str(item.get("description", "")),
                    task_type=str(item.get("task_type", "general")),
                    depends_on=list(item.get("depends_on", [])),
                    context=dict(item.get("context", {})),
                )
                dag.add_task(task)
        except Exception as e:
            logger.warning("Failed to parse JSON plan directly: %s. Using structured heuristic decomposition.", e)
            dag = self._fallback_decomposition(complex_request, context)

        dag.validate_acyclic()
        return dag

    def execute(self, complex_request: str, context: Any = None) -> dict:
        """Decompose upfront, validate DAG acyclicity, and execute topologically."""
        self.metrics = {"llm_calls": 0, "tokens": 0}
        dag = self.decompose(complex_request, context)
        execution_order = dag.validate_acyclic()

        execution_results = {}
        for task_id in execution_order:
            task = dag.tasks[task_id]
            parent_contexts = {dep_id: execution_results.get(dep_id) for dep_id in task.depends_on}
            task.context["parent_results"] = parent_contexts

            if self.router_fn:
                task_res = self.router_fn(task)
            else:
                task_res = self._execute_subtask(task)

            task.result = task_res
            task.status = "completed"
            execution_results[task_id] = task_res

        return {
            "status": "success",
            "method": "decomposition_first",
            "dag_tasks": {t_id: t.__dict__ for t_id, t in dag.tasks.items()},
            "execution_order": execution_order,
            "results": execution_results,
            "metrics": self.metrics.copy(),
        }

    def _execute_subtask(self, task: SubTask) -> Any:
        prompt = (
            f"Execute sub-task for Sterling Vance Bank:\n"
            f"Task ID: {task.id}\nType: {task.task_type}\nDescription: {task.description}\n"
            f"Context: {task.context}\n"
        )
        return self._call(prompt)

    def _call(self, prompt: str) -> str:
        self.metrics["llm_calls"] += 1
        response = _invoke(self.llm, prompt)
        self.metrics["tokens"] += len(response.split())
        return response

    def _fallback_decomposition(self, request: str, context: Any) -> PlanDAG:
        dag = PlanDAG()
        req_lower = request.lower()
        if "merch-" in req_lower or "portfolio" in req_lower or "fraud ring" in req_lower:
            dag.add_task(SubTask("task_1", "Inspect merchant status and aggregate dispute evidence", "evidence_aggregation", []))
            dag.add_task(SubTask("task_2", "Rank dispute recovery priorities against merchant reserve", "rank_recovery", ["task_1"]))
            dag.add_task(SubTask("task_3", "Execute priority refunds and network escalations", "process_refund", ["task_2"]))
            dag.add_task(SubTask("task_4", "Draft customer and network regulatory notifications", "notification_draft", ["task_3"]))
        else:
            dag.add_task(SubTask("task_1", f"Summarize dispute evidence for {request[:30]}", "evidence_aggregation", []))
            dag.add_task(SubTask("task_2", "Evaluate resolution policy and liability allocation", "sort_priority", ["task_1"]))
            dag.add_task(SubTask("task_3", "Execute resolution and record in database", "process_refund", ["task_2"]))
        return dag
