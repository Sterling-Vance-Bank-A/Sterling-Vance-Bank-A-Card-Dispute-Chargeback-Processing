import sqlite3

conn = sqlite3.connect("db/sterling_vance.db")
cursor = conn.cursor()
cursor.execute("SELECT customer_id, name, risk_flag FROM customers WHERE risk_flag = 'high'")
for row in cursor.fetchall():
    print(row)
conn.close()