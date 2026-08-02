import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "db", "sterling_vance.db")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT customer_id, name, risk_flag FROM customers WHERE risk_flag = 'high'")
for row in cursor.fetchall():
    print(row)
conn.close()