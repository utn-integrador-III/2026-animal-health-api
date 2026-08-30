"""Unit tests for admin veterinarian registration."""

import unittest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from app.services.vet_service import register_veterinarian
from app.schemas.vet import VetRegister


class TestVetAdmin(unittest.TestCase):
    """Pruebas para el registro de veterinarios por administradores."""

    def setUp(self):
        """Configuración inicial para cada prueba."""
        self.mock_db = MagicMock()

    @patch('app.services.vet_service.get_firestore_db')
    def test_register_veterinarian_success(self, mock_get_db):
        """Prueba que un administrador pueda registrar un veterinario correctamente."""
        mock_get_db.return_value = self.mock_db

        # Mockear la colección users
        mock_users = MagicMock()
        self.mock_db.collection.return_value = mock_users

        # Mockear la búsqueda de email (no existe)
        mock_users.where.return_value = mock_users
        mock_users.limit.return_value = mock_users
        mock_users.get.return_value = []

        # Mockear la creación del usuario
        mock_doc_ref = MagicMock()
        mock_users.document.return_value = mock_doc_ref
        mock_doc_ref.create.return_value = None
        
        # Mockear la obtención del usuario creado
        mock_created_user = MagicMock()
        mock_created_user.to_dict.return_value = {
            "email": "vet@test.com",
            "full_name": "Dr. Test",
            "role": "veterinarian",
            "phone": "88888888",
            "specialty": "Cardiología",
            "license_number": "LIC-12345",
            "created_at": "2026-07-31T00:00:00.000Z"
        }
        mock_doc_ref.get.return_value = mock_created_user

        # Datos de prueba
        vet_data = VetRegister(
            email="vet@test.com",
            password="password123",
            full_name="Dr. Test",
            phone="88888888",
            specialty="Cardiología",
            license_number="LIC-12345"
        )

        # Ejecutar
        result = register_veterinarian(vet_data, admin_id="admin123")

        # Verificar
        self.assertEqual(result["email"], "vet@test.com")
        self.assertEqual(result["full_name"], "Dr. Test")
        self.assertEqual(result["role"], "veterinarian")
        self.assertEqual(result["specialty"], "Cardiología")
        mock_doc_ref.create.assert_called_once()

    @patch('app.services.vet_service.get_firestore_db')
    def test_register_veterinarian_email_already_exists(self, mock_get_db):
        """Prueba que no se pueda registrar un email duplicado."""
        mock_get_db.return_value = self.mock_db

        # Mockear la colección users
        mock_users = MagicMock()
        self.mock_db.collection.return_value = mock_users

        # Mockear que el email ya existe
        mock_users.where.return_value = mock_users
        mock_users.limit.return_value = mock_users
        mock_users.get.return_value = [MagicMock()]  # Usuario existente

        # Datos de prueba
        vet_data = VetRegister(
            email="existing@test.com",
            password="password123",
            full_name="Dr. Existing",
            phone="88888888"
        )

        # Ejecutar y verificar que lanza HTTPException 409
        with self.assertRaises(HTTPException) as context:
            register_veterinarian(vet_data, admin_id="admin123")
        
        self.assertEqual(context.exception.status_code, 409)
        self.assertIn("already registered", context.exception.detail)


if __name__ == "__main__":
    unittest.main()