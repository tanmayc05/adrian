import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from apscheduler.schedulers.background import BackgroundScheduler
from graph.pipeline import run_pipeline
from db.database import cleanup_old_deals

logger = logging.getLogger(__name__)


def job():
    """Run the Adrian pipeline once."""
    logger.info("--- Scheduled run starting ---")
    try:
        cleanup_old_deals(days=7)
        result = run_pipeline()
        logger.info(f"--- Scheduled run done. Sent {result['sent_count']} alerts ---")
    except Exception as e:
        logger.error(f"--- Pipeline failed: {e} ---")


def start(interval_minutes: int = 30) -> BackgroundScheduler:
    """Start the scheduler in the background and return it."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        job,
        "interval",
        minutes=interval_minutes,
        id="adrian_pipeline",
        misfire_grace_time=300,  # 5 min grace before skipping a missed run
        coalesce=True,           # if multiple runs were missed, only run once
    )

    # Run immediately on startup, then every interval
    job()

    scheduler.start()
    logger.info(f"Scheduler started in background. Running every {interval_minutes} minutes.")
    return scheduler
