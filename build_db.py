import sqlite3
import os

db_path = os.path.join("db", "sterling_vance.db")


if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)

with open(os.path.join("db", "schema.sql"), encoding="utf-8") as f:
    conn.executescript(f.read())

with open(os.path.join("db", "seed.sql"), encoding="utf-8") as f:
    conn.executescript(f.read())

conn.commit()
conn.close()

print("Database built successfully at", db_path)