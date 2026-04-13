# application/services/sentiment_analyzer.py

from nltk.sentiment import SentimentIntensityAnalyzer
import nltk
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Download VADER lexicon if not present
try:
    nltk.data.find('sentiment/vader_lexicon')
except LookupError:
    nltk.download('vader_lexicon')

class SentimentAnalyzer:
    """VADER-based sentiment analysis for emotional intensity"""
    
    def __init__(self):
        self.sia = SentimentIntensityAnalyzer()
    
    def analyze(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment intensity
        Returns: {positive, negative, neutral, compound}
        - compound: -1.0 (most negative) to +1.0 (most positive)
        """
        try:
            if not text or len(text.strip()) == 0:
                return self._empty_sentiment()
            
            scores = self.sia.polarity_scores(text)
            
            return {
                'positive': float(scores['pos']),
                'negative': float(scores['neg']),
                'neutral': float(scores['neu']),
                'compound': float(scores['compound'])  # -1 to +1
            }
        
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return self._empty_sentiment()
    
    def get_emotional_intensity(self, sentiment_scores: Dict[str, float]) -> float:
        """
        Calculate overall emotional intensity (0 to 1)
        High intensity = strongly positive or negative
        """
        # abs(compound) gives intensity, normalize to 0-1
        intensity = abs(sentiment_scores['compound'])
        return intensity
    
    def is_highly_emotional(self, sentiment_scores: Dict[str, float], threshold: float = 0.6) -> bool:
        """Check if comment is highly emotional"""
        return self.get_emotional_intensity(sentiment_scores) > threshold
    
    def _empty_sentiment(self) -> Dict[str, float]:
        return {
            'positive': 0.0,
            'negative': 0.0,
            'neutral': 1.0,
            'compound': 0.0
        }