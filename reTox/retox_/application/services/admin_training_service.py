import logging
import os
import time
import csv
from datetime import datetime

from infrastructure.database import Database
from domain.enums import CommentStatus
from application.services.advanced_training_service import AdvancedTrainingService

logger = logging.getLogger(__name__)


class AdminTrainingService:
    def __init__(self, db: Database, advanced_training_service: AdvancedTrainingService | None = None):
        self.db = db
        self.advanced_training_service = advanced_training_service

    def delete_training_history_api(self) -> tuple[dict, int]:
        self.db.execute("DELETE FROM model_versions")

        settings = self.db.get_system_settings()
        settings.new_gold_since_last_train = 0
        settings.last_retrain_date = None
        self.db.update_system_settings(settings)

        logger.info("Training history deleted")
        return {"success": True, "message": "Training history cleared"}, 200

    def import_ruddit_csv_as_gold_labels(
        self,
        csv_path: str,
        max_rows: int = 2000,
        toxic_threshold: float = 0.2,
        clean_threshold: float = -0.2,
    ) -> dict:
        """
        Imports ruddit_comments_score.csv into DB as reviewed comments + moderator_reviews.
        Uses score thresholds to create pseudo-labels:
          score >= toxic_threshold  -> decision 'toxic'
          score <= clean_threshold  -> decision 'clean'
          otherwise skip
        """
        marker_external_id = "ruddit:__imported__"
        if self.db.get_comment_id_by_external_id(marker_external_id):
            return {"already_imported": True, "inserted": 0, "skipped": 0}

        inserted = 0
        skipped = 0

        conn = self.db._get_connection()
        cursor = conn.cursor()

        now = datetime.utcnow().isoformat()
        subreddit = "ruddit"
        author = "ruddit_dataset"

        try:
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

                    if score >= toxic_threshold:
                        decision = "toxic"
                    elif score <= clean_threshold:
                        decision = "clean"
                    else:
                        continue

                    comment_id = (row.get("comment_id") or "").strip()
                    if not comment_id:
                        continue

                    external_id = f"ruddit:{comment_id}"

                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO comments
                        (external_id, subreddit, author, text, parent_external_id, status, created_at, reddit_score, reddit_permalink, has_media)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            external_id,
                            subreddit,
                            author,
                            body,
                            None,
                            CommentStatus.REVIEWED.value,
                            now,
                            0,
                            "",
                            0,
                        ),
                    )

                    cursor.execute("SELECT id FROM comments WHERE external_id = ? LIMIT 1", (external_id,))
                    row_id = cursor.fetchone()
                    if not row_id:
                        skipped += 1
                        continue
                    db_comment_id = row_id[0]

                    cursor.execute(
                        "SELECT 1 FROM moderator_reviews WHERE comment_id = ? LIMIT 1",
                        (db_comment_id,),
                    )
                    if cursor.fetchone():
                        skipped += 1
                        continue

                    cursor.execute(
                        """
                        INSERT INTO moderator_reviews (comment_id, decision, moderator_notes, reviewed_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            db_comment_id,
                            decision,
                            "imported from ruddit_comments_score.csv",
                            now,
                        ),
                    )

                    inserted += 1
                    if inserted % 200 == 0:
                        conn.commit()

            cursor.execute(
                """
                INSERT OR IGNORE INTO comments
                (external_id, subreddit, author, text, parent_external_id, status, created_at, reddit_score, reddit_permalink, has_media)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    marker_external_id,
                    subreddit,
                    author,
                    "dataset imported marker",
                    None,
                    CommentStatus.COMPLETED.value,
                    now,
                    0,
                    "",
                    0,
                ),
            )

            conn.commit()
            return {"already_imported": False, "inserted": inserted, "skipped": skipped}
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def manual_train_api(self) -> tuple[dict, int]:
        t0 = time.time()

        csv_default = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "ruddit_comments_score.csv")
        )
        csv_path = os.getenv("RETOX_DATASET_CSV_PATH", csv_default)

        import_summary = None
        if os.getenv("RETOX_IMPORT_DATASET_ON_TRAIN", "1") == "1" and os.path.exists(csv_path):
            import_summary = self.import_ruddit_csv_as_gold_labels(
                csv_path=csv_path,
                max_rows=int(os.getenv("RETOX_DATASET_MAX_ROWS", "2000")),
                toxic_threshold=float(os.getenv("RETOX_TOXIC_THRESHOLD", "0.2")),
                clean_threshold=float(os.getenv("RETOX_CLEAN_THRESHOLD", "-0.2")),
            )

        if not self.advanced_training_service:
            return {"success": False, "error": "advanced_training_service_not_configured"}, 500

        result = self.advanced_training_service.train_model()

        if result.get("success"):
            settings = self.db.get_system_settings()
            settings.new_gold_since_last_train = 0
            settings.last_retrain_date = datetime.utcnow()
            self.db.update_system_settings(settings)

            return (
                {
                    "success": True,
                    "new_version": result["new_version"],
                    "improvement": result["performance"]["improvement"],
                    "import_summary": import_summary,
                    "duration_seconds": round(time.time() - t0, 2),
                },
                200,
            )

        return {"success": False, "error": result.get("reason") or result.get("error")}, 400
    
    def export_gold_labels_api(self) -> tuple[str, int, dict]:
        from io import StringIO

        reviews = self.db.get_all_reviews()

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["comment_id", "text", "decision", "notes", "reviewed_at"])

        for review in reviews:
            comment = self.db.get_comment_by_id(review.comment_id)
            writer.writerow([
                review.comment_id,
                comment.text[:100],
                review.decision.value,
                review.moderator_notes or "",
                review.reviewed_at.isoformat(),
            ])

        return output.getvalue(), 200, {"Content-Disposition": "attachment; filename=gold_labels.csv"}