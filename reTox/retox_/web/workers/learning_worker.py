import asyncio
import logging
from datetime import datetime
from infrastructure.database import Database
from application.runners.learning_runner import LearningRunner
import os
from dotenv import load_dotenv

from web.workers.backoff import ExponentialBackoff  # NEW

load_dotenv()
logger = logging.getLogger(__name__)

async def run_learning_worker(tick_interval: int = 10):
    """
    Background worker za učenje (retraining)
    """
    db = Database(db_path=os.getenv("DATABASE_PATH", "retox.db"))
    runner = LearningRunner(db)

    tick_count = 0
    backoff = ExponentialBackoff(base_delay_s=float(tick_interval), max_delay_s=300.0)  # NEW

    logger.info(f"Learning worker started (interval={tick_interval}s)")

    try:
        while True:
            try:
                result = await runner.step()
                tick_count += 1

                if result:
                    if result.retrain_executed:
                        logger.info(f"[Tick #{tick_count}] Model retrained: {result.new_model_version}")
                    else:
                        logger.debug(f"[Tick #{tick_count}] {result.message}")
                else:
                    logger.debug(f"[Tick #{tick_count}] No retrain needed")

                backoff.reset()  # NEW
                await asyncio.sleep(tick_interval)

            except Exception as e:
                delay = backoff.next_delay()  # NEW
                logger.error(f"Learning tick error: {e} (retry in {delay:.2f}s)", exc_info=True)
                await asyncio.sleep(delay)

    except KeyboardInterrupt:
        logger.info(f"Learning worker stopped. Completed {tick_count} ticks")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_learning_worker(tick_interval=10))