import networkx as nx
from typing import List, Dict, Optional
import re, time
from .chunker import get_chunks
from .vector_store import get_store

def build_policy_graph(chunks: List[Dict]) -> nx.DiGraph:
    """Build entity graph: ReasonCode -> PolicySection -> Threshold -> MerchantCategory."""
    G = nx.DiGraph()
    for chunk in chunks:
        section = chunk.get('section', '')
        text = chunk['text']
        # Add section node
        G.add_node(section, type='section', chunk_id=chunk['chunk_id'], text_preview=text[:100])
        # Extract reason codes
        codes = re.findall(r'\b(48\d{2})\b', text)
        for code in codes:
            G.add_node(f'RC:{code}', type='reason_code')
            G.add_edge(f'RC:{code}', section, relation='defined_in')
        # Extract thresholds
        thresholds = re.findall(r'\$([\d,]+(?:\.\d+)?)', text)
        for t in thresholds:
            node = f'THRESH:{t}'
            G.add_node(node, type='threshold', value=t)
            G.add_edge(section, node, relation='defines_threshold')
        # Extract VISA/MC rules
        rules = re.findall(r'(?:VISA|Mastercard)\s+Rule\s+([\d.]+)', text)
        for rule in rules:
            node = f'RULE:{rule}'
            G.add_node(node, type='card_rule')
            G.add_edge(node, section, relation='documented_in')
    return G

def graph_retrieve(query: str, n_results: int = 3) -> Dict:
    """Use graph traversal to augment vector retrieval."""
    t0 = time.time()
    chunks = get_chunks('section')
    G = build_policy_graph(chunks)
    store = get_store()
    
    # Vector search first
    initial = store.search(query, n_results=n_results)
    retrieved_sections = set(r['metadata'].get('section', '') for r in initial if 'metadata' in r)
    
    # Graph expansion: get neighbors of retrieved sections
    expanded_chunks = []
    seen_ids = set(r['chunk_id'] for r in initial)
    chunk_map = {c['chunk_id']: c for c in chunks}
    
    for section in retrieved_sections:
        if section in G:
            for neighbor in G.neighbors(section):
                node_data = G.nodes[neighbor]
                if node_data.get('type') == 'section':
                    cid = node_data.get('chunk_id')
                    if cid and cid not in seen_ids:
                        expanded_chunks.append(chunk_map[cid])
                        seen_ids.add(cid)
    
    all_chunks = initial + expanded_chunks[:2]  # cap expansion
    elapsed = time.time() - t0
    context = '\n\n'.join([r.get('text', '') for r in all_chunks])
    token_est = len(context.split()) + len(query.split())
    
    return {
        'query': query,
        'retrieved_chunks': all_chunks,
        'context': context,
        'token_estimate': token_est,
        'retrieval_latency_s': round(elapsed, 3),
        'graph_nodes': G.number_of_nodes(),
        'graph_edges': G.number_of_edges(),
        'architecture': 'graph_rag'
    }

def answer(query: str, n_results: int = 3, llm_fn=None) -> Dict:
    result = graph_retrieve(query, n_results)
    if llm_fn:
        t1 = time.time()
        result['answer'] = llm_fn(query, result['context'])
        result['generation_latency_s'] = round(time.time() - t1, 3)
    return result
