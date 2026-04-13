from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from infrastructure.database import Database
from domain.enums import CommentStatus
from datetime import datetime

if TYPE_CHECKING:
    from application.services.review_service import ReviewService

class ModerationService:
    def __init__(self, db: Database, review_service: "ReviewService"):
        self.db = db
        self.review_service = review_service


    @staticmethod
    def _parse_int(value: Optional[str], default: int, min_value: int, max_value: int) -> int:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return default
        if n < min_value:
            return min_value
        if n > max_value:
            return max_value
        return n

    @staticmethod
    def _clean_prefix(value: Optional[str], prefix: str) -> Optional[str]:
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        if s.lower().startswith(prefix):
            s = s[len(prefix):].strip()
        return s or None

    def get_pending_comments_api(
        self,
        limit_param: Optional[str],
        offset_param: Optional[str],
        author_param: Optional[str],
        subreddit_param: Optional[str],
    ) -> dict:
        limit = self._parse_int(limit_param, default=10, min_value=1, max_value=200)
        offset = self._parse_int(offset_param, default=0, min_value=0, max_value=100000)

        author = self._clean_prefix(author_param, "u/")
        subreddit = self._clean_prefix(subreddit_param, "r/")

        if author or subreddit:
            pending = self.db.get_comments_by_status_filtered(
                CommentStatus.PENDING_REVIEW,
                limit=limit,
                offset=offset,
                author=author,
                subreddit=subreddit,
            )
        else:
            pending = self.db.get_comments_by_status(CommentStatus.PENDING_REVIEW, limit, offset)

        default_jigsaw = {
            "toxicity": 0.0,
            "severe_toxicity": 0.0,
            "obscene": 0.0,
            "threat": 0.0,
            "insult": 0.0,
            "identity_attack": 0.0,
        }

        comments = []
        for comment in pending:
            prediction = self.db.get_prediction(comment.id)

            scores = dict(default_jigsaw)
            if prediction and isinstance(getattr(prediction, "jigsaw_scores", None), dict):
                for key in scores.keys():
                    v = prediction.jigsaw_scores.get(key)
                    if isinstance(v, (int, float)):
                        scores[key] = float(v)

            comments.append({
                "id": comment.id,
                "text": comment.text,
                "author": comment.author,
                "subreddit": comment.subreddit,
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
                "score": prediction.adjusted_toxicity if prediction else 0,
                "confidence": prediction.confidence if prediction else 0,
                "category": prediction.category.value if prediction else "clean",
                "jigsaw_scores": scores,
                "explanation": prediction.explanation if prediction else "",
                "status": comment.status.value,
            })

        return {
            "comments": comments,
            "count": len(comments),
            "total_pending": self.db.get_status_count(CommentStatus.PENDING_REVIEW),
            "total_reviewed": self.db.get_status_count(CommentStatus.REVIEWED),
        }
    
    def resolve_comment_api(self, comment_id: int, payload: dict) -> tuple[dict, int]:
        decision_raw = (payload.get("decision") or "").strip().lower()
        notes = payload.get("notes", "")

        from domain.entities import ModeratorReview
        from domain.enums import ReviewDecision, CommentStatus

        decision_map = {
            "approve": ReviewDecision.APPROVED,
            "reject": ReviewDecision.REJECTED,
            "clean": ReviewDecision.CLEAN,
            "toxic": ReviewDecision.TOXIC,
            "borderline": ReviewDecision.NEEDS_CONTEXT,
            "unsupported": ReviewDecision.NEEDS_CONTEXT,
        }

        if decision_raw not in decision_map:
            return {"error": f"Invalid decision '{decision_raw}'"}, 400

        review = ModeratorReview(
            comment_id=comment_id,
            decision=decision_map[decision_raw],
            moderator_notes=notes,
            reviewed_at=datetime.utcnow(),
        )

        self.review_service.save_review(review)
        self.db.update_comment_status(comment_id, CommentStatus.REVIEWED)

        return {"success": True, "comment_id": comment_id, "decision": decision_raw}, 200