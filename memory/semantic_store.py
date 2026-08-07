import sqlite3
import os
import datetime
import json

class SemanticStore:
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
            CREATE TABLE IF NOT EXISTS semantic_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                attribute TEXT NOT NULL,
                value TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active',
                valid_from TEXT NOT NULL,
                valid_until TEXT,
                deprecated_at TEXT,
                conflict_note TEXT,
                source_episode_ids TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')
        self.conn.commit()

    def upsert_fact(self, entity_type, entity_id, attribute, value, source_episode_ids=None, conflict_note=None):
        cursor = self.conn.cursor()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # Check active fact
        cursor.execute('''
            SELECT id, value, version FROM semantic_facts
            WHERE entity_type = ? AND entity_id = ? AND attribute = ? AND status = 'active'
        ''', (entity_type, entity_id, attribute))
        row = cursor.fetchone()
        
        source_ids_str = json.dumps(source_episode_ids) if source_episode_ids else "[]"
        
        if row:
            fact_id, old_value, version = row
            if old_value != value:
                # Deprecate old
                cursor.execute('''
                    UPDATE semantic_facts
                    SET status = 'deprecated', deprecated_at = ?, valid_until = ?
                    WHERE id = ?
                ''', (now, now, fact_id))
                
                # Insert new
                new_version = version + 1
                cursor.execute('''
                    INSERT INTO semantic_facts (entity_type, entity_id, attribute, value, version, valid_from, conflict_note, source_episode_ids)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (entity_type, entity_id, attribute, value, new_version, now, conflict_note, source_ids_str))
        else:
            # Insert new
            cursor.execute('''
                INSERT INTO semantic_facts (entity_type, entity_id, attribute, value, version, valid_from, conflict_note, source_episode_ids)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (entity_type, entity_id, attribute, value, 1, now, conflict_note, source_ids_str))
        
        self.conn.commit()

    def get_active_facts(self, entity_type=None, entity_id=None):
        cursor = self.conn.cursor()
        query = "SELECT * FROM semantic_facts WHERE status = 'active'"
        params = []
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)
        if entity_id:
            query += " AND entity_id = ?"
            params.append(entity_id)
            
        cursor.execute(query, tuple(params))
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_fact_history(self, entity_type, entity_id, attribute):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM semantic_facts
            WHERE entity_type = ? AND entity_id = ? AND attribute = ?
            ORDER BY version ASC
        ''', (entity_type, entity_id, attribute))
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def expire_old_facts(self, days=30):
        cursor = self.conn.cursor()
        threshold = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
        cursor.execute('''
            UPDATE semantic_facts
            SET status = 'expired'
            WHERE valid_from < ? AND status = 'active'
        ''', (threshold,))
        self.conn.commit()

    def get_all_for_recall(self, dispute_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM semantic_facts
            WHERE status = 'active' AND (entity_id = ? OR source_episode_ids LIKE ?)
        ''', (dispute_id, f"%{dispute_id}%"))
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self):
        self.conn.close()
