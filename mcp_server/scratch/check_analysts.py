import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "db", "sterling_vance.db")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT analyst_id, name, role FROM analysts LIMIT 10")
for row in cursor.fetchall():
    print(dict(row))

conn.close()