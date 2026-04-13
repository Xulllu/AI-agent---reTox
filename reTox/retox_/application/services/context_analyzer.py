# application/services/context_analyzer.py

from infrastructure.database import Database
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class ContextAnalyzer:
    """Analyze parent comments and subreddit context"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_parent_context(self, comment_id: int) -> Optional[str]:
        """Retrieve parent comment text for context"""
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            
            # Get current comment's parent_external_id
            cursor.execute('SELECT parent_external_id FROM comments WHERE id = ?', (comment_id,))
            result = cursor.fetchone()
            
            if not result or not result[0]:
                conn.close()
                return None
            
            parent_id = result[0]
            
            # Get parent comment text
            cursor.execute('SELECT text FROM comments WHERE external_id = ?', (parent_id,))
            parent = cursor.fetchone()
            
            conn.close()
            
            return parent[0] if parent else None
        
        except Exception as e:
            logger.error(f"Error getting parent context: {e}")
            return None
    
    def get_subreddit_context(self, subreddit: str) -> Dict:
        """Get subreddit-specific context (sensitivity, allowed_terms, etc)"""
        try:
            profile = self.db.get_or_create_profile(subreddit)
            
            return {
                'subreddit': subreddit,
                'allowed_terms': profile.allowed_terms if profile.allowed_terms else [],
                'sensitivity': profile.sensitivity,
                'threshold': profile.threshold,
                'false_positives': profile.false_positives,
                'false_negatives': profile.false_negatives
            }
        
        except Exception as e:
            logger.error(f"Error getting subreddit context: {e}")
            return {'subreddit': subreddit, 'allowed_terms': [], 'sensitivity': 1.0, 'threshold': 0.7}
    
    def analyze_context_compatibility(self, text: str, subreddit: str) -> float:
        """
        Score how compatible text is with subreddit context
        Returns: adjustment factor (-0.2 to +0.2)
        
        Example: "retarded" in r/medicine (technical term) vs r/gaming (slur)
        """
        context = self.get_subreddit_context(subreddit)
        text_lower = text.lower()
        
        # Check for allowed terms (reduce toxicity)
        allowed_count = sum(1 for term in context['allowed_terms'] if term.lower() in text_lower)
        if allowed_count > 0:
            return -0.15 * allowed_count  # Reduce score
        
        # Subreddit-specific rules
        if subreddit.lower() in ['medicine', 'science', 'askscience']:
            # Medical/scientific subreddits: technical jargon is acceptable
            technical_terms = ['retarded', 'handicapped', 'defective', 'lesion']
            technical_count = sum(1 for term in technical_terms if term in text_lower)
            if technical_count > 0:
                return -0.1  # Reduce toxicity score
        
        if subreddit.lower() in ['news', 'worldnews', 'politics']:
            # News subreddits: more formal, less slang tolerance
            slang_intensity = self._count_slang(text)
            if slang_intensity > 2:
                return 0.1  # Slightly increase toxicity
        
        return 0.0  # Neutral
    
    def _count_slang(self, text: str) -> int:
        """Count informal/slang language"""
        slang = ['gonna', 'wanna', 'gotta', 'ain\'t', 'y\'all', 'lol', 'omg']
        return sum(1 for s in slang if s in text.lower())