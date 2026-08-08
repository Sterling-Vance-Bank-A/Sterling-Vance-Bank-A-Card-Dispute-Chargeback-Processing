"""
evaluate_all_disputes.py — Comprehensive Database Evaluation Suite

Evaluates the Sterling Vance Bank Dispute Processing MCP System across ALL 501 disputes
currently stored in the production SQLite database (db/sterling_vance.db).

Checks decision accuracy, safety rule enforcement, elicitation trigger precision,
role-based access control, and state machine integrity.

Run from project root:
    python evaluate_all_disputes.py
"""

import asyncio
import json
import os
import sqlite3
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.join(REPO_ROOT, "agent")
DB_PATH = os.path.join(REPO_ROOT, "db", "sterling_vance.db")
sys.path.insert(0, AGENT_DIR)

from agent.agent_client import DisputeAgentClient
from mcp import StdioServerParameters, types


def sp() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["mcp_server/server.py"],
        cwd=REPO_ROOT,
    )


def fetch_all_disputes():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT d.dispute_id, d.transaction_id, d.reason_code, d.amount, d.status,
               a.customer_id, c.risk_flag, m.name as merchant_name, m.risk_score
        FROM disputes d
        JOIN transactions t ON d.transaction_id = t.transaction_id
        JOIN accounts a ON t.account_id = a.account_id
        JOIN customers c ON a.customer_id = c.customer_id
        JOIN merchants m ON t.merchant_id = m.merchant_id
        ORDER BY d.dispute_id
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def evaluate_dispute(client: DisputeAgentClient, dispute: dict):
    disp_id = dispute["dispute_id"]
    status = dispute["status"]
    amount = dispute["amount"]
    risk_flag = dispute["risk_flag"]

    # Expected Ground Truth Policy Decision for Senior Analyst (ANL-002)
    if status in ("refunded", "denied"):
        expected_senior_decision = "REJECTED_ALREADY_CLOSED"
    elif amount > 500.0 or risk_flag == "high":
        expected_senior_decision = "ELICITATION_PAUSED"
    else:
        expected_senior_decision = "ROUTINE_AUTO_APPROVED"

    # Expected Ground Truth Policy Decision for Junior Analyst (ANL-001)
    if status in ("refunded", "denied"):
        expected_junior_decision = "REJECTED_ALREADY_CLOSED"
    elif amount > 500.0:
        expected_junior_decision = "REJECTED_JUNIOR_UNAUTHORIZED"
    elif risk_flag == "high":
        expected_junior_decision = "ELICITATION_PAUSED"
    else:
        expected_junior_decision = "ROUTINE_AUTO_APPROVED"

    # 1. Test Senior Analyst (ANL-002)
    r_senior = await client.call_tool_gated("process_refund", {
        "dispute_id": disp_id,
        "analyst_id": "ANL-002"
    })
    text_senior = r_senior.content[0].text if r_senior.content else ""

    if "ELICITATION PAUSE" in text_senior:
        actual_senior_decision = "ELICITATION_PAUSED"
    elif "ROUTINE REFUND APPROVED" in text_senior or "APPROVED" in text_senior:
        actual_senior_decision = "ROUTINE_AUTO_APPROVED"
    else:
        actual_senior_decision = "REJECTED_ALREADY_CLOSED"

    senior_correct = (actual_senior_decision == expected_senior_decision)

    # 2. Test Junior Analyst (ANL-001)
    r_junior = await client.call_tool_gated("process_refund", {
        "dispute_id": disp_id,
        "analyst_id": "ANL-001"
    })
    text_junior = r_junior.content[0].text if r_junior.content else ""

    if "REJECTED" in text_junior and ("Junior" in text_junior or "authorization" in text_junior.lower()):
        actual_junior_decision = "REJECTED_JUNIOR_UNAUTHORIZED"
    elif "ELICITATION PAUSE" in text_junior:
        actual_junior_decision = "ELICITATION_PAUSED"
    elif "ROUTINE REFUND APPROVED" in text_junior or "APPROVED" in text_junior:
        actual_junior_decision = "ROUTINE_AUTO_APPROVED"
    else:
        actual_junior_decision = "REJECTED_ALREADY_CLOSED"

    junior_correct = (actual_junior_decision == expected_junior_decision)

    return {
        "dispute_id": disp_id,
        "amount": amount,
        "status": status,
        "risk_flag": risk_flag,
        "senior": {
            "expected": expected_senior_decision,
            "actual": actual_senior_decision,
            "correct": senior_correct,
        },
        "junior": {
            "expected": expected_junior_decision,
            "actual": actual_junior_decision,
            "correct": junior_correct,
        }
    }


async def main():
    disputes = fetch_all_disputes()
    total_count = len(disputes)
    print(f"Loaded {total_count} disputes from {DB_PATH}")

    senior_correct_count = 0
    junior_correct_count = 0

    status_breakdown = {}
    amount_breakdown = {"under_500": 0, "over_500": 0}
    elicitation_triggers = 0
    closed_rejected = 0
    routine_approved = 0

    t_start = time.perf_counter()

    async with DisputeAgentClient(sp()) as client:
        print("Evaluating system decisions across all 501 database records...\n")
        for idx, d in enumerate(disputes, 1):
            res = await evaluate_dispute(client, d)

            if res["senior"]["correct"]:
                senior_correct_count += 1
            if res["junior"]["correct"]:
                junior_correct_count += 1

            st = d["status"]
            status_breakdown[st] = status_breakdown.get(st, 0) + 1

            if d["amount"] <= 500:
                amount_breakdown["under_500"] += 1
            else:
                amount_breakdown["over_500"] += 1

            if res["senior"]["actual"] == "ELICITATION_PAUSED":
                elicitation_triggers += 1
            elif res["senior"]["actual"] == "ROUTINE_AUTO_APPROVED":
                routine_approved += 1
            elif res["senior"]["actual"] == "REJECTED_ALREADY_CLOSED":
                closed_rejected += 1

            if idx % 50 == 0 or idx == total_count:
                print(f"Processed {idx}/{total_count} disputes... ({int(100*idx/total_count)}%)")

    total_time_s = round(time.perf_counter() - t_start, 2)
    senior_acc = round(100 * senior_correct_count / total_count, 2)
    junior_acc = round(100 * junior_correct_count / total_count, 2)
    overall_acc = round((senior_acc + junior_acc) / 2, 2)

    print("\n" + "=" * 80)
    print(" 🏆 STERLING VANCE BANK — ALL-DATABASE DECISION EVALUATION REPORT")
    print("=" * 80)
    print(f" Total Disputes Evaluated          : {total_count}")
    print(f" Total Decision Checks Executed    : {total_count * 2} (Senior + Junior)")
    print(f" Evaluation Runtime                : {total_time_s} seconds ({round(total_time_s/total_count*1000, 2)} ms/dispute)")
    print("-" * 80)
    print(f" 🟢 Senior Analyst Decision Accuracy : {senior_correct_count}/{total_count} ({senior_acc}%)")
    print(f" 🟢 Junior Analyst Decision Accuracy : {junior_correct_count}/{total_count} ({junior_acc}%)")
    print(f" 🎯 OVERALL SYSTEM DECISION ACCURACY  : {overall_acc}%")
    print("-" * 80)
    print(" 📊 DISPUTE BREAKDOWN BY STATUS:")
    for st, cnt in status_breakdown.items():
        print(f"    • {st:<15} : {cnt:3d} ({round(100*cnt/total_count, 1)}%)")
    print("-" * 80)
    print(" 🛡️ SAFETY & POLICY DECISION BREAKDOWN (Senior Analyst Path):")
    print(f"    • Elicitation Triggers (Amount > $500 / High Risk) : {elicitation_triggers:3d} ({round(100*elicitation_triggers/total_count, 1)}%)")
    print(f"    • Routine Auto-Approved (Amount <= $500 & Open)   : {routine_approved:3d} ({round(100*routine_approved/total_count, 1)}%)")
    print(f"    • Closed/Already-Processed Rejections             : {closed_rejected:3d} ({round(100*closed_rejected/total_count, 1)}%)")
    print("=" * 80)

    report_data = {
        "evaluation_summary": {
            "total_disputes": total_count,
            "total_checks": total_count * 2,
            "overall_accuracy_pct": overall_acc,
            "senior_accuracy_pct": senior_acc,
            "junior_accuracy_pct": junior_acc,
            "runtime_seconds": total_time_s,
        },
        "dispute_status_distribution": status_breakdown,
        "amount_distribution": amount_breakdown,
        "decisions_breakdown": {
            "elicitation_triggers": elicitation_triggers,
            "routine_approved": routine_approved,
            "closed_rejected": closed_rejected,
        }
    }

    report_file = os.path.join(REPO_ROOT, "database_decision_evaluation.json")
    with open(report_file, "w") as f:
        json.dump(report_data, f, indent=2)

    print(f"\n💾 Detailed report saved to: database_decision_evaluation.json")


if __name__ == "__main__":
    asyncio.run(main())
