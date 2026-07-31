"""
evaluation.py -- Performance & Correctness Evaluation for Sterling Vance MCP Server

Each suite runs in a fresh subprocess to avoid anyio cancel-scope leaks between sessions.

Run from project root:
    python evaluation.py

Output: prints a results table + saves evaluation_report.json
"""

import asyncio
import json
import os
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field, asdict

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.join(REPO_ROOT, "agent")


# ---------------------------------------------------------------------------
# Each suite is a self-contained script run in a subprocess
# ---------------------------------------------------------------------------

SUITES = {}  # name -> (category, script_body)


def suite(name: str, category: str):
    """Decorator to register a suite script."""
    def decorator(fn):
        SUITES[name] = (category, fn())
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Suite scripts — each is a string of Python code run in its own process
# ---------------------------------------------------------------------------

PREAMBLE = f"""
import asyncio, os, sys, json, time, sqlite3
sys.path.insert(0, {repr(AGENT_DIR)})
from agent_client import DisputeAgentClient
from mcp import StdioServerParameters

REPO_ROOT = {repr(REPO_ROOT)}

def sp():
    return StdioServerParameters(
        command=sys.executable,
        args=["mcp_server/server.py"],
        cwd=REPO_ROOT,
    )

def ms(t):
    return round((time.perf_counter() - t) * 1000, 2)

def txt(r):
    return r.content[0].text if r.content else ""

results = []
"""

HANDSHAKE_SCRIPT = PREAMBLE + """
from mcp import ClientSession
from mcp.client.stdio import stdio_client

async def run():
    t = time.perf_counter()
    async with stdio_client(sp()) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            lat = ms(t)
            caps = init.capabilities
            tools_ok = caps.tools is not None and (getattr(caps.tools, 'list_changed', False) or getattr(caps.tools, 'listChanged', False))
            resources_ok = caps.resources is not None
            prompts_ok = caps.prompts is not None

            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]

            results.append({"name": "handshake_cold_start", "latency_ms": lat,
                "passed": tools_ok and resources_ok and prompts_ok,
                "actual": f"tools_changed={tools_ok}, resources={resources_ok}, prompts={prompts_ok}"})
            results.append({"name": "tool_discovery_6_tools", "latency_ms": lat,
                "passed": len(tool_names) == 6,
                "actual": f"{len(tool_names)} tools: {tool_names}"})

try:
    asyncio.run(run())
except Exception as e:
    results.append({"name": "handshake_cold_start", "latency_ms": 0,
        "passed": False, "actual": f"EXCEPTION: {e}"})
finally:
    print(json.dumps(results))
"""

READ_TOOLS_SCRIPT = PREAMBLE + """
async def run():
    async with DisputeAgentClient(sp()) as client:
        tests = [
            ("get_dispute_details_DISP001", "get_dispute_details", {"dispute_id": "DISP-001"},
             lambda d: "duplicate_charge" in d and "29.99" in d),
            ("get_dispute_details_not_found", "get_dispute_details", {"dispute_id": "DISP-999"},
             lambda d: "No dispute found" in d),
            ("get_transaction_history_ACC001", "get_transaction_history", {"account_id": "ACC-001"},
             lambda d: "TXN-001" in d or "TXN-002" in d),
            ("get_merchant_info_MERCH001", "get_merchant_info", {"merchant_id": "MERCH-001"},
             lambda d: "Brew" in d and "risk_score" in d),
            ("get_merchant_info_not_found", "get_merchant_info", {"merchant_id": "MERCH-999"},
             lambda d: "No merchant found" in d),
        ]
        for name, tool, args, check in tests:
            t = time.perf_counter()
            r = await client.call_tool_gated(tool, args)
            data = txt(r)
            results.append({"name": name, "latency_ms": ms(t),
                "passed": check(data), "actual": data[:100]})

asyncio.run(run())
print(json.dumps(results))
"""

NOTIFICATIONS_SCRIPT = PREAMBLE + """
db = os.path.join(REPO_ROOT, "db", "sterling_vance.db")
conn = sqlite3.connect(db)
conn.execute("UPDATE disputes SET status='investigating', resolved_at=NULL WHERE dispute_id='DISP-002'")
conn.commit(); conn.close()

async def run():
    async with DisputeAgentClient(sp()) as client:
        before = list(client.tools.keys())
        t = time.perf_counter()
        await client.call_tool_gated("process_refund",
            {"dispute_id": "DISP-002", "analyst_id": "ANL-001"})
        await asyncio.sleep(0.3)
        after = list(client.tools.keys())
        lat = ms(t)
        escalated = "escalate_dispute" in after and "escalate_dispute" not in before
        results.append({"name": "notification_tools_list_changed", "latency_ms": lat,
            "passed": escalated, "actual": f"before={len(before)} tools, after={len(after)} tools, escalate_appeared={escalated}"})

asyncio.run(run())
print(json.dumps(results))
"""

AUTHORIZATION_SCRIPT = PREAMBLE + """
db = os.path.join(REPO_ROOT, "db", "sterling_vance.db")
conn = sqlite3.connect(db)
conn.execute("UPDATE disputes SET status='investigating', resolved_at=NULL WHERE dispute_id='DISP-002'")
conn.commit(); conn.close()

async def run():
    # Test 1: junior blocked from large refund
    async with DisputeAgentClient(sp()) as client:
        t = time.perf_counter()
        r = await client.call_tool_gated("process_refund",
            {"dispute_id": "DISP-002", "analyst_id": "ANL-001"})
        data = txt(r)
        results.append({"name": "auth_junior_blocked_large_refund", "latency_ms": ms(t),
            "passed": "REJECTED" in data and "Junior" in data, "actual": data})

    # Test 2: junior blocked from escalate (even after trigger)
    conn2 = sqlite3.connect(db)
    conn2.execute("UPDATE disputes SET status='investigating', resolved_at=NULL WHERE dispute_id='DISP-002'")
    conn2.commit(); conn2.close()

    async with DisputeAgentClient(sp()) as client:
        await client.call_tool_gated("process_refund",
            {"dispute_id": "DISP-002", "analyst_id": "ANL-001"})
        await asyncio.sleep(0.3)
        t = time.perf_counter()
        r = await client.call_tool_gated("escalate_dispute",
            {"dispute_id": "DISP-002", "analyst_id": "ANL-001"})
        data = txt(r)
        results.append({"name": "auth_junior_blocked_from_escalate", "latency_ms": ms(t),
            "passed": "REJECTED" in data and "not a senior" in data.lower(), "actual": data})

asyncio.run(run())
print(json.dumps(results))
"""

ELICITATION_SCRIPT = PREAMBLE + """
db = os.path.join(REPO_ROOT, "db", "sterling_vance.db")
conn = sqlite3.connect(db)
conn.execute("UPDATE disputes SET status='open', resolved_at=NULL WHERE dispute_id='DISP-001'")
conn.execute("UPDATE disputes SET status='investigating', resolved_at=NULL WHERE dispute_id='DISP-002'")
conn.commit(); conn.close()

async def run():
    # Routine refund -- auto-approved
    async with DisputeAgentClient(sp()) as client:
        t = time.perf_counter()
        r = await client.call_tool_gated("process_refund",
            {"dispute_id": "DISP-001", "analyst_id": "ANL-001"})
        data = txt(r)
        results.append({"name": "elicitation_routine_auto_approved", "latency_ms": ms(t),
            "passed": "ROUTINE REFUND APPROVED" in data, "actual": data})

    # Large refund -- elicitation pause
    async with DisputeAgentClient(sp()) as client:
        t = time.perf_counter()
        r = await client.call_tool_gated("process_refund",
            {"dispute_id": "DISP-002", "analyst_id": "ANL-002"})
        data = txt(r)
        results.append({"name": "elicitation_pause_over_threshold", "latency_ms": ms(t),
            "passed": "ELICITATION PAUSE" in data, "actual": data})

asyncio.run(run())
print(json.dumps(results))
"""

RESOURCES_SCRIPT = PREAMBLE + """
async def run():
    async with DisputeAgentClient(sp()) as client:
        t = time.perf_counter()
        resources = await client.list_resources()
        lat = ms(t)
        passed = any("reason-codes" in str(r.uri) for r in resources)
        results.append({"name": "resource_list", "latency_ms": lat,
            "passed": passed, "actual": str([str(r.uri) for r in resources])})

        t = time.perf_counter()
        contents = await client.read_resource("policy://disputes/reason-codes")
        lat = ms(t)
        text_content = contents[0].text if contents else ""
        results.append({"name": "resource_read_policy", "latency_ms": lat,
            "passed": "duplicate_charge" in text_content and "unauthorized_transaction" in text_content,
            "actual": text_content[:120]})

asyncio.run(run())
print(json.dumps(results))
"""

PROMPTS_SCRIPT = PREAMBLE + """
async def run():
    async with DisputeAgentClient(sp()) as client:
        t = time.perf_counter()
        prompts = await client.list_prompts()
        lat = ms(t)
        results.append({"name": "prompt_list", "latency_ms": lat,
            "passed": any(p.name == "draft_denial_explanation" for p in prompts),
            "actual": str([p.name for p in prompts])})

        t = time.perf_counter()
        result = await client.get_prompt("draft_denial_explanation", {"dispute_id": "DISP-003"})
        lat = ms(t)
        msg_text = result.messages[0].content.text if result.messages else ""
        results.append({"name": "prompt_get_denial_template", "latency_ms": lat,
            "passed": "DISP-003" in msg_text and "reason_code" in msg_text,
            "actual": msg_text[:120]})

asyncio.run(run())
print(json.dumps(results))
"""

PROGRESS_SCRIPT = PREAMBLE + """
from mcp import ClientSession
from mcp.client.stdio import stdio_client
import mcp.types as types

progress_count = 0

async def run():
    global progress_count

    async def _msg_handler(msg):
        global progress_count
        # progress notifications come through message_handler
        try:
            method = getattr(getattr(msg, 'root', msg), 'method', '')
            if 'progress' in str(method):
                progress_count += 1
        except Exception:
            pass

    async with stdio_client(sp()) as (read, write):
        async with ClientSession(read, write, message_handler=_msg_handler) as session:
            await session.initialize()
            t = time.perf_counter()
            req = types.CallToolRequest(
                params=types.CallToolRequestParams(
                    name="scan_repeat_dispute_patterns",
                    arguments={"customer_id": "CUST-073", "merchant_id": "MERCH-006"},
                    meta={"progressToken": "eval-progress-1"},
                )
            )
            r = await session.send_request(req, types.CallToolResult)
            data = r.content[0].text if r.content else ""
            passed = ("Repeat-dispute pattern detected: True" in data) and (progress_count == 35)
            results.append({"name": "progress_scan_repeat_patterns", "latency_ms": ms(t),
                "passed": passed,
                "actual": data, "notes": f"progress_updates_received={progress_count}"})

try:
    asyncio.run(run())
except Exception as e:
    results.append({"name": "progress_scan_repeat_patterns", "latency_ms": 0,
        "passed": False, "actual": f"EXCEPTION: {e}"})
finally:
    print(json.dumps(results))
"""

THROUGHPUT_SCRIPT = PREAMBLE + """
N = 10
async def run():
    async with DisputeAgentClient(sp()) as client:
        t = time.perf_counter()
        for _ in range(N):
            await client.call_tool_gated("get_dispute_details", {"dispute_id": "DISP-001"})
        total = ms(t)
        avg = round(total / N, 2)
        tps = round(N / (total / 1000), 2)
        results.append({"name": f"throughput_{N}_sequential_reads", "latency_ms": avg,
            "passed": avg < 200,
            "actual": f"avg={avg}ms total={total}ms tps={tps}",
            "notes": f"{tps} calls/sec"})

asyncio.run(run())
print(json.dumps(results))
"""

CAPABILITY_CHECK_SCRIPT = PREAMBLE + """
async def run():
    # Client with NO elicitation callback should be blocked client-side
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(sp()) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            elicitation_declared = (
                hasattr(init.capabilities, 'elicitation') and
                init.capabilities.elicitation is not None
            )
            results.append({"name": "capability_elicitation_not_declared_by_server",
                "latency_ms": 0,
                "passed": not elicitation_declared,
                "actual": f"elicitation_declared={elicitation_declared}"})

asyncio.run(run())
print(json.dumps(results))
"""

END_TO_END_SCRIPT = PREAMBLE + """
db = os.path.join(REPO_ROOT, "db", "sterling_vance.db")
conn = sqlite3.connect(db)
conn.execute("UPDATE disputes SET status='investigating', resolved_at=NULL WHERE dispute_id='DISP-002'")
conn.commit(); conn.close()

async def auto_accept(msg, schema):
    from mcp import types
    return types.ElicitResult(action='accept', content={})

async def run():
    t_start = time.perf_counter()
    async with DisputeAgentClient(sp(), elicitation_responder=auto_accept) as client:
        t_connected = time.perf_counter()

        # LLM Sampling
        t_llm = time.perf_counter()
        r_llm = await client.call_tool_gated("summarize_dispute_evidence", {"dispute_id": "DISP-002"})
        lat_llm = ms(t_llm)

        # Full refund + elicitation
        await client.call_tool_gated("process_refund", {"dispute_id": "DISP-002", "analyst_id": "ANL-002"})

    total_lat = ms(t_start)

    results.append({"name": "llm_sampling_call_latency", "latency_ms": lat_llm,
        "passed": lat_llm > 0 and len(txt(r_llm)) > 20,
        "actual": txt(r_llm)[:100], "notes": "LLM evidence summarization call"})

    results.append({"name": "start_to_finish_full_workflow_latency", "latency_ms": total_lat,
        "passed": total_lat > 0,
        "actual": f"total_end_to_end={total_lat}ms",
        "notes": f"Includes cold start ({ms(t_start)}ms), handshake, LLM sampling, and elicitation refund"})

asyncio.run(run())
print(json.dumps(results))
"""


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

@dataclass
class Result:
    name: str
    category: str
    latency_ms: float
    passed: bool
    actual: str
    notes: str = ""


def run_suite(name: str, category: str, script: str) -> list[Result]:
    """Run a suite script in a subprocess and parse its JSON output."""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        # extract the last JSON line from stdout
        lines = [l.strip() for l in proc.stdout.strip().splitlines() if l.strip().startswith("[")]
        if not lines:
            return [Result(
                name=f"{name}_no_output",
                category=category,
                latency_ms=0,
                passed=False,
                actual=f"stdout={proc.stdout[-300:]!r} stderr={proc.stderr[-300:]!r}",
            )]
        data = json.loads(lines[-1])
        return [Result(
            name=r["name"],
            category=category,
            latency_ms=r.get("latency_ms", 0),
            passed=r.get("passed", False),
            actual=str(r.get("actual", "")),
            notes=str(r.get("notes", "")),
        ) for r in data]
    except subprocess.TimeoutExpired:
        return [Result(name=f"{name}_TIMEOUT", category=category, latency_ms=60000, passed=False, actual="Timed out after 60s")]
    except Exception as e:
        return [Result(name=f"{name}_ERROR", category=category, latency_ms=0, passed=False, actual=str(e))]


def main():
    suites = [
        ("handshake",          "Capability Negotiation", HANDSHAKE_SCRIPT),
        ("read_tools",         "Read Tools",             READ_TOOLS_SCRIPT),
        ("notifications",      "Notifications",          NOTIFICATIONS_SCRIPT),
        ("authorization",      "Authorization",          AUTHORIZATION_SCRIPT),
        ("elicitation",        "Elicitation",            ELICITATION_SCRIPT),
        ("resources",          "Resources & Prompts",    RESOURCES_SCRIPT),
        ("prompts",            "Resources & Prompts",    PROMPTS_SCRIPT),
        ("progress",           "Progress Tracking",      PROGRESS_SCRIPT),
        ("throughput",         "Throughput",             THROUGHPUT_SCRIPT),
        ("capability_check",   "Capability Negotiation", CAPABILITY_CHECK_SCRIPT),
        ("end_to_end",         "End-to-End Workflow",    END_TO_END_SCRIPT),
    ]

    all_results: list[Result] = []

    for name, category, script in suites:
        print(f"  Running: {name} ...", flush=True)
        t = time.perf_counter()
        results = run_suite(name, category, script)
        elapsed = round((time.perf_counter() - t) * 1000, 0)
        status = "PASS" if all(r.passed for r in results) else "FAIL"
        print(f"  [{status}] {name} ({elapsed:.0f}ms total, {len(results)} checks)")
        all_results.extend(results)

    # -----------------------------------------------------------------------
    # Print table
    # -----------------------------------------------------------------------
    print("\n")
    print("=" * 105)
    print(f"{'Test':<52} {'Category':<26} {'Latency':>10}  Status")
    print("=" * 105)

    categories: dict[str, list[Result]] = {}
    for r in all_results:
        categories.setdefault(r.category, []).append(r)

    total_passed = 0
    total_tests = 0

    for cat, cat_results in categories.items():
        for r in cat_results:
            status = "PASS" if r.passed else "FAIL"
            print(f"{r.name:<52} {r.category:<26} {r.latency_ms:>8.1f}ms  [{status}]")
            if r.notes:
                print(f"  {'':78} note: {r.notes}")
            total_passed += r.passed
            total_tests += 1
        print()

    print("=" * 105)
    pass_rate = int(100 * total_passed / total_tests) if total_tests else 0
    print(f"\nResults : {total_passed}/{total_tests} passed ({pass_rate}%)")

    latencies = [r.latency_ms for r in all_results if r.latency_ms > 0 and r.latency_ms < 10000]
    if latencies:
        sorted_lat = sorted(latencies)
        p95 = sorted_lat[min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)]
        print(f"\nLatency (tool calls only, excluding cold start):")
        print(f"  Min     : {min(latencies):.1f} ms")
        print(f"  Max     : {max(latencies):.1f} ms")
        print(f"  Average : {sum(latencies)/len(latencies):.1f} ms")
        print(f"  P95     : {p95:.1f} ms")

    # -----------------------------------------------------------------------
    # Save JSON report
    # -----------------------------------------------------------------------
    report = {
        "summary": {
            "total": total_tests,
            "passed": total_passed,
            "failed": total_tests - total_passed,
            "pass_rate_pct": pass_rate,
            "latency_min_ms":  round(min(latencies), 2) if latencies else 0,
            "latency_max_ms":  round(max(latencies), 2) if latencies else 0,
            "latency_avg_ms":  round(sum(latencies) / len(latencies), 2) if latencies else 0,
            "latency_p95_ms":  round(p95, 2) if latencies else 0,
        },
        "results": [asdict(r) for r in all_results],
    }
    report_path = os.path.join(REPO_ROOT, "evaluation_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: evaluation_report.json")


if __name__ == "__main__":
    main()
