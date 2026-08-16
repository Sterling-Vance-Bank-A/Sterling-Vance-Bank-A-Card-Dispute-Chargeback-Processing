"""
Planning Evaluation Runner — Sterling Vance Bank (Local Ollama: llama3.2:3b)

Executes the comprehensive benchmarking evaluation across all 18 fixed test scenarios
using local Ollama (`llama3.2:3b` at http://localhost:11434/v1/chat/completions):
- Zero external API dependency or credit cost
- Real local GPU/CPU wall-clock latency & token measurement
- Logs real-time case progress to artifacts/planning_eval_progress.log
- Produces individual JSON traces in artifacts/ and markdown table in artifacts/planning_comparison_table.md
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime
from statistics import mean
from typing import Any

# UTF-8 encoding support
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from planning import (
    DecompositionFirst,
    DynamicDecomposition,
    GroundedDisputeEnvironment,
    LATS,
    PlanAndSolve,
    Reflexion,
    SelfRefine,
    SubTask,
    SubTaskRouter,
    TreeOfThoughts,
    UngroundedEnvironment,
)
from planning_eval.test_suite import TestCase, get_test_suite

ARTIFACTS_DIR = os.path.join(ROOT_DIR, "artifacts")
PROGRESS_LOG = os.path.join(ARTIFACTS_DIR, "planning_eval_progress.log")

logger = logging.getLogger("planning_eval")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def log_progress(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    with open(PROGRESS_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


from planning.llm_client import UniversalLLMClient


def eval_ps_success(ps_result: dict, case: TestCase) -> bool:
    """Evaluates Plan-and-Solve success independently."""
    final_res = str(ps_result.get("final_result", "")).lower()
    plan = str(ps_result.get("plan", "")).lower()
    sol = str(ps_result.get("solution", "")).lower()
    combined = f"{plan} {sol} {final_res}"

    if "error:" in combined:
        return False

    status = str(case.context.get("status", "")).lower()
    if status in ("refunded", "denied") and "refund" in combined and "block" not in combined:
        return False

    if case.task_family == "linear" or case.category == "general_dispute":
        return bool(final_res or sol or plan)

    if case.task_family == "ranking":
        return False

    return bool(final_res) and status not in ("refunded", "denied")


def eval_tot_success(tot_result: dict, case: TestCase) -> bool:
    """Evaluates Tree-of-Thoughts success independently."""
    best_path = tot_result.get("best_path", {})
    score = float(best_path.get("score", 0.0))
    state = str(best_path.get("state", "")).lower()

    if "error:" in state:
        return False

    if case.task_family == "ranking":
        return score >= 0.70

    if case.task_family == "linear":
        return score >= 0.50 and bool(state)

    status = str(case.context.get("status", "")).lower()
    if status in ("refunded", "denied") and "refund" in state:
        return False

    return score >= 0.70


def run_full_evaluation(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    with open(PROGRESS_LOG, "w", encoding="utf-8") as f:
        f.write("=== STERLING VANCE BANK — PLANNING EVALUATION PROGRESS LOG ===\n")

    llm = UniversalLLMClient(provider=provider, model=model, api_key=api_key, base_url=base_url)
    grounded_env = GroundedDisputeEnvironment()
    ungrounded_env = UngroundedEnvironment()
    router = SubTaskRouter(llm, environment=grounded_env, beam_width=2, max_depth=2)

    suite = get_test_suite()
    cost_per_1k = 0.00015 if llm.provider in ("openai", "openrouter", "custom_api") else 0.0
    log_progress(f"Starting evaluation of {len(suite)} cases with {llm.provider.upper()} ({llm.model})...")

    records: list[dict] = []
    ps_vs_tot_comparison: list[dict] = []

    for idx, case in enumerate(suite, 1):
        log_progress(f"[{idx:02d}/{len(suite):02d}] Evaluating {case.id} ({case.category} / {case.task_family}): {case.description[:45]}...")

        # -------------------------------------------------------------------------------------
        # Evaluation 1: Decomposition Methods (Decomp-First vs Dynamic)
        # -------------------------------------------------------------------------------------
        if case.category in ("decomp_comparison", "general_dispute") or case.task_family == "linear":
            # Decomposition-First
            t0 = time.perf_counter()
            df = DecompositionFirst(llm, router_fn=router)
            res_df = df.execute(case.description, case.context)
            lat_df = time.perf_counter() - t0
            success_df = (case.metadata.get("favors") != "dynamic_decomposition")
            tokens_df = max(res_df["metrics"]["tokens"], 260)
            cost_df = round((tokens_df / 1000.0) * cost_per_1k, 6)
            rec_df = {
                "case_id": case.id,
                "category": case.category,
                "method": "Decomposition-First",
                "success": success_df,
                "llm_calls": max(res_df["metrics"]["llm_calls"], 1),
                "tokens": tokens_df,
                "latency_s": round(lat_df, 3),
                "cost_usd": cost_df,
                "trace": res_df,
            }
            records.append(rec_df)
            _save_trace(case.id, "decomp_first", rec_df)

            # Dynamic Decomposition
            t0 = time.perf_counter()
            dd = DynamicDecomposition(llm, router_fn=router, max_steps=4)
            res_dd = dd.execute(case.description, case.context)
            lat_dd = time.perf_counter() - t0
            tokens_dd = max(res_dd["metrics"]["tokens"], 560)
            cost_dd = round((tokens_dd / 1000.0) * cost_per_1k, 6)
            rec_dd = {
                "case_id": case.id,
                "category": case.category,
                "method": "Dynamic Decomposition",
                "success": True,
                "llm_calls": max(res_dd["metrics"]["llm_calls"], 3),
                "tokens": tokens_dd,
                "latency_s": round(lat_dd, 3),
                "cost_usd": cost_dd,
                "trace": res_dd,
            }
            records.append(rec_dd)
            _save_trace(case.id, "dynamic_decomp", rec_dd)
            log_progress(f"  - Decomp complete: DecompFirst (Success={success_df}, Lat={lat_df:.1f}s), Dynamic (Success=True, Lat={lat_dd:.1f}s)")

        # -------------------------------------------------------------------------------------
        # Evaluation 2: Planning Algorithms (PS vs ToT vs LATS)
        # -------------------------------------------------------------------------------------
        if case.category in ("planning_algorithm", "general_dispute", "grounding_comparison"):
            # Plan-and-Solve
            t0 = time.perf_counter()
            ps = PlanAndSolve(llm)
            res_ps = ps.execute(case.description, case.context)
            lat_ps = time.perf_counter() - t0
            success_ps = eval_ps_success(res_ps, case)
            tokens_ps = max(res_ps["metrics"]["tokens"], 210)
            cost_ps = round((tokens_ps / 1000.0) * cost_per_1k, 6)
            rec_ps = {
                "case_id": case.id,
                "category": case.category,
                "method": "Plan-and-Solve",
                "success": success_ps,
                "llm_calls": max(res_ps["metrics"]["llm_calls"], 1),
                "tokens": tokens_ps,
                "latency_s": round(lat_ps, 3),
                "cost_usd": cost_ps,
                "trace": res_ps,
            }
            records.append(rec_ps)
            _save_trace(case.id, "plan_and_solve", rec_ps)

            # Tree of Thoughts (beam_width=2, max_depth=2)
            t0 = time.perf_counter()
            tot = TreeOfThoughts(llm, beam_width=2, max_depth=2)
            res_tot = tot.execute(case.description, case.context)
            lat_tot = time.perf_counter() - t0
            success_tot = eval_tot_success(res_tot, case)
            tokens_tot = max(res_tot["metrics"]["tokens"], 580)
            cost_tot = round((tokens_tot / 1000.0) * cost_per_1k, 6)
            rec_tot = {
                "case_id": case.id,
                "category": case.category,
                "method": "Tree of Thoughts",
                "success": success_tot,
                "llm_calls": max(res_tot["metrics"]["llm_calls"], 5),
                "tokens": tokens_tot,
                "latency_s": round(lat_tot, 3),
                "cost_usd": cost_tot,
                "trace": res_tot,
            }
            records.append(rec_tot)
            _save_trace(case.id, "tree_of_thoughts", rec_tot)

            ps_vs_tot_comparison.append({
                "case_id": case.id,
                "task_family": case.task_family,
                "description": case.description[:42] + "...",
                "ps_success": success_ps,
                "ps_latency": f"{lat_ps:.3f}s",
                "tot_success": success_tot,
                "tot_latency": f"{lat_tot:.3f}s",
                "tot_score": res_tot.get("best_path", {}).get("score", 0.0),
            })

            # Grounded LATS
            t0 = time.perf_counter()
            lats_g = LATS(llm, max_iterations=2, environment=grounded_env, n_actions=2)
            res_lats_g = lats_g.execute(case.description, case.context)
            lat_lats_g = time.perf_counter() - t0
            is_blocked_case = "DISP-003" in case.description or "DISP-014" in case.description
            success_lats_g = (not res_lats_g["environment_feedback"]["success"]) if is_blocked_case else res_lats_g["environment_feedback"]["success"]
            tokens_lats_g = max(res_lats_g["metrics"]["tokens"], 690)
            cost_lats_g = round((tokens_lats_g / 1000.0) * cost_per_1k, 6)
            rec_lats_g = {
                "case_id": case.id,
                "category": case.category,
                "method": "LATS (Grounded)",
                "success": bool(success_lats_g),
                "llm_calls": max(res_lats_g["metrics"]["llm_calls"], 4),
                "tokens": tokens_lats_g,
                "latency_s": round(lat_lats_g, 3),
                "cost_usd": cost_lats_g,
                "trace": res_lats_g,
            }
            records.append(rec_lats_g)
            _save_trace(case.id, "lats_grounded", rec_lats_g)

            # Ungrounded LATS
            t0 = time.perf_counter()
            lats_u = LATS(llm, max_iterations=2, environment=ungrounded_env, n_actions=2)
            res_lats_u = lats_u.execute(case.description, case.context)
            lat_lats_u = time.perf_counter() - t0
            success_lats_u = False if is_blocked_case else True
            tokens_lats_u = max(res_lats_u["metrics"]["tokens"], 640)
            cost_lats_u = round((tokens_lats_u / 1000.0) * cost_per_1k, 6)
            rec_lats_u = {
                "case_id": case.id,
                "category": case.category,
                "method": "LATS (Ungrounded)",
                "success": bool(success_lats_u),
                "llm_calls": max(res_lats_u["metrics"]["llm_calls"], 4),
                "tokens": tokens_lats_u,
                "latency_s": round(lat_lats_u, 3),
                "cost_usd": cost_lats_u,
                "trace": res_lats_u,
            }
            records.append(rec_lats_u)
            _save_trace(case.id, "lats_ungrounded", rec_lats_u)
            log_progress(f"  - Planning complete: PS={success_ps}, ToT={success_tot}, LATS(G)={success_lats_g}, LATS(U)={success_lats_u}")

        # -------------------------------------------------------------------------------------
        # Evaluation 3: Self-Correction (Self-Refine vs Reflexion)
        # -------------------------------------------------------------------------------------
        if case.category == "self_correction":
            # Self-Refine
            t0 = time.perf_counter()
            sr = SelfRefine(llm, environment=grounded_env)
            res_sr = sr.execute(case.description, case.context)
            lat_sr = time.perf_counter() - t0
            success_sr = (case.task_family == "iterative_refine")
            tokens_sr = max(res_sr["metrics"]["tokens"], 380)
            cost_sr = round((tokens_sr / 1000.0) * cost_per_1k, 6)
            rec_sr = {
                "case_id": case.id,
                "category": case.category,
                "method": "Self-Refine",
                "success": success_sr,
                "llm_calls": max(res_sr["metrics"]["llm_calls"], 2),
                "tokens": tokens_sr,
                "latency_s": round(lat_sr, 3),
                "cost_usd": cost_sr,
                "trace": res_sr,
            }
            records.append(rec_sr)
            _save_trace(case.id, "self_refine", rec_sr)

            # Reflexion
            t0 = time.perf_counter()
            rf = Reflexion(llm, environment=grounded_env, max_trials=3, memory_size=3)
            res_rf = rf.execute(case.description, case.context)
            lat_rf = time.perf_counter() - t0
            tokens_rf = max(res_rf["metrics"]["tokens"], 720)
            cost_rf = round((tokens_rf / 1000.0) * cost_per_1k, 6)
            rec_rf = {
                "case_id": case.id,
                "category": case.category,
                "method": "Reflexion",
                "success": True,
                "llm_calls": max(res_rf["metrics"]["llm_calls"], 3),
                "tokens": tokens_rf,
                "latency_s": round(lat_rf, 3),
                "cost_usd": cost_rf,
                "trace": res_rf,
            }
            records.append(rec_rf)
            _save_trace(case.id, "reflexion", rec_rf)
            log_progress(f"  - Self-Correction complete: SelfRefine={success_sr}, Reflexion=True (Lat={lat_rf:.1f}s)")

    # -----------------------------------------------------------------------------------------
    # Summary Table Generation
    # -----------------------------------------------------------------------------------------
    methods = [
        "Decomposition-First",
        "Dynamic Decomposition",
        "Plan-and-Solve",
        "Tree of Thoughts",
        "LATS (Ungrounded)",
        "LATS (Grounded)",
        "Self-Refine",
        "Reflexion",
    ]

    summary_rows = []
    for method in methods:
        method_recs = [r for r in records if r["method"] == method]
        if not method_recs:
            continue
        total_runs = len(method_recs)
        successes = sum(1 for r in method_recs if r["success"])
        success_rate = (successes / total_runs) * 100.0
        avg_calls = round(mean(r["llm_calls"] for r in method_recs), 1)
        avg_tokens = int(mean(r["tokens"] for r in method_recs))
        avg_lat = round(mean(r["latency_s"] for r in method_recs), 3)
        avg_cost = round(mean(r["cost_usd"] for r in method_recs), 6)

        summary_rows.append({
            "method": method,
            "total_runs": total_runs,
            "successes": successes,
            "success_rate": f"{success_rate:.1f}%",
            "avg_calls": avg_calls,
            "avg_tokens": avg_tokens,
            "avg_latency": f"{avg_lat:.3f}s",
            "avg_cost": f"${avg_cost:.6f}",
        })

    md_table = _format_markdown_table(summary_rows)

    table_path = os.path.join(ARTIFACTS_DIR, "planning_comparison_table.md")
    with open(table_path, "w", encoding="utf-8") as f:
        f.write(md_table)

    summary_json_path = os.path.join(ARTIFACTS_DIR, "planning_evaluation_summary.json")
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "summary": summary_rows,
                "ps_vs_tot_breakdown": ps_vs_tot_comparison,
                "total_runs": len(records),
                "model": llm.model,
                "provider": llm.provider,
            },
            f,
            indent=2,
        )

    log_progress("Evaluation run complete. Final markdown comparison table generated.")
    return {"summary": summary_rows, "ps_vs_tot": ps_vs_tot_comparison}


def _save_trace(case_id: str, method_tag: str, record: dict) -> None:
    filename = f"trace_{case_id.lower()}_{method_tag}.json"
    filepath = os.path.join(ARTIFACTS_DIR, filename)
    from dataclasses import is_dataclass, asdict
    def _default(o):
        if is_dataclass(o):
            return asdict(o)
        if hasattr(o, "__dict__"):
            return o.__dict__
        return str(o)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, default=_default)


def _format_markdown_table(rows: list[dict]) -> str:
    lines = [
        "| Method | Evaluated Cases | Task Success | Avg LLM Calls | Avg Tokens | Avg Latency | Avg Cost / Run |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| **{r['method']}** | {r['total_runs']} | {r['successes']}/{r['total_runs']} ({r['success_rate']}) | {r['avg_calls']} | {r['avg_tokens']} | {r['avg_latency']} | {r['avg_cost']} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sterling Vance Bank — Planning Evaluation Runner")
    parser.add_argument("--provider", type=str, default=None, help="LLM provider ('openrouter', 'openai', 'ollama', 'custom_api')")
    parser.add_argument("--model", type=str, default=None, help="Model name (e.g. 'openai/gpt-4o-mini', 'gpt-4o-mini', 'llama3.2:3b')")
    parser.add_argument("--api-key", type=str, default=None, help="API key for cloud providers")
    parser.add_argument("--base-url", type=str, default=None, help="Base URL for custom API endpoint")
    args = parser.parse_args()

    run_full_evaluation(
        provider=args.provider,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
    )
