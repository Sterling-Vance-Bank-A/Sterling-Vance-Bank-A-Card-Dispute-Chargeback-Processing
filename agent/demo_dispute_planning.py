"""
Consolidated Demonstration Script — Sterling Vance Bank Planning & Decomposition Lab

Demonstrates all 5 core rubric capabilities:
1. Decomposition Divergence: Decomposition-First vs. Dynamic Decomposition on Terminal Dispute (DISP-003)
2. Sub-Task Routing: Live dispatch across Plan-and-Solve (PS), Tree-of-Thoughts (ToT), and Grounded LATS
3. Self-Refine: Grounded Compliance Critic refinement of customer disclosure notice
4. Reflexion: Multi-trial constraint resolution carrying episodic reflection across attempts
5. Grounded vs. Ungrounded Environment: Grounded DB constraint validation preventing illegal duplicate payouts

Run directly:
    python agent/demo_dispute_planning.py
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
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
MCP_SERVER_DIR = os.path.join(ROOT_DIR, "mcp_server")
if MCP_SERVER_DIR not in sys.path:
    sys.path.insert(0, MCP_SERVER_DIR)

from agent.dispute_planning_agent import DisputePlanningAgent
from planning.algorithms.environment import GroundedDisputeEnvironment
from planning.algorithms.self_refine import SelfRefine
from planning.benchmark import MockLLMClient
from planning.demo_divergence import run_divergence_demo
from planning.demo_grounding import run_grounding_demo
from planning.demo_reflexion import run_reflexion_demo


def reset_demo_database():
    """Resets key demo records in SQLite database to pristine states."""
    import sqlite3
    db_path = os.path.join(ROOT_DIR, "db", "sterling_vance.db")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE disputes SET status = 'open' WHERE dispute_id = 'DISP-001'")
        cursor.execute("UPDATE disputes SET status = 'investigating' WHERE dispute_id = 'DISP-002'")
        cursor.execute("UPDATE disputes SET status = 'refunded' WHERE dispute_id = 'DISP-003'")
        conn.commit()


def run_section_1_divergence():
    print("\n" + "=" * 95)
    print("DEMO SECTION 1: DECOMPOSITION DIVERGENCE (Decomposition-First vs. Dynamic Decomposition)")
    print("=" * 95)
    print("Scenario: Customer requests refund on DISP-003 ($150.00). Database status: 'refunded' (terminal).\n")
    run_divergence_demo()


def run_section_2_routing():
    print("\n" + "=" * 95)
    print("DEMO SECTION 2: MULTI-ALGORITHMIC SUB-TASK ROUTING (PS vs. ToT vs. Grounded LATS)")
    print("=" * 95)
    print("Scenario: Full end-to-end processing of routine dispute DISP-001 ($29.99 duplicate charge).\n")

    agent = DisputePlanningAgent()
    request = "Remediate dispute DISP-001 ($29.99 duplicate charge) with evidence aggregation, priority ranking, and refund."
    res = agent.handle_dispute(request, {"dispute_id": "DISP-001", "analyst_id": "ANL-001"})

    print("Sub-Tasks Executed & Algorithm Dispatching:")
    for tid, tinfo in res["subtasks_executed"].items():
        algo = tinfo.get("routed_algorithm", "unknown")
        stype = tinfo.get("subtask_type", "general")
        desc = tinfo.get("description", "")
        status = tinfo.get("status", "unknown")
        print(f"  * Task [{tid}] ({stype}): {desc}")
        print(f"    -> Dispatched To: {algo.upper()} | Status: {status}")
        if algo == "lats":
            print(f"    -> LATS Best Action: {tinfo.get('best_action')} | Grounded Score: {tinfo.get('environment_feedback', {}).get('score')}")
        elif algo == "tree_of_thoughts":
            print(f"    -> ToT Best Path: {tinfo.get('best_path', {}).get('state')[:65]}...")

    print(f"\nFinal Planning-Driven Action: {res['final_decision']['action']}")
    print(f"Action Details: {res['final_decision']['details']}")
    print(f"MCP Tools Invoked: {[a['tool'] for a in res['mcp_tool_actions']]}")


def run_section_3_self_refine():
    print("\n" + "=" * 95)
    print("DEMO SECTION 3: SELF-REFINE (Grounded Independent Compliance Critic Loop)")
    print("=" * 95)
    print("Scenario: Drafting a Regulation E dispute resolution letter with strict statutory disclosure rules.\n")

    llm = MockLLMClient()
    env = GroundedDisputeEnvironment()
    sr = SelfRefine(llm, environment=env)

    task = "Draft formal customer disclosure letter for dispute DISP-001 ($29.99)."
    context = {"dispute_id": "DISP-001", "amount": 29.99, "reason": "duplicate_charge"}

    res = sr.execute(task, context)

    print("--- Initial Draft ---")
    print(res["draft"])
    print("\n--- Independent Compliance Critique (Grounded DB + Rubric) ---")
    print(res["critique"])
    print(f"Grounded Issues Identified: {res['grounded_issues']}")
    print(f"Passed Initially: {res['passed_initially']}")
    print("\n--- Refined Final Document ---")
    print(res["revised"])


def run_section_4_reflexion():
    print("\n" + "=" * 95)
    print("DEMO SECTION 4: REFLEXION (Cross-Trial Episodic Verbal Memory Carry)")
    print("=" * 95)
    print("Scenario: Junior analyst (ANL-001) attempting resolution on a $899.00 unauthorized dispute (DISP-002).\n")
    run_reflexion_demo()


def run_section_5_grounding():
    print("\n" + "=" * 95)
    print("DEMO SECTION 5: GROUNDED VS. UNGROUNDED ENVIRONMENT CONTRAST")
    print("=" * 95)
    print("Scenario: Evaluating payout candidate on terminal dispute DISP-003 (status: 'refunded').\n")
    run_grounding_demo()


def main():
    print("=" * 95)
    print("STERLING VANCE BANK — CONSOLIDATED PLANNING & DECOMPOSITION DEMONSTRATION")
    print("=" * 95)
    reset_demo_database()

    t_start = time.perf_counter()
    run_section_1_divergence()
    run_section_2_routing()
    run_section_3_self_refine()
    run_section_4_reflexion()
    run_section_5_grounding()
    t_total = time.perf_counter() - t_start

    print("\n" + "=" * 95)
    print(f"ALL 5 DEMONSTRATION SECTIONS COMPLETED SUCCESSFULLY in {t_total:.3f}s")
    print("=" * 95)


if __name__ == "__main__":
    main()
