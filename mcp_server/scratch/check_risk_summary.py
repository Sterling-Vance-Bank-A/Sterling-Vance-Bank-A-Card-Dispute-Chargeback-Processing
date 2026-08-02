import os
import sqlite3
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "db", "sterling_vance.db")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM customers")
total = cursor.fetchone()[0]

cursor.execute("SELECT risk_flag, COUNT(*) FROM customers GROUP BY risk_flag")
breakdown = cursor.fetchall()

print(f"Total customers: {total}")
print("Breakdown by risk_flag:")
for row in breakdown:
    print(f"  {row[0]}: {row[1]}")

conn.close()