"""
Zone-based Pruning: partition transcript into 4 zones with per-zone token budgets.
Zones: system (always kept), key_facts (always kept), recent_dialogue (budgeted), tool_outputs (budgeted).
"""
from typing import List, Dict

DEFAULT_BUDGETS = {
    'system': 500,         # tokens
    'key_facts': 300,      # scratchpad-like important facts
    'recent_dialogue': 800,
    'tool_outputs': 600,
}

def _classify_turn(turn: Dict) -> str:
    role = turn.get('role', '')
    turn_type = turn.get('turn_type', '')
    if role == 'system' and turn_type != 'key_fact':
        return 'system'
    if turn_type == 'key_fact' or turn.get('is_key_fact'):
        return 'key_facts'
    if role in ('tool', 'function') or turn_type == 'tool_output':
        return 'tool_outputs'
    return 'recent_dialogue'

def apply(transcript: List[Dict], budgets: Dict = None) -> List[Dict]:
    """
    Classify each turn into a zone, then trim each zone to its token budget,
    keeping most recent turns in each zone.
    """
    budgets = budgets or DEFAULT_BUDGETS
    zones = {'system': [], 'key_facts': [], 'recent_dialogue': [], 'tool_outputs': []}
    for turn in transcript:
        zone = _classify_turn(turn)
        zones[zone].append(turn)
    
    result = []
    for zone_name in ['system', 'key_facts', 'tool_outputs', 'recent_dialogue']:
        turns = zones[zone_name]
        budget = budgets[zone_name]
        # Keep most recent turns that fit within budget (token approximation)
        kept = []
        tokens_used = 0
        for turn in reversed(turns):
            cost = len(turn.get('content', '').split())
            if tokens_used + cost <= budget:
                kept.insert(0, turn)
                tokens_used += cost
            # older turns dropped if over budget
        result.extend(kept)
    # Sort by turn number to restore order
    result.sort(key=lambda t: t.get('turn', 0))
    return result

def token_estimate(transcript: List[Dict]) -> int:
    return sum(len(t.get('content', '').split()) for t in transcript)
