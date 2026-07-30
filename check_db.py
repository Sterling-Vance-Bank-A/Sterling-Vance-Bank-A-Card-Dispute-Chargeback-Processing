import sqlite3

conn = sqlite3.connect("db/sterling_vance.db")
cursor = conn.cursor()

cursor.execute("SELECT dispute_id, status, amount, reason_code FROM disputes LIMIT 5")
rows = cursor.fetchall()

for row in rows:
    print(row)

conn.close()