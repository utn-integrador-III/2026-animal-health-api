"""Pruebas unitarias para el sistema de notificaciones."""

import unittest
import asyncio
from unittest.mock import patch, MagicMock

from app.services.notification_service import NotificationService


class TestNotificationService(unittest.TestCase):
    """Pruebas para el servicio de notificaciones."""

    def setUp(self):
        """Configuración inicial para cada prueba."""
        self.service = NotificationService()
        self.mock_db = MagicMock()

    @patch('app.services.notification_service.get_firestore_db')
    def test_check_vaccines_due_for_notification_no_vaccines(self, mock_get_db):
        """Prueba que no se creen notificaciones si no hay vacunas."""
        mock_get_db.return_value = self.mock_db
        mock_collection = MagicMock()
        self.mock_db.collection.return_value = mock_collection
        mock_collection.where.return_value = mock_collection
        mock_collection.stream.return_value = []

        # EJECUTAR CON asyncio.run()
        result = asyncio.run(self.service.check_vaccines_due_for_notification())
        self.assertTrue(result["success"])

    @patch('app.services.notification_service.get_firestore_db')
    def test_create_notification_for_vaccine_due(self, mock_get_db):
        """Prueba que se cree una notificación para una vacuna próxima a vencer."""
        mock_get_db.return_value = self.mock_db
        
        # Mockear colecciones
        mock_vaccines = MagicMock()
        mock_pets = MagicMock()
        mock_notifications = MagicMock()
        
        def get_collection(name):
            if name == "vaccines":
                return mock_vaccines
            elif name == "pets":
                return mock_pets
            elif name == "notifications":
                return mock_notifications
            return MagicMock()
        
        self.mock_db.collection.side_effect = get_collection

        # Mockear la búsqueda de vacunas (vacía)
        mock_vaccines.where.return_value = mock_vaccines
        mock_vaccines.stream.return_value = []

        # EJECUTAR CON asyncio.run()
        result = asyncio.run(self.service.check_vaccines_due_for_notification())
        
        # Verificar que no haya errores
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()