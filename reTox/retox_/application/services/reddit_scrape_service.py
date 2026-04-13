from __future__ import annotations

import logging
from datetime import datetime

from infrastructure.database import Database
from infrastructure.reddit_client import RedditClient
from application.services.queue_service import QueueService
from domain.entities import Comment, CollectionJob
from domain.enums import CommentStatus, CollectionJobStatus

logger = logging.getLogger(__name__)


class RedditScrapeService:
    def __init__(self, db: Database, queue_service: QueueService, reddit_client: RedditClient | None = None):
        self.db = db
        self.queue_service = queue_service
        self.reddit_client = reddit_client or RedditClient()

    def scrape_reddit_api(self, data) -> tuple[dict, int]:
        try:
            url = data["url"]
            limit = data.get("limit", 100)

            try:
                limit = int(limit)
            except (TypeError, ValueError):
                limit = 100

            post_info = self.reddit_client.extract_post_info(url)
            subreddit = post_info.get("subreddit", "unknown")

            job = CollectionJob(
                url=url,
                subreddit=subreddit,
                status=CollectionJobStatus.PROCESSING,
                created_at=datetime.utcnow(),
            )
            job_id = self.db.save_collection_job(job)
            job.id = job_id

            comments_data = self.reddit_client.collect_comments(url, limit=limit)

            enqueued_count = 0
            skipped_count = 0

            for comment_data in comments_data:
                try:
                    comment = Comment(
                        external_id=comment_data["id"],
                        subreddit=comment_data["subreddit"],
                        author=comment_data["author"],
                        text=comment_data["body"],
                        reddit_score=comment_data["score"],
                        reddit_permalink=comment_data["permalink"],
                        parent_external_id=comment_data.get("parent_id"),
                        has_media=comment_data.get("has_media", False),
                        status=CommentStatus.QUEUED,
                        created_at=datetime.utcfromtimestamp(comment_data["created_utc"]),
                        collection_job_id=job_id,
                    )

                    self.queue_service.enqueue_comment(comment)
                    enqueued_count += 1
                except Exception as e:
                    logger.warning(f"Failed to enqueue comment {comment_data.get('id')}: {e}")
                    skipped_count += 1
                    continue

            job.status = CollectionJobStatus.COMPLETED
            job.comments_collected = enqueued_count
            job.completed_at = datetime.utcnow()
            job.error_message = None
            self.db.update_collection_job(job)

            return ({
                "success": True,
                "url": url,
                "job_id": job_id,
                "total_comments": len(comments_data),
                "enqueued_count": enqueued_count,
                "skipped_count": skipped_count,
                "message": f"✅ Enqueued {enqueued_count} comments for processing ({skipped_count} skipped)",
            }, 200)

        except ValueError as e:
            logger.error(f"Invalid Reddit URL: {e}")
            return ({"error": f"Invalid Reddit URL: {str(e)}"}, 400)

        except Exception as e:
            logger.error(f"Reddit scrape error: {e}")
            return ({"error": f"Failed to scrape Reddit: {str(e)}"}, 400)