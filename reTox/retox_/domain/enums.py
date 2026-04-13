# domain/enums.py

from enum import Enum

class CommentStatus(Enum):
    """Status of comments in the processing pipeline."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    AUTO_APPROVED = "auto_approved"
    AUTO_REJECTED = "auto_rejected"
    PENDING_REVIEW = "pending_review"
    REVIEWED = "reviewed"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"

class ToxicityCategory(Enum):
    """Categories for toxicity classification."""
    CLEAN = "clean"
    BORDERLINE = "borderline"
    TOXIC = "toxic"
    UNSUPPORTED = "unsupported"

class ReviewDecision(Enum):
    """Moderator review decisions."""
    APPROVE = "approve"
    REJECT = "reject"
    APPROVED = "approved"
    REJECTED = "rejected"
    TOXIC = "toxic"
    CLEAN = "clean"
    NEEDS_CONTEXT = "needs_context"

class CollectionJobStatus(Enum):
    """Status of Reddit collection jobs."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"