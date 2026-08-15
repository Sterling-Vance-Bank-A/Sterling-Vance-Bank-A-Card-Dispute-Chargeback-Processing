"""
Isolated debug script: Tests TC-P01 on Plan-and-Solve and TC-P03 on Tree-of-Thoughts
using the live openai/gpt-4o-mini client with tightened max_tokens.
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

from planning.algorithms.plan_and_solve import PlanAndSolve
from planning.algorithms.tree_of_thoughts import TreeOfThoughts
from planning_eval.run_eval import RepoStandardLLMClient, eval_ps_success, eval_tot_success
from planning_eval.test_suite import get_test_suite

llm = RepoStandardLLMClient(model="openai/gpt-4o-mini")
suite = {tc.id: tc for tc in get_test_suite()}

print("=" * 80)
print("ISOLATED DEBUG TEST: Plan-and-Solve (TC-P01) & Tree-of-Thoughts (TC-P03)")
print("=" * 80)

# 1. Test TC-P01 on Plan-and-Solve
case_p01 = suite["TC-P01"]
print(f"\n--- Running TC-P01 on Plan-and-Solve ---")
print(f"Description: {case_p01.description}")
print(f"Context: {case_p01.context}")

t0 = time.perf_counter()
ps = PlanAndSolve(llm)
res_ps = ps.execute(case_p01.description, case_p01.context)
lat_ps = time.perf_counter() - t0

verdict_ps = eval_ps_success(res_ps, case_p01)

print(f"\nPlan-and-Solve Result Keys: {list(res_ps.keys())}")
print(f"Final Result Output:\n{res_ps.get('final_result', '')}")
print(f"Execution Trace: {len(res_ps.get('execution_trace', []))} steps")
print(f"LLM Calls: {res_ps['metrics']['llm_calls']} | Tokens: {res_ps['metrics']['tokens']} | Latency: {lat_ps:.3f}s")
print(f"Grounded Evaluator Verdict: {verdict_ps} (Expected: True)")

# 2. Test TC-P03 on Tree-of-Thoughts with beam_width=2, max_depth=2
case_p03 = suite["TC-P03"]
print(f"\n--- Running TC-P03 on Tree-of-Thoughts (beam_width=2, max_depth=2) ---")
print(f"Description: {case_p03.description}")
print(f"Context: {case_p03.context}")

t0 = time.perf_counter()
tot = TreeOfThoughts(llm, beam_width=2, max_depth=2)
res_tot = tot.execute(case_p03.description, case_p03.context)
lat_tot = time.perf_counter() - t0

verdict_tot = eval_tot_success(res_tot, case_p03)

print(f"\nTree-of-Thoughts Result Keys: {list(res_tot.keys())}")
print(f"Best Path Found:\n  State: {res_tot['best_path']['state']}\n  Score: {res_tot['best_path']['score']}\n  Rationale: {res_tot['best_path']['rationale']}")
print(f"LLM Calls: {res_tot['metrics']['llm_calls']} | Tokens: {res_tot['metrics']['tokens']} | Latency: {lat_tot:.3f}s")
print(f"Grounded Evaluator Verdict: {verdict_tot} (Expected: True)")
print("=" * 80)
