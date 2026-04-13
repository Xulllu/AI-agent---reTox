# initialize_jigsaw_real.py - Real Jigsaw dataset initialization

import sys
import os
import logging
import asyncio
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from datasets import load_dataset
    HAS_DATASETS = True
except ImportError:
    HAS_DATASETS = False
    logger.warning("⚠️  datasets library not installed. Install with: pip install datasets")

from infrastructure.database import Database
from application.services.toxicity_service import ToxicityService
from domain.entities import ModelVersion
import json

class JigsawRealInitializer:
    """Initialize model with real Jigsaw dataset from HuggingFace"""
    
    def __init__(self, db: Database):
        self.db = db
        self.toxicity_service = ToxicityService(db)
    
    async def download_jigsaw_dataset(self, max_samples: int = 1000) -> list:
        """
        Download Jigsaw Toxic Comment Classification dataset from HuggingFace
        
        Dataset info:
        - Source: google/jigsaw_toxicity_pred on HuggingFace
        - Size: ~160K comments for training
        - Labels: toxic, severe_toxic, obscene, threat, insult, identity_hate
        - We'll sample max_samples for initialization
        """
        logger.info(f"📥 Loading Jigsaw dataset (max {max_samples} samples)...")
        
        if not HAS_DATASETS:
            logger.error("Please install datasets library: pip install datasets")
            raise ImportError("datasets library required")
        
        try:
            # Load training dataset from HuggingFace
            logger.info("Downloading from HuggingFace (this may take a moment)...")
            dataset = load_dataset('google/jigsaw_toxicity_pred', split='train')
            
            logger.info(f"✓ Dataset loaded: {len(dataset)} total samples")
            
            # Sample data for processing
            samples = []
            
            # Take first max_samples
            for i, example in enumerate(dataset):
                if i >= max_samples:
                    break
                
                try:
                    text = example.get('comment_text', '')
                    
                    # Overall toxicity label
                    is_toxic = int(example.get('toxic', 0))
                    
                    # Skip empty comments
                    if not text or len(text.strip()) < 3:
                        continue
                    
                    # Skip comments with -1 labels (unlabeled)
                    if is_toxic == -1:
                        continue
                    
                    samples.append({
                        'text': text,
                        'is_toxic': is_toxic,
                        'severe_toxic': int(example.get('severe_toxic', 0)),
                        'obscene': int(example.get('obscene', 0)),
                        'threat': int(example.get('threat', 0)),
                        'insult': int(example.get('insult', 0)),
                        'identity_hate': int(example.get('identity_hate', 0))
                    })
                
                except Exception as e:
                    logger.debug(f"Skipped sample {i}: {e}")
                    continue
            
            logger.info(f"✓ Loaded {len(samples)} valid samples")
            
            # Count by category
            toxic_count = sum(1 for s in samples if s['is_toxic'] == 1)
            clean_count = len(samples) - toxic_count
            logger.info(f"  - Toxic: {toxic_count}")
            logger.info(f"  - Clean: {clean_count}")
            
            return samples
        
        except Exception as e:
            logger.error(f"Error downloading dataset: {e}")
            raise
    
    async def evaluate_model_on_jigsaw(self, samples: list) -> dict:
        """
        Evaluate pre-trained Detoxify model on Jigsaw samples
        This gives us baseline accuracy before any fine-tuning
        """
        logger.info(f"\n🧪 Evaluating model on {len(samples)} Jigsaw samples...")
        
        correct = 0
        false_positives = 0
        false_negatives = 0
        predictions = []
        
        # Sample rate for faster processing
        sample_rate = max(1, len(samples) // 100)  # Evaluate ~100 samples
        
        for i, sample in enumerate(samples):
            if i % sample_rate != 0:
                continue
            
            try:
                text = sample['text']
                true_label = sample['is_toxic']
                
                # Get model prediction
                prediction = await self.toxicity_service.predict(
                    text=text,
                    subreddit="jigsaw_baseline"
                )
                
                base_score = prediction['base_score']
                predicted_label = 1 if base_score > 0.5 else 0
                
                is_correct = predicted_label == true_label
                if is_correct:
                    correct += 1
                elif predicted_label == 1 and true_label == 0:
                    false_positives += 1
                elif predicted_label == 0 and true_label == 1:
                    false_negatives += 1
                
                # Store sample predictions
                if len(predictions) < 10:
                    predictions.append({
                        'text': text[:60],
                        'true': 'TOXIC' if true_label == 1 else 'CLEAN',
                        'pred': 'TOXIC' if predicted_label == 1 else 'CLEAN',
                        'score': round(base_score, 3),
                        'correct': is_correct
                    })
            
            except Exception as e:
                logger.debug(f"Error evaluating sample {i}: {e}")
                continue
        
        # Calculate metrics
        total = (len(samples) // sample_rate) if sample_rate > 0 else 1
        accuracy = correct / total if total > 0 else 0
        
        logger.info(f"  Accuracy: {accuracy:.1%} ({correct}/{total})")
        logger.info(f"  False Positives: {false_positives}")
        logger.info(f"  False Negatives: {false_negatives}")
        
        logger.info("\n  Sample predictions:")
        for pred in predictions[:5]:
            status = "✓" if pred['correct'] else "✗"
            logger.info(f"    {status} '{pred['text']}' → {pred['pred']} (score: {pred['score']})")
        
        return {
            'accuracy': accuracy,
            'correct': correct,
            'total': total,
            'false_positives': false_positives,
            'false_negatives': false_negatives,
            'predictions': predictions
        }
    
    def save_baseline_model_version(self, samples_count: int, performance: dict):
        """
        Create and save v1.0.0 model version with Jigsaw baseline performance
        """
        logger.info("\n💾 Creating v1.0.0 model version...")
        
        model_version = ModelVersion(
            version="v1.0.0",
            base_model="detoxify-original-jigsaw",
            accuracy_before=0.0,
            accuracy_after=performance['accuracy'],
            improvement=performance['accuracy'],
            false_positives=performance['false_positives'],
            false_negatives=performance['false_negatives'],
            samples_trained=samples_count,
            training_date=datetime.utcnow(),
            notes=f"Baseline Detoxify model evaluated on {samples_count} Jigsaw dataset samples"
        )
        
        try:
            self.db.save_model_version(model_version)
            logger.info(f"✅ Model version {model_version.version} saved")
            logger.info(f"   - Base Model: {model_version.base_model}")
            logger.info(f"   - Accuracy: {model_version.accuracy_after:.1%}")
            logger.info(f"   - Samples: {model_version.samples_trained}")
            logger.info(f"   - Date: {model_version.training_date}")
            return True
        except Exception as e:
            logger.error(f"Error saving model version: {e}")
            return False
    
    async def initialize(self):
        """Run full Jigsaw initialization"""
        logger.info("=" * 70)
        logger.info("🚀 ReTox Jigsaw Real Dataset Initialization")
        logger.info("=" * 70)
        
        try:
            # 1. Check if already initialized
            history = self.db.get_model_training_history()
            if history and len(history) > 0:
                logger.warning(f"⚠️  Model already initialized! Found {len(history)} versions")
                logger.info("   Existing versions:")
                for row in history[:3]:
                    logger.info(f"     - {row[0]}: {row[3]:.1%} accuracy")
                return False
            
            # 2. Download Jigsaw dataset
            samples = await self.download_jigsaw_dataset(max_samples=1000)
            
            if not samples:
                logger.error("No samples loaded from Jigsaw dataset")
                return False
            
            # 3. Evaluate baseline model performance
            performance = await self.evaluate_model_on_jigsaw(samples)
            
            # 4. Save baseline model version
            success = self.save_baseline_model_version(len(samples), performance)
            
            if success:
                logger.info("\n" + "=" * 70)
                logger.info("✅ Initialization Complete!")
                logger.info("=" * 70)
                logger.info("\nYour ReTox system is ready with Jigsaw baseline:")
                logger.info(f"  - Model Version: v1.0.0")
                logger.info(f"  - Base Model: detoxify-original")
                logger.info(f"  - Training Samples: {len(samples)}")
                logger.info(f"  - Baseline Accuracy: {performance['accuracy']:.1%}")
                logger.info(f"  - Status: Ready for learning")
                logger.info("\nNext steps:")
                logger.info("  1. Run: python run.py")
                logger.info("  2. Go to: http://localhost:5000/moderation")
                logger.info("  3. Approve/reject comments (teach the agent)")
                logger.info("  4. Accumulate gold labels (3/50)")
                logger.info("  5. At 50 labels → automatic retraining to v1.0.1")
                return True
            else:
                logger.error("❌ Failed to save model version")
                return False
        
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}", exc_info=True)
            return False

async def main():
    """Main entry point"""
    try:
        db = Database()
        initializer = JigsawRealInitializer(db)
        success = await initializer.initialize()
        
        if success:
            print("\n✅ Ready to start! Run: python run.py")
        else:
            print("\n❌ Initialization failed or already initialized")
        
        return success
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    success = asyncio.run(main())
    sys.exit(0 if success else 1)