import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sampling_handler import summarize_dispute_evidence


class TestSamplingProtocol(unittest.TestCase):
    """Test suite verifying Person A's Sampling Protocol behavior (sampling/createMessage)."""

    def test_sampling_prompt_construction(self):
        """Verify sampling handler constructs proper sampling request prompt with raw DB evidence."""
        res = summarize_dispute_evidence("DISP-002")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["dispute_id"], "DISP-002")

        prompt = res["sampling_request_prompt"]
        self.assertIn("[SERVER-TO-MODEL SAMPLING REQUEST (sampling/createMessage)]", prompt)
        self.assertIn("DISP-002", prompt)
        self.assertIn("TechGadgets Online", prompt)
        self.assertIn("Risk Score: 45/100", prompt)

    def test_sampling_summary_generation(self):
        """Verify sampling handler returns model-generated evidence summary."""
        mock_summary = "Dispute DISP-002 ($899.00) involves merchant TechGadgets Online. Customer alleges unauthorized charge but merchant claims IP address matches cardholder profile."
        res = summarize_dispute_evidence("DISP-002", mock_llm_response=mock_summary)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["sampling_response_summary"], mock_summary)


if __name__ == "__main__":
    unittest.main()
