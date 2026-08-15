"""
Grounded vs. Ungrounded Environment Demonstration — Sterling Vance Bank

Demonstrates the critical difference between ungrounded model self-evaluation
and grounded external database validation:
- Scenario: An analyst agent attempts to issue a refund on dispute DISP-003 ($150.00),
  which is already in terminal status (status='refunded' in sterling_vance.db).
- UngroundedEnvironment (Toolkit Default):
  Model self-approves the illegal action (score=1.0, success=True), causing a duplicate payout!
- GroundedDisputeEnvironment (Sterling Vance SQLite Validator):
  Directly inspects the live database, catches the terminal state violation, and blocks
  the illegal refund (score=0.0, success=False).
- Independent Critic Comparison:
  Contrasts lenient same-model self-critique with a strict independent compliance persona.
"""

from __future__ import annotations

import io
import os
import sys

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from planning.algorithms.environment import GroundedDisputeEnvironment, UngroundedEnvironment
from planning.algorithms.lats import LATS
from planning.benchmark import MockLLMClient


class FlawedRefundLLM:
    """Simulates an LLM proposing a plausible-sounding but illegal refund."""

    def generate(self, prompt: str) -> str:
        p = prompt.lower()
        if "generate candidate actions" in p or "lats action generator" in p:
            return (
                "Refund DISP-003 using ANL-002\n"
                "Refund DISP-003 using ANL-001\n"
                "Verify transaction DISP-003"
            )
        if "estimate future usefulness" in p:
            return "0.95"
        if "create a brief branch reflection" in p:
            return "Action failed external validation; must avoid terminal state conflicts."
        return "0.50"


def run_grounding_demo():
    llm = FlawedRefundLLM()
    task = "Evaluate and execute refund for dispute DISP-003 ($150.00 duplicate charge)."
    context = "DISP-003 amount=$150.00 customer=CUST-003"

    print("=" * 80)
    print("STERLING VANCE BANK — GROUNDED VS UNGROUNDED ENVIRONMENT DEMO")
    print("=" * 80)
    print(f"Task: {task}")
    print(f"Target Dispute: DISP-003 (Live DB Status: 'refunded' — Terminal State)\n")

    # 1. Ungrounded LATS Execution
    print("-" * 80)
    print("1. UNGROUNDED LATS (Toolkit Default — Model Self-Approves)")
    print("-" * 80)
    ungrounded_env = UngroundedEnvironment()
    lats_ungrounded = LATS(llm, max_iterations=2, environment=ungrounded_env, n_actions=2)
    res_ungrounded = lats_ungrounded.execute(task, context)

    print(f"Status:            {res_ungrounded['status']}")
    print(f"Best Action:        {res_ungrounded['best_action']}")
    print(f"Approved Proposal:  {res_ungrounded['final_state']}")
    print(f"Validator Score:    {res_ungrounded['environment_feedback']['score']}")
    print(f"Validator Details:  {res_ungrounded['environment_feedback']['details']}")
    print(f"Outcome Assessment: ❌ APPROVED ILLEGAL ACTION (Duplicate Payout / Compliance Violation)\n")

    # 2. Grounded LATS Execution
    print("-" * 80)
    print("2. GROUNDED LATS (Sterling Vance — Live SQLite Database Validation)")
    print("-" * 80)
    grounded_env = GroundedDisputeEnvironment()
    lats_grounded = LATS(llm, max_iterations=2, environment=grounded_env, n_actions=2)
    res_grounded = lats_grounded.execute(task, context)

    print(f"Status:            {res_grounded['status']}")
    print(f"Best Action:        {res_grounded['best_action']}")
    print(f"Target Proposal:    {res_grounded['final_state']}")
    print(f"Validator Score:    {res_grounded['environment_feedback']['score']}")
    print(f"Validator Details:  {res_grounded['environment_feedback']['details']}")
    print(f"Outcome Assessment: ✅ BLOCKED ILLEGAL ACTION (Caught Terminal Status 'refunded' in DB)\n")

    # 3. Side-by-Side Comparison Table
    print("=" * 80)
    print("SIDE-BY-SIDE GROUNDING CONTRAST")
    print("=" * 80)
    print(f"{'Evaluation Dimension':<25} | {'Ungrounded LATS':<25} | {'Grounded LATS (Sterling Vance)':<25}")
    print("-" * 80)
    print(f"{'Source of Truth':<25} | {'Model Opinion (Self-Approval)':<25} | {'db/sterling_vance.db (SQLite)':<25}")
    print(f"{'Feedback Score':<25} | {res_ungrounded['environment_feedback']['score']:<25} | {res_grounded['environment_feedback']['score']:<25}")
    print(f"{'Dispute DISP-003 Action':<25} | {'APPROVED (Duplicate Payout)':<25} | {'BLOCKED (Already Refunded)':<25}")
    print(f"{'Regulatory Compliance':<25} | {'VIOLATION':<25} | {'COMPLIANT':<25}")
    print("=" * 80)

    # 4. Independent Critic Test
    print("\n" + "-" * 80)
    print("3. INDEPENDENT CRITIC VS SELF-CRITIQUE TEST")
    print("-" * 80)
    draft_proposal = "Issue $899.00 instant refund for DISP-002 signed by Junior Analyst ANL-001."

    # Same-model self-critique (lenient)
    self_eval = "Self-Critique: The proposal is clear and quickly resolves the customer dispute. PASS."
    # Independent compliance critic (strict audit persona)
    independent_critic_eval = (
        "Independent Compliance Critic: REJECT. DISP-002 is $899.00, which exceeds the $500 threshold. "
        "Under Section 3.1 & 3.2, junior analyst ANL-001 lacks authorization; senior analyst review is mandatory."
    )

    print(f"Candidate Proposal: \"{draft_proposal}\"")
    print(f"  - Same-Model Self-Critique:     \"{self_eval}\"")
    print(f"  - Independent Compliance Critic: \"{independent_critic_eval}\"")
    print("Conclusion: Independent critic persona catches compliance threshold violations that naive self-critique misses.")
    print("=" * 80)


if __name__ == "__main__":
    run_grounding_demo()
