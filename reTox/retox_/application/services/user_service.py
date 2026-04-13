from infrastructure.database import Database
from domain.enums import ToxicityCategory


class UserService:
    def __init__(self, db: Database):
        self.db = db

    def get_user_profile_api(self, author: str) -> dict:
        comments = self.db.get_comments_by_author(author)

        toxic_count = 0
        clean_count = 0
        average_toxicity = 0
        last_toxic_date = None

        if comments:
            toxicity_scores = []
            for comment in comments:
                prediction = self.db.get_prediction(comment.id)
                if prediction:
                    toxicity_scores.append(prediction.adjusted_toxicity)

                    if prediction.category == ToxicityCategory.TOXIC:
                        toxic_count += 1
                        if not last_toxic_date or (comment.created_at and comment.created_at > last_toxic_date):
                            last_toxic_date = comment.created_at
                    else:
                        clean_count += 1

            average_toxicity = sum(toxicity_scores) / len(toxicity_scores) if toxicity_scores else 0

        return {
            "author": author,
            "total_comments": len(comments),
            "toxic_count": toxic_count,
            "clean_count": clean_count,
            "toxicity_rate": (toxic_count / len(comments)) if comments else 0,
            "average_toxicity": average_toxicity,
            "last_toxic_date": last_toxic_date.isoformat() if last_toxic_date else None,
            "is_high_risk": (toxic_count / len(comments) > 0.5) if comments else False,
        }