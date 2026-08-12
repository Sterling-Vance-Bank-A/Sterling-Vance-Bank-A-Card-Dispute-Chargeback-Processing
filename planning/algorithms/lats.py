from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .environment import Environment, EnvironmentFeedback, GroundedDisputeEnvironment
from .plan_and_solve import _invoke


@dataclass
class MCTSNode:
    state: str
    parent: "MCTSNode | None" = None
    action: str = "root"
    children: list["MCTSNode"] = field(default_factory=list)
    visits: int = 0
    value_sum: float = 0.0
    environment_score: float = 0.0
    model_score: float = 0.0
    feedback: EnvironmentFeedback | None = None
    reflections: list[str] = field(default_factory=list)

    @property
    def mean_value(self) -> float:
        return self.value_sum / self.visits if self.visits else 0.0

    def uct_score(self, exploration_weight: float = 1.414) -> float:
        if self.visits == 0:
            return float("inf")
        parent_visits = max(self.parent.visits if self.parent else 1, 1)
        return self.mean_value + exploration_weight * math.sqrt(math.log(parent_visits) / self.visits)


class LATS:
    """LATS/MCTS adaptation with real external feedback and branch reflection."""

    def __init__(
        self,
        llm_client: Any,
        max_iterations: int = 3,
        environment: Environment | None = None,
        n_actions: int = 3,
        exploration_weight: float = 1.414,
    ):
        if max_iterations < 1 or n_actions < 1:
            raise ValueError("max_iterations and n_actions must be positive")
        self.llm = llm_client
        self.max_iterations = max_iterations
        self.environment = environment or GroundedDisputeEnvironment()
        self.n_actions = n_actions
        self.exploration_weight = exploration_weight
        self.metrics = {"llm_calls": 0, "tokens": 0}

    def execute(self, task_description: str, initial_context: Any) -> dict:
        root = MCTSNode(state=str(initial_context))
        best: MCTSNode | None = None
        iteration_count = 0

        for iteration in range(self.max_iterations):
            iteration_count = iteration + 1
            leaf = self._select(root)
            self._expand(leaf, task_description)
            for child in leaf.children:
                feedback = self.environment.evaluate(child.state)
                child.feedback = feedback
                child.environment_score = feedback.score
                child.model_score = self._value(task_description, child, feedback)
                combined = 0.75 * feedback.score + 0.25 * child.model_score
                if not feedback.success:
                    child.reflections.append(self._reflect(task_description, child, feedback))
                self._backpropagate(child, combined)
                if best is None or child.environment_score > best.environment_score:
                    best = child
                if feedback.success:
                    return self._result(True, child, iteration_count, root)

        return self._result(False, best, iteration_count, root)

    def _select(self, root: MCTSNode) -> MCTSNode:
        node = root
        while node.children:
            node = max(node.children, key=lambda child: child.uct_score(self.exploration_weight))
        return node

    def _expand(self, node: MCTSNode, task: str) -> None:
        prompt = (
            "You are the LATS action generator for a bank dispute.\n"
            f"Task: {task}\nCurrent state: {node.state}\n"
            "Use prior branch reflections when present. Generate candidate actions, one per line.\n"
            f"Return at most {self.n_actions} complete candidates. Each candidate must include a concrete action, dispute ID, and analyst ID."
        )
        raw = self._call(prompt)
        lines = [line.strip(" -•\t") for line in raw.splitlines() if line.strip()][: self.n_actions]
        for line in lines:
            action = self._action_name(line)
            node.children.append(MCTSNode(state=line, parent=node, action=action))

    def _value(self, task: str, node: MCTSNode, feedback: EnvironmentFeedback) -> float:
        prompt = (
            "Estimate future usefulness from 0 to 1. Use external validator feedback as evidence.\n"
            f"Task: {task}\nCandidate: {node.state}\n"
            f"External score: {feedback.score}\nExternal feedback: {feedback.details}"
        )
        raw = self._call(prompt).strip()
        for token in raw.replace("|", " ").split():
            try:
                return max(0.0, min(1.0, float(token)))
            except ValueError:
                continue
        return 0.5

    def _reflect(self, task: str, node: MCTSNode, feedback: EnvironmentFeedback) -> str:
        prompt = (
            "Create a brief branch reflection grounded only in the external validator.\n"
            f"Task: {task}\nCandidate: {node.state}\nFailure feedback: {feedback.details}\n"
            "State what the next expansion should avoid."
        )
        return self._call(prompt).strip()

    def _call(self, prompt: str) -> str:
        self.metrics["llm_calls"] += 1
        response = _invoke(self.llm, prompt)
        self.metrics["tokens"] += len(response.split())
        return response

    @staticmethod
    def _action_name(text: str) -> str:
        lowered = text.lower()
        if "escalat" in lowered:
            return "escalate_dispute"
        if "refund" in lowered:
            return "process_refund"
        return "verify_transaction"

    @staticmethod
    def _backpropagate(node: MCTSNode, reward: float) -> None:
        while node is not None:
            node.visits += 1
            node.value_sum += reward
            node = node.parent

    @staticmethod
    def _flatten(root: MCTSNode) -> list[dict]:
        rows: list[dict] = []
        queue: list[tuple[MCTSNode, str | None]] = [(root, None)]
        counter = 0
        while queue:
            node, parent_id = queue.pop(0)
            node_id = f"n{counter}"
            counter += 1
            rows.append(
                {
                    "id": node_id,
                    "parent_id": parent_id,
                    "action": node.action,
                    "state": node.state,
                    "visits": node.visits,
                    "mean_value": round(node.mean_value, 6),
                    "environment_score": node.environment_score,
                    "model_score": node.model_score,
                    "feedback": node.feedback.__dict__ if node.feedback else None,
                    "reflections": node.reflections,
                }
            )
            queue.extend((child, node_id) for child in node.children)
        return rows

    def _result(self, success: bool, best: MCTSNode | None, iterations: int, root: MCTSNode) -> dict:
        return {
            "status": "success" if success else "failed",
            "best_action": best.action if best else None,
            "final_state": best.state if best else root.state,
            "environment_feedback": best.feedback.__dict__ if best and best.feedback else None,
            "mcts": self._flatten(root),
            "iterations": iterations,
            "metrics": self.metrics.copy(),
        }


def lats(task: str, llm: Any, environment: Environment, iterations: int = 2, n_actions: int = 2, exploration_weight: float = 1.414):
    """Reference-toolkit-compatible functional interface."""
    result = LATS(
        llm,
        max_iterations=iterations,
        environment=environment,
        n_actions=n_actions,
        exploration_weight=exploration_weight,
    ).execute(task, "No attempt yet")
    return result
