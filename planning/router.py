from __future__ import annotations

import logging
from typing import Any

from planning.algorithms.environment import GroundedDisputeEnvironment
from planning.algorithms.lats import LATS
from planning.algorithms.plan_and_solve import PlanAndSolve
from planning.algorithms.tree_of_thoughts import TreeOfThoughts

logger = logging.getLogger(__name__)


class SubTaskRouter:
    """Dispatch Person A's dispute DAG sub-tasks to the appropriate search method."""

    def __init__(self, llm_client: Any):
        self.llm = llm_client
        self.plan_and_solve = PlanAndSolve(llm_client)
        self.tree_of_thoughts = TreeOfThoughts(llm_client, beam_width=3, max_depth=2)
        self.lats = LATS(llm_client, max_iterations=3, environment=GroundedDisputeEnvironment())

    def select_algorithm(self, sub_task: dict) -> str:
        task_type = str(sub_task.get("type", "")).lower()
        description = str(sub_task.get("description", "")).lower()
        text = f"{task_type} {description}"

        if any(key in text for key in ("rank", "sort", "priority", "risk")):
            return "tree_of_thoughts"
        if any(key in text for key in ("refund", "escalate", "commit", "database state", "write")):
            return "lats"
        return "plan_and_solve"

    def route_and_execute(self, sub_task: dict) -> dict:
        algorithm = self.select_algorithm(sub_task)
        task_id = sub_task.get("id", "unknown")
        logger.info("Routing %s -> %s", task_id, algorithm)
        description = sub_task.get("description", "")
        context = sub_task.get("context", "")
        if algorithm == "tree_of_thoughts":
            return self.tree_of_thoughts.execute(description, context)
        if algorithm == "lats":
            return self.lats.execute(description, context)
        return self.plan_and_solve.execute(description, context)
