"""Unit tests for app/main.py (FastAPI endpoints and lifecycle events)."""

import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


class TestMainApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch("app.main.start_scheduler") as mock_start:
            mock_sched = MagicMock()
            mock_sched.running = True
            mock_start.return_value = mock_sched
            from app.main import app, root, health_check, shutdown_scheduler
            cls.app = app
            cls.root_fn = staticmethod(root)
            cls.health_check_fn = staticmethod(health_check)
            cls.shutdown_scheduler_fn = staticmethod(shutdown_scheduler)
            cls.mock_sched = mock_sched
        cls.client = TestClient(cls.app)

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["message"], "Animal Health API")
        self.assertEqual(data["docs"], "/docs")
        self.assertEqual(data["version"], "1.0.0")

    def test_health_check_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_root_function_directly(self):
        res = self.root_fn()
        self.assertEqual(res["message"], "Animal Health API")

    def test_health_check_function_directly(self):
        res = self.health_check_fn()
        self.assertEqual(res, {"status": "ok"})

    def test_shutdown_scheduler_when_running(self):
        from app import main
        mock_sched = MagicMock()
        mock_sched.running = True
        main.scheduler = mock_sched
        main.shutdown_scheduler()
        mock_sched.shutdown.assert_called_once()

    def test_shutdown_scheduler_when_not_running(self):
        from app import main
        mock_sched = MagicMock()
        mock_sched.running = False
        main.scheduler = mock_sched
        main.shutdown_scheduler()
        mock_sched.shutdown.assert_not_called()

    def test_shutdown_scheduler_when_none(self):
        from app import main
        main.scheduler = None
        main.shutdown_scheduler()


if __name__ == "__main__":
    unittest.main()
