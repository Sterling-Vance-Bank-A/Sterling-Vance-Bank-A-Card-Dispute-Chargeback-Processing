import sqlite3
import json
import uuid
from typing import Dict, Any

DB_PATH = "db/disputes_state.db"

def trigger_hitl_pause(dispute_id: str, reason: str, current_state: Dict[str, Any]) -> str:
    """Triggers an explicit HITL pause, saving state and opening an admin task."""
    task_id = f"hitl_{uuid.uuid4().hex[:8]}"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hitl_tasks (task_id, dispute_id, reason, status, current_state)
        VALUES (?, ?, ?, 'pending', ?)
    """, (task_id, dispute_id, reason, json.dumps(current_state, default=str)))
    conn.commit()
    conn.close()
    print(f"\n[⏸️ HITL PAUSE] Dispute {dispute_id} paused. Task created: {task_id}. Reason: {reason}")
    return task_id

def create_failure_ticket(dispute_id: str, error_message: str, state_at_failure: Dict[str, Any]) -> str:
    """Creates a failure ticket for unplanned mid-node failures."""
    ticket_id = f"tkt_{uuid.uuid4().hex[:8]}"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO failure_tickets (ticket_id, dispute_id, error_message, status, state_at_failure)
        VALUES (?, ?, ?, 'open', ?)
    """, (ticket_id, dispute_id, error_message, json.dumps(state_at_failure, default=str)))
    conn.commit()
    conn.close()
    print(f"\n[🚨 FAILURE TICKET] Unplanned failure on Dispute {dispute_id}. Ticket created: {ticket_id}. Error: {error_message}")
    return ticket_id
