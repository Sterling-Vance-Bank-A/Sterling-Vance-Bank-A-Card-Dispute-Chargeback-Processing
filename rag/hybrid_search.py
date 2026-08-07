from rank_bm25 import BM25Okapi
from .vector_store import get_store
from .chunker import get_chunks
from typing import List, Dict, Optional
import time

def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)

def hybrid_search(query: str, n_results: int = 3, reason_code: str = None) -> List[Dict]:
    """RRF fusion of vector and BM25 scores."""
    store = get_store()
    chunks = get_chunks('section')  # get all chunks for BM25 corpus
    
    # Vector search
    vector_results = store.search_with_filter(query, reason_code=reason_code, n_results=min(10, max(n_results*3, 10)))
    
    # BM25 search
    tokenized = [c['text'].lower().split() for c in chunks]
    bm25 = BM25Okapi(tokenized)
    query_tokens = query.lower().split()
    bm25_scores = bm25.get_scores(query_tokens)
    bm25_ranked = sorted(enumerate(bm25_scores), key=lambda x: x[1], reverse=True)[:10]
    
    # RRF fusion
    rrf = {}
    for rank, result in enumerate(vector_results):
        cid = result['chunk_id']
        rrf[cid] = rrf.get(cid, 0) + _rrf_score(rank)
    
    for rank, (idx, score) in enumerate(bm25_ranked):
        cid = chunks[idx]['chunk_id']
        rrf[cid] = rrf.get(cid, 0) + _rrf_score(rank)
    
    # Sort by RRF score, return top n_results
    top_ids = sorted(rrf.keys(), key=lambda x: rrf[x], reverse=True)[:n_results]
    chunk_map = {c['chunk_id']: c for c in chunks}
    return [{**chunk_map[cid], 'rrf_score': rrf[cid], 'rank': i} for i, cid in enumerate(top_ids) if cid in chunk_map]

def answer(query: str, n_results: int = 3, reason_code: str = None, llm_fn=None) -> Dict:
    t0 = time.time()
    chunks = hybrid_search(query, n_results, reason_code)
    retrieval_time = time.time() - t0
    context = '\n\n'.join([c['text'] for c in chunks])
    token_est = len(context.split()) + len(query.split())
    result = {
        'query': query,
        'retrieved_chunks': chunks,
        'context': context,
        'token_estimate': token_est,
        'retrieval_latency_s': round(retrieval_time, 3),
        'architecture': 'hybrid_search'
    }
    if llm_fn:
        t1 = time.time()
        result['answer'] = llm_fn(query, context)
        result['generation_latency_s'] = round(time.time() - t1, 3)
    return result
