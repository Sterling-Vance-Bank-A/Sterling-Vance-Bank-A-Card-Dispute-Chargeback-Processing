"""
Recursive Summarization: compact every COMPACT_EVERY turns into a summary node.
Requires an LLM call. Without LLM, falls back to extractive summary.
"""
from typing import List, Dict, Callable, Optional

COMPACT_EVERY = 15

def _extractive_summary(turns: List[Dict]) -> str:
    """Fallback extractive summary: keep first sentence of each turn."""
    lines = []
    for t in turns:
        content = t.get('content', '')
        first_line = content.split('.')[0][:120] if content else ''
        if first_line:
            lines.append(f"[{t.get('role','?')}]: {first_line}")
    return 'SUMMARY: ' + ' | '.join(lines)

def apply(transcript: List[Dict], compact_every: int = COMPACT_EVERY,
          llm_fn: Optional[Callable] = None) -> List[Dict]:
    """
    Walk through transcript in blocks of compact_every turns.
    Compact each full block into a single summary turn.
    Keep the most recent (incomplete) block in full.
    System prompt always kept.
    """
    system = [t for t in transcript if t.get('role') == 'system']
    non_system = [t for t in transcript if t.get('role') != 'system']
    
    blocks = [non_system[i:i+compact_every] for i in range(0, len(non_system), compact_every)]
    result = system.copy()
    
    for i, block in enumerate(blocks):
        is_last_block = (i == len(blocks) - 1)
        if is_last_block or len(block) < compact_every:
            result.extend(block)  # keep last block in full
        else:
            if llm_fn:
                block_text = '\n'.join(f"{t['role']}: {t['content']}" for t in block)
                summary_text = llm_fn(f"Summarize this conversation segment concisely, preserving all key facts, decisions, and entity IDs:\n{block_text}")
            else:
                summary_text = _extractive_summary(block)
            result.append({'role': 'system', 'content': summary_text, 'turn_type': 'summary', 'turn': block[0].get('turn', 0)})
    return result

def token_estimate(transcript: List[Dict]) -> int:
    return sum(len(t.get('content', '').split()) for t in transcript)
