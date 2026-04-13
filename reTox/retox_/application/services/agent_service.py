# application/services/agent_service.py
from infrastructure.database import Database
from datetime import datetime

class AgentService:
    def __init__(self, db: Database):
        self.db = db

    def get_recent_events(self, limit: int = 50) -> list[dict]:
        # Minimalna validacija (da ne sruši server neko sa limit=9999999)
        if limit is None:
            limit = 50
        limit = int(limit)
        if limit < 1:
            limit = 1
        if limit > 500:
            limit = 500

        return self.db.get_recent_agent_events(limit=limit)
    

    def health_api(self) -> dict:
        events = []
        try:
            events = self.db.get_recent_agent_events(limit=10)
        except Exception:
            events = []

        return {
            'status': 'ok',
            'timestamp': datetime.utcnow().isoformat(),
            'app': 'ReTox Agent',
            'agents': ['ClassificationRunner', 'LearningRunner', 'CollectionRunner'],
            'recent_agent_events': events
        }