import asyncio
import sqlite3
import os
import sys

import mcp.types as types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def auto_approve_elicitation(context, params) -> types.ElicitResult:
    """Deterministic stand-in for a human analyst: auto-approve every
    elicitation/create request so this script runs unattended.

    Without supplying this callback, ClientSession falls back to
    mcp.client.session._default_elicitation_callback, which returns an
    ErrorData("Elicitation not supported") for every request AND — just as
    important — never declares the 'elicitation' capability to the server
    during initialize() in the first place. That's what makes Case 2 below
    fail: server.py calls session.elicit(...) for the $899 refund, and the
    client has no way to answer it.
    """
    print(f"\n[ELICITATION REQUEST FROM SERVER]\n{params.message}\n(auto-approving for this test run)\n")
    return types.ElicitResult(action="accept", content={"approved": True})


async def echo_sampling_response(context, params) -> types.CreateMessageResult:
    """Deterministic stand-in for a real model: echo the evidence prompt
    back as the 'summary' instead of calling out to an LLM.

    Same underlying issue as above — without this callback, ClientSession
    uses _default_sampling_callback, which errors out and never declares
    the 'sampling' capability, so server.py's session.create_message(...)
    call for the evidence summary fails before it ever reaches elicitation.
    """
    last_text = ""
    for m in params.messages:
        block = m.content if not isinstance(m.content, list) else m.content[0]
        if isinstance(block, types.TextContent):
            last_text = block.text
    return types.CreateMessageResult(
        role="assistant",
        content=types.TextContent(type="text", text=last_text),
        model="no-model-attached",
    )


def reset_db():
    """Reset DISP-001 and DISP-002 back to their original seed state so this
    test produces the same result every time it's run (deterministic)."""
    db_path = os.path.join(os.path.dirname(__file__), "..", "db", "sterling_vance.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE disputes SET status = 'investigating', resolved_at = NULL WHERE dispute_id = 'DISP-002'"
    )
    conn.execute(
        "UPDATE disputes SET status = 'open', resolved_at = NULL WHERE dispute_id = 'DISP-001'"
    )
    conn.commit()
    conn.close()


async def main():
    reset_db()  # Ensures repeatable results across multiple runs

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["mcp_server/server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(
            read,
            write,
            elicitation_callback=auto_approve_elicitation,
            sampling_callback=echo_sampling_response,
        ) as session:
            await session.initialize()

            # --- Case 1: Junior analyst tries a large refund (DISP-002, $899) — should be REJECTED ---
            print("=== Case 1: Junior analyst (ANL-001) attempts large refund on DISP-002 ($899) ===")
            result = await session.call_tool(
                "process_refund", {"dispute_id": "DISP-002", "analyst_id": "ANL-001"}
            )
            for content in result.content:
                print(content.text)
            print()

            # --- Case 2: Senior analyst approves the same large refund — should be APPROVED ---
            print("=== Case 2: Senior analyst (ANL-002) attempts same refund on DISP-002 ===")
            result = await session.call_tool(
                "process_refund", {"dispute_id": "DISP-002", "analyst_id": "ANL-002"}
            )
            for content in result.content:
                print(content.text)
            print()

            # --- Case 3: Try refunding the SAME dispute again — should be REJECTED (already resolved) ---
            print("=== Case 3: Attempt to refund DISP-002 again (already resolved) ===")
            result = await session.call_tool(
                "process_refund", {"dispute_id": "DISP-002", "analyst_id": "ANL-002"}
            )
            for content in result.content:
                print(content.text)
            print()

            # --- Case 4: Small refund by a junior analyst (DISP-001, $29.99) — should be APPROVED ---
            print("=== Case 4: Junior analyst (ANL-001) approves small refund on DISP-001 ($29.99) ===")
            result = await session.call_tool(
                "process_refund", {"dispute_id": "DISP-001", "analyst_id": "ANL-001"}
            )
            for content in result.content:
                print(content.text)


if __name__ == "__main__":
    asyncio.run(main())