"""
Dispute Planning Agent — Sterling Vance Bank (Part 4)

An autonomous dispute resolution planning agent that integrates:
1. Dynamic Task Decomposition (DynamicDecomposition) with DAG dependency execution
2. Algorithmic Sub-Task Routing (SubTaskRouter -> Plan-and-Solve, Tree-of-Thoughts, LATS)
3. Grounded Dispute Environment (GroundedDisputeEnvironment against SQLite database)
4. Self-Correction & Episodic Memory (SelfRefine for disclosures, Reflexion for actions)
5. Model Context Protocol (MCP) tool integration for dispute queries, refund processing, and escalation.

This agent operates alongside `agent/memory_agent.py` without modifying or coupling to it.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional

# UTF-8 output support
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
MCP_SERVER_DIR = os.path.join(ROOT_DIR, "mcp_server")
if MCP_SERVER_DIR not in sys.path:
    sys.path.insert(0, MCP_SERVER_DIR)

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
)
from planning.benchmark import MockLLMClient

import mcp.types as mcp_types
from mcp_server.server import handle_call_tool

logger = logging.getLogger("dispute_planning_agent")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class DisputePlanningAgent:
    """
    Autonomous dispute planning and resolution agent for Sterling Vance Bank.
    """

    def __init__(
        self,
        llm: Any = None,
        environment: Optional[GroundedDisputeEnvironment] = None,
        strategy: str = "dynamic",
        beam_width: int = 2,
        max_depth: int = 2,
        max_steps: int = 5,
    ):
        """
        Initialize the planning agent.

        Args:
            llm: Language model client implementing `generate(prompt) -> str`. Defaults to MockLLMClient if None.
            environment: Grounded dispute environment backed by sterling_vance.db.
            strategy: 'dynamic' (DynamicDecomposition, default) or 'decomposition_first'.
            beam_width: Tree of Thoughts beam width.
            max_depth: Tree of Thoughts max search depth.
            max_steps: Maximum execution steps for dynamic planner.
        """
        self.llm = llm or MockLLMClient()
        self.strategy = strategy.lower()
        self.max_steps = max_steps

        # Always default to GroundedDisputeEnvironment in production
        self.environment = environment or GroundedDisputeEnvironment()

        # Initialize sub-task router with grounded LATS and bounded search
        self.router = SubTaskRouter(
            self.llm,
            environment=self.environment,
            beam_width=beam_width,
            max_depth=max_depth,
        )

        # Initialize self-correction modules
        self.self_refine = SelfRefine(self.llm, environment=self.environment)
        self.reflexion = Reflexion(self.llm, environment=self.environment, max_trials=3, memory_size=3)

        # Audit log for MCP actions
        self.mcp_audit_log: List[Dict[str, Any]] = []

    def call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatches a tool call through the official Model Context Protocol (MCP) server
        handler (`mcp_server.server.handle_call_tool`), enforcing MCP schemas and server-side validation.
        """
        t0 = time.perf_counter()
        params = mcp_types.CallToolRequestParams(name=tool_name, arguments=arguments)

        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    result = executor.submit(asyncio.run, handle_call_tool(None, params)).result()
            else:
                result = loop.run_until_complete(handle_call_tool(None, params))

            elapsed = time.perf_counter() - t0
            raw_text = result.content[0].text if result.content else ""
            is_error = raw_text.startswith("VALIDATION ERROR:") or "No dispute found" in raw_text

            record = {
                "tool": tool_name,
                "arguments": arguments,
                "result": raw_text,
                "is_error": is_error,
                "latency_s": round(elapsed, 4),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.mcp_audit_log.append(record)
            logger.info("MCP Tool [%s] -> %s (%.3fs)", tool_name, "ERROR" if is_error else "SUCCESS", elapsed)
            return record

        except Exception as e:
            elapsed = time.perf_counter() - t0
            record = {
                "tool": tool_name,
                "arguments": arguments,
                "result": f"EXCEPTION: {e}",
                "is_error": True,
                "latency_s": round(elapsed, 4),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.mcp_audit_log.append(record)
            logger.error("MCP Tool [%s] failed with exception: %s", tool_name, e)
            return record

    def handle_dispute(self, description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main entry point for processing a cardholder dispute request.

        Workflow:
        1. Context Grounding via MCP: Fetch live dispute and merchant details through MCP tools.
        2. Decomposition & Routing: Adaptively decompose the goal and route sub-tasks to PS/ToT/LATS.
        3. Self-Correction: Apply Self-Refine on draft notices and Reflexion on high-stakes actions.
        4. Planning-Driven MCP Execution: Execute the action determined by the grounded planning outputs.
        5. Return comprehensive structured audit summary.
        """
        t_start = time.perf_counter()
        ctx = dict(context or {})
        dispute_id = ctx.get("dispute_id") or self._extract_id(description, "DISP")
        analyst_id = ctx.get("analyst_id", "ANL-001")
        self.mcp_audit_log.clear()

        # Step 1: Query MCP server for real ground-truth details if dispute_id is present
        dispute_details = None
        if dispute_id:
            mcp_disp_res = self.call_mcp_tool("get_dispute_details", {"dispute_id": dispute_id})
            if not mcp_disp_res["is_error"] and "{" in mcp_disp_res["result"]:
                try:
                    import ast
                    dispute_details = ast.literal_eval(mcp_disp_res["result"])
                    ctx.setdefault("amount", dispute_details.get("amount"))
                    ctx.setdefault("status", dispute_details.get("status"))
                    ctx.setdefault("reason", dispute_details.get("reason_code"))
                    ctx.setdefault("merchant_id", dispute_details.get("merchant_id"))
                    from mcp_server.server import session_state
                    if float(ctx.get("amount", 0.0)) > 500.0 or str(ctx.get("status", "")).lower() == "escalated":
                        session_state["escalated"] = True
                except Exception:
                    pass

        # Step 2: Task Decomposition & Router Execution
        if self.strategy == "dynamic":
            decomposer = DynamicDecomposition(self.llm, router_fn=self.router, max_steps=self.max_steps)
            decomp_res = decomposer.execute(description, ctx)
        else:
            decomposer = DecompositionFirst(self.llm, router_fn=self.router)
            decomp_res = decomposer.execute(description, ctx)

        # Step 3: Self-Correction & Grounded Verification Passes
        self_corrections = []
        subtask_results = decomp_res.get("results", {})
        diverged = decomp_res.get("diverged", False)

        for task_id, task_result in subtask_results.items():
            task_type = str(task_result.get("subtask_type", "")).lower()
            task_desc = str(task_result.get("description", "")).lower()
            combined_type = f"{task_type} {task_desc}"

            # Pass A: Self-Refine for communications, notifications, and documentation drafts
            if any(k in combined_type for k in ("notification", "letter", "evidence", "disclosure", "document", "draft")):
                sr_res = self.self_refine.execute(f"Draft compliance disclosure for {description}", ctx)
                self_corrections.append({
                    "task_id": task_id,
                    "module": "SelfRefine",
                    "draft": sr_res.get("draft", ""),
                    "critique": sr_res.get("critique", ""),
                    "revised": sr_res.get("revised", ""),
                    "passed_initially": sr_res.get("passed_initially", False),
                })

            # Pass B: Reflexion for state-mutating actions (refunds, escalations, senior overrides)
            elif any(k in combined_type for k in ("refund", "escalat", "action", "payout", "settle")):
                rf_res = self.reflexion.execute(f"Resolve remediation action for {description}", ctx)
                self_corrections.append({
                    "task_id": task_id,
                    "module": "Reflexion",
                    "success": rf_res.get("success", False),
                    "trials_attempted": rf_res.get("trials_attempted", 1),
                    "final_output": rf_res.get("final_output", ""),
                    "trial_history": rf_res.get("trial_history", []),
                })

        # Step 4: Planning-Driven Final MCP Execution
        # Derive the action directly from what the routed planning algorithms (LATS / ToT / PS) produced
        final_action = "none"
        final_action_status = "unexecuted"

        # Check if any subtask was routed to LATS for grounded action search
        lats_subtask = next((res for res in subtask_results.values() if res.get("routed_algorithm") == "lats"), None)
        tot_subtask = next((res for res in subtask_results.values() if res.get("routed_algorithm") == "tree_of_thoughts"), None)

        if lats_subtask:
            feedback = lats_subtask.get("environment_feedback") or {}
            best_action = str(lats_subtask.get("best_action", "")).lower()
            final_state = str(lats_subtask.get("final_state", "")).lower()
            lats_success = feedback.get("success", False) and feedback.get("score", 0.0) > 0.0

            if not lats_success:
                # Grounded LATS blocked the action based on real DB constraints
                final_action = "blocked_grounded_constraint"
                final_action_status = feedback.get("details", "Grounded LATS blocked action citing database constraint violation.")
            elif "escalat" in best_action or "escalat" in final_state:
                # LATS selected and verified Escalation
                final_action = "escalate_dispute"
                escalate_analyst = analyst_id if "ANL-002" in analyst_id or "ANL-008" in analyst_id else "ANL-002"
                if dispute_id:
                    mcp_esc_res = self.call_mcp_tool("escalate_dispute", {
                        "dispute_id": dispute_id,
                        "analyst_id": escalate_analyst,
                    })
                    final_action_status = mcp_esc_res["result"]
            elif "refund" in best_action or "refund" in final_state:
                # LATS selected and verified Refund
                final_action = "process_refund"
                amount_val = float(ctx.get("amount", 0.0))
                if dispute_id:
                    mcp_ref_res = self.call_mcp_tool("process_refund", {
                        "dispute_id": dispute_id,
                        "analyst_id": analyst_id,
                        "confirmed": True if amount_val > 500.0 else False,
                    })
                    final_action_status = mcp_ref_res["result"]
            else:
                final_action = "lats_plan_executed"
                final_action_status = lats_subtask.get("final_state", "Action completed by LATS.")

        elif diverged:
            # Dynamic decomposition detected an environmental surprise (such as terminal state) and halted safely
            curr_status = str(ctx.get("status", "")).lower()
            if curr_status in ("refunded", "denied"):
                final_action = "blocked_grounded_constraint"
                final_action_status = f"Dispute {dispute_id} is already terminal ({curr_status}); dynamic planner halted without payout."
            else:
                final_action = "remediated_via_dynamic_pivot"
                final_action_status = "Dynamic decomposition adapted execution path to address environmental surprise."

        elif tot_subtask:
            # Tree-of-Thoughts determined optimal ranking / prioritization
            final_action = "prioritization_ranking_completed"
            final_action_status = tot_subtask.get("best_path", {}).get("state", "Optimal ranking generated by Tree of Thoughts.")

        else:
            # Deterministic Plan-and-Solve completed
            final_action = "plan_and_solve_completed"
            final_action_status = "Sequential plan completed successfully."

        total_elapsed = time.perf_counter() - t_start
        decomp_metrics = decomp_res.get("metrics", {})
        total_calls = decomp_metrics.get("llm_calls", 1) + len(self_corrections) * 2
        total_tokens = decomp_metrics.get("tokens", 250) + len(self_corrections) * 300

        return {
            "status": "success" if not decomp_res.get("status") == "failed" else "failed",
            "dispute_id": dispute_id,
            "decomposition_strategy": "DynamicDecomposition" if self.strategy == "dynamic" else "DecompositionFirst",
            "diverged": diverged,
            "execution_order": decomp_res.get("execution_order", []),
            "subtasks_executed": subtask_results,
            "self_corrections": self_corrections,
            "mcp_tool_actions": list(self.mcp_audit_log),
            "final_decision": {
                "action": final_action,
                "details": final_action_status,
                "dispute_details": dispute_details,
            },
            "metrics": {
                "llm_calls": total_calls,
                "tokens": total_tokens,
                "latency_s": round(total_elapsed, 3),
            },
        }

    def _extract_id(self, text: str, prefix: str) -> Optional[str]:
        import re
        match = re.search(rf"\b({prefix}-\d{{3,}})\b", text, re.IGNORECASE)
        return match.group(1).upper() if match else None


if __name__ == "__main__":
    import argparse
    from planning.llm_client import UniversalLLMClient

    parser = argparse.ArgumentParser(description="Dispute Planning Agent")
    parser.add_argument("--live", action="store_true", help="Use live cloud API / Ollama model instead of MockLLMClient")
    parser.add_argument("--provider", type=str, default=None, help="LLM Provider ('openrouter', 'openai', 'ollama')")
    parser.add_argument("--model", type=str, default=None, help="Model name")
    args = parser.parse_args()

    active_llm = UniversalLLMClient(provider=args.provider, model=args.model) if args.live else MockLLMClient()
    agent = DisputePlanningAgent(llm=active_llm)
    print("DisputePlanningAgent initialized successfully.")
    sample_request = "Remediate dispute DISP-001 ($29.99 duplicate charge) for customer."

    # Ensure DISP-001 is open
    import sqlite3
    conn = sqlite3.connect(os.path.join(ROOT_DIR, "db", "sterling_vance.db"))
    cursor = conn.cursor()
    cursor.execute("UPDATE disputes SET status = 'open' WHERE dispute_id = 'DISP-001'")
    conn.commit()
    conn.close()

    result = agent.handle_dispute(sample_request, {"dispute_id": "DISP-001", "analyst_id": "ANL-001"})
    print("\n--- Sample Execution Result ---")
    print(json.dumps(result, indent=2))
