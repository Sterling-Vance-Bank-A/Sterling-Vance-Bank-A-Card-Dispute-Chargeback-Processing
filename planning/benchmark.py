from __future__ import annotations

import json
import os
import re
import time
from statistics import mean

from planning.algorithms.environment import GroundedDisputeEnvironment, UngroundedEnvironment
from planning.algorithms.lats import LATS
from planning.algorithms.plan_and_solve import PlanAndSolve
from planning.algorithms.tree_of_thoughts import TreeOfThoughts

ARTIFACTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts")
COST_PER_1K_TOKENS = 0.01


class MockLLMClient:
    """Deterministic test double used only for reproducible local validation."""

    def generate(self, prompt: str) -> str:
        p = prompt.lower()
        case_match = re.search(r"pb(\d{2})", p)
        case_id = int(case_match.group(1)) if case_match else None

        if "plan-and-solve planner" in p:
            return "PLAN\n1. Identify the dispute and constraints.\n2. Summarize evidence and compute exposure.\nSOLUTION\nDispute summary prepared with constraints checked."

        if "generate distinct candidate next steps" in p:
            if "merch-" in p or "queue" in p:
                return "1. MERCH-C (1d, risk=30, recovery=.80) -> MERCH-A (2d, risk=60, recovery=.70) -> MERCH-B (5d, risk=90, recovery=.60)\n2. MERCH-A (2d) -> MERCH-C (1d) -> MERCH-B (5d)"
            if "d1" in p or "d2" in p or "urgency" in p:
                return "1. D1 (1d, $120) -> D4 (1d, $700) -> D3 (2d, $450) -> D2 (3d, $900) -> D5 (7d, $150)\n2. D4 (1d) -> D1 (1d) -> D3 (2d) -> D2 (3d) -> D5 (7d)"
            if "portfolio" in p or "risk concentration" in p:
                return "1. MERCH-004 (risk=92) -> MERCH-002 (risk=75) -> MERCH-003 (risk=50) -> MERCH-001 (risk=35)\n2. MERCH-002 -> MERCH-004 -> MERCH-003 -> MERCH-001"
            return "1. Option A: Prioritize by statutory deadline\n2. Option B: Prioritize by dollar exposure"

        if "evaluate this tree-of-thoughts candidate" in p:
            if any(opt in p for opt in ("merch-c (1d", "d1 (1d", "merch-004 (risk=92", "statutory deadline")):
                return "SCORE 0.95 | RATIONALE Optimal sequence balancing statutory timeline and recovery likelihood."
            return "SCORE 0.40 | RATIONALE Sub-optimal ordering."

        if "generate candidate actions" in p or "lats action generator" in p:
            dispute = re.search(r"disp-\d+", p)
            analyst = re.search(r"anl-\d+", p)
            dispute_id = dispute.group(0).upper() if dispute else "DISP-001"
            analyst_id = analyst.group(0).upper() if analyst else "ANL-002"
            if ("escalat" in p and "refund or escalat" not in p and "refund or escalation" not in p) or "disp-002" in p or "disp-014" in p:
                esc_analyst = analyst_id if analyst_id in ("ANL-002", "ANL-008") else "ANL-002"
                return f"Escalate {dispute_id} using {esc_analyst}\nEscalate {dispute_id} using {esc_analyst}\nEscalate {dispute_id} using {esc_analyst}"
            return f"Refund {dispute_id} using {analyst_id}\nRefund {dispute_id} using {analyst_id}\nRefund {dispute_id} using {analyst_id}"

        # Self-Refine generation, critique, and refinement
        if "independent compliance critic" in p or "evaluate the following draft" in p:
            return (
                "CRITIQUE:\n"
                "1. The draft omits the formal dispute reference identifier (DISP-001).\n"
                "2. The draft omits the exact disputed amount ($29.99).\n"
                "3. Regulation E § 1005.11 requires explicit notice that the cardholder may request documentation copies.\n"
                "REVISION REQUIRED: State DISP-001, specify $29.99, and include the statutory document request disclosure."
            )
        if "banking dispute specialist" in p or "revise and improve the deliverable" in p or "critic feedback:" in p:
            return (
                "Formal Dispute Resolution Notice — Sterling Vance Bank\n\n"
                "Dear Cardholder,\n\n"
                "Re: Dispute Reference DISP-001 ($29.99 - Duplicate Charge)\n"
                "We have completed our investigation into transaction TXN-002 ($29.99). In accordance with Regulation E "
                "(12 CFR § 1005.11), a permanent credit of $29.99 has been posted to your account. You have the right to request "
                "copies of all documents and evidence relied upon in making this determination.\n\n"
                "Sincerely,\nSterling Vance Bank Dispute Operations"
            )
        if "compliance drafting assistant" in p or "draft a formal customer" in p or "draft formal customer" in p or "notification_draft" in p:
            return "Customer Notice: Your recent duplicate transaction has been reviewed and a provisional adjustment was posted. Contact customer service for details."

        if "estimate future usefulness" in p:
            return "0.90"
        if "create a brief branch reflection" in p:
            return "Validator rejected this branch; the next expansion should avoid the same policy violation or terminal-state conflict."
        return "0.50"


def fixed_cases() -> list[dict]:
    return [
        {"id": "PB01", "family": "linear", "type": "evidence_aggregation", "description": "Summarize evidence for DISP-001 and compute dispute exposure.", "context": "DISP-001 amount=$29.99 reason=duplicate_charge", "expected": "PLAN and SOLUTION"},
        {"id": "PB02", "family": "linear", "type": "timeline_generation", "description": "Build a concise dispute timeline for DISP-002.", "context": "DISP-002 status=investigating amount=$899", "expected": "PLAN and SOLUTION"},
        {"id": "PB03", "family": "linear", "type": "fee_calculation", "description": "Calculate the monetary exposure for DISP-006.", "context": "DISP-006 amount=$320 reason=fraud", "expected": "PLAN and SOLUTION"},
        {"id": "PB04", "family": "linear", "type": "notification_draft", "description": "Draft a customer notification for DISP-009.", "context": "DISP-009 amount=$793.78 status=investigating", "expected": "PLAN and SOLUTION"},
        {"id": "PB05", "family": "linear", "type": "evidence_aggregation", "description": "Summarize evidence and constraints for DISP-013.", "context": "DISP-013 amount=$1337.92 reason=duplicate_charge", "expected": "PLAN and SOLUTION"},
        {"id": "PB06", "family": "ranking", "type": "rank_recovery", "description": "Rank these dispute priorities by filing deadline, merchant risk, and recoverability. PB06", "context": "M-A deadline=2d risk=60 recovery=.70; M-B deadline=5d risk=90 recovery=.60; M-C deadline=1d risk=30 recovery=.80", "expected": "M-C -> M-A -> M-B"},
        {"id": "PB07", "family": "ranking", "type": "sort_priority", "description": "Sort five disputes by urgency while balancing deadline and amount. PB07", "context": "D1 deadline=1d amount=120; D2 deadline=3d amount=900; D3 deadline=2d amount=450; D4 deadline=1d amount=700; D5 deadline=7d amount=150", "expected": "D1 -> D4 -> D3 -> D2 -> D5"},
        {"id": "PB08", "family": "ranking", "type": "rank_risk", "description": "Rank multi-merchant chargeback risk from highest to lowest. PB08", "context": "MERCH-A risk=88 history=12; MERCH-B risk=41 history=4; MERCH-C risk=72 history=9; MERCH-D risk=15 history=1", "expected": "MERCH-A -> MERCH-C -> MERCH-B -> MERCH-D"},
        {"id": "PB09", "family": "ranking", "type": "rank_recovery", "description": "Choose the best recovery-first ordering across three transactions. PB09", "context": "TX-A recovery=.82 deadline=4d; TX-B recovery=.61 deadline=1d; TX-C recovery=.76 deadline=2d", "expected": "TX-A -> TX-C -> TX-B"},
        {"id": "PB10", "family": "ranking", "type": "sort_priority", "description": "Prioritize a mixed portfolio of high-risk and time-sensitive disputes. PB10", "context": "P1 risk=95 deadline=5d; P2 risk=40 deadline=1d; P3 risk=70 deadline=2d; P4 risk=50 deadline=3d", "expected": "P1 -> P3 -> P4 -> P2"},
        {"id": "PB11", "family": "high_stakes", "type": "process_refund", "description": "Evaluate a refund candidate for DISP-001 using analyst ANL-001. PB11", "context": "DISP-001 amount=29.99 status=open analyst=ANL-001", "expected": True},
        {"id": "PB12", "family": "high_stakes", "type": "process_refund", "description": "Evaluate a high-value refund for DISP-002 using junior analyst ANL-001. PB12", "context": "DISP-002 amount=899 status=investigating junior analyst=ANL-001", "expected": False},
        {"id": "PB13", "family": "high_stakes", "type": "process_refund", "description": "Evaluate a refund for DISP-003, which is already refunded. PB13", "context": "DISP-003 amount=150 status=refunded analyst=ANL-002", "expected": False},
        {"id": "PB14", "family": "high_stakes", "type": "escalate_dispute", "description": "Evaluate escalation of DISP-014; it is already escalated. PB14", "context": "DISP-014 amount=370.78 status=escalated analyst=ANL-002", "expected": False},
        {"id": "PB15", "family": "high_stakes", "type": "process_refund", "description": "Evaluate a high-value refund for DISP-013 using senior analyst ANL-008. PB15", "context": "DISP-013 amount=1337.92 status=investigating senior analyst=ANL-008", "expected": True},
    ]


def _cost(tokens: int) -> float:
    return round(tokens / 1000.0 * COST_PER_1K_TOKENS, 6)


def _run(strategy: str, case: dict, llm: MockLLMClient) -> tuple[dict, float]:
    start = time.perf_counter()
    task = f"{case['description']} {case['id']}"
    if strategy == "plan_and_solve":
        result = PlanAndSolve(llm).execute(task, case["context"])
    elif strategy == "tree_of_thoughts":
        result = TreeOfThoughts(llm, beam_width=3, max_depth=2).execute(task, case["context"])
    elif strategy == "lats_ungrounded":
        result = LATS(llm, max_iterations=2, environment=UngroundedEnvironment()).execute(task, case["context"])
    elif strategy == "lats_grounded":
        result = LATS(llm, max_iterations=2, environment=GroundedDisputeEnvironment()).execute(task, case["context"])
    else:
        raise ValueError(strategy)
    return result, time.perf_counter() - start


def _success(strategy: str, case: dict, result: dict) -> tuple[bool, str]:
    if case["family"] == "linear":
        if strategy != "plan_and_solve":
            return False, "not the production method for this sub-task shape"
        text = result.get("final_result", "")
        return ("PLAN" in text and "SOLUTION" in text), "explicit PLAN/SOLUTION output"

    if case["family"] == "ranking":
        if strategy != "tree_of_thoughts":
            return False, "not the production method for this sub-task shape"
        best = (result.get("best_path") or {}).get("state", "")
        return case["expected"].lower() in best.lower(), "expected priority ordering present in best beam"

    # High-stakes expected value is not simply "success": it is whether the method
    # makes the correct safe/blocked decision according to the external validator.
    if not strategy.startswith("lats"):
        return False, "not a search method for high-stakes commits"
    observed = bool((result.get("environment_feedback") or {}).get("success"))
    return observed == bool(case["expected"]), "decision matches expected grounded policy outcome"


def run_benchmark() -> dict:
    os.makedirs(ARTIFACTS, exist_ok=True)
    llm = MockLLMClient()
    cases = fixed_cases()
    strategies = ["plan_and_solve", "tree_of_thoughts", "lats_ungrounded", "lats_grounded"]
    records: list[dict] = []

    for case in cases:
        for strategy in strategies:
            result, latency = _run(strategy, case, llm)
            passed, basis = _success(strategy, case, result)
            metrics = result.get("metrics", {})
            row = {
                "case_id": case["id"],
                "family": case["family"],
                "strategy": strategy,
                "applicable": ((case["family"] == "linear" and strategy == "plan_and_solve") or
                               (case["family"] == "ranking" and strategy == "tree_of_thoughts") or
                               (case["family"] == "high_stakes" and strategy.startswith("lats"))),
                "success": bool(passed),
                "success_basis": basis,
                "llm_calls": int(metrics.get("llm_calls", 0)),
                "tokens": int(metrics.get("tokens", 0)),
                "latency_seconds": round(latency, 6),
                "estimated_cost_usd": _cost(int(metrics.get("tokens", 0))),
                "result": result,
            }
            records.append(row)
            with open(os.path.join(ARTIFACTS, f"trace_{case['id'].lower()}_{strategy}.json"), "w", encoding="utf-8") as fh:
                json.dump(row, fh, indent=2)

    summary = []
    for strategy in strategies:
        rows = [r for r in records if r["strategy"] == strategy and r["applicable"]]
        summary.append({
            "strategy": strategy,
            "applicable_cases": len(rows),
            "successes": sum(r["success"] for r in rows),
            "success_rate": round(sum(r["success"] for r in rows) / len(rows), 3) if rows else 0.0,
            "avg_llm_calls": round(mean(r["llm_calls"] for r in rows), 2) if rows else 0.0,
            "avg_tokens": round(mean(r["tokens"] for r in rows), 2) if rows else 0.0,
            "avg_latency_seconds": round(mean(r["latency_seconds"] for r in rows), 6) if rows else 0.0,
            "avg_cost_usd": round(mean(r["estimated_cost_usd"] for r in rows), 6) if rows else 0.0,
        })

    report = {
        "benchmark": "Person B Planning & Search",
        "cases": cases,
        "strategies": strategies,
        "model": "deterministic MockLLMClient",
        "grounded_source": "db/sterling_vance.db (read-only)",
        "note": "This local run verifies control flow and reproducibility. Replace MockLLMClient with the team's live model adapter for final quality measurements.",
        "summary": summary,
        "runs": records,
    }
    with open(os.path.join(ARTIFACTS, "person_b_15_case_benchmark.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    with open(os.path.join(ARTIFACTS, "person_b_comparison_table.md"), "w", encoding="utf-8") as fh:
        fh.write("| Strategy | Applicable | Success | Avg LLM calls | Avg tokens | Avg latency (s) | Avg cost/run |\n")
        fh.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for row in summary:
            fh.write(f"| {row['strategy']} | {row['applicable_cases']} | {row['successes']}/{row['applicable_cases']} ({row['success_rate']:.0%}) | {row['avg_llm_calls']} | {row['avg_tokens']} | {row['avg_latency_seconds']} | ${row['avg_cost_usd']:.4f} |\n")
    return report


if __name__ == "__main__":
    report = run_benchmark()
    for row in report["summary"]:
        print(row)
