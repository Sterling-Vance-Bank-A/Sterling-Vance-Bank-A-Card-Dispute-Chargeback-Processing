from typing import List, Dict, Optional
import re

# Relevance keywords that signal a chunk is about the query topic
STOP_WORDS = {'the','a','an','is','in','of','for','to','and','or','with','by'}

def _keyword_overlap(query: str, text: str) -> float:
    """Simple lexical overlap score 0-1 between query and text."""
    q_words = set(query.lower().split()) - STOP_WORDS
    t_words = set(text.lower().split()) - STOP_WORDS
    if not q_words:
        return 0.0
    return len(q_words & t_words) / len(q_words)

def check_relevance(query: str, chunks: List[Dict], threshold: float = 0.15) -> Dict:
    """Check if retrieved chunks are relevant to the query.
    Returns {passed: bool, scores: list, irrelevant_chunks: list, action: str}"""
    scores = []
    irrelevant = []
    for chunk in chunks:
        text = chunk.get('text', '')
        score = _keyword_overlap(query, text)
        scores.append({'chunk_id': chunk.get('chunk_id','?'), 'score': round(score,3)})
        if score < threshold:
            irrelevant.append(chunk.get('chunk_id','?'))
    passed = len(irrelevant) < len(chunks)  # at least one relevant chunk
    action = 'proceed' if passed else 're_retrieve'
    return {'passed': passed, 'scores': scores, 'irrelevant_chunk_ids': irrelevant, 'action': action, 'threshold': threshold}

def check_support(query: str, answer: str, context: str, threshold: float = 0.10) -> Dict:
    """Check if the answer is supported by the retrieved context.
    Returns {passed: bool, score: float, action: str}"""
    if not answer or not context:
        return {'passed': False, 'score': 0.0, 'action': 'grounded_refusal'}
    # Check if key answer terms appear in context
    a_words = set(answer.lower().split()) - STOP_WORDS
    c_words = set(context.lower().split()) - STOP_WORDS
    score = len(a_words & c_words) / max(len(a_words), 1)
    passed = score >= threshold
    action = 'proceed' if passed else 'grounded_refusal'
    return {'passed': passed, 'score': round(score, 3), 'action': action, 'threshold': threshold}

def check_memory_recall(query: str, recalled_facts: List[Dict], threshold: float = 0.1) -> Dict:
    """Apply relevance check to episodic/semantic memory recall before injecting into context."""
    # Each fact: {attribute, value, entity_id, ...}
    relevant_facts = []
    dropped_facts = []
    for fact in recalled_facts:
        fact_text = f"{fact.get('entity_id','')} {fact.get('attribute','')} {fact.get('value','')}"
        score = _keyword_overlap(query, fact_text)
        if score >= threshold or any(kw in query.lower() for kw in [fact.get('entity_id','').lower(), fact.get('attribute','').lower()]):
            relevant_facts.append(fact)
        else:
            dropped_facts.append({'fact': fact, 'score': score})
    return {
        'relevant_facts': relevant_facts,
        'dropped_facts': dropped_facts,
        'passed': len(relevant_facts) > 0 or len(recalled_facts) == 0
    }

def verify_rag_answer(query: str, chunks: List[Dict], answer: str = None, context: str = None) -> Dict:
    """Full Self-RAG pipeline: relevance check then support check."""
    rel = check_relevance(query, chunks)
    result = {'relevance': rel}
    if not rel['passed']:
        result['final_action'] = 're_retrieve'
        result['answer'] = None
        return result
    if answer and context:
        sup = check_support(query, answer, context)
        result['support'] = sup
        result['final_action'] = sup['action']
        if not sup['passed']:
            result['answer'] = '[GROUNDED REFUSAL: Answer not sufficiently supported by retrieved policy content.]'
        else:
            result['answer'] = answer
    else:
        result['final_action'] = 'proceed'
    return result
