# application/services/dashboard_service.py
from typing import Optional
from infrastructure.database import Database
from domain.enums import CommentStatus, ToxicityCategory, ReviewDecision
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class DashboardService:
    """Service for aggregating and retrieving dashboard statistics."""
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_dashboard_stats(self) -> dict:
        """Retrieve comprehensive dashboard statistics including comments, predictions, and reviews."""
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        try:
            # Total comments
            cursor.execute("SELECT COUNT(*) FROM comments")
            total_comments = cursor.fetchone()[0]
            
            # Comments by status
            cursor.execute("""
                SELECT status, COUNT(*) FROM comments GROUP BY status
            """)
            status_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Predictions by category
            cursor.execute("""
                SELECT category, COUNT(*) FROM predictions GROUP BY category
            """)
            category_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Average toxicity score
            cursor.execute("SELECT AVG(adjusted_toxicity) FROM predictions")
            avg_toxicity = cursor.fetchone()[0] or 0.0
            
            # Reviews summary
            cursor.execute("SELECT COUNT(*) FROM moderator_reviews")
            total_reviews = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT decision, COUNT(*) FROM moderator_reviews GROUP BY decision
            """)
            review_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Gold labels
            settings = self.db.get_system_settings()
            gold_labels = settings.new_gold_since_last_train
            gold_threshold = settings.gold_threshold
            
            # Last retrain
            last_retrain = settings.last_retrain_date.isoformat() if settings.last_retrain_date else None
            
            # Subreddit count
            cursor.execute("SELECT COUNT(DISTINCT subreddit_name) FROM subreddit_profiles")
            subreddit_count = cursor.fetchone()[0]
            
            # Calculate false negatives (toxic comments predicted as clean)
            false_negatives = self._calculate_false_negatives()
            
            # Calculate accuracy
            accuracy = self._calculate_accuracy()
            
            # Get retrain cycle count
            cursor.execute("SELECT COUNT(*) FROM model_versions")
            retrain_cycles = cursor.fetchone()[0]
            
            return {
                'summary': {
                    'total_comments': total_comments,
                    'total_reviews': total_reviews,
                    'total_subreddits': subreddit_count,
                    'average_toxicity': round(float(avg_toxicity), 3),
                    'accuracy_percent': round(accuracy, 1),
                    'false_negatives': false_negatives,
                    'retrain_cycles': retrain_cycles,
                    'gold_labels': gold_labels,
                    'gold_threshold': gold_threshold,
                    'gold_progress_percent': int((gold_labels / gold_threshold * 100) if gold_threshold > 0 else 0),
                    'last_retrain': last_retrain,
                },
                'comment_status': status_counts,
                'toxicity_categories': category_counts,
                'review_decisions': review_counts,
                'gold_labels_progress': {
                    'current': gold_labels,
                    'threshold': gold_threshold,
                    'percent': round(gold_labels / gold_threshold * 100, 1) if gold_threshold > 0 else 0
                }
            }
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {e}")
            return {}
        finally:
            conn.close()
    
    def get_recent_comments(self, limit: int = 20) -> list:
        """Retrieve recent comments with their predictions and toxicity scores."""
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    c.id, c.external_id, c.subreddit, c.author, c.text, 
                    c.status, c.created_at, p.category, p.adjusted_toxicity, p.confidence
                FROM comments c
                LEFT JOIN predictions p ON c.id = p.comment_id
                ORDER BY c.created_at DESC
                LIMIT ?
            """, (limit,))
            
            comments = []
            for row in cursor.fetchall():
                text = row[4] if row[4] else ""
                comments.append({
                    'id': row[0],
                    'external_id': row[1],
                    'subreddit': row[2],
                    'author': row[3],
                    'text': text[:100] + '...' if len(text) > 100 else text,
                    'status': row[5],
                    'created_at': row[6],
                    'category': row[7],
                    'toxicity': round(float(row[8]), 3) if row[8] else None,
                    'confidence': round(float(row[9]), 3) if row[9] else None
                })
            
            return comments
        except Exception as e:
            logger.error(f"Error getting recent comments: {e}")
            return []
        finally:
            conn.close()
    
    def get_recent_comments_api(self, limit_param: Optional[str]) -> list:
        limit = self._parse_limit(limit_param, default=20, max_value=200)
        return self.get_recent_comments(limit)

    @staticmethod
    def _parse_limit(value: Optional[str], default: int, max_value: int) -> int:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return default

        if n < 1:
            return 1
        if n > max_value:
            return max_value
        return n    


    def get_subreddit_stats(self, subreddit: str) -> dict:
        """Retrieve statistics for a specific subreddit."""
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        try:
            # Profile
            cursor.execute("""
                SELECT allowed_terms, sensitivity, threshold, total_processed, 
                       false_positives, false_negatives 
                FROM subreddit_profiles 
                WHERE subreddit_name = ?
            """, (subreddit,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            allowed_terms = row[0].split(',') if row[0] else []
            
            # Comments from this subreddit
            cursor.execute("""
                SELECT COUNT(*) FROM comments WHERE subreddit = ?
            """, (subreddit,))
            comment_count = cursor.fetchone()[0]
            
            # Predictions from this subreddit
            cursor.execute("""
                SELECT category, COUNT(*) FROM predictions p
                JOIN comments c ON p.comment_id = c.id
                WHERE c.subreddit = ?
                GROUP BY category
            """, (subreddit,))
            predictions = {r[0]: r[1] for r in cursor.fetchall()}
            
            # Average toxicity
            cursor.execute("""
                SELECT AVG(adjusted_toxicity) FROM predictions p
                JOIN comments c ON p.comment_id = c.id
                WHERE c.subreddit = ?
            """, (subreddit,))
            avg_toxicity = cursor.fetchone()[0] or 0.0
            
            return {
                'subreddit': subreddit,
                'allowed_terms': allowed_terms,
                'sensitivity': row[1],
                'threshold': row[2],
                'total_processed': row[3],
                'false_positives': row[4],
                'false_negatives': row[5],
                'comments': comment_count,
                'predictions': predictions,
                'average_toxicity': round(float(avg_toxicity), 3)
            }
        except Exception as e:
            logger.error(f"Error getting subreddit stats for {subreddit}: {e}")
            return None
        finally:
            conn.close()
    
    def get_agent_stats(self) -> dict:
        """Retrieve agent activity and throughput statistics."""
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        try:
            # Comments processed in last hour
            one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
            cursor.execute("""
                SELECT COUNT(*) FROM predictions WHERE predicted_at > ?
            """, (one_hour_ago,))
            last_hour = cursor.fetchone()[0]
            
            # Reviews in last hour
            cursor.execute("""
                SELECT COUNT(*) FROM moderator_reviews WHERE reviewed_at > ?
            """, (one_hour_ago,))
            reviews_last_hour = cursor.fetchone()[0]
            
            # Processing rate
            cursor.execute("SELECT COUNT(*) FROM comments WHERE status = ?", (CommentStatus.PROCESSING.value,))
            processing = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM comments WHERE status = ?", (CommentStatus.QUEUED.value,))
            queued = cursor.fetchone()[0]
            
            return {
                'processed_last_hour': last_hour,
                'reviews_last_hour': reviews_last_hour,
                'currently_processing': processing,
                'in_queue': queued,
                'throughput': {
                    'predictions_per_hour': last_hour,
                    'reviews_per_hour': reviews_last_hour
                }
            }
        except Exception as e:
            logger.error(f"Error getting agent stats: {e}")
            return {}
        finally:
            conn.close()
    
    def _calculate_false_negatives(self) -> int:
        """Calculate false negatives (toxic comments predicted as clean)."""
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) FROM moderator_reviews mr
                JOIN predictions p ON mr.comment_id = p.comment_id
                WHERE mr.decision = ? AND p.category != ?
            """, (ReviewDecision.TOXIC.value, ToxicityCategory.TOXIC.value))
            
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            logger.error(f"Error calculating false negatives: {e}")
            return 0
    
    def _calculate_accuracy(self) -> float:
        """Calculate model accuracy based on moderator reviews."""
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            
            # Total predictions with reviews
            cursor.execute("""
                SELECT COUNT(*) FROM moderator_reviews mr
                JOIN predictions p ON mr.comment_id = p.comment_id
            """)
            total = cursor.fetchone()[0]
            
            if total == 0:
                conn.close()
                return 0.0
            
            # Correct predictions
            cursor.execute("""
                SELECT COUNT(*) FROM moderator_reviews mr
                JOIN predictions p ON mr.comment_id = p.comment_id
                WHERE (mr.decision = ? AND p.category = ?)
                   OR (mr.decision = ? AND p.category != ?)
            """, (
                ReviewDecision.TOXIC.value, ToxicityCategory.TOXIC.value,
                ReviewDecision.CLEAN.value, ToxicityCategory.TOXIC.value
            ))
            
            correct = cursor.fetchone()[0]
            conn.close()
            
            return (correct / total * 100) if total > 0 else 0.0
        except Exception as e:
            logger.error(f"Error calculating accuracy: {e}")
            return 0.0
        
        
    def get_recent_collection_jobs_api(self, limit_param: Optional[str]) -> list[dict]:
        limit = self._parse_limit(limit_param, default=10, max_value=200)
        return self.db.get_recent_collection_jobs(limit=limit)
        
    def get_collection_job_comments_api(self, job_id: int, limit_param: Optional[str]) -> list[dict]:
        limit = self._parse_limit(limit_param, default=200, max_value=500)
        return self.db.get_collection_job_comments(job_id=job_id, limit=limit)
        
    def get_recent_reviews_api(self, limit_param: Optional[str]) -> list[dict]:
        limit = self._parse_limit(limit_param, default=20, max_value=200)
        return self.db.get_recent_reviews_with_notes(limit=limit)