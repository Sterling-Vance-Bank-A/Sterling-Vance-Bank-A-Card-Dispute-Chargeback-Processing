"""
Long-context test suite for Sterling Vance Bank context window evaluation.

Design: A 40-turn dispute session for DISP-073 where a critical fraud flag is
mentioned at turn 3 and must survive to turn 40. Turns 4-39 are filled with
tool-call JSON outputs (transaction histories, merchant info, etc.) that
bury the key fact under token noise.

Accuracy metric: Does the pruned transcript still contain the key fact string?
Key fact: 'fraud_flag_detected_ACC-021' (a compact unique marker)
"""
import copy
from typing import List, Dict

KEY_FACT_MARKER = 'fraud_flag_detected_ACC-021'
KEY_FACT_TURN = 3  # turn index where the fact appears (0-indexed: index 3 = turn 4)
TOTAL_TURNS = 40

# Large tool output template to simulate JSON bloat
TOOL_OUTPUT_TEMPLATE = """{{"transaction_id": "TXN-{i:04d}", "account_id": "ACC-0{acct}", "merchant_id": "MERCH-{merch:03d}", "amount": {amt:.2f}, "timestamp": "2026-0{month:02d}-{day:02d}T{hour:02d}:00:00Z", "status": "completed", "merchant_name": "{mname}", "category": "{cat}", "auth_code": "AUTH-{code}", "pos_entry": "chip", "currency": "USD", "balance_after": {bal:.2f}, "risk_assessment": {{"score": {risk}, "flags": [], "reviewed": false}}}}"""

def _make_tool_output(i: int) -> str:
    import random
    r = random.Random(i)  # deterministic per-index
    merchants = ['Brew & Go Coffee', 'TechGadgets Online', 'Metro Grocery', 'FuelStop 24', 'CloudSub Services']
    cats = ['food_beverage', 'electronics', 'grocery', 'fuel', 'subscription']
    idx = i % 5
    return TOOL_OUTPUT_TEMPLATE.format(
        i=i, acct=r.randint(1,9), merch=r.randint(1,20),
        amt=round(r.uniform(10, 900), 2), month=r.randint(1,8), day=r.randint(1,28),
        hour=r.randint(8,20), mname=merchants[idx], cat=cats[idx],
        code=r.randint(100000, 999999), bal=round(r.uniform(100, 5000), 2),
        risk=r.randint(0, 95)
    )

def build_base_transcript() -> List[Dict]:
    """Build a 40-turn transcript with the key fact at turn 3 (index 2).

    The key fact (fraud flag on ACC-021) appears in TWO places:
      - Turn 3: tool_output (marked is_key_fact=True → zone-pruning keeps it)
      - Turn 4: assistant dialogue (observation masking keeps all dialogue → survives masking)
    Sliding window drops both if the window is small enough.
    This design produces a meaningful spread across strategies.
    """
    turns = [
        {'turn': 0, 'role': 'system', 'content': 'You are Sterling Vance Bank dispute resolution agent. Session: DISP-073.', 'turn_type': 'system'},
        {'turn': 1, 'role': 'user', 'content': 'Start investigation for dispute DISP-073. Customer claims unauthorized transaction.', 'turn_type': 'dialogue'},
        {'turn': 2, 'role': 'assistant', 'content': 'Beginning investigation for DISP-073. Fetching dispute details and transaction history.', 'turn_type': 'dialogue'},
        # Turn 3: tool_output — marked is_key_fact=True; zone-pruning protects it
        {'turn': 3, 'role': 'tool', 'content': f'{{"dispute_id": "DISP-073", "transaction_id": "TXN-073", "account_id": "ACC-021", "fraud_investigation": {{"flag": "detected", "marker": "{KEY_FACT_MARKER}", "risk_score": 92, "reason": "card_not_present_mismatch", "investigator": "ANL-002"}}, "amount": 847.50, "status": "investigating"}}', 'turn_type': 'tool_output', 'is_key': True, 'is_key_fact': True},
        # Turn 4: assistant dialogue — observation masking keeps all dialogue, so the fact survives here
        {'turn': 4, 'role': 'assistant', 'content': f'CRITICAL NOTE: Fraud flag detected on account ACC-021. Marker: {KEY_FACT_MARKER}. Risk score 92. This flag must be preserved through the full investigation and reported at final review.', 'turn_type': 'dialogue', 'is_key_fact': True},
    ]
    # Turns 5-38: alternating assistant + tool_output (tool heavy, JSON bloat)
    for i in range(5, 39):
        if i % 2 == 1:
            turns.append({'turn': i, 'role': 'assistant', 'content': f'Fetching transaction record {i-4} for pattern analysis.', 'turn_type': 'dialogue'})
        else:
            turns.append({'turn': i, 'role': 'tool', 'content': _make_tool_output(i), 'turn_type': 'tool_output'})
    # Turn 39 (final): analyst asks about the fraud flag
    turns.append({'turn': 39, 'role': 'user', 'content': f'Before we finalize, was there a fraud flag on the account associated with DISP-073? What was the risk score?', 'turn_type': 'dialogue', 'is_final_query': True})
    return turns

def build_test_suite(n_variations: int = 10) -> List[Dict]:
    """Build N variations of the base transcript. Each variation shuffles the
    intermediate tool output contents (different JSON values) to simulate real diversity."""
    base = build_base_transcript()
    variations = []
    for v in range(n_variations):
        variant = copy.deepcopy(base)
        # Vary the tool outputs (turns 5-38) with different seed offset
        for turn in variant:
            if turn.get('turn_type') == 'tool_output' and not turn.get('is_key'):
                turn['content'] = _make_tool_output(turn['turn'] + v * 100)
        variations.append({'variation_id': v, 'transcript': variant})
    return variations

def check_accuracy(pruned_transcript: List[Dict]) -> bool:
    """Check if the key fact survived the pruning."""
    combined = ' '.join(t.get('content', '') for t in pruned_transcript)
    return KEY_FACT_MARKER in combined

if __name__ == '__main__':
    suite = build_test_suite()
    print(f'Built {len(suite)} test variations, each with {len(suite[0]["transcript"])} turns')
    print(f'Key fact marker: {KEY_FACT_MARKER}')
    base = build_base_transcript()
    print(f'Key fact present in base transcript: {check_accuracy(base)}')
