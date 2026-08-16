"""
Unit and integration tests for the Sterling Vance dispute database.
Verifies schema constraints, referential integrity, seed data correctness,
and business queries required by the MCP server tools.
"""

import sqlite3
import os
import unittest


class TestDisputeDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = os.path.join(os.path.dirname(__file__), "sterling_vance.db")
        cls.schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        cls.seed_path = os.path.join(os.path.dirname(__file__), "seed.sql")

        # If DB doesn't exist, build it
        if not os.path.exists(cls.db_path):
            conn = sqlite3.connect(cls.db_path)
            with open(cls.schema_path, encoding="utf-8") as f:
                conn.executescript(f.read())
            with open(cls.seed_path, encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.commit()
            conn.close()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        return conn

    def test_database_integrity(self):
        """Verify SQLite database file has no corruption."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()[0]
        self.assertEqual(result, "ok")
        conn.close()

    def test_foreign_key_integrity(self):
        """Verify all foreign key relationships in seed data are valid."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_key_check;")
        violations = cursor.fetchall()
        self.assertEqual(len(violations), 0, f"Foreign key violations found: {violations}")
        conn.close()

    def test_tables_exist(self):
        """Verify all expected schema tables exist."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        expected = {"customers", "analysts", "merchants", "accounts", "transactions", "disputes", "dispute_history"}
        self.assertTrue(expected.issubset(tables), f"Missing tables: {expected - tables}")
        conn.close()

    def test_seed_row_counts(self):
        """Verify database contains sufficient seed data across all tables."""
        conn = self.get_connection()
        cursor = conn.cursor()
        counts = {}
        for table in ["customers", "analysts", "merchants", "accounts", "transactions", "disputes", "dispute_history"]:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
            self.assertTrue(counts[table] > 0, f"Table {table} is empty!")
        conn.close()

    def test_check_constraints_role(self):
        """Verify CHECK constraint prevents invalid analyst roles."""
        conn = self.get_connection()
        cursor = conn.cursor()
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO analysts (analyst_id, name, email, role) VALUES ('ANL-999', 'Fake', 'fake@bank.com', 'admin')"
            )
        conn.close()

    def test_check_constraints_amount(self):
        """Verify CHECK constraint prevents negative transaction amounts."""
        conn = self.get_connection()
        cursor = conn.cursor()
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO transactions (transaction_id, account_id, merchant_id, amount, txn_date) VALUES ('TXN-INVALID', 'ACC-001', 'MERCH-001', -50.0, '2026-07-31')"
            )
        conn.close()

    def test_dispute_queries(self):
        """Verify dispute detail lookup used by get_dispute_details."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM disputes WHERE dispute_id = 'DISP-001'")
        dispute = cursor.fetchone()
        self.assertIsNotNone(dispute)
        self.assertEqual(dispute["reason_code"], "duplicate_charge")
        self.assertIn(dispute["amount"], (29.99, 100.0))
        conn.close()

    def test_escalation_logic_data(self):
        """Verify data for high-value and high-risk escalation triggers."""
        conn = self.get_connection()
        cursor = conn.cursor()

        # DISP-002 is $899 (over $500 threshold)
        cursor.execute("SELECT amount FROM disputes WHERE dispute_id = 'DISP-002'")
        disp2 = cursor.fetchone()
        self.assertTrue(disp2["amount"] > 500)

        # High risk customer flag lookup
        cursor.execute("""
            SELECT c.risk_flag 
            FROM disputes d
            JOIN transactions t ON d.transaction_id = t.transaction_id
            JOIN accounts a ON t.account_id = a.account_id
            JOIN customers c ON a.customer_id = c.customer_id
            WHERE d.dispute_id = 'DISP-002'
        """)
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        conn.close()


if __name__ == "__main__":
    unittest.main()
