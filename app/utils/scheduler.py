"""Scheduler for background tasks like vaccine notifications."""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


def check_vaccine_notifications():
    """Task to check vaccines due for notification."""
    logger.info("Running vaccine notification check at %s", datetime.now())
    try:
        import asyncio
        service = NotificationService()
        result = asyncio.run(service.check_vaccines_due_for_notification())
        logger.info("Vaccine notification check completed: %s", result)
    except Exception as e:
        logger.error("Error in vaccine notification check: %s", e)


def start_scheduler():
    """Start the background scheduler for daily tasks."""
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        check_vaccine_notifications,
        trigger=CronTrigger(hour=8, minute=0),
        id="vaccine_notifications",
        replace_existing=True
    )

    scheduler.start()
    logger.info("Scheduler started - vaccine notifications will run daily at 8:00 AM")

    return scheduler