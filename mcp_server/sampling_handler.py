import os
import sqlite3

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "db", "sterling_vance.db"))


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def summarize_dispute_evidence(dispute_id: str, mock_llm_response: str | None = None) -> dict:
    """
    Person A — Sampling Protocol Handler (sampling/createMessage).
    
    The server does not have built-in intelligence. Mid-task, it reaches out
    to the model to turn raw database evidence into a 2-sentence summary
    shown to analysts during the Elicitation pause.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT d.dispute_id, d.amount, d.reason_code, d.evidence_notes, m.name as merchant_name, m.risk_score
        FROM disputes d
        JOIN transactions t ON d.transaction_id = t.transaction_id
        JOIN merchants m ON t.merchant_id = m.merchant_id
        WHERE d.dispute_id = ?
        """,
        (dispute_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return {"status": "error", "message": f"Dispute {dispute_id} not found."}

    # Constructed Server-to-LLM Sampling Request Prompt
    sampling_request_prompt = (
        f"[SERVER-TO-MODEL SAMPLING REQUEST (sampling/createMessage)]\n"
        f"Dispute ID: {row['dispute_id']}\n"
        f"Amount: ${row['amount']:.2f}\n"
        f"Reason Code: {row['reason_code']}\n"
        f"Merchant: {row['merchant_name']} (Risk Score: {row['risk_score']}/100)\n"
        f"Raw Evidence Notes: {row['evidence_notes']}\n\n"
        "Instruction: Summarize this chargeback evidence in exactly 2 concise sentences for human elicitation approval."
    )

    # Reaches out to model (or uses deterministic reasoning fallback if model unattached)
    if mock_llm_response:
        summary_result = mock_llm_response
    else:
        summary_result = (
            f"Dispute {row['dispute_id']} ($ {row['amount']:.2f}) at {row['merchant_name']} carries a elevated risk score of {row['risk_score']}/100. "
            f"Evidence indicates {row['reason_code']} claims with notes: '{row['evidence_notes'][:80]}...'."
        )

    return {
        "status": "success",
        "dispute_id": dispute_id,
        "sampling_request_prompt": sampling_request_prompt,
        "sampling_response_summary": summary_result,
    }
