import asyncio
import sqlite3
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def reset_db():
    """Reset DISP-002 so this test is repeatable (deterministic)."""
    db_path = os.path.join(os.path.dirname(__file__), "..", "db", "sterling_vance.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE disputes SET status = 'investigating', resolved_at = NULL WHERE dispute_id = 'DISP-002'"
    )
    conn.commit()
    conn.close()


async def main():
    reset_db()

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["mcp_server/server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # --- Step 1: check the tool list BEFORE any escalation trigger ---
            print("=== BEFORE trigger: available tools ===")
            tools_before = await session.list_tools()
            names_before = [t.name for t in tools_before.tools]
            for n in names_before:
                print("-", n)
            print("escalate_dispute visible?", "escalate_dispute" in names_before)
            print()

            # --- Step 2: fire the trigger (junior attempts a large refund) ---
            print("=== Firing trigger: junior analyst attempts large refund on DISP-002 ($899) ===")
            result = await session.call_tool(
                "process_refund", {"dispute_id": "DISP-002", "analyst_id": "ANL-001"}
            )
            for content in result.content:
                print(content.text)
            print()

            # --- Step 3: check the tool list AFTER the trigger, same session, no reconnect ---
            print("=== AFTER trigger: available tools (same session, no reconnect) ===")
            tools_after = await session.list_tools()
            names_after = [t.name for t in tools_after.tools]
            for n in names_after:
                print("-", n)
            print("escalate_dispute visible?", "escalate_dispute" in names_after)


if __name__ == "__main__":
    asyncio.run(main())