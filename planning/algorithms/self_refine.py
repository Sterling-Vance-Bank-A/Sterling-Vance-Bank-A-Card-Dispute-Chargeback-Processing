from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .environment import Environment, EnvironmentFeedback, GroundedDisputeEnvironment
from .plan_and_solve import _invoke

logger = logging.getLogger(__name__)


@dataclass
class SelfRefineResult:
    draft: str
    critique: str
    revised: str
    grounded_issues: list[str] = field(default_factory=list)
    grounded_feedback: dict[str, Any] | None = None
    passed_initially: bool = False
    metrics: dict[str, int] = field(default_factory=dict)


class SelfRefine:
    """
    Self-Refine Algorithm adapted from reference toolkit (Madaan et al., 2023).

    A single-pass self-correction loop designed for cheap-to-redo sub-tasks
    (e.g., customer dispute disclosures, regulatory notifications, timeline formatting).

    Loop:
      1. Initial Draft: Generate candidate output from task description & context.
      2. Grounded Check & Rubric Critique: Evaluate against database constraints
         (via GroundedDisputeEnvironment) and structural banking compliance rubrics.
      3. Revision: If issues are detected, revise the deliverable addressing every critique.
    """

    def __init__(self, llm_client: Any, environment: Environment | None = None):
        self.llm = llm_client
        self.environment = environment or GroundedDisputeEnvironment()
        self.metrics = {"llm_calls": 0, "tokens": 0}

    def execute(self, task_description: str, context: Any = None) -> dict:
        """Execute full Draft -> Grounded Critique -> Revision pipeline."""
        self.metrics = {"llm_calls": 0, "tokens": 0}

        # Step 1: Initial Draft
        draft = self._generate_draft(task_description, context)

        # Step 2: Grounded Environment & Deterministic Checks
        grounded_issues, env_feedback = self._run_grounded_checks(draft, context)
        grounded_report = (
            "\n".join(f"- {issue}" for issue in grounded_issues)
            if grounded_issues
            else "- Grounded bank validation checks passed."
        )

        # Step 3: Explicit Rubric Critique
        critique = self._critique(task_description, draft, grounded_report)

        # Step 4: Revision (or pass if clean)
        critique_stripped = critique.strip().upper()
        critique_passed = (critique_stripped == "PASS" or critique_stripped.startswith("PASS\n") or critique_stripped.startswith("PASS."))
        is_clean = (
            critique_passed
            and not grounded_issues
            and (env_feedback is None or env_feedback.success)
        )

        if is_clean:
            revised = draft
            passed_initially = True
        else:
            revised = self._revise(task_description, draft, grounded_report, critique)
            passed_initially = False

        res = SelfRefineResult(
            draft=draft,
            critique=critique,
            revised=revised,
            grounded_issues=grounded_issues,
            grounded_feedback=env_feedback.__dict__ if env_feedback else None,
            passed_initially=passed_initially,
            metrics=self.metrics.copy(),
        )
        return {
            "status": "success",
            "method": "self_refine",
            "draft": res.draft,
            "critique": res.critique,
            "revised": res.revised,
            "grounded_issues": res.grounded_issues,
            "grounded_feedback": res.grounded_feedback,
            "passed_initially": res.passed_initially,
            "metrics": res.metrics,
        }

    def _generate_draft(self, task: str, context: Any) -> str:
        prompt = (
            "You are a Banking Dispute Specialist at Sterling Vance Bank.\n"
            "Draft a professional, accurate response/deliverable for the following sub-task.\n"
            "Include required details such as dispute IDs, transaction amounts, regulatory citations, and customer next steps.\n\n"
            f"Task: {task}\nContext: {context}\n\nDraft:"
        )
        return self._call(prompt)

    def _run_grounded_checks(
        self, draft: str, context: Any
    ) -> tuple[list[str], EnvironmentFeedback | None]:
        """Grounded verification against real DB constraints and banking formatting rules."""
        issues: list[str] = []

        # 1. Structural & completeness checks
        if len(draft.split()) < 25:
            issues.append("Draft is under 25 words and lacks essential dispute details.")

        # 2. Dispute ID presence check
        has_disp = bool(re.search(r"DISP-\d+", draft, re.IGNORECASE))
        if not has_disp:
            issues.append("Draft omits the required formal dispute identifier (e.g. DISP-XXX).")

        # 3. Currency / amount formatting check
        has_amount = bool(re.search(r"\$\d+(?:\.\d{2})?", draft))
        if not has_amount:
            issues.append("Draft omits the monetary amount involved in the dispute.")

        # 4. Grounded DB environment evaluation
        env_feedback = None
        if self.environment:
            env_feedback = self.environment.evaluate(draft)
            if not env_feedback.success:
                issues.append(f"Grounded DB constraint failed: {env_feedback.details}")

        return issues, env_feedback

    def _critique(self, task: str, draft: str, grounded_report: str) -> str:
        prompt = (
            "You are an Independent Compliance Critic at Sterling Vance Bank.\n"
            "Evaluate the following draft against this strict rubric:\n"
            "Rubric:\n"
            "1. Correctness: Accurate dispute IDs, dollar figures, and status.\n"
            "2. Regulatory Compliance: Proper citation of dispute rights and statutory timelines (e.g. Reg E).\n"
            "3. Internal Consistency: Adherence to grounded bank constraints.\n"
            "4. Completeness & Structure: Clear headings, resolution summary, and actionable instructions.\n\n"
            f"Task: {task}\n"
            f"External Grounded Checks:\n{grounded_report}\n\n"
            f"Draft under Review:\n{draft}\n\n"
            "Instructions:\n"
            "List specific defects found. If the draft fully satisfies the rubric with no defects, respond exactly 'PASS'."
        )
        return self._call(prompt)

    def _revise(
        self, task: str, draft: str, grounded_report: str, critique: str
    ) -> str:
        prompt = (
            "You are a Banking Dispute Specialist at Sterling Vance Bank.\n"
            "Revise and improve the deliverable by resolving every item in the critique and grounded checks.\n\n"
            f"Task: {task}\n\n"
            f"Original Draft:\n{draft}\n\n"
            f"Grounded Validation Checks:\n{grounded_report}\n\n"
            f"Critic Feedback:\n{critique}\n\n"
            "Return only the revised, professional final deliverable."
        )
        return self._call(prompt)

    def _call(self, prompt: str) -> str:
        self.metrics["llm_calls"] += 1
        response = _invoke(self.llm, prompt)
        self.metrics["tokens"] += len(response.split())
        return response


def self_refine(task: str, llm: Any, environment: Environment | None = None) -> str:
    """Reference-toolkit-compatible functional interface."""
    result = SelfRefine(llm, environment=environment).execute(task)
    return result["revised"]
