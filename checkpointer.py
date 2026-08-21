import sqlite3
import json
import pickle
from typing import Dict, Any, Optional

class SQLiteCheckpointSaver:
    def __init__(self, db_path: str = "db/disputes_state.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
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
        conn.commit()
        conn.close()

    def put(self, config: Dict[str, Any], checkpoint: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint.get("id", "chk_" + str(hash(json.dumps(checkpoint, default=str))))
        parent_id = config["configurable"].get("checkpoint_id", "")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO checkpoints (thread_id, checkpoint_id, parent_id, checkpoint, metadata) VALUES (?, ?, ?, ?, ?)",
            (thread_id, checkpoint_id, parent_id, pickle.dumps(checkpoint), pickle.dumps(metadata))
        )
        conn.commit()
        conn.close()
        return {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}

    def get(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"].get("checkpoint_id")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if checkpoint_id:
            cursor.execute("SELECT checkpoint FROM checkpoints WHERE thread_id = ? AND checkpoint_id = ?", (thread_id, checkpoint_id))
        else:
            cursor.execute("SELECT checkpoint FROM checkpoints WHERE thread_id = ? ORDER BY rowid DESC LIMIT 1", (thread_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return pickle.loads(row[0])
        return None
