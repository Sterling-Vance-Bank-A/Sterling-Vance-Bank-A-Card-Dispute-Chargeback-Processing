from __future__ import annotations

from typing import Any


class PlanAndSolve:
    """Plan-and-Solve adapted from the course reference toolkit.

    The original toolkit exposes a single-call Plan-and-Solve function. This class
    preserves the team's local router API while keeping the same one-call PLAN/SOLUTION
    behavior and metrics needed by the benchmark.
    """

    def __init__(self, llm_client: Any):
        self.llm = llm_client
        self.metrics = {"llm_calls": 0, "tokens": 0}

    def execute(self, task_description: str, context: Any) -> dict:
        prompt = (
            "You are the Plan-and-Solve planner for Sterling Vance Bank card disputes.\n"
            "Use exactly one model call. Return two labeled sections: PLAN and SOLUTION.\n"
            "PLAN: list the required sequential steps.\n"
            "SOLUTION: execute those steps in order. Do not branch.\n"
            "Respect transaction amount, dispute state, reason code, and analyst constraints.\n\n"
            f"Task: {task_description}\nContext: {context}"
        )
        response = self._call(prompt)
        ok = bool(response.strip()) and "PLAN" in response and "SOLUTION" in response
        return {
            "status": "success" if ok else "failed",
            "final_result": response,
            "execution_trace": [{"phase": "plan", "result": response}],
            "metrics": self.metrics.copy(),
        }

    def _call(self, prompt: str) -> str:
        self.metrics["llm_calls"] += 1
        response = _invoke(self.llm, prompt)
        self.metrics["tokens"] += len(response.split())
        return response


def plan_and_solve(question: str, llm: Any) -> str:
    """Reference-toolkit-compatible function interface."""
    result = PlanAndSolve(llm).execute(question, "")
    return result["final_result"]


def _invoke(llm: Any, prompt: str) -> str:
    if hasattr(llm, "generate"):
        return str(llm.generate(prompt))
    if hasattr(llm, "invoke"):
        response = llm.invoke(prompt)
        content = getattr(response, "content", response)
        return str(content)
    raise TypeError("LLM client must expose generate(prompt) or invoke(prompt)")
