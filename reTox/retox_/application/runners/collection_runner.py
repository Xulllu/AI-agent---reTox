# application/runners/collection_runner.py

from core.software_agent import SoftwareAgent
from infrastructure.database import Database
from application.services.reddit_service import RedditService
from domain.entities import CollectionJob
from domain.enums import CollectionJobStatus
from typing import Optional
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class CollectionPercept:
    """Šta agent opaža"""
    job: CollectionJob

@dataclass
class CollectionAction:
    """Šta agent odluči"""
    job_id: int
    should_process: bool

@dataclass
class CollectionResult:
    """Rezultat tick-a"""
    job_id: int
    status: CollectionJobStatus
    comments_collected: int
    message: str

class CollectionRunner(
    SoftwareAgent[CollectionPercept, CollectionAction, CollectionResult]
):
    """
    AGENT ZA KOLEKCIJU - prikuplja komentare sa Reddita
    """
    
    def __init__(self, db: Database):
        self.db = db
        self.reddit_service = RedditService(db)
    
    async def sense(self) -> Optional[CollectionPercept]:
        """SENSE - uzmi sljedeći pending job"""
        job = self.db.get_next_pending_job()
        
        if job is None:
            return None
        
        logger.info(f"SENSE: Found collection job {job.id} for {job.url}")
        return CollectionPercept(job=job)
    
    async def think(self, percept: CollectionPercept) -> CollectionAction:
        """THINK - odluči da li procesirati"""
        job = percept.job
        
        # Možete dodati logiku: skip ako URL nije validan, itd.
        should_process = True
        
        logger.info(f"THINK: Job {job.id} - should_process={should_process}")
        return CollectionAction(
            job_id=job.id,
            should_process=should_process
        )
    
    async def act(self, action: CollectionAction) -> CollectionResult:
        """ACT - prikupi komentare"""
        job = self.db.get_next_pending_job()
        
        if not action.should_process or not job:
            return CollectionResult(
                job_id=action.job_id,
                status=CollectionJobStatus.FAILED,
                comments_collected=0,
                message="Job skipped"
            )
        
        try:
            # Ažuriraj status na PROCESSING
            job.status = CollectionJobStatus.PROCESSING
            self.db.update_collection_job(job)
            
            # Prikupi komentare
            collected = await self.reddit_service.collect_from_url(job)
            
            # Ažuriraj job
            job.status = CollectionJobStatus.COMPLETED
            job.comments_collected = collected
            job.completed_at = datetime.utcnow()
            self.db.update_collection_job(job)
            
            logger.info(f"ACT: Collected {collected} comments for job {job.id}")
            
            return CollectionResult(
                job_id=job.id,
                status=CollectionJobStatus.COMPLETED,
                comments_collected=collected,
                message=f"Collected {collected} comments"
            )
        
        except Exception as e:
            job.status = CollectionJobStatus.FAILED
            job.error_message = str(e)
            self.db.update_collection_job(job)
            
            logger.error(f"ACT: Collection failed - {e}")
            return CollectionResult(
                job_id=job.id,
                status=CollectionJobStatus.FAILED,
                comments_collected=0,
                message=f"Error: {str(e)}"
            )