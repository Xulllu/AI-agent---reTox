# infrastructure/database.py
import os
import time
import logging
import sqlite3
import json
from typing import Optional, List
from datetime import datetime
from domain.entities import *
from domain.enums import *

logger = logging.getLogger(__name__)


class Database:
    """Database abstraction layer for retox system."""

    def __init__(self, db_path: str = "retox.db"):
        self.db_path = db_path
        self._create_tables()
        self._init_settings()

    def _get_connection(self):
        """Get a database connection with Row factory + better concurrency settings."""
        timeout_s = float(os.getenv("RETOX_SQLITE_TIMEOUT", "30"))
        busy_ms = int(os.getenv("RETOX_SQLITE_BUSY_TIMEOUT_MS", str(int(timeout_s * 1000))))

        conn = sqlite3.connect(
            self.db_path,
            timeout=timeout_s,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row

        # Better multi-process behavior
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute(f"PRAGMA busy_timeout={busy_ms};")

        return conn

    def _create_tables(self):
        """Create all required database tables."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Comments table
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE NOT NULL,
                subreddit TEXT NOT NULL,
                author TEXT NOT NULL,
                text TEXT NOT NULL,
                parent_external_id TEXT,
                status TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                reddit_score INTEGER DEFAULT 0,
                reddit_permalink TEXT,
                has_media BOOLEAN DEFAULT 0
            )
        '''
        )
        # Ensure schema upgrades for existing DBs
        cursor.execute("PRAGMA table_info(comments)")
        existing_cols = {row[1] for row in cursor.fetchall()}  # row[1] = name

        if "collection_job_id" not in existing_cols:
            cursor.execute("ALTER TABLE comments ADD COLUMN collection_job_id INTEGER")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_collection_job_id ON comments(collection_job_id)")

        # Subreddit profiles table
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS subreddit_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subreddit_name TEXT UNIQUE NOT NULL,
                allowed_terms TEXT NOT NULL,
                sensitivity REAL DEFAULT 1.0,
                threshold REAL DEFAULT 0.7,
                total_processed INTEGER DEFAULT 0,
                false_positives INTEGER DEFAULT 0,
                false_negatives INTEGER DEFAULT 0,
                last_updated TIMESTAMP NOT NULL
            )
        '''
        )

        # Predictions table
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comment_id INTEGER NOT NULL,
                base_toxicity REAL NOT NULL,
                adjusted_toxicity REAL NOT NULL,
                confidence REAL DEFAULT 0.5,
                category TEXT NOT NULL,
                explanation TEXT,
                model_version TEXT,
                jigsaw_scores TEXT,
                predicted_at TIMESTAMP NOT NULL,
                FOREIGN KEY (comment_id) REFERENCES comments (id)
            )
        '''
        )

        # Reviews table
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS moderator_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comment_id INTEGER NOT NULL,
                decision TEXT NOT NULL,
                moderator_notes TEXT,
                reviewed_at TIMESTAMP NOT NULL,
                FOREIGN KEY (comment_id) REFERENCES comments (id)
            )
        '''
        )

        # Collection jobs table
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS collection_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                subreddit TEXT NOT NULL,
                status TEXT NOT NULL,
                comments_collected INTEGER DEFAULT 0,
                created_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                error_message TEXT
            )
        '''
        )

        # System settings table
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS system_settings (
                id INTEGER PRIMARY KEY,
                gold_threshold INTEGER DEFAULT 50,
                retraining_enabled BOOLEAN DEFAULT 1,
                new_gold_since_last_train INTEGER DEFAULT 0,
                last_retrain_date TIMESTAMP
            )
        '''
        )

        # Agent events table (proof of Sense→Think→Act loop)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                phase TEXT NOT NULL,
                message TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_events_created_at ON agent_events(created_at)")

        # Model versions table (training history)
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS model_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT UNIQUE NOT NULL,
                accuracy_before REAL NOT NULL,
                accuracy_after REAL NOT NULL,
                improvement REAL NOT NULL,
                false_positives_before INTEGER,
                false_positives_after INTEGER,
                false_negatives_before INTEGER,
                false_negatives_after INTEGER,
                training_samples INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
        '''
        )

        conn.commit()
        conn.close()

    def save_agent_event(self, agent: str, phase: str, message: str = "") -> None:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO agent_events (agent, phase, message, created_at) VALUES (?, ?, ?, ?)",
                (agent, phase, message, datetime.utcnow().isoformat()),
            )
            conn.commit()
        except Exception:
            # tracing must never crash the app
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def get_recent_agent_events(self, limit: int = 50) -> List[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT agent, phase, message, created_at FROM agent_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]



    def _init_settings(self):
        """Initialize system settings if not already present."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM system_settings")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                '''
                INSERT INTO system_settings
                (id, gold_threshold, retraining_enabled, new_gold_since_last_train)
                VALUES (1, 50, 1, 0)
            '''
            )
            conn.commit()

        conn.close()

    # === COMMENT OPERATIONS ===

    def get_comment_id_by_external_id(self, external_id: str) -> Optional[int]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM comments WHERE external_id = ? LIMIT 1", (external_id,))
        row = cursor.fetchone()
        conn.close()
        return int(row["id"]) if row else None

    def save_comment(self, comment: Comment) -> int:
        """Save a comment to the database (retries on SQLITE_BUSY; idempotent on external_id)."""
        max_retries = int(os.getenv("RETOX_SQLITE_WRITE_RETRIES", "5"))
        backoff_base = float(os.getenv("RETOX_SQLITE_BACKOFF_BASE", "0.15"))

        last_error = None

        for attempt in range(max_retries):
            conn = None
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO comments
                    (external_id, subreddit, author, text, parent_external_id,
                    status, created_at, reddit_score, reddit_permalink, has_media, collection_job_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(external_id) DO UPDATE SET
                        -- keep existing status/history; just attach job if missing + refresh metadata
                        reddit_score = excluded.reddit_score,
                        reddit_permalink = COALESCE(excluded.reddit_permalink, comments.reddit_permalink),
                        has_media = excluded.has_media,
                        collection_job_id = COALESCE(comments.collection_job_id, excluded.collection_job_id)
                    """,
                    (
                        comment.external_id,
                        comment.subreddit,
                        comment.author,
                        comment.text,
                        comment.parent_external_id,
                        comment.status.value,
                        comment.created_at,
                        comment.reddit_score,
                        comment.reddit_permalink,
                        comment.has_media,
                        getattr(comment, "collection_job_id", None),
                    ),
                )

                cursor.execute("SELECT id FROM comments WHERE external_id = ? LIMIT 1", (comment.external_id,))
                row = cursor.fetchone()
                conn.commit()
                return int(row["id"]) if row else 0

            except sqlite3.OperationalError as e:
                last_error = e
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(backoff_base * (2**attempt))
                    continue
                raise

            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

        raise last_error if last_error else Exception("Failed to save comment")
    
    def claim_next_queued_comment(self) -> Optional[Comment]:
        """
        Atomically claim next queued comment by transitioning QUEUED -> PROCESSING.
        Prevents double-processing when multiple workers run.
        Uses BEGIN IMMEDIATE (SQLite) so select+update is atomic.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")

            cursor.execute(
                """
                SELECT * FROM comments
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (CommentStatus.QUEUED.value,),
            )
            row = cursor.fetchone()
            if not row:
                conn.commit()
                return None

            comment_id = int(row["id"])

            cursor.execute(
                """
                UPDATE comments
                SET status = ?
                WHERE id = ? AND status = ?
                """,
                (CommentStatus.PROCESSING.value, comment_id, CommentStatus.QUEUED.value),
            )

            if cursor.rowcount != 1:
                # someone else claimed it
                conn.commit()
                return None

            cursor.execute("SELECT * FROM comments WHERE id = ? LIMIT 1", (comment_id,))
            claimed = cursor.fetchone()

            conn.commit()
            return self._row_to_comment(claimed) if claimed else None

        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def get_next_queued_comment(self) -> Optional[Comment]:
        """Get the next queued comment for processing (atomic claim)."""
        return self.claim_next_queued_comment()

    def update_comment_status(self, comment_id: int, status: CommentStatus):
        """Update a comment's status."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("UPDATE comments SET status = ? WHERE id = ?", (status.value, comment_id))

        conn.commit()
        conn.close()

    def get_comment_by_id(self, comment_id: int) -> Optional[Comment]:
        """Retrieve a comment by its ID."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_comment(row)
        return None

    def get_comments_by_status(
        self, status: CommentStatus, limit: int = 10, offset: int = 0
    ) -> List[Comment]:
        """Get comments filtered by status with pagination."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM comments
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """,
            (status.value, limit, offset),
        )

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_comment(row) for row in rows]

    def get_comments_by_status_filtered(
        self,
        status: CommentStatus,
        limit: int = 10,
        offset: int = 0,
        author: Optional[str] = None,
        subreddit: Optional[str] = None,
    ) -> List[Comment]:
        conn = self._get_connection()
        cursor = conn.cursor()

        conditions = ["status = ?"]
        params: List[object] = [status.value]

        if author:
            conditions.append("author LIKE ?")
            params.append(f"%{author}%")

        if subreddit:
            conditions.append("subreddit LIKE ?")
            params.append(f"%{subreddit}%")

        sql = f"""
            SELECT * FROM comments
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """
        params.extend([limit, offset])

        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_comment(row) for row in rows]

    def get_status_count(self, status: CommentStatus) -> int:
        """Count comments by status."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM comments WHERE status = ?", (status.value,))
        row = cursor.fetchone()
        conn.close()

        return row["count"] if row else 0

    def get_comments_by_author(self, author: str) -> List[Comment]:
        """Get all comments by a specific author."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM comments WHERE author = ? ORDER BY created_at DESC", (author,))
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_comment(row) for row in rows]

    def get_all_comments(self, limit: int = 100, offset: int = 0) -> List[Comment]:
        """Get all comments with pagination."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM comments ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_comment(row) for row in rows]

    def count_by_status(self) -> dict:
        """Count comments by each status."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT status, COUNT(*) as count FROM comments GROUP BY status")
        rows = cursor.fetchall()
        conn.close()

        result = {}
        for row in rows:
            result[row["status"]] = row["count"]
        return result

    # === PROFILE OPERATIONS ===

    def get_or_create_profile(self, subreddit: str) -> SubredditProfile:
        """Get or create a subreddit profile."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM subreddit_profiles WHERE subreddit_name = ?", (subreddit,))
        row = cursor.fetchone()

        if row:
            profile = self._row_to_profile(row)
        else:
            cursor.execute(
                """
                INSERT INTO subreddit_profiles
                (subreddit_name, allowed_terms, sensitivity, threshold, last_updated)
                VALUES (?, ?, ?, ?, ?)
            """,
                (subreddit, json.dumps([]), 1.0, 0.7, datetime.utcnow()),
            )

            profile_id = cursor.lastrowid
            conn.commit()

            profile = SubredditProfile(
                id=profile_id,
                subreddit_name=subreddit,
                allowed_terms=[],
                sensitivity=1.0,
                threshold=0.7,
            )

        conn.close()
        return profile

    def update_profile(self, profile: SubredditProfile):
        """Update a subreddit profile."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE subreddit_profiles
            SET allowed_terms = ?,
                sensitivity = ?,
                threshold = ?,
                total_processed = ?,
                false_positives = ?,
                false_negatives = ?,
                last_updated = ?
            WHERE id = ?
        """,
            (
                json.dumps(profile.allowed_terms),
                profile.sensitivity,
                profile.threshold,
                profile.total_processed,
                profile.false_positives,
                profile.false_negatives,
                datetime.utcnow(),
                profile.id,
            ),
        )

        conn.commit()
        conn.close()

    # === PREDICTION OPERATIONS ===

    def save_prediction(self, prediction: Prediction) -> int:
        """Save a toxicity prediction to the database."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO predictions
            (comment_id, base_toxicity, adjusted_toxicity, confidence,
             category, explanation, model_version, jigsaw_scores, predicted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                prediction.comment_id,
                prediction.base_toxicity,
                prediction.adjusted_toxicity,
                prediction.confidence if hasattr(prediction, "confidence") else 0.5,
                prediction.category.value,
                prediction.explanation,
                prediction.model_version,
                json.dumps(prediction.jigsaw_scores) if prediction.jigsaw_scores else "{}",
                prediction.predicted_at,
            ),
        )

        prediction_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return prediction_id

    def get_prediction_by_comment_id(self, comment_id: int) -> Optional[Prediction]:
        """Get the latest prediction for a comment."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM predictions WHERE comment_id = ?", (comment_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_prediction(row)
        return None

    def get_prediction(self, comment_id: int) -> Optional[Prediction]:
        """Alias for get_prediction_by_comment_id."""
        return self.get_prediction_by_comment_id(comment_id)

    def count_by_category(self) -> dict:
        """Count predictions by toxicity category."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT category, COUNT(*) as count FROM predictions GROUP BY category")
        rows = cursor.fetchall()
        conn.close()

        result = {}
        for row in rows:
            result[row["category"]] = row["count"]
        return result

    # === REVIEW OPERATIONS ===

    def save_review(self, review: ModeratorReview) -> int:
        """Save a moderator review."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO moderator_reviews
            (comment_id, decision, moderator_notes, reviewed_at)
            VALUES (?, ?, ?, ?)
        """,
            (
                review.comment_id,
                review.decision.value,
                review.moderator_notes,
                review.reviewed_at,
            ),
        )

        review_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return review_id

    def get_all_reviews(self) -> List[ModeratorReview]:
        """Get all moderator reviews."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM moderator_reviews ORDER BY reviewed_at DESC")
        rows = cursor.fetchall()
        conn.close()

        reviews = []
        for row in rows:
            review = ModeratorReview(
                id=row["id"],
                comment_id=row["comment_id"],
                decision=ReviewDecision(row["decision"]),
                moderator_notes=row["moderator_notes"],
                reviewed_at=datetime.fromisoformat(row["reviewed_at"]),
            )
            reviews.append(review)

        return reviews

    def get_recent_collection_jobs(self, limit: int = 10) -> List[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, url, subreddit, status, comments_collected, created_at, completed_at, error_message
            FROM collection_jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_collection_job_comments(self, job_id: int, limit: int = 200) -> List[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                c.id,
                c.subreddit,
                c.author,
                c.text,
                c.created_at,
                c.reddit_permalink,
                c.status,

                p.adjusted_toxicity AS score,
                p.confidence AS confidence,
                p.category AS category,

                mr.decision AS review_decision,
                mr.moderator_notes AS review_notes,
                mr.reviewed_at AS reviewed_at

            FROM comments c

            LEFT JOIN predictions p
                ON p.id = (
                    SELECT p2.id FROM predictions p2
                    WHERE p2.comment_id = c.id
                    ORDER BY p2.predicted_at DESC
                    LIMIT 1
                )

            LEFT JOIN moderator_reviews mr
                ON mr.id = (
                    SELECT mr2.id FROM moderator_reviews mr2
                    WHERE mr2.comment_id = c.id
                    ORDER BY mr2.reviewed_at DESC
                    LIMIT 1
                )

            WHERE c.collection_job_id = ?
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (job_id, limit),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_recent_reviews_with_notes(self, limit: int = 20) -> List[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                mr.id AS review_id,
                mr.comment_id,
                mr.decision,
                mr.moderator_notes,
                mr.reviewed_at,

                c.subreddit,
                c.author,
                c.text,
                c.reddit_permalink,

                p.adjusted_toxicity AS score,
                p.confidence AS confidence,
                p.category AS category

            FROM moderator_reviews mr
            JOIN comments c ON c.id = mr.comment_id

            LEFT JOIN predictions p
                ON p.id = (
                    SELECT p2.id FROM predictions p2
                    WHERE p2.comment_id = c.id
                    ORDER BY p2.predicted_at DESC
                    LIMIT 1
                )

            ORDER BY mr.reviewed_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]





    # === COLLECTION JOB OPERATIONS ===

    def save_collection_job(self, job: CollectionJob) -> int:
        """Save a collection job."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO collection_jobs
            (url, subreddit, status, created_at)
            VALUES (?, ?, ?, ?)
        """,
            (job.url, job.subreddit, job.status.value, job.created_at),
        )

        job_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return job_id

    def get_next_pending_job(self) -> Optional[CollectionJob]:
        """Get the next pending collection job."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM collection_jobs
            WHERE status = ?
            ORDER BY created_at ASC
            LIMIT 1
        """,
            (CollectionJobStatus.PENDING.value,),
        )

        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_collection_job(row)
        return None

    def update_collection_job(self, job: CollectionJob):
        """Update a collection job's status."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE collection_jobs
            SET status = ?,
                comments_collected = ?,
                completed_at = ?,
                error_message = ?
            WHERE id = ?
        """,
            (
                job.status.value,
                job.comments_collected,
                job.completed_at,
                job.error_message,
                job.id,
            ),
        )

        conn.commit()
        conn.close()

    # === SYSTEM SETTINGS ===

    def get_system_settings(self) -> SystemSettings:
        """Retrieve system settings."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM system_settings WHERE id = 1")
        row = cursor.fetchone()
        conn.close()

        return SystemSettings(
            id=row["id"],
            gold_threshold=row["gold_threshold"],
            retraining_enabled=bool(row["retraining_enabled"]),
            new_gold_since_last_train=row["new_gold_since_last_train"],
            last_retrain_date=datetime.fromisoformat(row["last_retrain_date"]) if row["last_retrain_date"] else None,
        )

    def update_system_settings(self, settings: SystemSettings):
        """Update system settings."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE system_settings
            SET gold_threshold = ?,
                retraining_enabled = ?,
                new_gold_since_last_train = ?,
                last_retrain_date = ?
            WHERE id = 1
        """,
            (
                settings.gold_threshold,
                settings.retraining_enabled,
                settings.new_gold_since_last_train,
                settings.last_retrain_date,
            ),
        )

        conn.commit()
        conn.close()

    def execute(self, query: str, params: tuple = ()):
        """Execute raw SQL query."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        conn.close()

    def save_model_version(self, model_version) -> int:
        """Save a new model version to database."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO model_versions
            (version, base_model, accuracy_before, accuracy_after, improvement,
             false_positives, false_negatives, samples_trained, training_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                model_version.version,
                model_version.base_model,
                model_version.accuracy_before,
                model_version.accuracy_after,
                model_version.improvement,
                model_version.false_positives,
                model_version.false_negatives,
                model_version.samples_trained,
                model_version.training_date.isoformat()
                if hasattr(model_version.training_date, "isoformat")
                else model_version.training_date,
                model_version.notes,
            ),
        )

        conn.commit()
        conn.close()
        return cursor.lastrowid

    def get_model_training_history(self):
        """Get all model versions ordered by date (works with old/new schemas)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # New schema
            cursor.execute(
                """
                SELECT version, base_model, accuracy_before, accuracy_after, improvement,
                       false_positives, false_negatives, samples_trained, training_date, notes
                FROM model_versions
                ORDER BY training_date DESC
            """
            )
            rows = cursor.fetchall()
            return rows if rows else []

        except sqlite3.OperationalError:
            # Old schema fallback
            cursor.execute(
                """
                SELECT version,
                       'detoxify-original' as base_model,
                       accuracy_before, accuracy_after, improvement,
                       false_positives_after as false_positives,
                       false_negatives_after as false_negatives,
                       training_samples as samples_trained,
                       created_at as training_date,
                       '' as notes
                FROM model_versions
                ORDER BY created_at DESC
            """
            )
            rows = cursor.fetchall()
            return rows if rows else []

        finally:
            conn.close()

    # === HELPER METHODS ===

    def _row_to_comment(self, row) -> Comment:
        return Comment(
            id=row["id"],
            external_id=row["external_id"],
            subreddit=row["subreddit"],
            author=row["author"],
            text=row["text"],
            parent_external_id=row["parent_external_id"],
            status=CommentStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            reddit_score=row["reddit_score"],
            reddit_permalink=row["reddit_permalink"],
            has_media=bool(row["has_media"]),
            collection_job_id=row["collection_job_id"] if "collection_job_id" in row.keys() else None,
        )

    def _row_to_profile(self, row) -> SubredditProfile:
        """Convert database row to SubredditProfile entity."""
        return SubredditProfile(
            id=row["id"],
            subreddit_name=row["subreddit_name"],
            allowed_terms=json.loads(row["allowed_terms"]),
            sensitivity=row["sensitivity"],
            threshold=row["threshold"],
            total_processed=row["total_processed"],
            false_positives=row["false_positives"],
            false_negatives=row["false_negatives"],
            last_updated=datetime.fromisoformat(row["last_updated"]),
        )

    def _row_to_prediction(self, row) -> Prediction:
        """Convert database row to Prediction entity."""
        return Prediction(
            id=row["id"],
            comment_id=row["comment_id"],
            base_toxicity=row["base_toxicity"],
            adjusted_toxicity=row["adjusted_toxicity"],
            confidence=row["confidence"],
            category=ToxicityCategory(row["category"]),
            explanation=row["explanation"],
            model_version=row["model_version"],
            jigsaw_scores=json.loads(row["jigsaw_scores"]),
            predicted_at=datetime.fromisoformat(row["predicted_at"]),
        )

    def _row_to_collection_job(self, row) -> CollectionJob:
        """Convert database row to CollectionJob entity."""
        return CollectionJob(
            id=row["id"],
            url=row["url"],
            subreddit=row["subreddit"],
            status=CollectionJobStatus(row["status"]),
            comments_collected=row["comments_collected"],
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            error_message=row["error_message"],
        )