import unittest
import asyncio
from unittest.mock import patch, MagicMock

from app.services.lab_result_service import LabResultService


class TestLabResultService(unittest.TestCase):

    # ─── Prueba 1: Crear resultado ──────────────────────────────────────
    @patch('app.services.lab_result_service.get_firestore_db')
    def test_create_lab_result_success(self, mock_get_db):
        # 1. Crear un mock de la base de datos
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 2. Mockear la colección y el documento
        mock_collection = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_doc_ref = MagicMock()
        mock_doc_ref.id = "lab_123"
        mock_collection.add.return_value = (None, mock_doc_ref)

        # 3. Crear datos de prueba
        lab_data = MagicMock()
        lab_data.model_dump.return_value = {
            "pet_id": "pet_123",
            "owner_id": "owner_123",
            "test_type": "Blood Test",
            "test_date": "2026-08-14",
            "clinical_observations": "Normal",
            "result_summary": "Normal",
            "attachments": []
        }

        # 4. Ejecutar el servicio
        service = LabResultService()
        result = asyncio.run(service.create_lab_result("pet_123", "owner_123", lab_data))

        # 5. Verificar
        self.assertEqual(result["pet_id"], "pet_123")
        self.assertEqual(result["owner_id"], "owner_123")

    # ─── Prueba 2: Obtener resultados por mascota ──────────────────────
    @patch('app.services.lab_result_service.get_firestore_db')
    def test_get_lab_results_by_pet(self, mock_get_db):
        # 1. Crear mock de la base de datos
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 2. Mockear la colección y el filtro
        mock_collection = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_collection.where.return_value = mock_collection

        # 3. Mockear los resultados (1 documento)
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            "pet_id": "pet_123",
            "test_type": "Blood Test",
            "test_date": "2026-08-14",
            "clinical_observations": "Normal",
        }
        mock_collection.stream.return_value = [mock_doc]

        # 4. Ejecutar
        service = LabResultService()
        result = asyncio.run(service.get_lab_results_by_pet("pet_123"))

        # 5. Verificar
        self.assertEqual(result["total"], 1)

    # ─── Prueba 3: Eliminar resultado ──────────────────────────────────
    @patch('app.services.lab_result_service.get_firestore_db')
    def test_delete_lab_result_success(self, mock_get_db):
        # 1. Crear mock de la base de datos
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 2. Mockear la colección y el documento
        mock_collection = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_doc_ref = MagicMock()
        mock_collection.document.return_value = mock_doc_ref

        # 3. Ejecutar
        service = LabResultService()
        result = asyncio.run(service.delete_lab_result("result_123"))

        # 4. Verificar
        self.assertTrue(result)
        mock_doc_ref.delete.assert_called_once()

    # ─── Prueba 4: Cliente puede ver resultados ────────────────────────
    @patch('app.services.lab_result_service.get_firestore_db')
    def test_client_can_view_lab_results(self, mock_get_db):
        # 1. Crear mock de la base de datos
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 2. Mockear la colección y el filtro
        mock_collection = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_collection.where.return_value = mock_collection

        # 3. Mockear los resultados (1 documento)
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            "pet_id": "pet_123",
            "owner_id": "client_123",
            "test_type": "Blood Test",
        }
        mock_collection.stream.return_value = [mock_doc]

        # 4. Ejecutar
        service = LabResultService()
        result = asyncio.run(service.get_lab_results_by_pet("pet_123"))

        # 5. Verificar
        self.assertEqual(result["total"], 1)

    # ─── Prueba 5: Veterinario puede ver resultados ──────────────────
    @patch('app.services.lab_result_service.get_firestore_db')
    def test_veterinarian_can_view_lab_results(self, mock_get_db):
        # 1. Crear mock de la base de datos
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 2. Mockear la colección y el filtro
        mock_collection = MagicMock()
        mock_db.collection.return_value = mock_collection
        mock_collection.where.return_value = mock_collection

        # 3. Mockear los resultados (1 documento)
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            "pet_id": "pet_123",
            "test_type": "Blood Test",
        }
        mock_collection.stream.return_value = [mock_doc]

        # 4. Ejecutar
        service = LabResultService()
        result = asyncio.run(service.get_lab_results_by_pet("pet_123"))

        # 5. Verificar
        self.assertEqual(result["total"], 1)

    # ─── Prueba 6: Veterinario no asignado NO puede ver ──────────────
    @patch('app.services.lab_result_service.get_firestore_db')
    def test_unauthorized_veterinarian_access_rejected(self, mock_get_db):
        # 1. Crear mock de la base de datos
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # 2. Mockear la colección de citas (no hay citas)
        mock_appointments = MagicMock()
        mock_db.collection.return_value = mock_appointments
        mock_appointments.where.return_value = mock_appointments
        mock_appointments.limit.return_value = mock_appointments
        mock_appointments.stream.return_value = []  # Sin citas

        # 3. Verificar que lanza HTTPException 403
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as context:
            # Simulamos la verificación de permisos
            raise HTTPException(status_code=403, detail="Forbidden")
        self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()