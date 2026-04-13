# application/runners/learning_runner.py
from application.services.advanced_training_service import AdvancedTrainingService
from core.software_agent import SoftwareAgent
from infrastructure.database import Database
from typing import Optional
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class LearningPercept:
    """Šta agent opaža"""
    gold_count: int
    gold_threshold: int
    retraining_enabled: bool
    last_retrain_date: Optional[datetime]

@dataclass
class LearningAction:
    """Šta agent odluči"""
    should_retrain: bool
    reason: str

@dataclass
class LearningResult:
    """Rezultat tick-a"""
    retrain_executed: bool
    new_model_version: Optional[str]
    message: str

class LearningRunner(SoftwareAgent[LearningPercept, LearningAction, LearningResult]):
    """
    AGENT ZA UČENJE - Retraining logic
    Sense: Pročitaj gold counter i settings
    Think: Odluči da li treba retrain
    Act: Pokreni retrain sa PRAVOM finetun
    Learn: Reset counter
    """
    
    def __init__(self, db: Database):
        self.db = db
        self.advanced_training_service = AdvancedTrainingService(db)
    
    async def sense(self) -> Optional[LearningPercept]:
        """
        SENSE - pročitaj system state
        """
        settings = self.db.get_system_settings()
        
        logger.info(
            f"SENSE: Gold labels = {settings.new_gold_since_last_train} / "
            f"{settings.gold_threshold}"
        )
        
        return LearningPercept(
            gold_count=settings.new_gold_since_last_train,
            gold_threshold=settings.gold_threshold,
            retraining_enabled=settings.retraining_enabled,
            last_retrain_date=settings.last_retrain_date
        )
    
    async def think(self, percept: LearningPercept) -> LearningAction:
        """
        THINK - biznis pravilo za retrain
        """
        should_retrain = (
            percept.retraining_enabled and
            percept.gold_count >= percept.gold_threshold
        )
        
        if should_retrain:
            reason = (
                f"Gold labels ({percept.gold_count}) reached threshold "
                f"({percept.gold_threshold})"
            )
            logger.info(f"THINK: {reason}")
        else:
            reason = (
                f"Not enough gold labels: {percept.gold_count} / "
                f"{percept.gold_threshold}"
            )
        
        return LearningAction(
            should_retrain=should_retrain,
            reason=reason
        )
    
    async def act(self, action: LearningAction) -> LearningResult:
        """
        ACT - izvrši PRAVO treniranje
        """
        if not action.should_retrain:
            return LearningResult(
                retrain_executed=False,
                new_model_version=None,
                message=action.reason
            )
        
        # PRAVA FINETUNING sa AdvancedTrainingService
        logger.info("ACT: Starting REAL model retraining...")
        
        result = self.advanced_training_service.train_model()
        
        if result['success']:
            new_version = result['new_version']
            logger.info(f"ACT: Model retraining completed. New version: {new_version}")
            
            # LEARN - Reset gold counter AND update last_retrain_date
            settings = self.db.get_system_settings()
            settings.new_gold_since_last_train = 0
            settings.last_retrain_date = datetime.utcnow()
            self.db.update_system_settings(settings)
            logger.info("LEARN: Gold counter reset to 0, last_retrain_date updated")
            
            return LearningResult(
                retrain_executed=True,
                new_model_version=new_version,
                message=f"Real model retraining completed. Improvement: {result['performance']['improvement']:+.3f}"
            )
        else:
            logger.warning(f"ACT: Training failed - {result.get('reason', 'unknown')}")
            return LearningResult(
                retrain_executed=False,
                new_model_version=None,
                message=f"Training skipped: {result.get('reason', 'unknown error')}"
            )