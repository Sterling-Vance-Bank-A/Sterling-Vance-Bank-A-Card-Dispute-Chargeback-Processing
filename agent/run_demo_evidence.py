"""
Part 5 (Person C): Test Cases and Demo Evidence.

Fixed, repeatable list of scenarios covering every concern the team needs
proof of, each saved as a distinct evidence file under evidence/. Uses
agent_client.DisputeAgentClient throughout, not raw ad-hoc scripts, so the
evidence reflects the real client path an analyst would go through.

Run: python run_demo_evidence.py
(re-run any time — every scenario resets the DB rows it depends on first,
 so results are identical run to run)
"""

import asyncio
import os
import sqlite3

from mcp import StdioServerParameters

from agent_client import DisputeAgentClient

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(REPO_ROOT, "db", "sterling_vance.db")
EVIDENCE_DIR = os.path.join(REPO_ROOT, "evidence")
os.makedirs(EVIDENCE_DIR, exist_ok=True)


def reset_db():
    """Put DISP-001 / DISP-002 back to their seeded state so every
    scenario below produces the same result on every run."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE disputes SET status = 'open', resolved_at = NULL WHERE dispute_id = 'DISP-001'")
    conn.execute("UPDATE disputes SET status = 'investigating', resolved_at = NULL WHERE dispute_id = 'DISP-002'")
    conn.commit()
    conn.close()


def save(name: str, text: str):
    path = os.path.join(EVIDENCE_DIR, name)
    with open(path, "w") as f:
        f.write(text)
    print(f"saved: evidence/{name}")


def new_server_params() -> StdioServerParameters:
    # A fresh process per scenario => session_state (escalation flag) starts
    # clean every time, exactly like a brand-new analyst session would.
    return StdioServerParameters(command="python", args=["mcp_server/server.py"], cwd=REPO_ROOT)


async def tc01_handshake_discovery_and_read():
    """What to prove for Part 1: connect, visible handshake, live tool
    discovery, a normal read-only action, end to end. Also doubles as the
    'small routine dispute' scenario."""
    lines = []
    async with DisputeAgentClient(new_server_params()) as client:
        lines.append(f"Server capabilities: {client.server_capabilities}")
        lines.append(f"Discovered tools at connect: {sorted(client.tools.keys())}")

        result = await client.call_tool_gated("get_dispute_details", {"dispute_id": "DISP-001"})
        lines.append("get_dispute_details(DISP-001):")
        for c in result.content:
            lines.append(c.text)

        lines.append("")
        lines.append("Routine small refund — junior analyst, $29.99 dispute:")
        result = await client.call_tool_gated(
            "process_refund", {"dispute_id": "DISP-001", "analyst_id": "ANL-001"}
        )
        for c in result.content:
            lines.append(c.text)

    save("tc01_handshake_discovery_and_routine_refund.txt", "\n".join(lines))


async def tc02_large_dispute_triggers_escalation():
    """Large dispute -> junior rejected, notifications/tools/list_changed
    fires, escalate_dispute becomes visible in the SAME session."""
    lines = []
    async with DisputeAgentClient(new_server_params()) as client:
        lines.append(f"Tools BEFORE trigger: {sorted(client.tools.keys())}")

        result = await client.call_tool_gated(
            "process_refund", {"dispute_id": "DISP-002", "analyst_id": "ANL-001"}
        )
        lines.append("Junior attempts $899 refund on DISP-002:")
        for c in result.content:
            lines.append(c.text)

        # give the ToolListChangedNotification a beat to arrive and be
        # handled by our message_handler before we check
        await asyncio.sleep(0.2)
        lines.append(f"Tools AFTER trigger (no reconnect): {sorted(client.tools.keys())}")
        lines.append(f"escalate_dispute now visible? {'escalate_dispute' in client.tools}")

    save("tc02_large_dispute_escalation_trigger.txt", "\n".join(lines))


async def tc03_unauthorized_escalation_attempt():
    """Unauthorized attempt at a risky action: fire the escalation trigger,
    then have a JUNIOR analyst try to use the senior-only escalate_dispute
    tool that just became visible."""
    lines = []
    async with DisputeAgentClient(new_server_params()) as client:
        await client.call_tool_gated(
            "process_refund", {"dispute_id": "DISP-002", "analyst_id": "ANL-001"}
        )
        await asyncio.sleep(0.2)
        await client.refresh_tools()

        lines.append("escalate_dispute visible after trigger: " + str("escalate_dispute" in client.tools))
        result = await client.call_tool_gated(
            "escalate_dispute", {"dispute_id": "DISP-002", "analyst_id": "ANL-001"}
        )
        lines.append("Junior analyst (ANL-001) attempts escalate_dispute (senior-only):")
        for c in result.content:
            lines.append(c.text)

    save("tc03_unauthorized_action_blocked.txt", "\n".join(lines))


async def tc04_repeat_pattern_and_slow_scan():
    """Covers TWO required scenarios at once: a customer with a
    repeat-dispute pattern, AND the one genuinely slow tool — same tool,
    since scanning dozens of real transactions incrementally IS what makes
    the pattern check slow. Progress updates are logged as they arrive."""
    lines = []
    progress_log = []

    def on_progress(progress, total, message):
        entry = f"[PROGRESS {progress}/{total}] {message}"
        progress_log.append(entry)

    async with DisputeAgentClient(new_server_params()) as client:
        result = await client.call_tool_gated(
            "scan_repeat_dispute_patterns",
            {"customer_id": "CUST-073", "merchant_id": "MERCH-006"},
            progress_callback=on_progress,
        )
        lines.append(f"Progress updates received: {len(progress_log)}")
        lines.extend(progress_log)
        lines.append("")
        lines.append("Final result:")
        for c in result.content:
            lines.append(c.text)

    save("tc04_repeat_pattern_and_slow_scan.txt", "\n".join(lines))


async def tc05_missing_capability_blocked():
    """Client connecting without a needed capability: this server never
    declares elicitation, so a tool call gated on it must be refused
    CLIENT-SIDE, before any request is sent — not silently, not by
    trying anyway."""
    lines = []
    async with DisputeAgentClient(new_server_params()) as client:
        lines.append(f"Server capabilities: {client.server_capabilities}")
        lines.append(f"elicitation declared? {client.supports_capability('elicitation')}")
        try:
            await client.call_tool_gated(
                "process_refund",
                {"dispute_id": "DISP-001", "analyst_id": "ANL-001"},
                requires_capability="elicitation",
            )
            lines.append("ERROR: call was NOT blocked (should not reach here)")
        except PermissionError as e:
            lines.append(f"BLOCKED CLIENT-SIDE, as expected: {e}")

    save("tc05_missing_capability_blocked.txt", "\n".join(lines))


async def tc06_resource_read():
    """A resource being read: fetch the dispute reason-code policy — a
    reference document, not a tool call."""
    lines = []
    async with DisputeAgentClient(new_server_params()) as client:
        resources = await client.list_resources()
        lines.append(f"Discovered resources: {[r.uri for r in resources]}")

        contents = await client.read_resource("policy://disputes/reason-codes")
        for c in contents:
            lines.append("--- policy://disputes/reason-codes (first 400 chars) ---")
            lines.append(c.text[:400])

    save("tc06_resource_read.txt", "\n".join(lines))


async def tc07_prompt_template_used():
    """A prompt template being used: discover draft_denial_explanation and
    fetch it filled in for a real dispute_id."""
    lines = []
    async with DisputeAgentClient(new_server_params()) as client:
        prompts = await client.list_prompts()
        lines.append(f"Discovered prompts: {[p.name for p in prompts]}")

        result = await client.get_prompt("draft_denial_explanation", {"dispute_id": "DISP-003"})
        lines.append(f"Prompt description: {result.description}")
        for m in result.messages:
            lines.append(f"[{m.role}] {m.content.text}")

    save("tc07_prompt_template_used.txt", "\n".join(lines))


async def main():
    reset_db()
    await tc01_handshake_discovery_and_read()
    reset_db()
    await tc02_large_dispute_triggers_escalation()
    reset_db()
    await tc03_unauthorized_escalation_attempt()
    await tc04_repeat_pattern_and_slow_scan()
    await tc05_missing_capability_blocked()
    await tc06_resource_read()
    await tc07_prompt_template_used()
    print("\nAll evidence generated in evidence/")


if __name__ == "__main__":
    asyncio.run(main())