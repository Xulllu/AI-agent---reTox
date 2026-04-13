import asyncio
import logging
from datetime import datetime, timedelta
from infrastructure.database import Database
from application.runners.classification_runner import ClassificationRunner
import os
from dotenv import load_dotenv

from web.workers.backoff import ExponentialBackoff  # NEW

load_dotenv()

logger = logging.getLogger(__name__)

async def run_classification_worker(tick_interval: int = 2):
    """
    Background worker koji kontinuirano radi ClassificationRunner tickove
    """
    db = Database(db_path=os.getenv("DATABASE_PATH", "retox.db"))
    runner = ClassificationRunner(db)

    tick_count = 0
    start_time = datetime.utcnow()

    backoff = ExponentialBackoff(base_delay_s=float(tick_interval), max_delay_s=60.0)  # NEW

    logger.info(f"Classification worker started (interval={tick_interval}s)")

    try:
        while True:
            try:
                result = await runner.step()
                tick_count += 1

                if result:
                    logger.info(
                        f"[Tick #{tick_count}] Classified comment {result.comment_id} "
                        f"({result.category.value}) in r/{result.subreddit}"
                    )
                else:
                    logger.debug(f"[Tick #{tick_count}] No work (queue empty)")

                backoff.reset()  # NEW
                await asyncio.sleep(tick_interval)

            except Exception as e:
                delay = backoff.next_delay()  # NEW
                logger.error(f"Tick error: {e} (retry in {delay:.2f}s)", exc_info=True)
                await asyncio.sleep(delay)

    except KeyboardInterrupt:
        elapsed = datetime.utcnow() - start_time
        logger.info(
            f"Classification worker stopped. "
            f"Completed {tick_count} ticks in {elapsed.total_seconds():.1f}s"
        )


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_classification_worker(tick_interval=2))