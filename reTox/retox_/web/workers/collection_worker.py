import asyncio
import logging
import os
from dotenv import load_dotenv

from infrastructure.database import Database
from application.runners.collection_runner import CollectionRunner
from web.workers.backoff import ExponentialBackoff  # NEW

load_dotenv()
logger = logging.getLogger(__name__)

async def run_collection_worker(tick_interval: int = 5):
    """
    Background worker za kolekciju komentara sa Reddita
    """
    db = Database(db_path=os.getenv("DATABASE_PATH", "retox.db"))
    runner = CollectionRunner(db)

    tick_count = 0
    backoff = ExponentialBackoff(base_delay_s=float(tick_interval), max_delay_s=60.0)  # NEW

    logger.info(f"Collection worker started (interval={tick_interval}s)")

    try:
        while True:
            try:
                result = await runner.step()
                tick_count += 1

                if result:
                    logger.info(
                        f"[Tick #{tick_count}] Job {result.job_id} "
                        f"→ {result.status.value} "
                        f"({result.comments_collected} comments)"
                    )
                else:
                    logger.debug(f"[Tick #{tick_count}] No pending collection jobs")

                backoff.reset()  # NEW (success -> reset backoff)
                await asyncio.sleep(tick_interval)

            except Exception as e:
                delay = backoff.next_delay()  # NEW
                logger.error(f"Collection tick error: {e} (retry in {delay:.2f}s)", exc_info=True)
                await asyncio.sleep(delay)

    except KeyboardInterrupt:
        logger.info(f"Collection worker stopped. Completed {tick_count} ticks")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_collection_worker(tick_interval=5))