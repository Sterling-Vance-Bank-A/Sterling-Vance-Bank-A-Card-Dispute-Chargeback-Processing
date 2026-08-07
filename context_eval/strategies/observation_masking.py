"""
Observation Masking strategy: keep all dialogue turns, but mask/truncate tool
output turns older than the last K tool calls. Preserves the conversational
thread while dropping bloated JSON tool results.
"""
from typing import List, Dict

DEFAULT_KEEP_TOOL_OUTPUTS = 3
TRUNCATED_MARKER = '[TOOL OUTPUT MASKED — older than retention window]'

def apply(transcript: List[Dict], keep_last_k_tool_outputs: int = DEFAULT_KEEP_TOOL_OUTPUTS) -> List[Dict]:
    """
    Keep all non-tool turns intact.
    For tool output turns (role='tool' or turn_type='tool_output'):
      keep the last keep_last_k_tool_outputs in full, mask earlier ones.
    System prompt always kept.
    """
    result = []
    tool_output_indices = [i for i, t in enumerate(transcript)
                           if t.get('role') in ('tool', 'function') or t.get('turn_type') == 'tool_output']
    keep_from_index = tool_output_indices[-keep_last_k_tool_outputs] if len(tool_output_indices) >= keep_last_k_tool_outputs else 0
    for i, turn in enumerate(transcript):
        is_tool_output = turn.get('role') in ('tool', 'function') or turn.get('turn_type') == 'tool_output'
        is_protected = turn.get('is_key_fact', False)  # never mask key-fact turns
        if is_tool_output and not is_protected and i < keep_from_index:
            masked = dict(turn)
            masked['content'] = TRUNCATED_MARKER
            result.append(masked)
        else:
            result.append(turn)
    return result

def token_estimate(transcript: List[Dict]) -> int:
    return sum(len(t.get('content', '').split()) for t in transcript)
