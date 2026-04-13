# application/services/toxicity_service.py (UPDATED)
import logging
import os
import ssl
import math
import threading
import time
from typing import Dict, Optional

import joblib
from detoxify import Detoxify

from application.services.sentiment_analyzer import SentimentAnalyzer
from application.services.entity_recognizer import EntityRecognizer
from application.services.context_analyzer import ContextAnalyzer
from application.services.confidence_estimator import ConfidenceEstimator
from infrastructure.database import Database


if os.getenv("RETOX_DISABLE_SSL_VERIFY", "0") == "1":
    ssl._create_default_https_context = ssl._create_unverified_context

logger = logging.getLogger(__name__)


class ToxicityService:
    def __init__(self, db: Database = None):
        # Load Detoxify model
        self.model = Detoxify("original")

        # Initialize NLP services
        self.sentiment_analyzer = SentimentAnalyzer()
        self.entity_recognizer = EntityRecognizer()
        self.confidence_estimator = ConfidenceEstimator()

        # Context requires database
        self.context_analyzer = ContextAnalyzer(db) if db else None

        # Optional sklearn model (trained via Admin)
        self.sklearn_model = None

        # --- NEW: reload support (mtime watcher) ---
        self._sklearn_model_path = self._resolve_sklearn_model_path()
        self._sklearn_model_mtime: Optional[float] = None
        self._sklearn_lock = threading.RLock()
        self._sklearn_last_check_ts = 0.0
        self._sklearn_check_interval_s = float(os.getenv("RETOX_SKLEARN_RELOAD_CHECK_S", "1.0"))
        # ------------------------------------------

        self._load_sklearn_model(force=True)

    def _resolve_sklearn_model_path(self) -> str:
        model_path = os.getenv("RETOX_SKLEARN_MODEL_PATH", "").strip()
        if not model_path:
            model_path = os.path.join("models", "toxicity_sklearn.joblib")
        return model_path

    def _load_sklearn_model(self, force: bool = False) -> None:
        """
        Load or reload sklearn model from disk.
        Uses mtime to avoid re-loading when unchanged.
        """
        # re-read env each time in case someone changes it (optional but safe)
        self._sklearn_model_path = self._resolve_sklearn_model_path()
        model_path = self._sklearn_model_path

        with self._sklearn_lock:
            if not os.path.exists(model_path):
                self.sklearn_model = None
                self._sklearn_model_mtime = None
                return

            try:
                mtime = os.path.getmtime(model_path)
                if (
                    not force
                    and self.sklearn_model is not None
                    and self._sklearn_model_mtime == mtime
                ):
                    return

                self.sklearn_model = joblib.load(model_path)
                self._sklearn_model_mtime = mtime
                logger.info(f"Loaded/Reloaded sklearn model from: {model_path} (mtime={mtime})")
            except Exception as e:
                logger.warning(f"Failed to load sklearn model from {model_path}: {e}")
                # keep previous model if any; don't crash
                if self.sklearn_model is None:
                    self._sklearn_model_mtime = None

    def _maybe_reload_sklearn_model(self) -> None:
        """
        Check if model file changed; if yes reload.
        Throttled to run at most once per _sklearn_check_interval_s.
        """
        now = time.time()
        if (now - self._sklearn_last_check_ts) < self._sklearn_check_interval_s:
            return
        self._sklearn_last_check_ts = now

        model_path = self._sklearn_model_path
        try:
            if not model_path or (not os.path.exists(model_path)):
                return
            mtime = os.path.getmtime(model_path)
            if self._sklearn_model_mtime != mtime:
                self._load_sklearn_model(force=True)
        except Exception:
            return

    async def predict(
        self,
        text: str,
        subreddit: str = "general",
        comment_id: Optional[int] = None,
    ) -> Dict:
        """
        Comprehensive toxicity prediction with context
        Returns: toxicity, confidence, reasoning
        """
        try:
            if not text or len(text.strip()) == 0:
                return self._empty_prediction()

            # NEW: reload model automatically after retrain (no restart)
            self._maybe_reload_sklearn_model()

            # 1. BASE TOXICITY SCORES (Detoxify)
            jigsaw_scores = self.model.predict(text)
            toxicity_scores = {
                "toxicity": float(jigsaw_scores["toxicity"]),
                "severe_toxicity": float(jigsaw_scores["severe_toxicity"]),
                "obscene": float(jigsaw_scores["obscene"]),
                "threat": float(jigsaw_scores["threat"]),
                "insult": float(jigsaw_scores["insult"]),
                "identity_attack": float(jigsaw_scores["identity_attack"]),
            }

            base_score = self.calculate_composite_score(toxicity_scores)

            # Optional: blend sklearn score into base_score
            sklearn_score = None
            if self.sklearn_model is not None:
                try:
                    if hasattr(self.sklearn_model, "predict_proba"):
                        proba = self.sklearn_model.predict_proba([text])[0]
                        sklearn_score = float(proba[1])  # P(toxic)
                    elif hasattr(self.sklearn_model, "decision_function"):
                        logit = float(self.sklearn_model.decision_function([text])[0])
                        sklearn_score = 1.0 / (1.0 + math.exp(-logit))
                    else:
                        raise ValueError("Sklearn model has no predict_proba/decision_function")

                    w = float(os.getenv("RETOX_SKLEARN_WEIGHT", "0.35"))
                    if w < 0.0:
                        w = 0.0
                    if w > 1.0:
                        w = 1.0

                    base_score = (1.0 - w) * base_score + w * sklearn_score
                except Exception as e:
                    logger.warning(f"Sklearn scoring failed: {e}")

            # 2. SENTIMENT ANALYSIS
            sentiment_scores = self.sentiment_analyzer.analyze(text)
            emotional_intensity = self.sentiment_analyzer.get_emotional_intensity(sentiment_scores)

            # 3. ENTITY RECOGNITION
            entities = self.entity_recognizer.extract_entities(text)
            has_personal_attacks = self.entity_recognizer.has_personal_attacks(text, entities)
            entity_count = self.entity_recognizer.count_entities(entities)

            # 4. CONTEXT ANALYSIS
            context_adjustment = 0.0
            parent_context = None

            if self.context_analyzer and comment_id:
                parent_context = self.context_analyzer.get_parent_context(comment_id)
                context_adjustment = self.context_analyzer.analyze_context_compatibility(text, subreddit)

            # 5. APPLY ADJUSTMENTS
            if emotional_intensity > 0.7 and base_score > 0.5:
                context_adjustment += 0.1
            elif emotional_intensity < 0.3 and base_score > 0.5:
                context_adjustment -= 0.05

            if has_personal_attacks:
                context_adjustment += 0.15

            # 6. CALCULATE FINAL SCORE
            adjusted_score = self.adjust_score(base_score, context_adjustment, 1.0)

            # 7. CONFIDENCE ESTIMATION
            confidence_data = self.confidence_estimator.estimate_confidence(
                toxicity_scores,
                sentiment_scores,
                entity_count,
                len(text),
            )

            return {
                "base_score": round(base_score, 3),
                "adjusted_score": round(adjusted_score, 3),
                "confidence": round(confidence_data["overall_confidence"], 3),
                "uncertainty": round(confidence_data["uncertainty"], 3),
                "toxicity_scores": toxicity_scores,
                "sentiment": sentiment_scores,
                "emotional_intensity": round(emotional_intensity, 3),
                "entities": entities,
                "has_personal_attacks": has_personal_attacks,
                "entity_count": entity_count,
                "context_adjustment": round(context_adjustment, 3),
                "parent_context_available": parent_context is not None,
                "sklearn_score": None if sklearn_score is None else round(sklearn_score, 3),
            }

        except Exception as e:
            logger.error(f"Error predicting toxicity: {e}", exc_info=True)
            return self._empty_prediction()

    def calculate_composite_score(self, scores: Dict[str, float]) -> float:
        return (
            scores["toxicity"] * 0.4
            + scores["severe_toxicity"] * 0.3
            + scores["insult"] * 0.2
            + scores["threat"] * 0.1
        )

    def adjust_score(self, base_score: float, context_adjustment: float, sensitivity: float) -> float:
        adjusted = (base_score + context_adjustment) * sensitivity
        return max(0.0, min(1.0, adjusted))

    def _empty_prediction(self) -> Dict:
        return {
            "base_score": 0.0,
            "adjusted_score": 0.0,
            "confidence": 0.0,
            "uncertainty": 1.0,
            "toxicity_scores": {
                k: 0.0
                for k in [
                    "toxicity",
                    "severe_toxicity",
                    "obscene",
                    "threat",
                    "insult",
                    "identity_attack",
                ]
            },
            "sentiment": {"positive": 0.0, "negative": 0.0, "neutral": 1.0, "compound": 0.0},
            "emotional_intensity": 0.0,
            "entities": {},
            "has_personal_attacks": False,
            "entity_count": 0,
            "context_adjustment": 0.0,
            "parent_context_available": False,
            "sklearn_score": None,
        }