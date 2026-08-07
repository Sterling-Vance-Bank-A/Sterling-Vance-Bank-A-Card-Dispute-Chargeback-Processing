from .vector_store import get_store
from .hybrid_search import hybrid_search
from typing import List, Dict, Callable, Optional
import time

MAX_HOPS = 3

def _needs_more_retrieval(query: str, retrieved_chunks: List[Dict], hop: int) -> bool:
    """Heuristic: if query contains multi-part keywords and we haven't found all parts, retrieve again."""
    multi_part_signals = ['and', 'also', 'what else', 'additionally', 'both', 'sequence', 'steps']
    query_lower = query.lower()
    if hop >= MAX_HOPS:
        return False
    # Check if key entities from query appear in retrieved content
    combined = ' '.join([c['text'].lower() for c in retrieved_chunks])
    if any(sig in query_lower for sig in multi_part_signals) and hop < 2:
        # For multi-part queries, do at least 2 hops
        return hop < 2
    return False

def _rewrite_query(original: str, retrieved_chunks: List[Dict], hop: int) -> str:
    """Generate a follow-up query based on what was found."""
    if hop == 1:
        return f"additional requirements and documentation for: {original}"
    return f"further policy details: {original}"

def agentic_retrieve(query: str, n_per_hop: int = 3) -> Dict:
    """Multi-hop retrieval loop: retrieve -> observe -> decide -> retrieve again if needed."""
    t0 = time.time()
    all_chunks = []
    seen_ids = set()
    hops_taken = 0
    current_query = query
    hop_log = []
    
    for hop in range(MAX_HOPS):
        hops_taken += 1
        hop_chunks = hybrid_search(current_query, n_per_hop)
        new_chunks = [c for c in hop_chunks if c['chunk_id'] not in seen_ids]
        all_chunks.extend(new_chunks)
        seen_ids.update(c['chunk_id'] for c in new_chunks)
        hop_log.append({'hop': hop+1, 'query': current_query, 'chunks_found': len(new_chunks)})
        
        if not _needs_more_retrieval(query, all_chunks, hop):
            break
        current_query = _rewrite_query(query, all_chunks, hop + 1)
    
    elapsed = time.time() - t0
    context = '\n\n'.join([c['text'] for c in all_chunks])
    token_est = len(context.split()) + len(query.split())
    
    return {
        'query': query,
        'retrieved_chunks': all_chunks,
        'context': context,
        'token_estimate': token_est,
        'retrieval_latency_s': round(elapsed, 3),
        'hops_taken': hops_taken,
        'hop_log': hop_log,
        'architecture': 'agentic_rag'
    }

def answer(query: str, n_per_hop: int = 3, llm_fn=None) -> Dict:
    result = agentic_retrieve(query, n_per_hop)
    if llm_fn:
        t1 = time.time()
        result['answer'] = llm_fn(query, result['context'])
        result['generation_latency_s'] = round(time.time() - t1, 3)
    return result
