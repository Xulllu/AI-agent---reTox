# application/services/reddit_service.py

from infrastructure.reddit_client import RedditClient
from infrastructure.database import Database
from domain.entities import Comment, CollectionJob
from domain.enums import CommentStatus, CollectionJobStatus
from typing import List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class RedditService:
    def __init__(self, db: Database):
        self.db = db
        self.reddit_client = RedditClient()
    
    async def collect_from_url(self, job: CollectionJob) -> int:
        """
        Prikuplja komentare sa Reddit URL-a i sprema u bazu
        """
        try:
            # Collect comments using PRAW
            comments_data = self.reddit_client.collect_comments(job.url)
            
            logger.info(f"Collected {len(comments_data)} comments from {job.url}")
            
            # Save to database
            saved_count = 0
            for data in comments_data:
                comment = Comment(
                    external_id=data['id'],
                    subreddit=data['subreddit'],
                    author=data['author'],
                    text=data['text'],
                    parent_external_id=data['parent_id'],
                    status=CommentStatus.UNSUPPORTED if data['has_media'] 
                           else CommentStatus.QUEUED,
                    created_at=data['created_utc'],
                    reddit_score=data['score'],
                    reddit_permalink=data['permalink'],
                    has_media=data['has_media']
                )
                
                try:
                    self.db.save_comment(comment)
                    saved_count += 1
                except Exception as e:
                    # Skip duplicates (external_id is unique)
                    if "UNIQUE constraint failed" in str(e):
                        logger.debug(f"Skipping duplicate comment {data['id']}")
                    else:
                        logger.error(f"Error saving comment: {e}")
            
            # Update job
            job.status = CollectionJobStatus.COMPLETED
            job.comments_collected = saved_count
            job.completed_at = datetime.utcnow()
            self.db.update_collection_job(job)
            
            logger.info(f"Successfully saved {saved_count} comments")
            
            return saved_count
        
        except Exception as e:
            logger.error(f"Error collecting from URL: {e}")
            
            job.status = CollectionJobStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            self.db.update_collection_job(job)
            
            raise