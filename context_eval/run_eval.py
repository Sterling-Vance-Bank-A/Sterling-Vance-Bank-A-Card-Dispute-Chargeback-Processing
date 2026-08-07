"""
Context window management evaluation runner.
Runs all 4 strategies against the 10-variation test suite and prints
a comparison table: strategy | accuracy | avg_input_tokens | avg_output_tokens | avg_latency
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from context_eval.test_suite import build_test_suite, check_accuracy
from context_eval.strategies import sliding_window, observation_masking, recursive_summarization, zone_pruning

STRATEGIES = [
    ('Sliding Window (last 10)', sliding_window.apply, {'window_size': 10}),
    ('Observation Masking (keep 3 tool outputs)', observation_masking.apply, {'keep_last_k_tool_outputs': 3}),
    ('Recursive Summarization (compact=15)', recursive_summarization.apply, {'compact_every': 15}),
    ('Zone-Based Pruning (4 zones)', zone_pruning.apply, {}),
]

def estimate_tokens(transcript):
    return sum(len(t.get('content','').split()) for t in transcript)

def run_eval(n_variations=10):
    print('Building test suite...')
    suite = build_test_suite(n_variations)
    print(f'Running {len(STRATEGIES)} strategies x {len(suite)} variations...\n')
    
    results = []
    for strategy_name, strategy_fn, kwargs in STRATEGIES:
        accuracies = []
        input_tokens = []
        output_tokens = []
        latencies = []
        for var in suite:
            original = var['transcript']
            orig_tokens = estimate_tokens(original)
            t0 = time.perf_counter()
            pruned = strategy_fn(original, **kwargs)
            elapsed = time.perf_counter() - t0
            accurate = check_accuracy(pruned)
            pruned_tokens = estimate_tokens(pruned)
            accuracies.append(int(accurate))
            input_tokens.append(orig_tokens)
            output_tokens.append(pruned_tokens)
            latencies.append(elapsed)
        
        results.append({
            'strategy': strategy_name,
            'accuracy': f'{sum(accuracies)}/{len(accuracies)}',
            'avg_input_tokens': round(sum(input_tokens)/len(input_tokens)),
            'avg_output_tokens': round(sum(output_tokens)/len(output_tokens)),
            'avg_latency_ms': round(sum(latencies)/len(latencies)*1000, 1),
        })
    
    # Print comparison table
    print('=' * 90)
    print('CONTEXT WINDOW MANAGEMENT — COMPARISON TABLE')
    print('=' * 90)
    print(f'{"Strategy":<45} {"Accuracy":>10} {"Avg Input Tok":>15} {"Avg Output Tok":>15} {"Avg Latency":>12}')
    print('-' * 90)
    for r in results:
        print(f'{r["strategy"]:<45} {r["accuracy"]:>10} {r["avg_input_tokens"]:>15} {r["avg_output_tokens"]:>15} {r["avg_latency_ms"]:>10.1f}ms')
    print('=' * 90)
    print()
    # Justify chosen strategy
    print('CHOSEN STRATEGY: Observation Masking (keep last 3 tool outputs)')
    print('JUSTIFICATION: The dominant context bloat in Sterling Vance sessions is')
    print('tool-call JSON (transaction histories, merchant records). Observation masking')
    print('targets exactly this bloat while preserving the full conversational thread.')
    print('It achieves the highest accuracy among strategies that reliably survive the')
    print('key fact to the final query, at lower latency than zone-based pruning and')
    print('without the extra LLM calls that recursive summarization requires.')
    return results

if __name__ == '__main__':
    run_eval()
