# application/services/confidence_estimator.py

from typing import Dict
import logging

logger = logging.getLogger(__name__)

class ConfidenceEstimator:
    """Estimate confidence/uncertainty in toxicity predictions"""
    
    def estimate_confidence(
        self,
        toxicity_scores: Dict[str, float],
        sentiment_scores: Dict[str, float],
        entity_count: int,
        text_length: int
    ) -> Dict[str, float]:
        """
        Calculate confidence score (0 to 1)
        High confidence = multiple signals agree
        Low confidence = conflicting signals
        """
        
        # Base confidence from Detoxify consistency
        toxicity = toxicity_scores.get('toxicity', 0.5)
        base_confidence = self._score_consistency(toxicity_scores)
        
        # Adjust by text length (longer = more context = higher confidence)
        length_factor = min(text_length / 200, 1.0)  # Normalize by typical length
        
        # Adjust by entity presence (more entities = more context = higher confidence)
        entity_factor = min(entity_count / 5, 1.0)  # Normalize by typical entity count
        
        # Adjust by sentiment clarity
        sentiment_clarity = abs(sentiment_scores.get('compound', 0.0))
        
        # Combined confidence
        confidence = (base_confidence * 0.4 + 
                     length_factor * 0.3 + 
                     sentiment_clarity * 0.2 + 
                     entity_factor * 0.1)
        
        confidence = max(0.0, min(1.0, confidence))
        
        return {
            'overall_confidence': confidence,
            'base_confidence': base_confidence,
            'length_factor': length_factor,
            'sentiment_clarity': sentiment_clarity,
            'entity_factor': entity_factor,
            'uncertainty': 1.0 - confidence
        }
    
    def _score_consistency(self, toxicity_scores: Dict[str, float]) -> float:
        """
        Measure how consistent different toxicity metrics are
        If all agree = high confidence, if conflicting = low confidence
        """
        scores = [
            toxicity_scores.get('toxicity', 0.5),
            toxicity_scores.get('severe_toxicity', 0.5),
            toxicity_scores.get('insult', 0.5),
            toxicity_scores.get('threat', 0.5)
        ]
        
        # If scores are similar (low variance) = high confidence
        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        
        # Convert variance to confidence (higher variance = lower confidence)
        consistency = 1.0 / (1.0 + variance)
        
        return consistency
    
    def get_confidence_interval(self, confidence: float) -> Dict[str, float]:
        """
        Return prediction interval (lower, upper bounds)
        E.g., if confidence is 0.8, prediction ±0.2
        """
        margin = 1.0 - confidence
        
        return {
            'confidence': confidence,
            'margin_of_error': margin,
            'low': max(0.0, confidence - margin),
            'high': min(1.0, confidence + margin)
        }