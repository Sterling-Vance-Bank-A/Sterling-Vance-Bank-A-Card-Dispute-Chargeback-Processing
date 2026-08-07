"""
Memory-augmented dispute agent for Sterling Vance Bank.
Wraps DisputeAgentClient with:
- Short-term buffer + scratchpad
- Episodic memory recall on session start
- Semantic fact recall via Self-RAG verification
- RAG pipeline for policy questions
- Promote-or-drop routing on buffer overflow
- End-of-session consolidation scheduling
"""
import asyncio
import os
import sys
import json
from datetime import datetime

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from memory.short_term import RollingBuffer, Scratchpad
from memory.episodic_store import EpisodicStore
from memory.semantic_store import SemanticStore
from memory.router import PromoteOrDropRouter
from memory.consolidation import ConsolidationEngine
from rag.naive_rag import retrieve as naive_retrieve
from rag.hybrid_search import hybrid_search
from rag.self_rag_verifier import verify_rag_answer, check_memory_recall

# Policy question keywords that trigger RAG instead of tool calls
POLICY_KEYWORDS = [
    'refund window', 'reason code', 'policy', 'rule', 'section', 'eligible',
    'escalation steps', 'documentation required', 'visa rule', 'mastercard',
    'chargeback threshold', 'unauthorized transaction', 'sign-off', 'days'
]

def is_policy_question(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in POLICY_KEYWORDS)

class MemoryAgent:
    """
    Memory-augmented agent wrapping the existing MCP dispute server.
    Demonstrates every concern: short-term buffer, scratchpad, episodic recall,
    semantic recall, promote-or-drop routing, RAG for policy questions, self-RAG verification.
    """
    
    def __init__(self, session_id: str = None, dispute_id: str = None, analyst_id: str = None):
        self.session_id = session_id or f'SESSION-{datetime.now().strftime("%Y%m%d-%H%M%S")}'
        self.dispute_id = dispute_id
        self.analyst_id = analyst_id
        
        # Memory subsystem
        self.buffer = RollingBuffer(maxlen=20)
        self.scratchpad = Scratchpad()
        self.episodic = EpisodicStore()
        self.semantic = SemanticStore()
        self.router = PromoteOrDropRouter(episodic_store=self.episodic)
        self.consolidation = ConsolidationEngine(episodic_store=self.episodic, semantic_store=self.semantic)
        
        print(f'[MemoryAgent] Session: {self.session_id}')
    
    def start_session(self, dispute_id: str, analyst_id: str):
        """Load episodic + semantic recall for dispute at session start."""
        self.dispute_id = dispute_id
        self.analyst_id = analyst_id
        self.scratchpad.update(
            active_dispute_id=dispute_id,
            active_analyst_id=analyst_id,
            working_state={'phase': 'investigation', 'started': datetime.now().isoformat()}
        )
        
        # Load episodic recall
        episodes = self.episodic.get_episodes_for_dispute(dispute_id, limit=5)
        if episodes:
            print(f'[Memory] Loaded {len(episodes)} episodic memories for {dispute_id}')
            for ep in episodes:
                print(f'  [Episode] {ep["timestamp"]}: {str(ep["content"])[:80]}...')
        
        # Load semantic recall
        facts = self.semantic.get_active_facts(entity_id=dispute_id)
        if facts:
            # Self-RAG verification on recalled facts
            verified = check_memory_recall(dispute_id, facts)
            print(f'[Memory] Recalled {len(verified["relevant_facts"])} semantic facts (dropped {len(verified["dropped_facts"])})')
            for fact in verified['relevant_facts']:
                print(f'  [Fact] {fact["entity_id"]}.{fact["attribute"]} = {fact["value"]} (v{fact.get("version",1)})')
        else:
            print(f'[Memory] No prior semantic facts for {dispute_id}')
    
    def push_turn(self, role: str, content: str, tags: list = None, turn_type: str = 'dialogue'):
        """Add a turn to short-term buffer; route overflow through promote-or-drop."""
        item = {
            'role': role,
            'content': content,
            'turn': len(self.buffer),
            'timestamp': datetime.now().isoformat(),
            'tags': tags or [],
            'turn_type': turn_type,
        }
        # If buffer is full, route oldest item before pushing
        if len(self.buffer) >= self.buffer.maxlen:
            oldest = self.buffer.items()[0]
            decision = self.router.route(oldest, self.session_id, len(self.buffer))
            print(f'[Router] Turn {oldest["turn"]} -> {decision} (score logged)')
        self.buffer.push(item)
    
    def answer_policy_question(self, question: str) -> str:
        """Route policy questions through RAG + Self-RAG verification."""
        print(f'[RAG] Policy question detected: {question[:60]}...')
        
        # Use hybrid search for policy questions (handles both semantic and exact IDs)
        chunks = hybrid_search(question, n_results=3)
        context = '\n\n'.join([c['text'] for c in chunks])
        
        # Self-RAG: relevance check
        verification = verify_rag_answer(question, chunks)
        if not verification['relevance']['passed']:
            print('[Self-RAG] Relevance check FAILED — re-retrieving...')
            chunks = hybrid_search(question, n_results=5)  # wider retrieval
            context = '\n\n'.join([c['text'] for c in chunks])
            verification = verify_rag_answer(question, chunks)
        
        if verification['relevance']['passed']:
            print(f'[Self-RAG] Relevance check PASSED ({len(chunks)} chunks relevant)')
            return f'[Based on Sterling Vance Policy]\n\n{context}'
        else:
            return '[POLICY NOT FOUND: The retrieved content does not appear to address this question. Please consult the Dispute & Chargeback Operations Manual directly.]'
    
    def process_turn(self, role: str, content: str) -> dict:
        """Process a conversation turn: route to RAG or buffer.
        
        Returns a dict with keys:
          - role: str
          - content: str
          - routed_to: 'rag' | 'buffer' | 'both'
          - rag_answer: str | None (set when a policy question is answered)
          - answer: str | None (alias for rag_answer for compatibility)
        """
        # Tag turn based on content
        tags = []
        if self.dispute_id and self.dispute_id in content:
            tags.append('dispute_id')
        if self.analyst_id and self.analyst_id in content:
            tags.append('analyst_id')
        if any(kw in content.lower() for kw in ['fraud', 'risk', 'flag']):
            tags.append('fraud_flag')
        if '$' in content or 'amount' in content.lower():
            tags.append('amount')
        
        self.push_turn(role, content, tags)
        
        # Policy questions go to RAG
        if role == 'user' and is_policy_question(content):
            rag_answer = self.answer_policy_question(content)
            return {
                'role': role,
                'content': content,
                'routed_to': 'rag',
                'rag_answer': rag_answer,
                'answer': rag_answer,
            }
        
        return {
            'role': role,
            'content': content,
            'routed_to': 'buffer',
            'rag_answer': None,
            'answer': None,
        }

    
    def end_session(self):
        """Flush remaining buffer through router and schedule consolidation."""
        print(f'[Session] Ending session {self.session_id}. Flushing buffer ({len(self.buffer)} items)...')
        for item in list(self.buffer.items()):
            decision = self.router.route(item, self.session_id, len(self.buffer))
        print(f'[Session] Buffer flushed. Scratchpad preserved: {self.scratchpad.to_dict()}')
        print(f'[Session] Consolidation will run on next scheduled pass (every 24h).')
    
    def run_consolidation_now(self):
        """Run consolidation immediately (for demo purposes)."""
        print('[Consolidation] Running consolidation pass...')
        summary = self.consolidation.run_consolidation_pass(older_than_hours=0)  # 0 = all episodes
        print(f'[Consolidation] Done: {summary}')
        return summary
    
    def demonstrate_conflict(self):
        """Demonstrate the MERCH-004 risk_score conflict resolution."""
        print('[Conflict Demo] Demonstrating real semantic conflict resolution...')
        result = self.consolidation.demonstrate_real_conflict()
        print(f'[Conflict Demo] Old fact: {result["old_fact"]}')
        print(f'[Conflict Demo] New fact: {result["new_fact"]}')
        print(f'[Conflict Demo] Resolution: {result["resolution"]}')
        return result
