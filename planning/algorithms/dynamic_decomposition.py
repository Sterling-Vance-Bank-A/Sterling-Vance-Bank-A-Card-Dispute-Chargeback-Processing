from __future__ import annotations

import json
import logging
from typing import Any, Callable

from .decomposition import DeadlockPlanError, PlanDAG, SubTask
from .plan_and_solve import _invoke

logger = logging.getLogger(__name__)


class DynamicDecomposition:
    """
    Dynamic / Interleaved Decomposition: Adapted from the reference toolkit.

    Instead of generating a static plan upfront, the agent observes the execution output
    of prior sub-tasks, evaluates whether the goal has been met or if new constraints
    have emerged, incrementally grows the DAG, and generates the next sub-task adaptively.
    Acyclicity is validated at every incremental step.
    """

    def __init__(
        self,
        llm_client: Any,
        router_fn: Callable[[SubTask], Any] | None = None,
        max_steps: int = 5,
    ):
        self.llm = llm_client
        self.router_fn = router_fn
        self.max_steps = max_steps
        self.metrics = {"llm_calls": 0, "tokens": 0}

    def execute(self, complex_request: str, context: Any = None) -> dict:
        """
        Execute dynamic / interleaved decomposition loop:
        observe history -> LLM decides done or next_task -> validate incremental DAG -> execute -> repeat.
        """
        self.metrics = {"llm_calls": 0, "tokens": 0}
        dag = PlanDAG()
        history: list[tuple[str, str]] = []
        execution_order: list[str] = []
        execution_results: dict[str, Any] = {}
        diverged = False

        for step in range(self.max_steps):
            observation = (
                "\n".join(f"[{task_id}]: {res}" for task_id, res in execution_results.items())
                or "No completed sub-tasks yet."
            )

            # Step 1: Decision - Decide next sub-task or if goal is met
            decision = self._decide_next_step(complex_request, context, observation, step)

            if decision.get("done", False):
                logger.info("Dynamic planner decided goal is met at step %d", step + 1)
                break

            task_description = decision.get("next_task", "").strip()
            task_type = decision.get("task_type", "general")
            depends_on = decision.get("depends_on", [])
            task_id = f"task_{step + 1}"

            if not task_description:
                logger.warning("Dynamic planner omitted next_task at step %d, stopping.", step + 1)
                break

            # Check if dynamic planner diverged from standard linear flow
            if decision.get("divergence_reason"):
                diverged = True

            # Step 2: Incrementally add to DAG and enforce acyclicity at construction time
            subtask = SubTask(
                id=task_id,
                description=task_description,
                task_type=task_type,
                depends_on=depends_on if isinstance(depends_on, list) else [],
                context={
                    "request": complex_request,
                    "initial_context": context,
                    "prior_observations": observation,
                    "step": step + 1,
                },
            )
            dag.add_task(subtask)

            # Enforce acyclicity at every incremental step
            dag.validate_acyclic()

            # Step 3: Execute the sub-task (via router or direct model call)
            if self.router_fn:
                result = self.router_fn(subtask)
            else:
                result = self._execute_subtask(subtask, complex_request, observation)

            subtask.result = result
            subtask.status = "completed"
            execution_results[task_id] = result
            execution_order.append(task_id)
            history.append((task_description, str(result)))

        return {
            "status": "success",
            "method": "dynamic_decomposition",
            "dag_tasks": {t_id: t.__dict__ for t_id, t in dag.tasks.items()},
            "execution_order": execution_order,
            "results": execution_results,
            "history": history,
            "diverged": diverged,
            "steps_taken": len(execution_order),
            "metrics": self.metrics.copy(),
        }

    def _decide_next_step(
        self, goal: str, context: Any, observation: str, step: int
    ) -> dict:
        prompt = (
            "You are the Adaptive Dispute Planning Agent for Sterling Vance Bank.\n"
            "Review the current remediation goal, initial context, and completed observations.\n"
            "Decide if the overall goal is fully satisfied ('done': true) or what single next sub-task is required ('done': false).\n\n"
            "Return a clean JSON object with keys:\n"
            "- 'done': boolean (true if dispute remediation plan is complete)\n"
            "- 'next_task': string (actionable sub-task description, empty if done)\n"
            "- 'task_type': one of ['evidence_aggregation', 'timeline_generation', 'fee_calculation', 'rank_recovery', 'sort_priority', 'process_refund', 'escalate_dispute', 'notification_draft']\n"
            "- 'depends_on': list of prior task IDs this step directly depends on\n"
            "- 'divergence_reason': string (explain if dynamic replanning altered the flow due to an early failure/finding, otherwise null)\n\n"
            f"Goal: {goal}\nInitial Context: {context}\nPrior Observations:\n{observation}\n\n"
            "JSON Output:"
        )

        response = self._call(prompt)
        try:
            raw = response.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception as e:
            logger.debug("Could not parse JSON decision directly: %s. Using heuristic fallback.", e)
        return self._heuristic_decision(goal, observation, step)

    def _execute_subtask(self, task: SubTask, goal: str, observation: str) -> Any:
        prompt = (
            f"Execute adaptive sub-task for Sterling Vance Bank:\n"
            f"Goal: {goal}\nTask ID: {task.id}\nType: {task.task_type}\nDescription: {task.description}\n"
            f"Prior Observations:\n{observation}\n"
        )
        return self._call(prompt)

    def _call(self, prompt: str) -> str:
        self.metrics["llm_calls"] += 1
        response = _invoke(self.llm, prompt)
        self.metrics["tokens"] += len(response.split())
        return response

    def _heuristic_decision(self, goal: str, observation: str, step: int) -> dict:
        """Heuristic decision generator for testing and mock runners."""
        obs_lower = observation.lower()

        # Divergence trigger 1: Early terminal state detected
        if "already terminal" in obs_lower or "status=refunded" in obs_lower or "status=denied" in obs_lower:
            if step == 1:
                return {
                    "done": False,
                    "next_task": "Generate terminal state audit record and dispute closure notice",
                    "task_type": "notification_draft",
                    "depends_on": ["task_1"],
                    "divergence_reason": "Dispute is already terminal; canceled refund/escalation pipeline.",
                }
            return {"done": True, "next_task": "", "task_type": "general", "depends_on": []}

        # Divergence trigger 2: Missing merchant record or exhausted reserve
        if "merchant not found" in obs_lower or "reserve exhausted" in obs_lower or "missing merchant" in obs_lower:
            if step == 1:
                return {
                    "done": False,
                    "next_task": "Route to Card Network Pre-Arbitration due to missing merchant escrow",
                    "task_type": "escalate_dispute",
                    "depends_on": ["task_1"],
                    "divergence_reason": "Merchant escrow unavailable; pivoted from direct debit to card network arbitration.",
                }
            return {"done": True, "next_task": "", "task_type": "general", "depends_on": []}

        # Standard step progression
        steps = [
            {"done": False, "next_task": "Aggregate dispute and transaction evidence", "task_type": "evidence_aggregation", "depends_on": []},
            {"done": False, "next_task": "Evaluate reason code eligibility and risk thresholds", "task_type": "sort_priority", "depends_on": ["task_1"]},
            {"done": False, "next_task": "Execute resolution action (refund or escalation)", "task_type": "process_refund", "depends_on": ["task_2"]},
            {"done": False, "next_task": "Draft customer disclosure and compliance notice", "task_type": "notification_draft", "depends_on": ["task_3"]},
            {"done": True, "next_task": "", "task_type": "general", "depends_on": []},
        ]
        return steps[min(step, len(steps) - 1)]


def dynamic_decomposition(goal: str, llm: Any, max_steps: int = 4) -> list[tuple[str, str]]:
    """Reference-toolkit-compatible functional interface."""
    result = DynamicDecomposition(llm, max_steps=max_steps).execute(goal)
    return result.get("history", [])
