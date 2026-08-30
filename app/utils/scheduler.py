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


def check_medication_notifications():
    """Task to check active medications and schedule notifications."""
    logger.info("Running medication notification check at %s", datetime.now())
    try:
        import asyncio
        service = NotificationService()
        result = asyncio.run(service.check_medications_due_for_notification(check_time=True))
        logger.info("Medication check completed: %s", result)
    except Exception as e:
        logger.error("Error in medication check: %s", e)


def run_daily_backup():
    """Task to run daily database backup and purge backups older than 30 days (off-peak 03:00 AM)."""
    logger.info("Running daily database backup check at %s", datetime.now())
    try:
        from app.services.backup_service import BackupService
        service = BackupService()
        result = service.create_backup(purge_retention_days=30)
        logger.info("Daily database backup completed: %s", result)
    except Exception as e:
        logger.error("Error running daily database backup: %s", e)


def start_scheduler():
    """Start the background scheduler for daily tasks."""
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        check_vaccine_notifications,
        trigger=CronTrigger(minute="*"),
        id="vaccine_notifications",
        replace_existing=True
    )

    scheduler.add_job(
        check_medication_notifications,
        trigger=CronTrigger(minute="*"),
        id="medication_notifications",
        replace_existing=True
    )

    scheduler.add_job(
        run_daily_backup,
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_database_backup",
        replace_existing=True
    )

    scheduler.start()
    logger.info("Scheduler started - vaccine notifications daily, medication checks minutely, backups daily at 03:00 AM.")

    return scheduler