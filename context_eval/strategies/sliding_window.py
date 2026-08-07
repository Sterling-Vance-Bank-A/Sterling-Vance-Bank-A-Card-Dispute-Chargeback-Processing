"""
Sliding Window strategy: keep only the last N turns of the conversation.
Pros: Simple, predictable token budget.
Cons: Drops all early turns, including critical early decisions.
"""
from typing import List, Dict

DEFAULT_WINDOW = 10

def apply(transcript: List[Dict], window_size: int = DEFAULT_WINDOW) -> List[Dict]:
    """
    Keep the system prompt (role='system') always, then the last window_size turns.
    Tool output turns count toward the window.
    Returns pruned transcript.
    """
    system = [t for t in transcript if t.get('role') == 'system']
    non_system = [t for t in transcript if t.get('role') != 'system']
    window = non_system[-window_size:] if len(non_system) > window_size else non_system
    return system + window

def token_estimate(transcript: List[Dict]) -> int:
    return sum(len(t.get('content', '').split()) for t in transcript)
