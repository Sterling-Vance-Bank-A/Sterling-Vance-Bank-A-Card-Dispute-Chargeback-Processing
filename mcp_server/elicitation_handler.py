import os
import sqlite3

# Absolute path to Sterling Vance database
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "db", "sterling_vance.db"))
ELICITATION_THRESHOLD = 500.00


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def process_refund_with_elicitation(dispute_id: str, analyst_id: str, confirmed: bool | None = None) -> dict:
    """
    Rule:
    1. Refunds <= $500.00 proceed immediately.
    2. Refunds > $500.00 trigger an explicit Elicitation Pause for human sign-off.
    3. If confirmed is True -> Refund APPROVED and executed in database.
    4. If confirmed is False -> Refund DECLINED & BLOCKED, database state remains UNCHANGED.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Fetch dispute record
    cursor.execute("SELECT * FROM disputes WHERE dispute_id = ?", (dispute_id,))
    dispute = cursor.fetchone()
    if dispute is None:
        conn.close()
        return {"status": "error", "message": f"Dispute {dispute_id} not found."}

    # 2. Defensive check: reject double refunds
    if dispute["status"] in ("refunded", "denied"):
        conn.close()
        return {
            "status": "error",
            "message": f"Dispute {dispute_id} is already resolved ('{dispute['status']}'). Cannot process duplicate refund.",
        }

    # 3. Check Analyst Authorization
    cursor.execute("SELECT * FROM analysts WHERE analyst_id = ?", (analyst_id,))
    analyst = cursor.fetchone()
    if analyst is None:
        conn.close()
        return {"status": "error", "message": f"Analyst {analyst_id} not found."}

    amount = dispute["amount"]

    # 4. Routine path (<= $500)
    if amount <= ELICITATION_THRESHOLD:
        cursor.execute(
            "UPDATE disputes SET status = 'refunded', resolved_at = datetime('now') WHERE dispute_id = ?",
            (dispute_id,),
        )
        cursor.execute(
            "UPDATE transactions SET status = 'reversed' WHERE transaction_id = (SELECT transaction_id FROM disputes WHERE dispute_id = ?)",
            (dispute_id,),
        )
        conn.commit()
        conn.close()
        return {
            "status": "approved",
            "elicitation_required": False,
            "message": f"ROUTINE REFUND APPROVED: Dispute {dispute_id} (${amount:.2f}) processed by analyst {analyst_id}.",
        }

    # 5. Elicitation Threshold Path (> $500)
    if analyst["role"] == "junior":
        conn.close()
        return {
            "status": "rejected",
            "elicitation_required": True,
            "message": f"REJECTED: Junior analyst {analyst_id} cannot approve refunds > ${ELICITATION_THRESHOLD:.2f}.",
        }

    # Case A: Elicitation Pause (no confirmation provided yet)
    if confirmed is None:
        conn.close()
        return {
            "status": "elicitation_pause",
            "elicitation_required": True,
            "message": (
                f"ELICITATION PAUSE: Dispute {dispute_id} (${amount:.2f}) exceeds policy threshold "
                f"(${ELICITATION_THRESHOLD:.2f}). Pausing execution for explicit human sign-off."
            ),
        }

    # Case B: Elicitation Declined (explicit confirmed=False)
    if confirmed is False:
        conn.close()
        return {
            "status": "declined_blocked",
            "elicitation_required": True,
            "message": (
                f"DECLINED & BLOCKED: Elicitation approval was DECLINED for dispute {dispute_id} "
                f"(${amount:.2f}). Database state remains UNCHANGED (status: '{dispute['status']}')."
            ),
        }

    # Case C: Elicitation Approved (explicit confirmed=True)
    if confirmed is True:
        cursor.execute(
            "UPDATE disputes SET status = 'refunded', resolved_at = datetime('now') WHERE dispute_id = ?",
            (dispute_id,),
        )
        cursor.execute(
            "UPDATE transactions SET status = 'reversed' WHERE transaction_id = (SELECT transaction_id FROM disputes WHERE dispute_id = ?)",
            (dispute_id,),
        )
        conn.commit()
        conn.close()
        return {
            "status": "approved_after_elicitation",
            "elicitation_required": True,
            "message": f"APPROVED AFTER ELICITATION: Senior analyst {analyst_id} explicitly approved refund of ${amount:.2f} for dispute {dispute_id}.",
        }

    conn.close()
    return {"status": "error", "message": "Invalid elicitation flag state."}
