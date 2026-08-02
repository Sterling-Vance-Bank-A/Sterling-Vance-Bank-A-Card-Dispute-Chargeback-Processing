import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from elicitation_handler import process_refund_with_elicitation, DB_PATH, ELICITATION_THRESHOLD


def reset_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE disputes SET status = 'open', resolved_at = NULL WHERE dispute_id = 'DISP-001'")
    conn.execute("UPDATE disputes SET status = 'investigating', resolved_at = NULL WHERE dispute_id = 'DISP-002'")
    conn.execute("UPDATE transactions SET status = 'settled' WHERE transaction_id IN ('TXN-002', 'TXN-003')")
    conn.commit()
    conn.close()


class TestElicitationProtocol(unittest.TestCase):
    """Test suite verifying Person A's Elicitation Protocol behavior."""

    def setUp(self):
        reset_db()

    def tearDown(self):
        reset_db()

    def test_routine_refund_under_threshold(self):
        """Dispute DISP-001 ($29.99 <= $500) should auto-approve without elicitation."""
        res = process_refund_with_elicitation("DISP-001", "ANL-001")
        self.assertEqual(res["status"], "approved")
        self.assertFalse(res["elicitation_required"])
        self.assertIn("ROUTINE REFUND APPROVED", res["message"])

    def test_elicitation_pause_over_threshold(self):
        """Dispute DISP-002 ($899.00 > $500) should trigger Elicitation Pause when unconfirmed."""
        res = process_refund_with_elicitation("DISP-002", "ANL-002", confirmed=None)
        self.assertEqual(res["status"], "elicitation_pause")
        self.assertTrue(res["elicitation_required"])
        self.assertIn("ELICITATION PAUSE", res["message"])

    def test_elicitation_declined_blocks_refund(self):
        """When human declines (confirmed=False), refund is BLOCKED and DB stays unchanged."""
        res = process_refund_with_elicitation("DISP-002", "ANL-002", confirmed=False)
        self.assertEqual(res["status"], "declined_blocked")
        self.assertIn("DECLINED & BLOCKED", res["message"])

        # Verify DB dispute status remains 'investigating'
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM disputes WHERE dispute_id = 'DISP-002'")
        status = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(status, "investigating")

    def test_elicitation_approved_executes_refund(self):
        """When human approves (confirmed=True), refund is APPROVED and DB is updated."""
        res = process_refund_with_elicitation("DISP-002", "ANL-002", confirmed=True)
        self.assertEqual(res["status"], "approved_after_elicitation")
        self.assertIn("APPROVED AFTER ELICITATION", res["message"])

        # Verify DB dispute status updated to 'refunded'
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM disputes WHERE dispute_id = 'DISP-002'")
        status = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(status, "refunded")


if __name__ == "__main__":
    unittest.main()