"""
Planning Evaluation Test Suite — Sterling Vance Bank

Fixed set of 18 domain-specific dispute scenarios covering every required comparison:
- Decomposition-First vs. Dynamic Decomposition (cases favoring static plan vs dynamic adaptation)
- Plan-and-Solve vs. Tree of Thoughts vs. LATS
- Self-Refine vs. Reflexion
- Grounded vs. Ungrounded Environment validation

GUARDRAIL: This test suite is fixed once written and must not be altered during evaluation runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestCase:
    id: str
    category: str  # 'decomp_comparison', 'planning_algorithm', 'self_correction', 'grounding_comparison', 'general_dispute'
    task_family: str  # 'linear', 'ranking', 'high_stakes', 'dynamic_divergence', 'iterative_refine', 'multi_trial_memory'
    description: str
    context: dict[str, Any]
    expected_favorable_method: str
    expected_outcome: str
    grounded_eval_rule: str
    metadata: dict[str, Any] = field(default_factory=dict)


def get_test_suite() -> list[TestCase]:
    """Returns the complete, fixed 18-case evaluation suite."""
    return [
        # -----------------------------------------------------------------------------------------
        # Category 1: Decomposition Comparison (Decomposition-First vs. Dynamic Decomposition)
        # -----------------------------------------------------------------------------------------
        TestCase(
            id="TC-D01",
            category="decomp_comparison",
            task_family="linear",
            description="Remediate routine low-value duplicate charge dispute DISP-001 ($29.99).",
            context={"dispute_id": "DISP-001", "amount": 29.99, "status": "open", "analyst_id": "ANL-001"},
            expected_favorable_method="decomposition_first",
            expected_outcome="Linear 3-step plan executes cleanly; dynamic re-evaluation adds unnecessary LLM turns/tokens.",
            grounded_eval_rule="amount <= 500 and status == 'open'",
            metadata={"favors": "decomposition_first", "reason": "Zero ambiguity, no intermediate surprises, lower token cost"},
        ),
        TestCase(
            id="TC-D02",
            category="decomp_comparison",
            task_family="dynamic_divergence",
            description="Remediate dispute DISP-003 ($150.00) claiming duplicate charge.",
            context={"dispute_id": "DISP-003", "amount": 150.00, "status": "refunded", "analyst_id": "ANL-001"},
            expected_favorable_method="dynamic_decomposition",
            expected_outcome="Dynamic observes terminal 'refunded' status at step 1 and pivots to audit closure; Decomp-First attempts illegal refund.",
            grounded_eval_rule="status == 'refunded' blocks refund attempts",
            metadata={"favors": "dynamic_decomposition", "reason": "Early terminal status requires immediate plan course change"},
        ),
        TestCase(
            id="TC-D03",
            category="decomp_comparison",
            task_family="dynamic_divergence",
            description="Process merchant remediation for DISP-005 ($200.00) with missing merchant reserve escrow.",
            context={"dispute_id": "DISP-005", "amount": 200.00, "status": "denied", "merchant_status": "reserve_exhausted"},
            expected_favorable_method="dynamic_decomposition",
            expected_outcome="Dynamic observes missing merchant escrow and pivots from direct debit to network arbitration.",
            grounded_eval_rule="status == 'denied' blocks direct debit",
            metadata={"favors": "dynamic_decomposition", "reason": "Merchant escrow failure requires dynamic escalation pivot"},
        ),

        # -----------------------------------------------------------------------------------------
        # Category 2: Planning Algorithms (Plan-and-Solve vs. Tree-of-Thoughts vs. LATS)
        # -----------------------------------------------------------------------------------------
        TestCase(
            id="TC-P01",
            category="planning_algorithm",
            task_family="linear",
            description="Summarize dispute timeline and statutory deadlines for DISP-002 ($899.00).",
            context={"dispute_id": "DISP-002", "amount": 899.00, "reason": "unauthorized_transaction"},
            expected_favorable_method="plan_and_solve",
            expected_outcome="Explicit PLAN and SOLUTION generated in a single pass with minimal token overhead.",
            grounded_eval_rule="deterministic timeline extraction",
            metadata={"subtask_type": "timeline_generation"},
        ),
        TestCase(
            id="TC-P02",
            category="planning_algorithm",
            task_family="linear",
            description="Calculate total monetary exposure and card network interchange fee impact for DISP-006 ($320.00).",
            context={"dispute_id": "DISP-006", "amount": 320.00, "reason": "fraud"},
            expected_favorable_method="plan_and_solve",
            expected_outcome="Deterministic fee arithmetic executed in one pass without branching.",
            grounded_eval_rule="accurate exposure calculation",
            metadata={"subtask_type": "fee_calculation"},
        ),
        TestCase(
            id="TC-P03",
            category="planning_algorithm",
            task_family="ranking",
            description="Rank 3 competing merchant recovery queues by filing deadline, merchant risk score, and recovery probability.",
            context={"queues": "MERCH-A deadline=2d risk=60 recovery=.70; MERCH-B deadline=5d risk=90 recovery=.60; MERCH-C deadline=1d risk=30 recovery=.80"},
            expected_favorable_method="tree_of_thoughts",
            expected_outcome="ToT beam search explores candidate priority orderings (MERCH-C -> MERCH-A -> MERCH-B) and prunes sub-optimal paths.",
            grounded_eval_rule="optimal priority sequence selection",
            metadata={"subtask_type": "rank_recovery"},
        ),
        TestCase(
            id="TC-P04",
            category="planning_algorithm",
            task_family="ranking",
            description="Sort 5 high-value chargeback disputes by urgency balancing statutory Reg E deadline and dollar amount.",
            context={"disputes": "D1(1d, $120), D2(3d, $900), D3(2d, $450), D4(1d, $700), D5(7d, $150)"},
            expected_favorable_method="tree_of_thoughts",
            expected_outcome="ToT explores candidate sequences and evaluates score to return D1 -> D4 -> D3 -> D2 -> D5.",
            grounded_eval_rule="balanced multi-criteria dispute sorting",
            metadata={"subtask_type": "sort_priority"},
        ),
        TestCase(
            id="TC-P05",
            category="planning_algorithm",
            task_family="ranking",
            description="Evaluate multi-merchant portfolio risk ranking across MERCH-001 through MERCH-004.",
            context={"merchants": "MERCH-004(risk=92, cb=14), MERCH-002(risk=75, cb=8), MERCH-001(risk=35, cb=2), MERCH-003(risk=50, cb=4)"},
            expected_favorable_method="tree_of_thoughts",
            expected_outcome="ToT correctly ranks highest risk concentration to lowest: MERCH-004 -> MERCH-002 -> MERCH-003 -> MERCH-001.",
            grounded_eval_rule="risk score and chargeback ratio ordering",
            metadata={"subtask_type": "rank_risk"},
        ),
        TestCase(
            id="TC-P06",
            category="planning_algorithm",
            task_family="high_stakes",
            description="Evaluate and commit refund for routine dispute DISP-001 ($29.99) assigned to junior analyst ANL-001.",
            context={"dispute_id": "DISP-001", "amount": 29.99, "status": "open", "analyst_id": "ANL-001"},
            expected_favorable_method="lats",
            expected_outcome="LATS MCTS confirms junior analyst eligibility for amount <= $500, verifies DB state, and commits refund.",
            grounded_eval_rule="amount <= 500 and role in ['junior', 'senior']",
            metadata={"subtask_type": "process_refund"},
        ),
        TestCase(
            id="TC-P07",
            category="planning_algorithm",
            task_family="high_stakes",
            description="Evaluate high-value refund for DISP-013 ($1,337.92) assigned to senior analyst ANL-008.",
            context={"dispute_id": "DISP-013", "amount": 1337.92, "status": "investigating", "analyst_id": "ANL-008"},
            expected_favorable_method="lats",
            expected_outcome="LATS verifies senior analyst role, confirms amount > $1000 requires Section 3/9 sign-off, and validates in DB.",
            grounded_eval_rule="amount > 1000 and role == 'senior'",
            metadata={"subtask_type": "process_refund"},
        ),

        # -----------------------------------------------------------------------------------------
        # Category 3: Self-Correction (Self-Refine vs. Reflexion)
        # -----------------------------------------------------------------------------------------
        TestCase(
            id="TC-S01",
            category="self_correction",
            task_family="iterative_refine",
            description="Draft customer Regulation E provisional credit notification letter for DISP-001 ($29.99).",
            context={"dispute_id": "DISP-001", "amount": 29.99, "status": "open"},
            expected_favorable_method="self_refine",
            expected_outcome="Draft is critiqued against compliance rubric for required statutory language; refined in single revision pass.",
            grounded_eval_rule="contains dispute_id, dollar amount, and statutory disclosure",
            metadata={"favors": "self_refine", "reason": "Cheap-to-redo document formatting; 1 revision suffices"},
        ),
        TestCase(
            id="TC-S02",
            category="self_correction",
            task_family="iterative_refine",
            description="Draft formal merchant chargeback rebuttal filing for high-risk merchant MERCH-004.",
            context={"merchant_id": "MERCH-004", "dispute_id": "DISP-002", "amount": 899.00},
            expected_favorable_method="self_refine",
            expected_outcome="Draft is critiqued against evidence completeness rubric and revised with clear transaction chronology.",
            grounded_eval_rule="contains merchant_id, evidence items, and structured headings",
            metadata={"favors": "self_refine", "reason": "Document restructuring resolved in single critique-revision loop"},
        ),
        TestCase(
            id="TC-S03",
            category="self_correction",
            task_family="multi_trial_memory",
            description="Resolve high-value dispute DISP-002 ($899.00 unauthorized transaction) where initial attempt uses junior analyst.",
            context={"dispute_id": "DISP-002", "amount": 899.00, "status": "investigating"},
            expected_favorable_method="reflexion",
            expected_outcome="Trial 1 (junior analyst) fails grounded DB check; verbal reflection carries lesson; Trial 2 assigns senior analyst ANL-002 and succeeds.",
            grounded_eval_rule="amount > 500 requires senior analyst",
            metadata={"favors": "reflexion", "reason": "Single retry fails; requires multi-trial verbal memory to correct analyst assignment"},
        ),
        TestCase(
            id="TC-S04",
            category="self_correction",
            task_family="multi_trial_memory",
            description="Resolve compound fraud dispute DISP-014 ($370.78) where trial 1 attempts re-escalation and trial 2 attempts refund on escalated state.",
            context={"dispute_id": "DISP-014", "amount": 370.78, "status": "escalated"},
            expected_favorable_method="reflexion",
            expected_outcome="Trial 1 (re-escalate) fails; Trial 2 (refund) fails; Reflection buffer guides Trial 3 to network status inquiry and succeeds.",
            grounded_eval_rule="status == 'escalated' permits inquiry but blocks direct refund/re-escalate",
            metadata={"favors": "reflexion", "reason": "Multi-constraint state requires multiple trial reflections to reach valid action"},
        ),

        # -----------------------------------------------------------------------------------------
        # Category 4: Grounded vs. Ungrounded Validation
        # -----------------------------------------------------------------------------------------
        TestCase(
            id="TC-G01",
            category="grounding_comparison",
            task_family="high_stakes",
            description="Evaluate refund request for DISP-003 ($150.00), currently in 'refunded' terminal status.",
            context={"dispute_id": "DISP-003", "amount": 150.00, "status": "refunded"},
            expected_favorable_method="grounded_lats",
            expected_outcome="Ungrounded LATS self-approves duplicate refund (violation); Grounded LATS blocks illegal action using live DB status.",
            grounded_eval_rule="status in ['refunded', 'denied'] must return score=0.0 and success=False",
            metadata={"contrast": "ungrounded_vs_grounded"},
        ),
        TestCase(
            id="TC-G02",
            category="grounding_comparison",
            task_family="high_stakes",
            description="Evaluate escalation request for DISP-014 ($370.78), currently in 'escalated' terminal status.",
            context={"dispute_id": "DISP-014", "amount": 370.78, "status": "escalated"},
            expected_favorable_method="grounded_lats",
            expected_outcome="Ungrounded LATS self-approves re-escalation; Grounded LATS blocks action citing terminal status.",
            grounded_eval_rule="status in ['refunded', 'denied', 'escalated'] blocks re-escalation",
            metadata={"contrast": "ungrounded_vs_grounded"},
        ),

        # -----------------------------------------------------------------------------------------
        # Category 5: General Ordinary Banking Dispute Scenarios
        # -----------------------------------------------------------------------------------------
        TestCase(
            id="TC-O01",
            category="general_dispute",
            task_family="linear",
            description="Aggregate transaction history and dispute evidence for DISP-004 ($75.00 item not received).",
            context={"dispute_id": "DISP-004", "amount": 75.00, "reason": "item_not_received"},
            expected_favorable_method="plan_and_solve",
            expected_outcome="Evidence aggregated and summarized into structured output.",
            grounded_eval_rule="dispute exists in database",
            metadata={"subtask_type": "evidence_aggregation"},
        ),
        TestCase(
            id="TC-O02",
            category="general_dispute",
            task_family="high_stakes",
            description="Execute senior analyst review and resolution for DISP-009 ($793.78 unauthorized transaction).",
            context={"dispute_id": "DISP-009", "amount": 793.78, "status": "investigating", "analyst_id": "ANL-002"},
            expected_favorable_method="lats",
            expected_outcome="Senior analyst ANL-002 validated against DB and resolution committed.",
            grounded_eval_rule="amount > 500 and role == 'senior'",
            metadata={"subtask_type": "process_refund"},
        ),
    ]


def get_cases_by_category(category: str) -> list[TestCase]:
    """Filter test cases by category."""
    return [c for c in get_test_suite() if c.category == category]
