# application/services/lime_explainer.py

import logging
from typing import Dict, List, Tuple
import re

logger = logging.getLogger(__name__)

class LimeExplainer:
    """
    LIME-inspired local interpretable explanations
    Shows which words/phrases drive toxicity predictions
    """
    
    def __init__(self):
        # Toxicity indicator words (common in toxic comments)
        self.toxic_indicators = {
            'insults': ['stupid', 'idiot', 'moron', 'dumb', 'fool', 'loser', 
                       'pathetic', 'worthless', 'trash', 'garbage', 'awful'],
            'hate': ['hate', 'despise', 'abhor', 'detest', 'disgusting'],
            'threats': ['kill', 'hurt', 'harm', 'beat', 'punch', 'destroy'],
            'slurs': ['retarded', 'gay', 'n-word', 'f-word'],  # Placeholder
            'aggression': ['fuck', 'shit', 'damn', 'ass', 'bastard'],
        }
    
    def explain_prediction(
        self, 
        text: str, 
        toxicity_score: float,
        confidence: float
    ) -> Dict:
        """
        Explain why a comment got its toxicity score
        Returns: contributions of different parts
        """
        try:
            explanation = {
                'text': text,
                'score': toxicity_score,
                'confidence': confidence,
                'influential_words': self._find_influential_words(text),
                'contributing_factors': self._identify_factors(text),
                'summary': self._generate_summary(text, toxicity_score),
                'word_contributions': self._score_word_contributions(text)
            }
            
            return explanation
        
        except Exception as e:
            logger.error(f"Error explaining prediction: {e}")
            return self._empty_explanation(text, toxicity_score)
    
    def _find_influential_words(self, text: str) -> List[Dict]:
        """Find words that most influence toxicity"""
        words = text.lower().split()
        influential = []
        
        for category, indicators in self.toxic_indicators.items():
            for word in words:
                # Check for partial matches (e.g., "stupid" in "stupidly")
                for indicator in indicators:
                    if indicator in word:
                        influential.append({
                            'word': word,
                            'category': category,
                            'influence': 'high'
                        })
        
        return influential
    
    def _identify_factors(self, text: str) -> List[str]:
        """Identify what factors contribute to toxicity"""
        factors = []
        text_lower = text.lower()
        
        # Check for caps (aggression signal)
        if any(word.isupper() for word in text.split() if len(word) > 2):
            factors.append("excessive capitalization (aggression signal)")
        
        # Check for punctuation (intensity)
        exclamation_count = text.count('!')
        if exclamation_count > 2:
            factors.append(f"excessive exclamation marks ({exclamation_count}x)")
        
        # Check for negation (stronger statements)
        negations = ['no', 'not', 'never', 'neither', 'nobody']
        if any(neg in text_lower.split() for neg in negations):
            factors.append("negation (stronger statement)")
        
        # Check for profanity
        profanity = ['damn', 'shit', 'fuck', 'ass', 'crap']
        if any(p in text_lower for p in profanity):
            factors.append("profanity/strong language")
        
        # Check for attack words
        attack_words = ['you are', 'you\'re', 'you should', 'stupid', 'idiot']
        if any(a in text_lower for a in attack_words):
            factors.append("direct personal attack")
        
        # Check for emotional intensity
        emotional_words = ['hate', 'love', 'disgusting', 'amazing', 'awful']
        if any(e in text_lower for e in emotional_words):
            factors.append("emotional language")
        
        return factors
    
    def _score_word_contributions(self, text: str) -> Dict[str, float]:
        """Score how much each word contributes to toxicity"""
        words = text.lower().split()
        contributions = {}
        
        for word in words:
            score = 0.0
            
            # Check against toxic indicators
            for category, indicators in self.toxic_indicators.items():
                for indicator in indicators:
                    if indicator in word:
                        # Exact match = higher score
                        if indicator == word:
                            score += 0.8
                        else:
                            score += 0.4
            
            # Penalize common words
            if word in ['the', 'a', 'is', 'are', 'and', 'or', 'but', 'to', 'of']:
                score -= 0.2
            
            if score > 0:
                contributions[word] = min(1.0, score)  # Cap at 1.0
        
        # Sort by contribution
        return dict(sorted(contributions.items(), key=lambda x: x[1], reverse=True))
    
    def _generate_summary(self, text: str, score: float) -> str:
        """Generate human-readable explanation"""
        if score > 0.8:
            base = "This comment appears highly toxic"
        elif score > 0.7:
            base = "This comment shows signs of toxicity"
        elif score > 0.5:
            base = "This comment is borderline - contains some problematic language"
        elif score > 0.3:
            base = "This comment has minor issues"
        else:
            base = "This comment appears safe"
        
        factors = self._identify_factors(text)
        if factors:
            details = " Main concerns: " + ", ".join(factors)
        else:
            details = ""
        
        return base + details
    
    def _empty_explanation(self, text: str, score: float) -> Dict:
        return {
            'text': text,
            'score': score,
            'confidence': 0.0,
            'influential_words': [],
            'contributing_factors': [],
            'summary': 'Unable to generate explanation',
            'word_contributions': {}
        }