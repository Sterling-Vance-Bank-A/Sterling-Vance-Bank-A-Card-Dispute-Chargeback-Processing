import os
import datetime
from .episodic_store import EpisodicStore
from .short_term import RollingBuffer

class PromoteOrDropRouter:
    def __init__(self, episodic_store: EpisodicStore, threshold=0.4, log_path=None):
        self.episodic_store = episodic_store
        self.threshold = threshold
        if log_path is None:
            self.log_path = os.path.join(os.path.dirname(__file__), 'router_decisions.log')
        else:
            self.log_path = log_path

    def score_item(self, item: dict) -> float:
        score = 0.0
        
        # recency
        turn = item.get('turn', 0)
        # simplistic recency scoring
        if turn < 5:
            score += 0.3
        else:
            score += 0.1
            
        # entity_tags
        tags = item.get('tags', [])
        if any(tag in tags for tag in ['dispute_id', 'analyst_id', 'fraud_flag', 'amount']):
            score += 0.4
            
        # content_weight
        content = item.get('content', '').lower()
        keywords = ['disp-', 'fraud', 'escalat', 'refund', 'amount', 'risk']
        if any(kw in content for kw in keywords):
            score += 0.3
            
        return min(score, 1.0)

    def route(self, item: dict, session_id: str, buffer_size: int) -> str:
        score = self.score_item(item)
        decision = 'PROMOTE' if score >= self.threshold else 'FORGET'
        
        content_preview = item.get('content', '')[:80].replace('\n', ' ')
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        turn = item.get('turn', 0)
        
        log_line = f"{timestamp} | {session_id} | {turn} | {score:.2f} | {decision} | {content_preview}\n"
        self._log(log_line)
        
        if decision == 'PROMOTE':
            self.episodic_store.add_episode(
                session_id=session_id,
                content=item.get('content', ''),
                dispute_id=next((t for t in item.get('tags', []) if t.startswith('DISP-')), None),
                analyst_id=next((t for t in item.get('tags', []) if t.startswith('ANL-')), None),
                promoted_from='router'
            )
            
        return decision

    def route_overflow(self, buffer: RollingBuffer, session_id: str):
        if len(buffer) > 0:
            oldest_item = buffer.items()[0]
            self.route(oldest_item, session_id, len(buffer))

    def _log(self, line: str):
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(line)
