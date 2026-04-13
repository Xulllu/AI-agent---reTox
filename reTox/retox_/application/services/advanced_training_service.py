# application/services/advanced_training_service.py

import torch
import numpy as np
from detoxify import Detoxify
from typing import List, Dict, Tuple
from datetime import datetime
from infrastructure.database import Database
import logging
import os
import csv
import joblib

from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import accuracy_score, confusion_matrix

logger = logging.getLogger(__name__)


class AdvancedTrainingService:
    """Advanced model retraining with actual fine-tuning (sklearn text model)."""

    def __init__(self, db: Database):
        self.db = db
        self.model = Detoxify("original")

        # Keep torch device (Detoxify depends on torch)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.current_version = "v1.0.0"

        # Optional sklearn model
        self.sklearn_model = None
        self._load_sklearn_model()

    def _default_sklearn_model_path(self) -> str:
        return os.path.join("models", "toxicity_sklearn.joblib")

    def _get_sklearn_model_path(self) -> str:
        return os.getenv("RETOX_SKLEARN_MODEL_PATH", self._default_sklearn_model_path())

    def _load_sklearn_model(self) -> None:
        model_path = self._get_sklearn_model_path()
        try:
            if os.path.exists(model_path):
                self.sklearn_model = joblib.load(model_path)
                logger.info(f"Loaded sklearn model from {model_path}")
        except Exception as e:
            logger.warning(f"Could not load sklearn model: {e}")
            self.sklearn_model = None

    def get_training_data(self) -> Tuple[List[str], List[int]]:
        """
        Collect all reviewed comments (gold labels) for training
        Returns: (texts, labels) where labels are 0 (clean) or 1 (toxic)
        """
        conn = self.db._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT c.text, mr.decision
            FROM comments c
            JOIN moderator_reviews mr ON c.id = mr.comment_id
            WHERE mr.decision IN ('approve','approved','clean','reject','rejected','toxic')
        """
        )

        texts: List[str] = []
        labels: List[int] = []

        for text, decision in cursor.fetchall():
            decision = (decision or "").lower()

            if decision in ("approve", "approved", "clean"):
                label = 0
            elif decision in ("reject", "rejected", "toxic"):
                label = 1
            else:
                continue

            if not text:
                continue

            texts.append(text)
            labels.append(label)

        conn.close()

        logger.info(f"Collected {len(texts)} training examples")
        logger.info(f"  Clean (0): {sum(1 for l in labels if l == 0)}")
        logger.info(f"  Toxic (1): {sum(1 for l in labels if l == 1)}")

        return texts, labels

    def _get_previous_accuracy(self) -> float:
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT accuracy_after FROM model_versions ORDER BY created_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            conn.close()
            return float(row[0]) if row and row[0] is not None else 0.0
        except Exception:
            return 0.0

    def _load_ruddit_csv(
        self,
        csv_path: str,
        max_rows: int,
        toxic_threshold: float,
        clean_threshold: float,
    ) -> Tuple[List[str], List[int]]:
        texts: List[str] = []
        labels: List[int] = []

        if not csv_path or not os.path.exists(csv_path):
            logger.warning(f"CSV not found: {csv_path}")
            return texts, labels

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break

                body = (row.get("body") or "").strip()
                if not body or body in ("[deleted]", "[removed]"):
                    continue

                try:
                    score = float(row.get("score", "0"))
                except Exception:
                    continue

                # Ruddit score: positive tends to be more "toxic", negative less
                if score >= toxic_threshold:
                    label = 1
                elif score <= clean_threshold:
                    label = 0
                else:
                    continue

                texts.append(body)
                labels.append(label)

        logger.info(f"Loaded {len(texts)} samples from CSV")
        return texts, labels

    def _train_sklearn_text_model(self, texts: List[str], labels: List[int]) -> Dict:
        model_path = self._get_sklearn_model_path()

        X_train, X_test, y_train, y_test = train_test_split(
            texts,
            labels,
            test_size=0.2,
            random_state=42,
            stratify=labels if len(set(labels)) > 1 else None,
        )

        pipeline = Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        ngram_range=(1, 2),
                        min_df=2,
                        max_features=int(os.getenv("RETOX_TFIDF_MAX_FEATURES", "50000")),
                        strip_accents="unicode",
                        lowercase=True,
                    ),
                ),
                (
                    "clf",
                    SGDClassifier(
                        loss="log_loss",
                        max_iter=int(os.getenv("RETOX_SGD_MAX_ITER", "1000")),
                        tol=1e-3,
                        class_weight="balanced",
                        random_state=42,
                    ),
                ),
            ]
        )

        pipeline.fit(X_train, y_train)

        y_pred = pipeline.predict(X_test)
        acc = float(accuracy_score(y_test, y_pred))

        cm = confusion_matrix(y_test, y_pred, labels=[0, 1])
        tn = int(cm[0][0]) if cm.shape == (2, 2) else 0
        fp = int(cm[0][1]) if cm.shape == (2, 2) else 0
        fn = int(cm[1][0]) if cm.shape == (2, 2) else 0
        tp = int(cm[1][1]) if cm.shape == (2, 2) else 0

        os.makedirs(os.path.dirname(model_path) or ".", exist_ok=True)
        joblib.dump(pipeline, model_path)

        # update in-memory model so API can use immediately (no restart required)
        self.sklearn_model = pipeline

        return {
            "model_path": model_path,
            "accuracy": acc,
            "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
            "samples": len(texts),
        }

    def analyze_model_performance(self) -> Dict:
        """Analyze current model performance on gold labels (Detoxify pipeline metrics)."""
        conn = self.db._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                p.adjusted_toxicity,
                mr.decision,
                c.subreddit
            FROM predictions p
            JOIN comments c ON p.comment_id = c.id
            JOIN moderator_reviews mr ON c.id = mr.comment_id
        """
        )

        correct = 0
        total = 0
        false_positives = 0
        false_negatives = 0
        predictions_by_subreddit: Dict[str, Dict[str, int]] = {}

        for row in cursor.fetchall():
            toxicity_score, decision, subreddit = row
            decision = (decision or "").lower()

            if decision in ("reject", "rejected", "toxic"):
                is_toxic = True
            elif decision in ("approve", "approved", "clean"):
                is_toxic = False
            else:
                continue

            total += 1
            predicted_toxic = float(toxicity_score) > 0.7

            if predicted_toxic == is_toxic:
                correct += 1
            elif predicted_toxic and not is_toxic:
                false_positives += 1
            elif (not predicted_toxic) and is_toxic:
                false_negatives += 1

            if subreddit not in predictions_by_subreddit:
                predictions_by_subreddit[subreddit] = {"correct": 0, "total": 0}

            if predicted_toxic == is_toxic:
                predictions_by_subreddit[subreddit]["correct"] += 1
            predictions_by_subreddit[subreddit]["total"] += 1

        conn.close()

        accuracy = correct / total if total > 0 else 0.0

        return {
            "total_predictions": total,
            "correct_predictions": correct,
            "accuracy": round(accuracy, 3),
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "precision": round(
                correct / (correct + false_positives) if (correct + false_positives) > 0 else 0.0,
                3,
            ),
            "by_subreddit": predictions_by_subreddit,
        }

    def train_model(self) -> Dict:
        """
        Train a real scikit-learn text classifier and persist it to disk.
        Uses: DB gold labels + optional external CSV dataset.
        """
        try:
            logger.info("=" * 60)
            logger.info("STARTING SKLEARN TEXT MODEL TRAINING")
            logger.info("=" * 60)

            # 1) Gold labels from DB
            texts_db, labels_db = self.get_training_data()

            # 2) Optional Kaggle CSV (Ruddit)
            csv_path = os.getenv(
                "RETOX_DATASET_CSV_PATH",
                os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..", "..", "..", "ruddit_comments_score.csv")
                ),
            )
            max_rows = int(os.getenv("RETOX_DATASET_MAX_ROWS", "50000"))
            toxic_thr = float(os.getenv("RETOX_TOXIC_THRESHOLD", "0.2"))
            clean_thr = float(os.getenv("RETOX_CLEAN_THRESHOLD", "-0.2"))

            texts_csv, labels_csv = self._load_ruddit_csv(
                csv_path, max_rows, toxic_thr, clean_thr
            )

            texts = list(texts_db) + list(texts_csv)
            labels = list(labels_db) + list(labels_csv)

            if len(texts) < 200:
                logger.warning(f"Not enough training data ({len(texts)} samples).")
                return {
                    "success": False,
                    "reason": "insufficient_training_data",
                    "samples": len(texts),
                }

            if len(set(labels)) < 2:
                logger.warning("Training data has only one class; cannot train a classifier.")
                return {
                    "success": False,
                    "reason": "single_class_training_data",
                    "samples": len(texts),
                }

            accuracy_before = self._get_previous_accuracy()

            # Train sklearn model
            result = self._train_sklearn_text_model(texts, labels)

            accuracy_after = float(result["accuracy"])
            improvement = accuracy_after - float(accuracy_before)

            new_version = self._generate_model_version()

            # Persist to model_versions
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO model_versions
                (version, accuracy_before, accuracy_after, improvement,
                 false_positives_before, false_positives_after,
                 false_negatives_before, false_negatives_after,
                 training_samples, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    new_version,
                    round(float(accuracy_before), 4),
                    round(float(accuracy_after), 4),
                    round(float(improvement), 4),
                    None,
                    int(result["confusion"]["fp"]),
                    None,
                    int(result["confusion"]["fn"]),
                    int(result["samples"]),
                    datetime.utcnow(),
                ),
            )
            conn.commit()
            conn.close()

            logger.info("SKLEARN TRAINING COMPLETED")
            logger.info(f"Saved model: {result['model_path']}")
            logger.info(f"Accuracy: {accuracy_after:.3f} (Δ {improvement:+.3f})")

            return {
                "success": True,
                "new_version": new_version,
                "training_data_size": len(texts),
                "performance": {
                    "accuracy_before": accuracy_before,
                    "accuracy_after": accuracy_after,
                    "improvement": improvement,
                },
            }

        except Exception as e:
            logger.error(f"Training error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _generate_model_version(self) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM model_versions")
        count = cursor.fetchone()[0]
        conn.close()
        return f"v{count + 1}.0.0_{timestamp}"

    def get_model_history(self) -> List[Dict]:
        rows = self.db.get_model_training_history()

        history: List[Dict] = []
        for row in rows:
            history.append(
                {
                    "version": row["version"],
                    "base_model": row["base_model"],
                    "accuracy_before": row["accuracy_before"],
                    "accuracy_after": row["accuracy_after"],
                    "improvement": row["improvement"],
                    "false_positives": row["false_positives"],
                    "false_negatives": row["false_negatives"],
                    "samples_trained": row["samples_trained"],
                    "training_date": row["training_date"],
                    "notes": row["notes"],
                }
            )

        return history

    def get_model_history_api(self) -> Dict:
        history = self.get_model_history()
        return {
            "models": history,
            "total_retrains": len(history),
        }

    def analyze_model_performance_api(self) -> Dict:
        return self.analyze_model_performance()
    
    def get_current_version(self) -> str:
        return self.current_version