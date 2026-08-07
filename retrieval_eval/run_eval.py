"""
Retrieval architecture evaluation runner.
Runs naive RAG, hybrid search, agentic RAG, and graph RAG
against the 12 domain-specific test questions.
Measures: retrieval accuracy (key terms present), token estimate, latency.
Produces comparison table.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval_eval.test_questions import get_questions

def check_retrieval_accuracy(result_dict, key_terms):
    """Check if key terms appear in retrieved context."""
    context = result_dict.get('context', '').lower()
    hits = sum(1 for term in key_terms if term.lower() in context)
    return hits, len(key_terms), hits == len(key_terms)

def run_eval():
    # Import here so the vector store builds lazily
    from rag.naive_rag import answer as naive_answer
    from rag.hybrid_search import answer as hybrid_answer
    from rag.agentic_rag import answer as agentic_answer
    from rag.graph_rag import answer as graph_answer
    
    questions = get_questions()
    
    ARCHITECTURES = [
        ('Naive RAG', naive_answer, {}),
        ('Hybrid Search (vector+BM25)', hybrid_answer, {}),
        ('Agentic RAG (multi-hop)', agentic_answer, {}),
        ('Graph RAG', graph_answer, {}),
    ]
    
    print('Initializing vector store (first run downloads model)...')
    # Warm up
    from rag.vector_store import get_store
    store = get_store()
    print(f'Vector store ready: {store.count()} chunks indexed.\n')
    
    all_results = {}
    for arch_name, arch_fn, kwargs in ARCHITECTURES:
        print(f'Evaluating {arch_name}...')
        arch_results = []
        for q in questions:
            t0 = time.perf_counter()
            result = arch_fn(q['text'], **kwargs)
            elapsed = time.perf_counter() - t0
            hits, total, accurate = check_retrieval_accuracy(result, q['key_terms'])
            arch_results.append({
                'question_id': q['id'],
                'accurate': accurate,
                'hits': hits,
                'total_terms': total,
                'token_estimate': result.get('token_estimate', 0),
                'latency_s': round(elapsed, 3),
            })
        all_results[arch_name] = arch_results
    
    # Print comparison table
    print()
    print('=' * 100)
    print('RETRIEVAL ARCHITECTURE — COMPARISON TABLE')
    print('=' * 100)
    print(f'{"Architecture":<40} {"Accuracy":>12} {"Avg Tokens":>12} {"Avg Latency":>14}')
    print('-' * 100)
    for arch_name, arch_results in all_results.items():
        n = len(arch_results)
        accuracy = sum(r['accurate'] for r in arch_results)
        avg_tokens = round(sum(r['token_estimate'] for r in arch_results) / n)
        avg_latency = round(sum(r['latency_s'] for r in arch_results) / n, 3)
        print(f'{arch_name:<40} {f"{accuracy}/{n}":>12} {avg_tokens:>12} {avg_latency:>12.3f}s')
    print('=' * 100)
    print()
    print('CHOSEN ARCHITECTURE: Hybrid Search as default, Agentic RAG for multi-hop queries.')
    print('JUSTIFICATION: Sterling Vance analysts ask two types of questions:')
    print('  1. Quick policy lookups during live calls (reason code windows, exact section text).')
    print('     Hybrid search wins here: vector finds semantic context, BM25 finds exact IDs.')
    print('  2. Multi-condition queries requiring multiple policy sections to resolve.')
    print('     Agentic RAG handles these via its multi-hop loop at acceptable latency.')
    print('  Graph RAG adds value for entity-relationship traversal at lower token cost,')
    print('  and will be used for cross-entity queries (reason code -> policy section -> threshold).')
    return all_results

if __name__ == '__main__':
    run_eval()
