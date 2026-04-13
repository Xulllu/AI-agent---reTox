# run.py

import os
import sys
import asyncio
import logging
from multiprocessing import Process
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import workers
from web.workers.classification_worker import run_classification_worker
from web.workers.learning_worker import run_learning_worker
from web.workers.collection_worker import run_collection_worker
from web.app import app

def run_api_server():
    """Run Flask API server"""
    logger.info("Starting Flask API server on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False)

def run_classification_background():
    """Run classification agent worker"""
    asyncio.run(run_classification_worker(tick_interval=2))

def run_learning_background():
    """Run learning agent worker"""
    asyncio.run(run_learning_worker(tick_interval=10))

def run_collection_background():
    """Run collection agent worker"""
    asyncio.run(run_collection_worker(tick_interval=5))

def main():
    """
    Main entry point - starts all components:
    1. Flask API (thin layer for submissions + moderator reviews)
    2. Classification worker (background agent - classifies comments)
    3. Learning worker (background agent - handles retraining)
    4. Collection worker (background agent - collects from Reddit)
    """
    
    logger.info("="*60)
    logger.info("ReTox - Context-Aware Toxicity Detection Agent")
    logger.info("Multi-agent system with Sense→Think→Act→Learn cycles")
    logger.info("="*60)
    
    # Create processes
    processes = []
    
    try:
        # Start API server
        p_api = Process(target=run_api_server, daemon=False)
        p_api.start()
        processes.append(("API Server", p_api))
        logger.info("✓ API Server process started")
        
        # Start background workers
        p_classification = Process(target=run_classification_background, daemon=False)
        p_classification.start()
        processes.append(("Classification Worker", p_classification))
        logger.info("✓ Classification Worker process started")
        
        p_learning = Process(target=run_learning_background, daemon=False)
        p_learning.start()
        processes.append(("Learning Worker", p_learning))
        logger.info("✓ Learning Worker process started")
        
        p_collection = Process(target=run_collection_background, daemon=False)
        p_collection.start()
        processes.append(("Collection Worker", p_collection))
        logger.info("✓ Collection Worker process started")
        
        logger.info("="*60)
        logger.info("All components started!")
        logger.info("API: http://localhost:5000")
        logger.info("Agents running in background...")
        logger.info("Press Ctrl+C to stop")
        logger.info("="*60)
        
        # Keep main process alive
        for name, p in processes:
            p.join()
    
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        for name, p in processes:
            logger.info(f"Stopping {name}...")
            p.terminate()
            p.join(timeout=5)
            if p.is_alive():
                p.kill()
        logger.info("All components stopped")

if __name__ == '__main__':
    main()