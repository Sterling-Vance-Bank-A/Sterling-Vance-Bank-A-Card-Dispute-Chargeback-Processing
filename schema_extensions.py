import sqlite3

def init_db_extensions(db_path: str = "db/disputes_state.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Checkpoints table for LangGraph state persistence
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS checkpoints (
        thread_id TEXT,
        checkpoint_id TEXT,
        parent_id TEXT,
        checkpoint BLOB,
        metadata BLOB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (thread_id, checkpoint_id)
    );
    """)
    
    # Human-in-the-loop (HITL) pending tasks table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hitl_tasks (
        task_id TEXT PRIMARY KEY,
        dispute_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        status TEXT DEFAULT 'pending', -- pending, approved, rejected
        current_state TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMP,
        resolved_by TEXT
    );
    """)
    
    # Failure tickets table for unplanned tool/schema errors
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS failure_tickets (
        ticket_id TEXT PRIMARY KEY,
        dispute_id TEXT NOT NULL,
        error_message TEXT NOT NULL,
        status TEXT DEFAULT 'open', -- open, investigating, resolved
        state_at_failure TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMP
    );
    """)
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db_extensions()
    print("Database schema extensions initialized successfully.")
