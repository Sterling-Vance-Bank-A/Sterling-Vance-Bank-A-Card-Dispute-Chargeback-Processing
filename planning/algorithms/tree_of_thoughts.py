from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .plan_and_solve import _invoke


@dataclass
class Thought:
    state: str
    score: float
    rationale: str


class TreeOfThoughts:
    """Bounded ToT beam search adapted to dispute-priority ranking."""

    def __init__(self, llm_client: Any, beam_width: int = 3, max_depth: int = 2):
        if beam_width < 1 or max_depth < 1:
            raise ValueError("beam_width and max_depth must be positive")
        self.llm = llm_client
        self.beam_width = beam_width
        self.max_depth = max_depth
        self.metrics = {"llm_calls": 0, "tokens": 0}

    def execute(self, task_description: str, context: Any) -> dict:
        frontier = [Thought(state=f"Start | {context}", score=0.5, rationale="root")]
        pruned = 0
        levels: list[list[dict]] = []

        for depth in range(self.max_depth):
            candidates: list[Thought] = []
            level_trace: list[dict] = []
            for parent in frontier:
                thoughts = self._generate_thoughts(task_description, parent, depth)
                for thought in thoughts:
                    score, rationale = self._evaluate(task_description, parent, thought)
                    level_trace.append({"parent": parent.state, "candidate": thought, "score": score, "rationale": rationale})
                    if score <= 0.0:
                        pruned += 1
                        continue
                    candidates.append(Thought(state=thought, score=score, rationale=rationale))
            candidates.sort(key=lambda item: item.score, reverse=True)
            frontier = candidates[: self.beam_width]
            levels.append(level_trace)
            if not frontier:
                break

        best = frontier[0] if frontier else None
        return {
            "status": "success" if best else "failed",
            "best_path": best.__dict__ if best else None,
            "search": {
                "method": "BFS/beam",
                "beam_width": self.beam_width,
                "max_depth": self.max_depth,
                "pruned": pruned,
                "levels": levels,
            },
            "metrics": self.metrics.copy(),
        }

    def _generate_thoughts(self, task: str, parent: Thought, depth: int) -> list[str]:
        prompt = (
            "Generate distinct candidate next steps for Tree-of-Thoughts dispute ranking.\n"
            f"Task: {task}\nPartial path: {parent.state}\nDepth: {depth}\n"
            f"Return {self.beam_width} candidates, one per line."
        )
        raw = self._call(prompt)
        return [line.strip(" -•\t") for line in raw.splitlines() if line.strip()][: self.beam_width]

    def _evaluate(self, task: str, parent: Thought, candidate: str) -> tuple[float, str]:
        prompt = (
            "Evaluate this Tree-of-Thoughts candidate for correctness, feasibility, and progress.\n"
            "Return: SCORE <0..1> | RATIONALE <short reason>.\n"
            f"Task: {task}\nParent: {parent.state}\nCandidate: {candidate}"
        )
        raw = self._call(prompt).strip()
        score = 0.0
        rationale = raw
        try:
            first = raw.split()[0]
            score = float(first.replace("SCORE", "").strip(":"))
        except (ValueError, IndexError):
            if "score" in raw.lower():
                for token in raw.replace("|", " ").split():
                    try:
                        score = float(token)
                        break
                    except ValueError:
                        continue
            if score == 0.0:
                score = 0.5
        return max(0.0, min(1.0, score)), rationale

    def _call(self, prompt: str) -> str:
        self.metrics["llm_calls"] += 1
        response = _invoke(self.llm, prompt)
        self.metrics["tokens"] += len(response.split())
        return response


def tree_of_thoughts(problem: str, llm: Any, depth: int = 2, beam_width: int = 2) -> list[Thought]:
    """Reference-toolkit-compatible functional interface."""
    result = TreeOfThoughts(llm, beam_width=beam_width, max_depth=depth).execute(problem, "")
    best = result.get("best_path")
    return [Thought(**best)] if best else []
