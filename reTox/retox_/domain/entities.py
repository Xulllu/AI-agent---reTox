# domain/entities.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from .enums import CommentStatus, ToxicityCategory, ReviewDecision, CollectionJobStatus

# domain/entities.py
from typing import Optional  # već ima

@dataclass
class Comment:
    id: Optional[int] = None
    external_id: str = ""
    subreddit: str = ""
    author: str = ""
    text: str = ""
    parent_external_id: Optional[str] = None
    status: CommentStatus = CommentStatus.QUEUED
    created_at: datetime = field(default_factory=datetime.utcnow)
    reddit_score: int = 0
    reddit_permalink: str = ""
    has_media: bool = False

    collection_job_id: Optional[int] = None  # <-- DODAJ OVO

@dataclass
class SubredditProfile:
    id: Optional[int] = None
    subreddit_name: str = ""
    allowed_terms: List[str] = field(default_factory=list)
    sensitivity: float = 1.0
    threshold: float = 0.7
    total_processed: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    last_updated: datetime = field(default_factory=datetime.utcnow)

@dataclass
class Prediction:
    id: Optional[int] = None
    comment_id: int = 0
    base_toxicity: float = 0.0
    adjusted_toxicity: float = 0.0
    confidence: float = 0.5   # <-- ADD THIS
    category: ToxicityCategory = ToxicityCategory.CLEAN
    explanation: str = ""
    model_version: str = "v1"
    jigsaw_scores: dict = field(default_factory=dict)
    predicted_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class ModeratorReview:
    id: Optional[int] = None
    comment_id: int = 0
    decision: ReviewDecision = ReviewDecision.APPROVE
    moderator_notes: Optional[str] = None
    reviewed_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class CollectionJob:
    id: Optional[int] = None
    url: str = ""
    subreddit: str = ""
    status: CollectionJobStatus = CollectionJobStatus.PENDING
    comments_collected: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

@dataclass
class SystemSettings:
    id: int = 1
    gold_threshold: int = 50
    retraining_enabled: bool = True
    new_gold_since_last_train: int = 0
    last_retrain_date: Optional[datetime] = None
    
@dataclass
class ModelVersion:
    """Model training history and versioning"""
    id: Optional[int] = None
    version: str = "v1.0.0"
    base_model: str = "detoxify-original"
    accuracy_before: float = 0.0
    accuracy_after: float = 0.0
    improvement: float = 0.0
    false_positives: int = 0
    false_negatives: int = 0
    samples_trained: int = 0
    training_date: datetime = field(default_factory=datetime.utcnow)
    notes: str = ""