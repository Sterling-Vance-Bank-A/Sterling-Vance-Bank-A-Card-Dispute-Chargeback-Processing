"""
12 test questions covering naive RAG (simple), hybrid (exact IDs), and agentic (multi-hop).
Each question has: id, text, expected_winner, key_terms (list of strings that MUST appear in correct retrieval), category
"""
TEST_QUESTIONS = [
    # --- Naive RAG questions (simple semantic lookup) ---
    {'id': 'Q01', 'text': 'What is the standard refund window for duplicate charge disputes?', 'expected_winner': 'naive_rag', 'key_terms': ['90 days', 'duplicate charge', 'original charge'], 'category': 'naive'},
    {'id': 'Q02', 'text': 'What does reason code 4853 say about services not rendered?', 'expected_winner': 'naive_rag', 'key_terms': ['4853', 'Services Not Rendered', '120 days'], 'category': 'naive'},
    {'id': 'Q03', 'text': 'What is the refund eligibility window for unauthorized transaction disputes?', 'expected_winner': 'naive_rag', 'key_terms': ['120 days', 'unauthorized', 'fraud score'], 'category': 'naive'},
    {'id': 'Q04', 'text': 'How do fraud risk scores affect escalation routing in the system?', 'expected_winner': 'naive_rag', 'key_terms': ['75', 'escalation', 'senior analyst', 'fraud risk score'], 'category': 'naive'},
    # --- Hybrid search questions (exact IDs, section references) ---
    {'id': 'Q05', 'text': 'What does Policy Section 7.2.1 say exactly?', 'expected_winner': 'hybrid_search', 'key_terms': ['7.2.1', 'Senior analyst', '24 hours', 'transaction evidence'], 'category': 'hybrid'},
    {'id': 'Q06', 'text': 'What is the chargeback threshold defined in Rule 4.2b?', 'expected_winner': 'hybrid_search', 'key_terms': ['4.2b', '1.0%', 'Chargeback Monitoring Program', '100 per month'], 'category': 'hybrid'},
    {'id': 'Q07', 'text': 'When does VISA Rule 10.4 apply versus VISA Rule 10.5?', 'expected_winner': 'hybrid_search', 'key_terms': ['10.4', '10.5', 'ATM', 'counterfeit', 'EMV'], 'category': 'hybrid'},
    {'id': 'Q08', 'text': 'What exact wording does the policy use for unauthorized transaction?', 'expected_winner': 'hybrid_search', 'key_terms': ['explicit consent', 'account holder', 'phishing', 'identity theft'], 'category': 'hybrid'},
    # --- Agentic RAG questions (multi-hop, decomposition needed) ---
    {'id': 'Q09', 'text': 'For a $750 fraud dispute with a high-risk merchant, what are the escalation steps and required documentation?', 'expected_winner': 'agentic_rag', 'key_terms': ['7.2', 'senior analyst', 'fraud investigation', 'documentation', 'card network'], 'category': 'agentic'},
    {'id': 'Q10', 'text': 'What policy applies when a junior analyst flags a dispute AND the merchant has prior chargebacks AND the amount exceeds $500?', 'expected_winner': 'agentic_rag', 'key_terms': ['9.1', 'senior analyst queue', 'junior analyst', '$500', 'cannot approve'], 'category': 'agentic'},
    {'id': 'Q11', 'text': 'Does a refund denial require both Section 3 and Section 9 sign-off for amounts over $1000?', 'expected_winner': 'agentic_rag', 'key_terms': ['Section 3', 'Section 9', 'Senior Supervisor', '$1,000', '72 hours'], 'category': 'agentic'},
    {'id': 'Q12', 'text': 'What sequence of checks must a senior analyst complete for a dispute involving both duplicate charge and merchant fraud?', 'expected_winner': 'agentic_rag', 'key_terms': ['9.2', 'compound disputes', 'duplicate charge', 'fraud', 'Code 4837', '4853'], 'category': 'agentic'},
]

def get_questions(): return TEST_QUESTIONS
