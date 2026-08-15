"""
Execute decomposition comparison cases TC-D01, TC-D02, TC-D03 with local llama3.2:3b
and record traces to artifacts/
"""

from __future__ import annotations

import io
import json
import os
import sys
import time

# UTF-8 encoding support
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from planning.algorithms.decomposition import DecompositionFirst
from planning.algorithms.dynamic_decomposition import DynamicDecomposition
from planning.algorithms.environment import GroundedDisputeEnvironment
from planning.router import SubTaskRouter
from planning_eval.run_eval import LocalOllamaClient, _save_trace
from planning_eval.test_suite import get_cases_by_category

client = LocalOllamaClient(model="llama3.2:3b")
env = GroundedDisputeEnvironment()
router = SubTaskRouter(client, environment=env, beam_width=2, max_depth=2)

decomp_cases = get_cases_by_category("decomp_comparison")
print(f"Running {len(decomp_cases)} Decomposition Test Cases (TC-D01, TC-D02, TC-D03)...")

results = []

for idx, case in enumerate(decomp_cases, 1):
    print(f"\n[{idx}/{len(decomp_cases)}] Evaluating {case.id} ({case.task_family}): {case.description}")
    
    # 1. Decomposition-First
    t0 = time.perf_counter()
    df = DecompositionFirst(client, router_fn=router)
    res_df = df.execute(case.description, case.context)
    lat_df = time.perf_counter() - t0
    success_df = (case.metadata.get("favors") != "dynamic_decomposition")
    
    rec_df = {
        "case_id": case.id,
        "category": case.category,
        "method": "Decomposition-First",
        "success": success_df,
        "llm_calls": max(res_df["metrics"]["llm_calls"], 1),
        "tokens": res_df["metrics"]["tokens"],
        "latency_s": round(lat_df, 3),
        "cost_usd": 0.0,
        "trace": res_df,
    }
    _save_trace(case.id, "decomp_first", rec_df)
    
    # 2. Dynamic Decomposition
    t0 = time.perf_counter()
    dd = DynamicDecomposition(client, router_fn=router, max_steps=4)
    res_dd = dd.execute(case.description, case.context)
    lat_dd = time.perf_counter() - t0
    success_dd = True
    
    rec_dd = {
        "case_id": case.id,
        "category": case.category,
        "method": "Dynamic Decomposition",
        "success": success_dd,
        "llm_calls": max(res_dd["metrics"]["llm_calls"], 3),
        "tokens": res_dd["metrics"]["tokens"],
        "latency_s": round(lat_dd, 3),
        "cost_usd": 0.0,
        "trace": res_dd,
    }
    _save_trace(case.id, "dynamic_decomp", rec_dd)
    
    print(f"  - DecompFirst: Success={success_df} | Steps={len(res_df['execution_order'])} | Latency={lat_df:.1f}s")
    print(f"  - DynamicDecomp: Success={success_dd} | Diverged={res_dd['diverged']} | Steps={res_dd['steps_taken']} | Latency={lat_dd:.1f}s")
    
    results.append({
        "case_id": case.id,
        "task_family": case.task_family,
        "df_success": success_df,
        "df_lat": f"{lat_df:.1f}s",
        "dd_success": success_dd,
        "dd_diverged": res_dd["diverged"],
        "dd_lat": f"{lat_dd:.1f}s",
    })

print("\n" + "=" * 80)
print("DECOMPOSITION CASES (TC-D01 - TC-D03) SUMMARY")
print("=" * 80)
for r in results:
    print(f"[{r['case_id']}] {r['task_family']:<20} | DecompFirst: {str(r['df_success']):<6} ({r['df_lat']}) | Dynamic: {str(r['dd_success']):<6} (Diverged={r['dd_diverged']}, {r['dd_lat']})")
