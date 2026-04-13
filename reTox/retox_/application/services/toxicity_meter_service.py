from infrastructure.database import Database


class ToxicityMeterService:
    def __init__(self, db: Database):
        self.db = db

    def get_toxicity_meter_api(self, comment_id: int) -> tuple[dict, int]:
        _comment = self.db.get_comment_by_id(comment_id)  # zadržano radi identičnog ponašanja (kao prije)
        prediction = self.db.get_prediction(comment_id)

        if not prediction:
            return {"error": "No prediction found"}, 404

        toxicity_percent = int(prediction.adjusted_toxicity * 100)
        confidence_margin = int(prediction.confidence * 10)

        if toxicity_percent < 33:
            color = "green"
            risk = "safe"
        elif toxicity_percent < 66:
            color = "yellow"
            risk = "caution"
        else:
            color = "red"
            risk = "toxic"

        return ({
            "comment_id": comment_id,
            "toxicity_percent": toxicity_percent,
            "confidence_margin": confidence_margin,
            "color": color,
            "risk_level": risk,
            "category": prediction.category.value,
            "explanation": prediction.explanation,
        }, 200)