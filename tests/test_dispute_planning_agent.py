"""
Unit tests for DisputePlanningAgent (agent/dispute_planning_agent.py)
"""

import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
MCP_SERVER_DIR = os.path.join(ROOT_DIR, "mcp_server")
if MCP_SERVER_DIR not in sys.path:
    sys.path.insert(0, MCP_SERVER_DIR)

from agent.dispute_planning_agent import DisputePlanningAgent
from planning import GroundedDisputeEnvironment
from planning.benchmark import MockLLMClient


class TestDisputePlanningAgent(unittest.TestCase):
    def setUp(self):
        self.llm = MockLLMClient()
        self.env = GroundedDisputeEnvironment()
        self.agent = DisputePlanningAgent(llm=self.llm, environment=self.env, strategy="dynamic")
        # Ensure test disputes are in expected initial states
        import sqlite3
        conn = sqlite3.connect(os.path.join(ROOT_DIR, "db", "sterling_vance.db"))
        cursor = conn.cursor()
        cursor.execute("UPDATE disputes SET status = 'open' WHERE dispute_id = 'DISP-001'")
        cursor.execute("UPDATE disputes SET status = 'investigating' WHERE dispute_id = 'DISP-002'")
        conn.commit()
        conn.close()

    def test_handle_routine_refund(self):
        res = self.agent.handle_dispute(
            "Remediate routine low-value duplicate charge dispute DISP-001 ($29.99).",
            {"dispute_id": "DISP-001", "analyst_id": "ANL-001"},
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["dispute_id"], "DISP-001")
        self.assertEqual(res["decomposition_strategy"], "DynamicDecomposition")
        self.assertIn("mcp_tool_actions", res)
        self.assertTrue(len(res["mcp_tool_actions"]) >= 1)
        self.assertEqual(res["final_decision"]["action"], "process_refund")

    def test_handle_terminal_dispute_blocks_safe(self):
        res = self.agent.handle_dispute(
            "Remediate dispute DISP-003 ($150.00) claiming duplicate charge.",
            {"dispute_id": "DISP-003", "analyst_id": "ANL-001", "status": "refunded"},
        )
        self.assertEqual(res["final_decision"]["action"], "blocked_grounded_constraint")
        self.assertIn("already terminal", res["final_decision"]["details"])

    def test_handle_high_value_escalation(self):
        res = self.agent.handle_dispute(
            "Escalate dispute DISP-002 ($899.00) unauthorized transaction to card network.",
            {"dispute_id": "DISP-002", "analyst_id": "ANL-002", "amount": 899.0},
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["final_decision"]["action"], "escalate_dispute")


if __name__ == "__main__":
    unittest.main()
