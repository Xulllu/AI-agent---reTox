# application/services/profile_service.py

from infrastructure.database import Database
from domain.entities import SubredditProfile
from typing import List
import logging

logger = logging.getLogger(__name__)

class ProfileService:
    """Upravljanje subreddit profilima - KLJUČNA ZA KONTEKST"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_or_create(self, subreddit: str) -> SubredditProfile:
        """Uzmi ili kreiraj profil za subreddit"""
        return self.db.get_or_create_profile(subreddit)
    
    def get_profile_api(self, subreddit: str) -> dict:
        profile = self.get_or_create(subreddit)
        return {
            'subreddit': profile.subreddit_name,
            'allowed_terms': profile.allowed_terms,
            'sensitivity': profile.sensitivity,
            'threshold': profile.threshold,
            'total_processed': profile.total_processed,
            'false_positives': profile.false_positives,
            'false_negatives': profile.false_negatives
        }

    def calculate_context_adjustment(
        self,
        text: str,
        allowed_terms: List[str],
        parent_is_toxic: bool
    ) -> float:
        """
        Glavna KONTEKST logika!
        Ako tekst sadrži allowed_terms, smanjimo score
        """
        adjustment = 0.0
        
        text_lower = text.lower()
        
        # -1. Ako je parent toxic, povećaj suspicion
        if parent_is_toxic:
            adjustment += 0.1
        
        # -2. Ako text sadrži allowed_terms, SMANJI toxicity
        for term in allowed_terms:
            if term.lower() in text_lower:
                adjustment -= 0.15
                logger.debug(
                    f"Found allowed term '{term}' → adjustment {adjustment:+.3f}"
                )
        
        # Clamp adjustment
        adjustment = max(-0.5, min(0.3, adjustment))
        
        return adjustment
    
    def update_allowed_terms_api(self, subreddit: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")

        terms = payload.get("allowed_terms", [])
        if not isinstance(terms, list):
            raise ValueError("allowed_terms must be a list of strings")

        terms = [str(t).strip() for t in terms if str(t).strip()]

        profile = self.get_or_create(subreddit)
        profile.allowed_terms = terms
        self.db.update_profile(profile)

        return {"success": True, "subreddit": subreddit, "allowed_terms": terms}
    
    def update_threshold_api(self, subreddit: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")

        if "threshold" not in payload:
            raise ValueError("threshold is required")

        try:
            new_threshold = float(payload["threshold"])
        except (TypeError, ValueError):
            raise ValueError("threshold must be a number")

        self.update_threshold(subreddit, new_threshold)

        # Re-read so API returns clamped value (0.0..1.0)
        profile = self.get_or_create(subreddit)
        return {
            "success": True,
            "subreddit": subreddit,
            "new_threshold": profile.threshold,
        }
        
    def update_threshold(self, subreddit: str, new_threshold: float) -> None:
        """Dinamički promijeni threshold za subreddit"""
        profile = self.db.get_or_create_profile(subreddit)
        profile.threshold = max(0.0, min(1.0, new_threshold))
        self.db.update_profile(profile)
        logger.info(f"Updated threshold for r/{subreddit} → {new_threshold:.2f}")
    
    def update_sensitivity(self, subreddit: str, sensitivity: float) -> None:
        """Promijeni sensitivity (osjetljivost) za subreddit"""
        profile = self.db.get_or_create_profile(subreddit)
        profile.sensitivity = max(0.5, min(2.0, sensitivity))
        self.db.update_profile(profile)
        logger.info(f"Updated sensitivity for r/{subreddit} → {sensitivity:.2f}")
        
    def update_sensitivity_api(self, subreddit: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")

        if "sensitivity" not in payload:
            raise ValueError("sensitivity is required")

        try:
            new_sensitivity = float(payload["sensitivity"])
        except (TypeError, ValueError):
            raise ValueError("sensitivity must be a number")

        self.update_sensitivity(subreddit, new_sensitivity)

        # Re-read so API returns the clamped value (0.5..2.0)
        profile = self.get_or_create(subreddit)
        return {
            "success": True,
            "subreddit": subreddit,
            "new_sensitivity": profile.sensitivity,
        }