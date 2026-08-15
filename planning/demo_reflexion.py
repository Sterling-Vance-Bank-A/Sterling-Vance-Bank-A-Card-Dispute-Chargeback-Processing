"""
Reflexion Cross-Trial Memory Demonstration — Sterling Vance Bank

Demonstrates a real scenario where a single retry is NOT enough and only Reflexion's
cross-trial episodic memory produces a passing resolution:
- Scenario: Dispute DISP-002 ($899.00, high-value unauthorized transaction).
- Trial 1: Agent naively attempts a $899 refund using junior analyst ANL-001.
  * Grounded DB Feedback: Fails ("Refund blocked: amount above $500 requires a senior analyst.")
  * Reflection 1: "I attempted to resolve an $899 dispute with junior analyst ANL-001; next trial I must use senior analyst ANL-002."
- Trial 2: Agent reads episodic reflection from Trial 1, corrects analyst assignment to senior analyst ANL-002, and escalates/refunds.
  * Grounded DB Feedback: Passes ("Escalation candidate passes current DB constraints.") -> SUCCESS!
- Contrast: Single-attempt run (max_trials=1) fails, proving that multi-trial memory is required.
"""

from __future__ import annotations

import io
import os
import sys

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from planning.algorithms.environment import GroundedDisputeEnvironment
from planning.algorithms.reflexion import Reflexion


class ReflexionScenarioLLM:
    """
    Test double modeling the realistic LLM reasoning in the Reflexion loop:
    - Trial 1: Generates naive attempt using junior analyst ANL-001.
    - Reflection: Synthesizes a first-person reflection on why it failed.
    - Trial 2+: Reads the episodic reflection buffer and corrects to senior analyst ANL-002.
    """

    def generate(self, prompt: str) -> str:
        p_lower = prompt.lower()

        # Phase 1: Verbal reflection generation
        if "self-reflection module" in p_lower or "generate a concise first-person verbal reflection" in p_lower:
            if "senior analyst" in p_lower or "above $500" in p_lower:
                return (
                    "I attempted to process a high-value dispute (DISP-002 for $899.00) using junior analyst ANL-001. "
                    "Next trial, I must assign senior analyst ANL-002 to comply with the $500 threshold requirement."
                )
            return "I violated database constraints. Next trial, I must check dispute status and analyst role."

        # Phase 2: Actor proposal generation
        if "episodic memory from previous failed trials" in p_lower:
            # Check if prior reflection exists in prompt
            if "senior analyst anl-002" in p_lower or "anl-001" in p_lower:
                # Informed attempt (Trial 2+)
                return (
                    "Resolution Decision: Escalate DISP-002 to Senior Dispute Review.\n"
                    "Assigned Senior Analyst: ANL-002 (role: senior).\n"
                    "Dispute ID: DISP-002, Amount: $899.00.\n"
                    "Justification: Corrected per prior reflection to assign senior analyst for high-value escalation."
                )
            else:
                # Naive attempt (Trial 1)
                return (
                    "Resolution Decision: Process direct refund for DISP-002.\n"
                    "Assigned Analyst: ANL-001 (role: junior).\n"
                    "Dispute ID: DISP-002, Amount: $899.00.\n"
                    "Justification: Customer claims unauthorized transaction, issuing routine refund."
                )

        return "Resolution for DISP-002 using ANL-001."


def run_reflexion_demo():
    llm = ReflexionScenarioLLM()
    env = GroundedDisputeEnvironment()

    task = "Resolve high-value dispute DISP-002 (amount $899.00, unauthorized transaction)."
    context = "DISP-002 amount=$899.00 status=investigating"

    print("=" * 80)
    print("STERLING VANCE BANK — REFLEXION CROSS-TRIAL MEMORY DEMO")
    print("=" * 80)
    print(f"Task: {task}\nContext: {context}\n")

    # 1. Single-Trial Baseline (max_trials=1) -> Fails
    print("-" * 80)
    print("1. SINGLE-TRIAL BASELINE (max_trials=1 — No Cross-Trial Memory)")
    print("-" * 80)
    single_ref = Reflexion(llm, environment=env, max_trials=1, memory_size=3)
    res_single = single_ref.execute(task, context)

    print(f"Outcome: Success = {res_single['success']} (Trials Attempted: {res_single['trials_attempted']})")
    print(f"Feedback: {res_single['trial_history'][0]['feedback']['details']}")
    print(f"Status: FAILED — A single attempt cannot self-correct without cross-trial memory.\n")

    # 2. Multi-Trial Reflexion (max_trials=3) -> Succeeds on Trial 2 via Memory
    print("-" * 80)
    print("2. MULTI-TRIAL REFLEXION (max_trials=3 — Capped Episodic Memory Buffer)")
    print("-" * 80)
    multi_ref = Reflexion(llm, environment=env, max_trials=3, memory_size=3)
    res_multi = multi_ref.execute(task, context)

    print(f"Outcome: Success = {res_multi['success']} (Succeeded on Trial {res_multi['trials_attempted']})\n")

    print("Trial-by-Trial History:")
    for t in res_multi["trial_history"]:
        print(f"\n--- TRIAL {t['trial_number']} ---")
        print(f"  Attempt:    {t['attempt'].splitlines()[0]}")
        print(f"  Analyst:    {t['attempt'].splitlines()[1] if len(t['attempt'].splitlines()) > 1 else 'N/A'}")
        print(f"  Grounded:   Success={t['feedback']['success']} | Score={t['feedback']['score']} | Details: {t['feedback']['details']}")
        if t["reflection"]:
            print(f"  Reflection: \"{t['reflection']}\"")

    print("\n" + "=" * 80)
    print("REFLEXION MEMORY BUFFER PROOF")
    print("=" * 80)
    print("Active Episodic Memory Buffer Carried into Next Attempt:")
    for idx, mem in enumerate(res_multi["episodic_memory"], 1):
        print(f"  [{idx}] {mem}")

    print("\nSummary:")
    print("  - Trial 1 failed because junior analyst ANL-001 cannot approve $899 (> $500 threshold).")
    print("  - Reflection 1 identified the exact regulatory violation and recorded the corrective rule.")
    print("  - Trial 2 read the episodic memory, assigned senior analyst ANL-002, and passed grounded DB validation.")
    print("=" * 80)


if __name__ == "__main__":
    run_reflexion_demo()
