from __future__ import annotations

import logging
from typing import Any

from planning.algorithms.decomposition import SubTask
from planning.algorithms.environment import Environment, GroundedDisputeEnvironment
from planning.algorithms.lats import LATS
from planning.algorithms.plan_and_solve import PlanAndSolve
from planning.algorithms.tree_of_thoughts import TreeOfThoughts

logger = logging.getLogger(__name__)


class SubTaskRouter:
    """
    Sub-Task Dispatcher for Sterling Vance Bank Dispute Planning Agent.

    Inspects sub-task shape, task_type taxonomy, and risk level, then routes execution
    to the optimal planning algorithm:

    ROUTING RATIONALE & DISPATCH TABLE:
    -------------------------------------------------------------------------------------------------
    Sub-Task Shape / Type                    | Algorithm       | Rationale
    -------------------------------------------------------------------------------------------------
    - evidence_aggregation                   | Plan-and-Solve  | Single deterministic pass; linear step-by-
    - timeline_generation                    |                 | step execution with no real branching.
    - fee_calculation                        |                 |
    - notification_draft                     |                 |
    -------------------------------------------------------------------------------------------------
    - rank_recovery                          | Tree-of-Thoughts| Combinatorial search; multiple candidate
    - sort_priority                          |                 | priority orderings and reason code branches
    - rank_risk                              |                 | worth comparing before committing.
    -------------------------------------------------------------------------------------------------
    - process_refund                         | Grounded LATS   | High-stakes financial/compliance commits;
    - escalate_dispute                       |                 | MCTS guided by real external SQLite DB
    - commit_action / write                  |                 | feedback to prevent illegal refunds/payouts.
    -------------------------------------------------------------------------------------------------
    """

    def __init__(
        self,
        llm_client: Any,
        environment: Environment | None = None,
        beam_width: int = 3,
        max_depth: int = 2,
        lats_iterations: int = 3,
    ):
        self.llm = llm_client
        self.environment = environment or GroundedDisputeEnvironment()
        self.plan_and_solve = PlanAndSolve(llm_client)
        self.tree_of_thoughts = TreeOfThoughts(llm_client, beam_width=beam_width, max_depth=max_depth)
        self.lats = LATS(llm_client, max_iterations=lats_iterations, environment=self.environment)

    def select_algorithm(self, sub_task: SubTask | dict) -> str:
        """Inspects sub-task taxonomy and returns algorithm identifier."""
        if isinstance(sub_task, SubTask):
            task_type = str(sub_task.task_type).lower()
            description = str(sub_task.description).lower()
        else:
            task_type = str(sub_task.get("task_type", sub_task.get("type", ""))).lower()
            description = str(sub_task.get("description", "")).lower()

        combined = f"{task_type} {description}"

        # 1. High-Stakes State Changes -> Grounded LATS
        if any(kw in combined for kw in ("refund", "escalat", "commit", "payout", "write", "settle", "debit")):
            return "lats"

        # 2. Combinatorial / Prioritization -> Tree of Thoughts
        if any(kw in combined for kw in ("rank", "sort", "priority", "risk", "combinatorial", "order", "candidate")):
            return "tree_of_thoughts"

        # 3. Linear / Deterministic -> Plan-and-Solve (default)
        return "plan_and_solve"

    def route_and_execute(self, sub_task: SubTask | dict) -> dict:
        """Dispatches sub-task to the selected algorithm and returns structured result."""
        algorithm = self.select_algorithm(sub_task)

        if isinstance(sub_task, SubTask):
            task_id = sub_task.id
            description = sub_task.description
            context = sub_task.context
        else:
            task_id = sub_task.get("id", "unknown")
            description = sub_task.get("description", "")
            context = sub_task.get("context", "")

        logger.info("SubTaskRouter: Dispatching [%s] -> %s", task_id, algorithm)

        if algorithm == "tree_of_thoughts":
            result = self.tree_of_thoughts.execute(description, context)
        elif algorithm == "lats":
            result = self.lats.execute(description, context)
        else:
            result = self.plan_and_solve.execute(description, context)

        if isinstance(sub_task, SubTask):
            task_type = sub_task.task_type
        else:
            task_type = sub_task.get("task_type", sub_task.get("type", "general"))

        result["routed_algorithm"] = algorithm
        result["task_id"] = task_id
        result["subtask_type"] = task_type
        result["description"] = description
        return result

    def __call__(self, sub_task: SubTask | dict) -> dict:
        """Allows SubTaskRouter instance to be passed directly as a router_fn callback."""
        return self.route_and_execute(sub_task)
