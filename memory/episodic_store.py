import sqlite3
import os
import datetime

class EpisodicStore:
    def __init__(self, db_path=None):
        if db_path is None:
            # Resolve db_path relative to this file
            self.db_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'memory.db')
        else:
            self.db_path = db_path
            
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self._create_table()

    def _create_table(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                dispute_id TEXT,
                analyst_id TEXT,
                timestamp TEXT NOT NULL,
                content TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                promoted_from TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')
        self.conn.commit()

    def add_episode(self, session_id, content, dispute_id=None, analyst_id=None, entity_type=None, entity_id=None, promoted_from=None):
        cursor = self.conn.cursor()
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor.execute('''
            INSERT INTO episodes (session_id, dispute_id, analyst_id, timestamp, content, entity_type, entity_id, promoted_from)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session_id, dispute_id, analyst_id, timestamp, content, entity_type, entity_id, promoted_from))
        self.conn.commit()
        return cursor.lastrowid

    def get_episodes_for_dispute(self, dispute_id, limit=20):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM episodes 
            WHERE dispute_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (dispute_id, limit))
        return cursor.fetchall()

    def get_recent_episodes(self, session_id, limit=10):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM episodes 
            WHERE session_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (session_id, limit))
        return cursor.fetchall()

    def get_episodes_older_than_hours(self, hours=24):
        cursor = self.conn.cursor()
        time_threshold = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat()
        cursor.execute('''
            SELECT * FROM episodes 
            WHERE timestamp < ?
        ''', (time_threshold,))
        return cursor.fetchall()

    def count(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM episodes')
        return cursor.fetchone()[0]

    def close(self):
        self.conn.close()
