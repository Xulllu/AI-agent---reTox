# application/services/queue_service.py

from infrastructure.database import Database
from domain.entities import Comment
from domain.enums import CommentStatus
from typing import Optional, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class QueueService:
    """Service for managing the comment classification queue with status tracking and metrics."""
    
    def __init__(self, db: Database):
        self.db = db
    
    def enqueue_comment(self, comment: Comment) -> int:
        """Add a comment to the classification queue."""
        try:
            comment.status = CommentStatus.QUEUED
            comment_id = self.db.save_comment(comment)
            logger.info(f"Enqueued comment {comment_id} from r/{comment.subreddit}")
            return comment_id
        except Exception as e:
            logger.error(f"Failed to enqueue comment: {e}")
            raise
    def submit_comment_api(self, payload: dict) -> tuple[dict, int]:
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")

        required = ("external_id", "subreddit", "author", "text")
        missing = [k for k in required if not payload.get(k)]
        if missing:
            raise ValueError(f"Missing required field(s): {', '.join(missing)}")

        external_id = str(payload["external_id"]).strip()
        subreddit = str(payload["subreddit"]).strip()
        author = str(payload["author"]).strip()
        text = str(payload["text"])

        reddit_score_raw = payload.get("reddit_score", 0)
        try:
            reddit_score = int(reddit_score_raw) if reddit_score_raw is not None else 0
        except (TypeError, ValueError):
            reddit_score = 0

        reddit_permalink = str(payload.get("reddit_permalink", "") or "")
        has_media = bool(payload.get("has_media", False))

        comment = Comment(
            external_id=external_id,
            subreddit=subreddit,
            author=author,
            text=text,
            reddit_score=reddit_score,
            reddit_permalink=reddit_permalink,
            has_media=has_media,
            status=CommentStatus.UNSUPPORTED if has_media else CommentStatus.QUEUED,
            created_at=datetime.utcnow(),
        )

        comment_id = self.enqueue_comment(comment)

        return ({
            "success": True,
            "comment_id": comment_id,
            "message": "Comment enqueued for classification"
        }, 201)
    
    def enqueue_batch(self, comments: List[Comment]) -> dict:
        """Add multiple comments to the queue at once. Returns success count and failed IDs."""
        success_ids = []
        failed_count = 0
        
        for idx, comment in enumerate(comments):
            try:
                comment_id = self.enqueue_comment(comment)
                success_ids.append(comment_id)
            except Exception as e:
                logger.warning(f"Failed to enqueue comment {idx}: {e}")
                failed_count += 1
        
        result = {
            'total': len(comments),
            'successful': len(success_ids),
            'failed': failed_count,
            'comment_ids': success_ids
        }
        
        logger.info(f"Enqueued batch: {len(success_ids)}/{len(comments)} successful")
        return result
    
    def get_next_queued(self) -> Optional[Comment]:
        """Retrieve the next queued comment for processing."""
        try:
            return self.db.get_next_queued_comment()
        except Exception as e:
            logger.error(f"Failed to get next queued comment: {e}")
            return None
    
    def get_queued_count(self) -> int:
        """Get the total number of comments in the queue."""
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT COUNT(*) FROM comments WHERE status = ?", (CommentStatus.QUEUED.value,))
                count = cursor.fetchone()[0]
                return count
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Failed to get queue count: {e}")
            return 0
    
    def get_queued_comments(self, limit: int = 10, offset: int = 0) -> List[Comment]:
        """Retrieve queued comments with pagination."""
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    SELECT * FROM comments 
                    WHERE status = ? 
                    ORDER BY created_at ASC 
                    LIMIT ? OFFSET ?
                """, (CommentStatus.QUEUED.value, limit, offset))
                
                comments = []
                for row in cursor.fetchall():
                    comments.append(self.db._row_to_comment(row))
                return comments
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Failed to get queued comments: {e}")
            return []
    
    def get_comments_by_status(self, status: CommentStatus, limit: int = 10, offset: int = 0) -> List[Comment]:
        """Get comments filtered by any status with pagination."""
        try:
            return self.db.get_comments_by_status(status, limit, offset)
        except Exception as e:
            logger.error(f"Failed to get comments by status {status.value}: {e}")
            return []
    
    def update_status(self, comment_id: int, status: CommentStatus) -> None:
        """Update the status of a comment."""
        try:
            self.db.update_comment_status(comment_id, status)
            logger.debug(f"Comment {comment_id} status → {status.value}")
        except Exception as e:
            logger.error(f"Failed to update comment status: {e}")
            raise
    
    def mark_processing(self, comment_id: int) -> None:
        """Mark a comment as currently processing."""
        try:
            self.update_status(comment_id, CommentStatus.PROCESSING)
        except Exception as e:
            logger.error(f"Failed to mark comment as processing: {e}")
            raise
    
    def mark_completed(self, comment_id: int) -> None:
        """Mark a comment as completed (classified)."""
        try:
            self.update_status(comment_id, CommentStatus.COMPLETED)
        except Exception as e:
            logger.error(f"Failed to mark comment as completed: {e}")
            raise
    
    def mark_failed(self, comment_id: int, error_message: str = None) -> None:
        """Mark a comment as failed with optional error details."""
        try:
            self.update_status(comment_id, CommentStatus.FAILED)
            if error_message:
                logger.warning(f"Comment {comment_id} marked as failed: {error_message}")
            else:
                logger.warning(f"Comment {comment_id} marked as failed")
        except Exception as e:
            logger.error(f"Failed to mark comment as failed: {e}")
            raise
    
    def get_queue_stats(self) -> dict:
        """Get comprehensive statistics about the current queue."""
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            
            try:
                # Get all status counts
                cursor.execute("SELECT COUNT(*) FROM comments WHERE status = ?", (CommentStatus.QUEUED.value,))
                queued = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM comments WHERE status = ?", (CommentStatus.PROCESSING.value,))
                processing = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM comments WHERE status = ?", (CommentStatus.COMPLETED.value,))
                completed = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM comments WHERE status = ?", (CommentStatus.FAILED.value,))
                failed = cursor.fetchone()[0]
                
                # Calculate throughput (last hour)
                one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
                cursor.execute("""
                    SELECT COUNT(*) FROM comments 
                    WHERE status = ? AND created_at > ?
                """, (CommentStatus.COMPLETED.value, one_hour_ago))
                completed_last_hour = cursor.fetchone()[0]
                
                total = queued + processing + completed + failed
                
                return {
                    'queued': queued,
                    'processing': processing,
                    'completed': completed,
                    'failed': failed,
                    'total': total,
                    'completed_last_hour': completed_last_hour,
                    'throughput_per_hour': completed_last_hour,
                    'queue_depth': queued + processing
                }
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {
                'queued': 0, 'processing': 0, 'completed': 0, 'failed': 0, 
                'total': 0, 'completed_last_hour': 0, 'throughput_per_hour': 0, 'queue_depth': 0
            }
    
    def get_processing_time_stats(self) -> dict:
        """Get average processing time for recently completed comments."""
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            
            try:
                # Get average time between comment creation and completion
                cursor.execute("""
                    SELECT 
                        AVG(CAST((julianday(c.created_at) - julianday(c.created_at)) * 24 * 60 AS FLOAT)) as avg_minutes,
                        MIN(CAST((julianday(c.created_at) - julianday(c.created_at)) * 24 * 60 AS FLOAT)) as min_minutes,
                        MAX(CAST((julianday(c.created_at) - julianday(c.created_at)) * 24 * 60 AS FLOAT)) as max_minutes
                    FROM comments c
                    WHERE c.status = ?
                    AND c.created_at > datetime('now', '-1 hour')
                """, (CommentStatus.COMPLETED.value,))
                
                row = cursor.fetchone()
                
                return {
                    'avg_processing_minutes': round(row[0], 2) if row[0] else 0,
                    'min_processing_minutes': round(row[1], 2) if row[1] else 0,
                    'max_processing_minutes': round(row[2], 2) if row[2] else 0
                }
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Failed to get processing time stats: {e}")
            return {'avg_processing_minutes': 0, 'min_processing_minutes': 0, 'max_processing_minutes': 0}
    
    def clear_old_completed(self, days: int = 30) -> int:
        """Remove completed comments older than specified days (archive only)."""
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            conn = self.db._get_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    DELETE FROM comments 
                    WHERE status = ? AND created_at < ?
                """, (CommentStatus.COMPLETED.value, cutoff_date))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                logger.info(f"Cleared {deleted_count} completed comments older than {days} days")
                return deleted_count
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Failed to clear old completed comments: {e}")
            return 0
    
    def get_queue_health(self) -> dict:
        """Get overall queue health metrics."""
        try:
            stats = self.get_queue_stats()
            
            # Calculate health indicators
            queue_depth = stats['queue_depth']
            throughput = stats['throughput_per_hour']
            failure_rate = (stats['failed'] / max(stats['completed'], 1) * 100) if stats['completed'] > 0 else 0
            
            # Estimate time to clear queue (hours)
            hours_to_clear = (queue_depth / max(throughput, 1)) if throughput > 0 else float('inf')
            
            health_status = 'healthy'
            if queue_depth > 1000 or hours_to_clear > 8:
                health_status = 'degraded'
            if queue_depth > 5000 or hours_to_clear > 24:
                health_status = 'critical'
            
            return {
                'status': health_status,
                'queue_depth': queue_depth,
                'estimated_hours_to_clear': round(hours_to_clear, 2),
                'failure_rate_percent': round(failure_rate, 2),
                'throughput_per_hour': throughput,
                'stats': stats
            }
        except Exception as e:
            logger.error(f"Failed to get queue health: {e}")
            return {'status': 'unknown', 'error': str(e)}