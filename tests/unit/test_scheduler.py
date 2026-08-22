from unittest.mock import MagicMock, patch

from app.utils import scheduler


def test_check_vaccine_notifications_success():
    mock_service_instance = MagicMock()

    with patch("app.utils.scheduler.NotificationService", return_value=mock_service_instance), \
         patch("asyncio.run", return_value=3) as mock_asyncio_run:
        scheduler.check_vaccine_notifications()

        mock_asyncio_run.assert_called_once_with(mock_service_instance.check_vaccines_due_for_notification())


def test_check_vaccine_notifications_handles_exception():
    mock_service_instance = MagicMock()

    with patch("app.utils.scheduler.NotificationService", return_value=mock_service_instance), \
         patch("asyncio.run", side_effect=RuntimeError("Database error")):
        # Should catch exception gracefully and log error
        scheduler.check_vaccine_notifications()


def test_check_medication_notifications_success():
    mock_service_instance = MagicMock()

    with patch("app.utils.scheduler.NotificationService", return_value=mock_service_instance), \
         patch("asyncio.run", return_value=5) as mock_asyncio_run:
        scheduler.check_medication_notifications()

        mock_asyncio_run.assert_called_once_with(mock_service_instance.check_medications_due_for_notification())


def test_check_medication_notifications_handles_exception():
    mock_service_instance = MagicMock()

    with patch("app.utils.scheduler.NotificationService", return_value=mock_service_instance), \
         patch("asyncio.run", side_effect=RuntimeError("Async error")):
        # Should catch exception gracefully and log error
        scheduler.check_medication_notifications()


def test_start_scheduler():
    mock_scheduler_instance = MagicMock()

    with patch("app.utils.scheduler.BackgroundScheduler", return_value=mock_scheduler_instance):
        result = scheduler.start_scheduler()

        assert result == mock_scheduler_instance
        assert mock_scheduler_instance.add_job.call_count == 3
        mock_scheduler_instance.start.assert_called_once()


def test_run_daily_backup_task():
    mock_service_instance = MagicMock()
    with patch("app.services.backup_service.BackupService", return_value=mock_service_instance):
        scheduler.run_daily_backup()
        mock_service_instance.create_backup.assert_called_once_with(purge_retention_days=30)

