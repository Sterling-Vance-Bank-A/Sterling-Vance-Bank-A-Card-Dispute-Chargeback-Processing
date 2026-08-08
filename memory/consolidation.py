import re
from .episodic_store import EpisodicStore
from .semantic_store import SemanticStore

class ConsolidationEngine:
    def __init__(self, episodic_store: EpisodicStore, semantic_store: SemanticStore):
        self.episodic_store = episodic_store
        self.semantic_store = semantic_store

    def extract_facts_from_episode(self, episode_row) -> list[dict]:
        facts = []
        content = episode_row[5] if isinstance(episode_row, tuple) else episode_row.get('content', '')
        
        # 'MERCH-XXX risk_score = N'
        merch_match = re.search(r'(MERCH-\w+)\s+risk_score\s*=\s*(\d+)', content, re.IGNORECASE)
        if merch_match:
            facts.append({
                'entity_type': 'merchant',
                'entity_id': merch_match.group(1).upper(),
                'attribute': 'risk_score',
                'value': merch_match.group(2)
            })

        # 'DISP-XXX assigned to ANL-XXX'
        disp_assign_match = re.search(r'(DISP-\w+)\s+assigned to\s+(ANL-\w+)', content, re.IGNORECASE)
        if disp_assign_match:
            facts.append({
                'entity_type': 'dispute',
                'entity_id': disp_assign_match.group(1).upper(),
                'attribute': 'assigned_analyst',
                'value': disp_assign_match.group(2).upper()
            })

        # 'DISP-XXX status: WORD'
        disp_status_match = re.search(r'(DISP-\w+)\s+status:\s*(\w+)', content, re.IGNORECASE)
        if disp_status_match:
            facts.append({
                'entity_type': 'dispute',
                'entity_id': disp_status_match.group(1).upper(),
                'attribute': 'status',
                'value': disp_status_match.group(2)
            })

        # 'DISP-XXX amount: $N'
        disp_amount_match = re.search(r'(DISP-\w+)\s+amount:\s*\$?([\d.]+)', content, re.IGNORECASE)
        if disp_amount_match:
            facts.append({
                'entity_type': 'dispute',
                'entity_id': disp_amount_match.group(1).upper(),
                'attribute': 'amount',
                'value': disp_amount_match.group(2)
            })

        # 'fraud flag' near 'DISP-XXX'
        if 'fraud flag' in content.lower():
            disp_match = re.search(r'(DISP-\w+)', content, re.IGNORECASE)
            if disp_match:
                facts.append({
                    'entity_type': 'dispute',
                    'entity_id': disp_match.group(1).upper(),
                    'attribute': 'fraud_flag',
                    'value': 'detected'
                })
                
        return facts

    def run_consolidation_pass(self, older_than_hours=24) -> dict:
        episodes = self.episodic_store.get_episodes_older_than_hours(hours=older_than_hours)
        
        episodes_processed = len(episodes)
        facts_extracted = 0
        facts_updated = 0
        facts_new = 0
        conflicts_resolved = []
        
        for ep in episodes:
            ep_id = ep[0] if isinstance(ep, tuple) else ep.get('id')
            facts = self.extract_facts_from_episode(ep)
            facts_extracted += len(facts)
            
            for fact in facts:
                # To accurately track new vs updated, we would check before upsert
                active_facts = self.semantic_store.get_active_facts(
                    entity_type=fact['entity_type'], 
                    entity_id=fact['entity_id']
                )
                
                existing_fact = next((f for f in active_facts if f['attribute'] == fact['attribute']), None)
                
                conflict_note = None
                if existing_fact and existing_fact['value'] != fact['value']:
                    conflict_note = f"Updated from {existing_fact['value']} to {fact['value']}"
                    facts_updated += 1
                    conflicts_resolved.append({
                        'old_value': existing_fact['value'],
                        'new_value': fact['value'],
                        'entity': fact['entity_id'],
                        'attribute': fact['attribute']
                    })
                elif not existing_fact:
                    facts_new += 1
                    
                self.semantic_store.upsert_fact(
                    entity_type=fact['entity_type'],
                    entity_id=fact['entity_id'],
                    attribute=fact['attribute'],
                    value=fact['value'],
                    source_episode_ids=[ep_id],
                    conflict_note=conflict_note
                )
                
        self.semantic_store.expire_old_facts(days=30)
        
        return {
            'episodes_processed': episodes_processed,
            'facts_extracted': facts_extracted,
            'facts_updated': facts_updated,
            'facts_new': facts_new,
            'conflicts_resolved': conflicts_resolved
        }

    def demonstrate_real_conflict(self) -> dict:
        session_id = 'DEMO-CONFLICT'
        content_a = 'MERCH-004 risk_score = 45 as of initial onboarding assessment'
        content_b = 'MERCH-004 risk_score = 92 following fraud investigation completed'
        
        ep_id_a = self.episodic_store.add_episode(session_id=session_id, content=content_a)
        ep_id_b = self.episodic_store.add_episode(session_id=session_id, content=content_b)
        
        ep_a = self.episodic_store.conn.cursor().execute('SELECT * FROM episodes WHERE id=?', (ep_id_a,)).fetchone()
        ep_b = self.episodic_store.conn.cursor().execute('SELECT * FROM episodes WHERE id=?', (ep_id_b,)).fetchone()
        
        fact_a = self.extract_facts_from_episode(ep_a)[0]
        fact_b = self.extract_facts_from_episode(ep_b)[0]
        
        self.semantic_store.upsert_fact(**fact_a, source_episode_ids=[ep_id_a])
        self.semantic_store.upsert_fact(
            **fact_b, 
            source_episode_ids=[ep_id_b], 
            conflict_note="Conflict resolution: newer_value_wins"
        )
        
        history = self.semantic_store.get_fact_history(fact_b['entity_type'], fact_b['entity_id'], fact_b['attribute'])
        v1 = next((h for h in history if h['version'] == 1), None)
        v2 = next((h for h in history if h['version'] == 2), None)
        
        return {
            'old_fact': v1,
            'new_fact': v2,
            'resolution': 'newer_value_wins'
        }
