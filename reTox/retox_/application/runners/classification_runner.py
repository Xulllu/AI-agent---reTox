# application/runners/classification_runner.py

from application.services.lime_explainer import LimeExplainer
from core.software_agent import SoftwareAgent
from infrastructure.database import Database
from application.services.toxicity_service import ToxicityService
from application.services.profile_service import ProfileService
from domain.entities import Comment, Prediction, SubredditProfile
from domain.enums import CommentStatus, ToxicityCategory
from typing import Optional
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ClassificationPercept:
    """Šta agent opaža"""
    comment: Comment
    profile: SubredditProfile
    parent_is_toxic: bool


@dataclass
class ClassificationAction:
    """Šta agent odluči"""
    comment_id: int
    base_toxicity: float
    adjusted_toxicity: float
    confidence: float
    category: ToxicityCategory
    new_status: CommentStatus
    explanation: str
    full_prediction: dict


@dataclass
class ClassificationResult:
    """Rezultat tick-a"""
    comment_id: int
    subreddit: str
    category: ToxicityCategory
    score: float
    confidence: float
    explanation: str


class ClassificationRunner(
    SoftwareAgent[ClassificationPercept, ClassificationAction, ClassificationResult]
):
    """
    AGENT ZA KLASIFIKACIJU - glavna logika
    Sense: Uzima komentar iz queue-a + učitava profil
    Think: ML model + context + confidence
    Act: Sprema prediction + ažurira status
    """

    def __init__(self, db: Database):
        self.db = db
        self.toxicity_service = ToxicityService(db)
        self.profile_service = ProfileService(db)
        self.lime_explainer = LimeExplainer()

    async def sense(self) -> Optional[ClassificationPercept]:
        """
        SENSE - prikupi kontekst
        """
        # Uzmi sljedeći queued comment (atomic claim QUEUED -> PROCESSING)
        comment = self.db.get_next_queued_comment()

        if comment is None:
            return None  # No work

        # REMOVE: DB claim already set status to PROCESSING atomically
        # self.db.update_comment_status(comment.id, CommentStatus.PROCESSING)

        # Učitaj subreddit profil
        profile = self.profile_service.get_or_create(comment.subreddit)

        # Check parent comment
        parent_is_toxic = False
        if comment.parent_external_id:
            parent_is_toxic = False

        logger.info(
            f"SENSE: Comment {comment.id} from r/{comment.subreddit} "
            f"(profile has {len(profile.allowed_terms)} allowed terms)"
        )

        return ClassificationPercept(
            comment=comment,
            profile=profile,
            parent_is_toxic=parent_is_toxic
        )

    async def think(self, percept: ClassificationPercept) -> ClassificationAction:
        """
        THINK - rasuđuj sa kontekstom i pouzdanošću
        """
        comment = percept.comment
        profile = percept.profile

        # 1. COMPREHENSIVE TOXICITY PREDICTION
        full_prediction = await self.toxicity_service.predict(
            text=comment.text,
            subreddit=comment.subreddit,
            comment_id=comment.id
        )

        base_toxicity = full_prediction['base_score']
        adjusted_toxicity = full_prediction['adjusted_score']
        confidence = full_prediction['confidence']

        logger.info(
            f"THINK: Base={base_toxicity:.3f}, Adjusted={adjusted_toxicity:.3f}, "
            f"Confidence={confidence:.3f}"
        )

        # Log additional context
        if full_prediction['has_personal_attacks']:
            logger.info("THINK: Personal attack detected")

        if full_prediction['emotional_intensity'] > 0.7:
            logger.info(f"THINK: High emotional intensity={full_prediction['emotional_intensity']:.3f}")

        if full_prediction['entities']:
            logger.info(f"THINK: Entities found: {full_prediction['entities']}")

        # 2. KATEGORIJA (now considering confidence)
        category = self._categorize(adjusted_toxicity, profile.threshold, confidence)

        # 3. STATUS ODLUKA
        new_status = self._determine_status(category, confidence)

        # 4. EXPLAINABILITY with LIME
        explanation = self._generate_explanation(
            base_toxicity,
            adjusted_toxicity,
            confidence,
            category,
            profile,
            full_prediction,
            comment.text
        )

        logger.info(f"THINK: Category={category.value}, Status={new_status.value}, Confidence={confidence:.3f}")

        return ClassificationAction(
            comment_id=comment.id,
            base_toxicity=base_toxicity,
            adjusted_toxicity=adjusted_toxicity,
            confidence=confidence,
            category=category,
            new_status=new_status,
            explanation=explanation,
            full_prediction=full_prediction
        )

    async def act(self, action: ClassificationAction) -> ClassificationResult:
        """
        ACT - izvrši odluku i spremi sve
        """
        # Save prediction with confidence
        prediction = Prediction(
            comment_id=action.comment_id,
            base_toxicity=action.base_toxicity,
            adjusted_toxicity=action.adjusted_toxicity,
            category=action.category,
            explanation=action.explanation,
            model_version="v1",
            jigsaw_scores=action.full_prediction['toxicity_scores'],
            predicted_at=datetime.utcnow()
        )

        self.db.save_prediction(prediction)

        # Update comment status
        self.db.update_comment_status(action.comment_id, action.new_status)

        # Get comment for result
        comment = self.db.get_comment_by_id(action.comment_id)

        logger.info(
            f"ACT: Saved prediction for comment {action.comment_id} "
            f"-> {action.category.value} (confidence={action.confidence:.3f})"
        )

        return ClassificationResult(
            comment_id=action.comment_id,
            subreddit=comment.subreddit,
            category=action.category,
            score=action.adjusted_toxicity,
            confidence=action.confidence,
            explanation=action.explanation
        )

    # === HELPER METHODS ===

    def _categorize(self, score: float, threshold: float, confidence: float) -> ToxicityCategory:
        """Kategorija na osnovu score-a i pouzdanosti"""
        # High confidence decisions
        if confidence > 0.8:
            if score > 0.65:  # CHANGED from 0.8
                return ToxicityCategory.TOXIC
            elif score > threshold:
                return ToxicityCategory.BORDERLINE
            else:
                return ToxicityCategory.CLEAN

        # Low confidence: be more conservative
        elif confidence < 0.5:
            if score > 0.70:  # CHANGED from 0.85
                return ToxicityCategory.TOXIC
            else:
                return ToxicityCategory.BORDERLINE

        # Medium confidence
        else:
            if score > 0.65:  # CHANGED from 0.8
                return ToxicityCategory.TOXIC
            elif score > threshold:
                return ToxicityCategory.BORDERLINE
            else:
                return ToxicityCategory.CLEAN

    def _determine_status(self, category: ToxicityCategory, confidence: float) -> CommentStatus:
        """Status odluka - PROAKTIVNA"""
        if category == ToxicityCategory.CLEAN:
            return CommentStatus.AUTO_APPROVED
        else:
            return CommentStatus.PENDING_REVIEW

    def _generate_explanation(
        self,
        base_score: float,
        adjusted_score: float,
        confidence: float,
        category: ToxicityCategory,
        profile: SubredditProfile,
        full_prediction: dict,
        comment_text: str
    ) -> str:
        """EXPLAINABILITY - detaljan opis sa LIME"""

        # Get LIME explanation
        lime_explanation = self.lime_explainer.explain_prediction(
            comment_text,
            adjusted_score,
            confidence
        )

        lines = [
            f"=== TOXICITY EXPLANATION ===",
            f"Text: {comment_text[:100]}...",
            f"",
            f"Summary: {lime_explanation['summary']}",
            f"",
            f"Score Analysis:",
            f"  Base toxicity: {base_score:.3f}",
            f"  Context adjustment: {full_prediction['context_adjustment']:+.3f}",
            f"  Final score: {adjusted_score:.3f}",
            f"  Confidence: {confidence:.3f}",
            f"  Category: {category.value.upper()}",
            f"",
        ]

        # Add influential words
        if lime_explanation['influential_words']:
            lines.append("Influential Words:")
            for word_info in lime_explanation['influential_words'][:5]:
                lines.append(f"  - {word_info['word']} ({word_info['category']})")
            lines.append("")

        # Add contributing factors
        if lime_explanation['contributing_factors']:
            lines.append("Contributing Factors:")
            for factor in lime_explanation['contributing_factors']:
                lines.append(f"  ⚠ {factor}")
            lines.append("")

        # Add word contributions
        if lime_explanation['word_contributions']:
            lines.append("Word Contribution Scores:")
            for word, score in list(lime_explanation['word_contributions'].items())[:5]:
                lines.append(f"  {word}: {score:.2f}")
            lines.append("")

        # Add additional insights
        if full_prediction['emotional_intensity'] > 0.7:
            lines.append(f"⚠ Highly emotional (intensity={full_prediction['emotional_intensity']:.3f})")

        if full_prediction['has_personal_attacks']:
            lines.append(f"⚠ Personal attack detected ({full_prediction['entity_count']} entities)")

        if confidence < 0.5:
            lines.append("⚠ LOW CONFIDENCE - recommend manual review")

        if category != ToxicityCategory.CLEAN:
            lines.append("→ Pending moderator review")

        return "\n".join(lines)