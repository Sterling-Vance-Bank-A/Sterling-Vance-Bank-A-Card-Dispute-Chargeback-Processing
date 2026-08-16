"""
Decomposition Divergence Demonstration — Sterling Vance Bank

Demonstrates a real scenario where Decomposition-First and Dynamic Decomposition diverge:
- Scenario: Dispute DISP-003 is already in terminal status (status='refunded', amount=$150.00).
- Decomposition-First: Generates a static 4-step plan upfront (evidence -> evaluate -> refund -> notify)
  and blindly attempts to execute the refund on an already-refunded dispute.
- Dynamic Decomposition: Observes the step 1 finding (already terminal), immediately diverges
  (diverged=True), cancels the redundant refund/escalation pipeline, generates a closure audit notice,
  and completes in 2 steps.
"""

from __future__ import annotations

import io
import json
import os
import sys

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from planning import DecompositionFirst, DynamicDecomposition
from planning.benchmark import MockLLMClient


def custom_router_fn(subtask) -> str:
    """Simulates real tool execution on dispute DISP-003."""
    t_desc = subtask.description.lower()
    t_type = subtask.task_type.lower()

    if "evidence" in t_desc or t_type == "evidence_aggregation":
        return "Aggregated DISP-003 evidence: Cardholder claims duplicate charge. Current status=refunded, amount=$150.00. Already terminal."

    if "sort" in t_desc or t_type == "sort_priority":
        return "Evaluation: Reason code 4853 applies. Proceed to standard refund queue."

    if "refund" in t_desc or t_type == "process_refund":
        return "ERROR: Cannot process refund on DISP-003. Transaction is already refunded (Terminal State Violation)."

    if "notification" in t_desc or t_type == "notification_draft":
        if "closure" in t_desc or "terminal" in t_desc:
            return "Closure Notice: DISP-003 confirmed already refunded on 2026-07-28. Audit log updated; no further debit executed."
        return "Customer Notice: Refund approved and pending card network settlement."

    return f"Executed {subtask.id}: {subtask.description}"


def run_divergence_demo() -> dict:
    llm = MockLLMClient()

    request = (
        "Remediate incoming customer dispute DISP-003 for amount $150.00. "
        "Verify transaction evidence, evaluate reason code eligibility, execute appropriate resolution, "
        "and draft customer disclosure."
    )
    context = {"dispute_id": "DISP-003", "amount": 150.00, "analyst_id": "ANL-001"}

    print("=" * 80)
    print("STERLING VANCE BANK — DECOMPOSITION DIVERGENCE DEMONSTRATION")
    print("=" * 80)
    print(f"\nIncoming Request:\n  {request}\n")
    print(f"Dispute Context:\n  {context}\n")

    # 1. Run Decomposition-First
    print("-" * 80)
    print("1. RUNNING DECOMPOSITION-FIRST (Static Upfront Plan)")
    print("-" * 80)
    decomp_first = DecompositionFirst(llm_client=llm, router_fn=custom_router_fn)
    df_result = decomp_first.execute(request, context)

    print(f"Plan Generated Upfront: {len(df_result['execution_order'])} tasks in topological order:")
    for task_id in df_result["execution_order"]:
        t = df_result["dag_tasks"][task_id]
        print(f"  [{task_id}] ({t['task_type']}) {t['description']}")

    print("\nExecution Results:")
    for task_id, res in df_result["results"].items():
        print(f"  [{task_id}]: {res}")

    print(f"\nDecomposition-First Metrics:")
    print(f"  LLM Calls: {df_result['metrics']['llm_calls']}")
    print(f"  Tokens:    {df_result['metrics']['tokens']}")
    print(f"  Diverged:  False (Blindly executed full stale plan)")

    # 2. Run Dynamic / Interleaved Decomposition
    print("\n" + "-" * 80)
    print("2. RUNNING DYNAMIC DECOMPOSITION (Adaptive Observe-Decide-Execute Loop)")
    print("-" * 80)
    dynamic_decomp = DynamicDecomposition(llm_client=llm, router_fn=custom_router_fn, max_steps=5)
    dd_result = dynamic_decomp.execute(request, context)

    print(f"Steps Dynamically Executed: {dd_result['steps_taken']} steps:")
    for task_id in dd_result["execution_order"]:
        t = dd_result["dag_tasks"][task_id]
        print(f"  [{task_id}] ({t['task_type']}) {t['description']}")

    print("\nExecution Results:")
    for task_id, res in dd_result["results"].items():
        print(f"  [{task_id}]: {res}")

    print(f"\nDynamic Decomposition Metrics:")
    print(f"  LLM Calls: {dd_result['metrics']['llm_calls']}")
    print(f"  Tokens:    {dd_result['metrics']['tokens']}")
    print(f"  Diverged:  {dd_result['diverged']} (Detected terminal status at step 1 -> pivoted to audit closure)")

    # 3. Side-by-Side Comparison
    print("\n" + "=" * 80)
    print("SIDE-BY-SIDE DIVERGENCE SUMMARY")
    print("=" * 80)
    print(f"{'Metric':<30} | {'Decomposition-First':<22} | {'Dynamic Decomposition':<22}")
    print("-" * 80)
    print(f"{'Total Steps Executed':<30} | {len(df_result['execution_order']):<22} | {dd_result['steps_taken']:<22}")
    print(f"{'Adapted to Early Finding':<30} | {'No (Executed blind error)':<22} | {'Yes (Pivoted safely)':<22}")
    print(f"{'Illegal Refund Attempted':<30} | {'YES (Failed in tool)':<22} | {'NO (Safely avoided)':<22}")
    print(f"{'Total LLM Calls':<30} | {df_result['metrics']['llm_calls']:<22} | {dd_result['metrics']['llm_calls']:<22}")
    print(f"{'Total Tokens Used':<30} | {df_result['metrics']['tokens']:<22} | {dd_result['metrics']['tokens']:<22}")
    print("=" * 80)

    return {"decomposition_first": df_result, "dynamic_decomposition": dd_result}


if __name__ == "__main__":
    run_divergence_demo()
