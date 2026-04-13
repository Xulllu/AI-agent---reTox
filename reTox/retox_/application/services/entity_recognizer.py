# application/services/entity_recognizer.py

import spacy
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class EntityRecognizer:
    """Named Entity Recognition - detect targeting of people/groups"""
    
    def __init__(self):
        try:
            self.nlp = spacy.load('en_core_web_sm')
        except OSError:
            logger.warning("Spacy model not found. Installing...")
            import os
            os.system('python -m spacy download en_core_web_sm')
            self.nlp = spacy.load('en_core_web_sm')
    
    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """
        Extract named entities from text
        Returns: {PERSON: [...], ORG: [...], GPE: [...], etc}
        """
        try:
            if not text or len(text.strip()) == 0:
                return {}
            
            doc = self.nlp(text)
            entities = {}
            
            for ent in doc.ents:
                if ent.label_ not in entities:
                    entities[ent.label_] = []
                entities[ent.label_].append(ent.text)
            
            return entities
        
        except Exception as e:
            logger.error(f"Error extracting entities: {e}")
            return {}
    
    def has_personal_attacks(self, text: str, entities: Dict[str, List[str]]) -> bool:
        """
        Check if entities (people/groups) are being attacked
        High confidence if: entity mentioned + toxic language nearby
        """
        if not entities:
            return False
        
        # Check for personal attack indicators
        attack_words = [
            'stupid', 'idiot', 'moron', 'dumb', 'hate', 'trash',
            'disgusting', 'loser', 'pathetic', 'worthless'
        ]
        
        text_lower = text.lower()
        has_attack_language = any(word in text_lower for word in attack_words)
        has_entity = any(entities.get(label) for label in ['PERSON', 'ORG', 'GPE'])
        
        return has_attack_language and has_entity
    
    def count_entities(self, entities: Dict[str, List[str]]) -> int:
        """Count total entities mentioned"""
        return sum(len(ents) for ents in entities.values())