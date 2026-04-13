# application/services/review_service.py

from infrastructure.database import Database
from domain.entities import ModeratorReview, Comment, SubredditProfile
from domain.enums import ReviewDecision, CommentStatus
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ReviewService:
    """Upravljanje moderatorskim feedback-om i učenjem"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def save_review(self, review: ModeratorReview) -> int:
        """Spremi moderatorsku procjenu (gold label)"""
        review_id = self.db.save_review(review)
         # LEARN: update subreddit error stats + auto-tune threshold from corrections
        self._learn_from_correction(review)
        # Ažuriraj counter za learning
        settings = self.db.get_system_settings()
        settings.new_gold_since_last_train += 1
        self.db.update_system_settings(settings)
        
        # LEARN: Ako je decision = APPROVE, dodaj term u allowed_terms profila
        comment = self.db.get_comment_by_id(review.comment_id)
        if comment and review.decision == ReviewDecision.APPROVE:
            self._learn_allowed_term(comment, review)
        
        logger.info(
            f"Saved review for comment {review.comment_id}: "
            f"{review.decision.value} (gold #{settings.new_gold_since_last_train})"
        )
        
        return review_id
    
    def submit_review_api(self, payload: dict) -> int:
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")

        if "comment_id" not in payload:
            raise ValueError("comment_id is required")
        try:
            comment_id = int(payload["comment_id"])
        except (TypeError, ValueError):
            raise ValueError("comment_id must be an integer")

        decision_raw = payload.get("decision")
        if not decision_raw:
            raise ValueError("decision is required")
        decision_raw = str(decision_raw).strip().lower()

        try:
            decision = ReviewDecision(decision_raw)
        except ValueError:
            raise ValueError(f"Invalid decision '{decision_raw}'")

        notes = payload.get("notes")
        if notes is not None:
            notes = str(notes)

        review = ModeratorReview(
            comment_id=comment_id,
            decision=decision,
            moderator_notes=notes,
            reviewed_at=datetime.utcnow(),
        )
        return self.save_review(review)
    
    def _learn_from_correction(self, review: ModeratorReview) -> None:
        comment = self.db.get_comment_by_id(review.comment_id)
        if not comment:
            return

        pred = self.db.get_prediction(review.comment_id)
        if not pred:
            return

        profile = self.db.get_or_create_profile(comment.subreddit)

        # Map moderator label to binary target for error counting
        moderator_toxic = review.decision in (ReviewDecision.REJECT, ReviewDecision.REJECTED, ReviewDecision.TOXIC)
        moderator_clean = review.decision in (ReviewDecision.APPROVE, ReviewDecision.APPROVED, ReviewDecision.CLEAN)

        # Borderline/needs_context/unsupported -> don't count as FP/FN
        if not (moderator_toxic or moderator_clean):
            return

        predicted_toxic = pred.adjusted_toxicity >= profile.threshold

        profile.total_processed += 1

        if predicted_toxic and moderator_clean:
            profile.false_positives += 1
            # Too aggressive -> raise threshold slightly
            profile.threshold = min(0.90, profile.threshold + 0.01)

        if (not predicted_toxic) and moderator_toxic:
            profile.false_negatives += 1
            # Too lenient -> lower threshold slightly
            profile.threshold = max(0.30, profile.threshold - 0.01)

        self.db.update_profile(profile)
    
    
    def _learn_allowed_term(self, comment: Comment, review: ModeratorReview) -> None:
        """Ako moderator approve-a, dodaj termine u profil kao dozvoljene"""
        profile = self.db.get_or_create_profile(comment.subreddit)
        
        if review.moderator_notes:
            if "approved_term:" in review.moderator_notes:
                terms = [
                    t.strip() 
                    for t in review.moderator_notes.split("approved_term:")
                    if t.strip()
                ]
                profile.allowed_terms.extend(terms)
                profile.last_updated = datetime.utcnow()
                self.db.update_profile(profile)
                logger.info(
                    f"Learned {len(terms)} allowed terms for r/{comment.subreddit}"
                )
    
    def get_review_stats(self, subreddit: str) -> dict:
        """Statistika za subreddit"""
        profile = self.db.get_or_create_profile(subreddit)
        return {
            'subreddit': subreddit,
            'allowed_terms': profile.allowed_terms,
            'total_processed': profile.total_processed,
            'false_positives': profile.false_positives,
            'false_negatives': profile.false_negatives
        }