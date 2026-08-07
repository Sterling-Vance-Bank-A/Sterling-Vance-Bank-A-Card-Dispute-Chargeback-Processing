"""
End-to-end demo: Sterling Vance Bank Memory & RAG Lab
Shows every concern firing in sequence.
Run: python memory_rag_demo.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.memory_agent import MemoryAgent
from rag.vector_store import get_store
from context_eval.run_eval import run_eval as run_context_eval
from retrieval_eval.run_eval import run_eval as run_retrieval_eval

DIVIDER = '=' * 70

def section(title):
    print(f'\n{DIVIDER}')
    print(f' {title}')
    print(DIVIDER)

def run_demo():
    section('1. VECTOR STORE INITIALIZATION')
    store = get_store()
    print(f'ChromaDB initialized: {store.count()} policy chunks indexed')
    print('HNSW index: cosine similarity, sentence-transformers/all-MiniLM-L6-v2')

    section('2. SHORT-TERM MEMORY + SCRATCHPAD')
    agent = MemoryAgent(session_id='DEMO-001')
    agent.start_session(dispute_id='DISP-073', analyst_id='ANL-002')
    
    # Simulate a multi-turn session
    turns = [
        ('user', 'Start investigation for DISP-073. Customer claims unauthorized charge.'),
        ('assistant', 'Beginning investigation. Fetching dispute details.'),
        ('tool', '{"dispute_id": "DISP-073", "amount": 847.50, "fraud_flag": "detected", "risk_score": 92}'),
        ('user', 'What is the refund window for unauthorized transaction disputes?'),  # policy question
        ('assistant', 'Checking policy for refund eligibility.'),
        ('tool', '{"merchant_id": "MERCH-004", "risk_score": 92, "category": "electronics"}'),
        ('user', 'DISP-073 assigned to ANL-002 for senior review'),
        ('assistant', 'Senior analyst review initiated for DISP-073.'),
    ]
    
    for role, content in turns:
        response = agent.process_turn(role, content)
        print(f'[Turn] {role}: {content[:60]}...' if len(content) > 60 else f'[Turn] {role}: {content}')
        if response and response.get('rag_answer'):
            print(f'[RAG Response] {str(response["rag_answer"])[:200]}...')


    section('3. PROMOTE-OR-DROP ROUTING')
    print(f'Buffer size: {len(agent.buffer)}/{agent.buffer.maxlen}')
    print('Routing decisions logged to memory/router_decisions.log')
    # Fill buffer to trigger routing
    for i in range(15):
        agent.push_turn('tool', f'{{"transaction_id": "TXN-{i:04d}", "amount": {10*i}}}', turn_type='tool_output')
    print(f'Buffer after fill: {len(agent.buffer)}/{agent.buffer.maxlen}')

    section('4. SEMANTIC CONFLICT RESOLUTION')
    conflict_result = agent.demonstrate_conflict()
    
    section('5. SESSION END + CONSOLIDATION')
    agent.end_session()
    consolidation_summary = agent.run_consolidation_now()
    print(f'Consolidation summary: {consolidation_summary}')

    section('6. CONTEXT WINDOW MANAGEMENT — ALL 4 STRATEGIES')
    print('Running 4 strategies x 10 test variations...')
    run_context_eval(n_variations=10)

    section('7. RETRIEVAL ARCHITECTURES — ALL 4')
    print('Running Naive RAG, Hybrid, Agentic, Graph RAG x 12 questions...')
    run_retrieval_eval()

    section('DEMO COMPLETE')
    print('Every concern demonstrated:')
    print('  [x] Short-term buffer + scratchpad')
    print('  [x] Promote-or-drop routing (logged)')
    print('  [x] Semantic conflict resolution (MERCH-004 risk_score)')
    print('  [x] Session end + consolidation')
    print('  [x] Context eval: 4 strategies x 10 variations')
    print('  [x] Retrieval eval: 4 architectures x 12 questions')
    print('  [x] Self-RAG verification on policy questions')
    print('  [x] Memory + RAG wired into agent loop')

if __name__ == '__main__':
    run_demo()
