from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .environment import Environment, EnvironmentFeedback, GroundedDisputeEnvironment
from .plan_and_solve import _invoke

logger = logging.getLogger(__name__)


@dataclass
class ReflexionTrial:
    number: int
    attempt: str
    feedback: EnvironmentFeedback
    reflection: str | None = None


@dataclass
class ReflexionResult:
    success: bool
    output: str
    trials: list[ReflexionTrial] = field(default_factory=list)
    memory: list[str] = field(default_factory=list)
    metrics: dict[str, int] = field(default_factory=dict)


class Reflexion:
    """
    Reflexion Algorithm adapted from reference toolkit (Shinn et al., 2023).

    A multi-trial self-correction architecture with a capped episodic buffer of verbal
    reflections carried across failed attempts within the same task run.

    Loop:
      1. Actor Attempt: Formulate complete dispute remediation action, incorporating
         all accumulated verbal reflections from prior failed trials.
      2. Grounded Evaluation: Evaluate candidate against real external database constraints
         using GroundedDisputeEnvironment.
      3. Success Check: If grounded feedback passes, return immediate success.
      4. Verbal Reflection: If feedback fails, generate a first-person verbal reflection
         explaining the root defect and the specific corrective strategy for the next attempt.
      5. Episodic Buffer: Append reflection to the capped memory buffer (size=3) and retry.
    """

    def __init__(
        self,
        llm_client: Any,
        environment: Environment | None = None,
        max_trials: int = 3,
        memory_size: int = 3,
    ):
        if max_trials < 1 or memory_size < 1:
            raise ValueError("max_trials and memory_size must be positive integers")
        self.llm = llm_client
        self.environment = environment or GroundedDisputeEnvironment()
        self.max_trials = max_trials
        self.memory_size = memory_size
        self.metrics = {"llm_calls": 0, "tokens": 0}

    def execute(self, task_description: str, context: Any = None) -> dict:
        """Execute multi-trial Reflexion loop with episodic verbal memory."""
        self.metrics = {"llm_calls": 0, "tokens": 0}
        memory: list[str] = []
        trials: list[ReflexionTrial] = []
        best_attempt = ""
        best_score = -1.0
        best_feedback: EnvironmentFeedback | None = None

        for trial_num in range(1, self.max_trials + 1):
            # Step 1: Format episodic memory from previous failed trials
            active_memory = memory[-self.memory_size:]
            recalled_context = (
                "\n".join(f"- {item}" for item in active_memory)
                if active_memory
                else "- No prior trial failures recorded."
            )

            # Step 2: Actor Attempt incorporating verbal memories
            attempt = self._generate_attempt(task_description, context, recalled_context)

            # Step 3: Grounded Evaluation via real SQLite DB / validator
            feedback = self.environment.evaluate(attempt)
            trial = ReflexionTrial(number=trial_num, attempt=attempt, feedback=feedback)

            if feedback.score > best_score:
                best_attempt = attempt
                best_score = feedback.score
                best_feedback = feedback

            # Step 4: Early Termination on Success
            if feedback.success:
                trials.append(trial)
                logger.info("Reflexion succeeded on trial %d for task: %s", trial_num, task_description[:40])
                return self._build_result(
                    success=True,
                    output=attempt,
                    trials=trials,
                    memory=memory[-self.memory_size:],
                    trial_count=trial_num,
                )

            # Step 5: Generate Verbal Reflection on Failure
            reflection = self._reflect(task_description, attempt, feedback, trial_num)
            trial.reflection = reflection
            trials.append(trial)
            memory.append(reflection)
            logger.info("Reflexion trial %d failed (%s). Generated reflection: %s", trial_num, feedback.details, reflection[:60])

        logger.warning("Reflexion exhausted %d trials without passing grounded constraints.", self.max_trials)
        return self._build_result(
            success=False,
            output=best_attempt,
            trials=trials,
            memory=memory[-self.memory_size:],
            trial_count=self.max_trials,
        )

    def _generate_attempt(self, task: str, context: Any, recalled_memories: str) -> str:
        prompt = (
            "You are a Banking Dispute Resolution Agent at Sterling Vance Bank.\n"
            "Formulate a complete, concrete resolution action for the following dispute task.\n"
            "Specify the exact action (e.g. refund, escalate), dispute ID (DISP-XXX), analyst ID (ANL-XXX), and justification.\n\n"
            f"Task: {task}\n"
            f"Dispute Context: {context}\n\n"
            "Episodic memory from previous failed trials in this run:\n"
            f"{recalled_memories}\n\n"
            "Instructions:\n"
            "Apply the lessons from your prior failed trials to avoid repeating bank policy violations. "
            "Return the complete dispute resolution decision."
        )
        return self._call(prompt)

    def _reflect(
        self, task: str, attempt: str, feedback: EnvironmentFeedback, trial_num: int
    ) -> str:
        prompt = (
            "You are the Self-Reflection Module of an autonomous banking agent.\n"
            f"Trial {trial_num} of the following task failed external bank validation:\n"
            f"Task: {task}\n"
            f"Failed Proposal: {attempt}\n"
            f"External Grounded Validator Feedback (Score {feedback.score}): {feedback.details}\n\n"
            "Generate a concise first-person verbal reflection stating what constraint was violated and "
            "the specific corrective rule to apply on the next trial. Start your sentence with 'I'."
        )
        return self._call(prompt)

    def _call(self, prompt: str) -> str:
        self.metrics["llm_calls"] += 1
        response = _invoke(self.llm, prompt)
        self.metrics["tokens"] += len(response.split())
        return response

    def _build_result(
        self,
        success: bool,
        output: str,
        trials: list[ReflexionTrial],
        memory: list[str],
        trial_count: int,
    ) -> dict:
        return {
            "status": "success" if success else "failed",
            "method": "reflexion",
            "success": success,
            "final_output": output,
            "trials_attempted": trial_count,
            "episodic_memory": memory,
            "trial_history": [
                {
                    "trial_number": t.number,
                    "attempt": t.attempt,
                    "feedback": t.feedback.__dict__ if t.feedback else None,
                    "reflection": t.reflection,
                }
                for t in trials
            ],
            "metrics": self.metrics.copy(),
        }


def reflexion(
    task: str,
    llm: Any,
    environment: Environment | None = None,
    max_trials: int = 3,
    memory_size: int = 3,
) -> ReflexionResult:
    """Reference-toolkit-compatible functional interface."""
    res_dict = Reflexion(
        llm, environment=environment, max_trials=max_trials, memory_size=memory_size
    ).execute(task)
    trials = [
        ReflexionTrial(
            number=t["trial_number"],
            attempt=t["attempt"],
            feedback=EnvironmentFeedback(**t["feedback"]) if t["feedback"] else None,
            reflection=t["reflection"],
        )
        for t in res_dict["trial_history"]
    ]
    return ReflexionResult(
        success=res_dict["success"],
        output=res_dict["final_output"],
        trials=trials,
        memory=res_dict["episodic_memory"],
    )
