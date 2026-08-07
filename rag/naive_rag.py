from .vector_store import get_store
from typing import List, Dict, Optional
import time

def retrieve(query: str, n_results: int = 3, reason_code: str = None) -> List[Dict]:
    store = get_store()
    return store.search_with_filter(query, reason_code=reason_code, n_results=n_results)

def answer(query: str, n_results: int = 3, llm_fn=None) -> Dict:
    """Retrieve top chunks. If llm_fn provided, generate answer. Else return retrieved context only."""
    t0 = time.time()
    chunks = retrieve(query, n_results)
    retrieval_time = time.time() - t0
    context = '\n\n'.join([c['text'] for c in chunks])
    token_est = len(context.split()) + len(query.split())
    result = {
        'query': query,
        'retrieved_chunks': chunks,
        'context': context,
        'token_estimate': token_est,
        'retrieval_latency_s': round(retrieval_time, 3),
        'architecture': 'naive_rag'
    }
    if llm_fn:
        t1 = time.time()
        result['answer'] = llm_fn(query, context)
        result['generation_latency_s'] = round(time.time() - t1, 3)
    return result
