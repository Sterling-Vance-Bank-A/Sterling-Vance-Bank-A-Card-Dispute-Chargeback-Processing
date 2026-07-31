"""
mcp_server/test_edge_cases.py — Comprehensive Edge Case & Boundary Testing Suite

Tests the Sterling Vance Bank MCP Server against security vulnerabilities, input sanitization,
boundary conditions ($500.00 vs $500.01), illegal arguments, non-existent entities,
SQL injection attempts, role escalation bypasses, and invalid resource URIs.

Run from project root:
    python -m unittest mcp_server/test_edge_cases.py
"""

import asyncio
import os
import sqlite3
import sys
import unittest
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO_ROOT, "db", "sterling_vance.db")


def server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["mcp_server/server.py"],
        cwd=REPO_ROOT,
    )


def reset_test_dispute(disp_id: str, status: str, amount: float):
    """Utility to set a dispute to a precise test state."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE disputes SET status = ?, amount = ?, resolved_at = NULL WHERE dispute_id = ?",
        (status, amount, disp_id),
    )
    conn.commit()
    conn.close()


def text(result: Any) -> str:
    return result.content[0].text if result.content else ""


class TestEdgeCases(unittest.IsolatedAsyncioTestCase):

    # ---------------------------------------------------------------------------
    # 1. BOUNDARY VALUE EDGE CASES ($500.00 vs $500.01)
    # ---------------------------------------------------------------------------

    async def test_boundary_exactly_500_dollars_auto_approved(self):
        """Edge Case 1: Amount exactly $500.00 must NOT trigger elicitation (auto-approved)."""
        reset_test_dispute("DISP-001", "open", 500.00)
        async with stdio_client(server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("process_refund", {
                    "dispute_id": "DISP-001",
                    "analyst_id": "ANL-001",
                })
                output = text(res)
                self.assertIn("ROUTINE REFUND APPROVED", output)
                self.assertNotIn("ELICITATION PAUSE", output)

    async def test_boundary_500_dollars_one_cent_triggers_elicitation(self):
        """Edge Case 2: Amount $500.01 MUST trigger elicitation pause."""
        reset_test_dispute("DISP-001", "open", 500.01)
        async with stdio_client(server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("process_refund", {
                    "dispute_id": "DISP-001",
                    "analyst_id": "ANL-002",
                })
                output = text(res)
                self.assertIn("ELICITATION PAUSE", output)

    # ---------------------------------------------------------------------------
    # 2. INPUT SANITIZATION & SQL INJECTION DEFENSES
    # ---------------------------------------------------------------------------

    async def test_sql_injection_attempt_in_dispute_id(self):
        """Edge Case 3: SQL injection payload safely parameterized without corrupting database."""
        payload = "DISP-001'; DROP TABLE disputes;--"
        async with stdio_client(server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("get_dispute_details", {"dispute_id": payload})
                output = text(res)
                self.assertIn("No dispute found", output)

        # Verify DB is unharmed and disputes table still exists
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM disputes").fetchone()[0]
        conn.close()
        self.assertGreater(count, 0)

    async def test_invalid_dispute_id_format_handled_safely(self):
        """Edge Case 4: Malformed dispute ID (e.g. 'BAD_FORMAT') returns safe error message."""
        async with stdio_client(server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("get_dispute_details", {"dispute_id": "BAD_FORMAT"})
                output = text(res)
                self.assertIn("No dispute found", output)

    # ---------------------------------------------------------------------------
    # 3. NON-EXISTENT ENTITY HANDLING
    # ---------------------------------------------------------------------------

    async def test_non_existent_dispute_id_handled_gracefully(self):
        """Edge Case 5: Requesting details for validly formatted but non-existent dispute DISP-99999."""
        async with stdio_client(server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("get_dispute_details", {"dispute_id": "DISP-99999"})
                output = text(res)
                self.assertIn("No dispute found", output)

    async def test_non_existent_analyst_id_rejected(self):
        """Edge Case 6: Non-existent analyst ID (ANL-99999) rejected with Analyst not found."""
        reset_test_dispute("DISP-001", "open", 100.00)
        async with stdio_client(server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("process_refund", {
                    "dispute_id": "DISP-001",
                    "analyst_id": "ANL-99999",
                })
                output = text(res)
                self.assertIn("not found", output.lower())

    # ---------------------------------------------------------------------------
    # 4. REPEAT DISPUTE MUTATION DEFENSES
    # ---------------------------------------------------------------------------

    async def test_double_refund_attempt_blocked(self):
        """Edge Case 7: Attempting to refund an already refunded dispute DISP-003 fails gracefully."""
        reset_test_dispute("DISP-003", "refunded", 450.00)
        async with stdio_client(server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("process_refund", {
                    "dispute_id": "DISP-003",
                    "analyst_id": "ANL-001",
                })
                output = text(res)
                self.assertTrue("cannot process duplicate refund" in output.lower() or "already resolved" in output.lower())

    async def test_denied_dispute_refund_blocked(self):
        """Edge Case 8: Attempting to refund a denied dispute DISP-003 fails gracefully."""
        reset_test_dispute("DISP-003", "denied", 450.00)
        async with stdio_client(server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("process_refund", {
                    "dispute_id": "DISP-003",
                    "analyst_id": "ANL-001",
                })
                output = text(res)
                self.assertTrue("cannot process duplicate refund" in output.lower() or "already resolved" in output.lower())

    # ---------------------------------------------------------------------------
    # 5. RESOURCE & PROMPT LOOKUPS
    # ---------------------------------------------------------------------------

    async def test_invalid_resource_uri_returns_error(self):
        """Edge Case 9: Reading a non-existent resource URI policy://disputes/invalid-path."""
        async with stdio_client(server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                with self.assertRaises(Exception):
                    await session.read_resource("policy://disputes/invalid-path")

    async def test_prompt_template_with_non_existent_dispute_id(self):
        """Edge Case 10: Prompt template handles non-existent dispute_id DISP-99999 gracefully."""
        async with stdio_client(server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.get_prompt("draft_denial_explanation", {"dispute_id": "DISP-99999"})
                output = res.messages[0].content.text if res.messages else ""
                self.assertIn("DISP-99999", output)

    # ---------------------------------------------------------------------------
    # 6. SCAN PATTERN ZERO-MATCH EDGE CASE
    # ---------------------------------------------------------------------------

    async def test_scan_repeat_patterns_zero_matching_transactions(self):
        """Edge Case 11: Scanning customer CUST-001 with merchant MERCH-999 (0 transactions)."""
        async with stdio_client(server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("scan_repeat_dispute_patterns", {
                    "customer_id": "CUST-001",
                    "merchant_id": "MERCH-999",
                })
                output = text(res)
                self.assertIn("Found 0 transaction(s)", output)
                self.assertIn("Repeat-dispute pattern detected: False", output)


if __name__ == "__main__":
    unittest.main()
