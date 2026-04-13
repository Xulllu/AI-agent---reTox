# application/services/training_service.py

from infrastructure.database import Database
from domain.entities import SystemSettings
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class TrainingService:
    """Upravljanje modelom i retrainingom"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def should_retrain(self) -> bool:
        """Provjeri da li treba retrain"""
        settings = self.db.get_system_settings()
        
        should = (
            settings.retraining_enabled and
            settings.new_gold_since_last_train >= settings.gold_threshold
        )
        
        logger.info(
            f"Retrain check: {settings.new_gold_since_last_train} / "
            f"{settings.gold_threshold} (enabled={settings.retraining_enabled})"
        )
        
        return should
    
    def train_model(self) -> str:
        """Simuliraj treniranje modela"""
        logger.info("Starting simulated model retraining...")
        
        # Za sada: simulacija (u async context, ali vraća string)
        new_version = f"v{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Model training completed: {new_version}")
        
        return new_version
    
    def reset_gold_counter(self) -> None:
        """Reset counter nakon što se model retrenira"""
        settings = self.db.get_system_settings()
        settings.new_gold_since_last_train = 0
        settings.last_retrain_date = datetime.utcnow()
        self.db.update_system_settings(settings)
        logger.info("Gold counter reset")
    
    def set_retraining_enabled(self, enabled: bool) -> None:
        """Omogući/onemogući automatic retraining"""
        settings = self.db.get_system_settings()
        settings.retraining_enabled = enabled
        self.db.update_system_settings(settings)
        logger.info(f"Retraining {'enabled' if enabled else 'disabled'}")
    
    def set_retraining_enabled_api(self, enabled: bool) -> dict:
        self.set_retraining_enabled(enabled)
        return {
            "success": True,
            "retraining_enabled": bool(enabled),
            "message": "Retraining enabled" if enabled else "Retraining disabled",
        }
    
    def get_training_status_api(self) -> dict:
        settings = self.db.get_system_settings()
        return {
            'gold_labels_since_last_train': settings.new_gold_since_last_train,
            'gold_threshold': settings.gold_threshold,
            'retraining_enabled': settings.retraining_enabled,
            'last_retrain_date': settings.last_retrain_date.isoformat() if settings.last_retrain_date else None,
            'should_retrain': self.should_retrain(),
        }