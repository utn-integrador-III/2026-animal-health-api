"""Pruebas unitarias para el sistema de resultados de laboratorio."""

import unittest
import asyncio
from unittest.mock import patch, MagicMock

from app.services.lab_result_service import LabResultService


class TestLabResultService(unittest.TestCase):
    """Pruebas para el servicio de resultados de laboratorio."""

    def setUp(self):
        """Configuración inicial para cada prueba."""
        patcher = patch('app.services.lab_result_service.get_firestore_db')
        self.mock_get_db = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_db = MagicMock()
        self.mock_get_db.return_value = self.mock_db
        self.service = LabResultService()

    @patch('app.services.lab_result_service.get_firestore_db')
    def test_create_lab_result_request_success(self, mock_get_db):
        """Prueba que se cree una solicitud de examen de laboratorio (Fase 1 EDUS)."""
        mock_get_db.return_value = self.mock_db
        
        mock_collection = MagicMock()
        self.mock_db.collection.return_value = mock_collection
        mock_doc_ref = MagicMock()
        mock_doc_ref.id = "lab_req_123"
        mock_collection.add.return_value = (None, mock_doc_ref)

        pet_id = "pet_123"
        owner_id = "owner_123"
        veterinarian_id = "vet_123"
        veterinarian_name = "Dra. María Sánchez"

        lab_data = MagicMock()
        lab_data.model_dump.return_value = {
            "test_type": "Hemograma",
            "priority": "Urgente",
            "reason": "Sospecha de anemia y decaimiento",
            "clinical_observations": "Mucosas pálidas",
            "requested_at": "2026-08-27",
            "status": "Solicitado",
            "veterinarian_id": veterinarian_id,
            "veterinarian_name": veterinarian_name,
        }

        result = asyncio.run(self.service.create_lab_result(
            pet_id=pet_id,
            owner_id=owner_id,
            data=lab_data,
            veterinarian_id=veterinarian_id,
            veterinarian_name=veterinarian_name,
        ))
        
        self.assertEqual(result["pet_id"], pet_id)
        self.assertEqual(result["owner_id"], owner_id)
        self.assertEqual(result["test_type"], "Hemograma")
        self.assertEqual(result["priority"], "Urgente")
        self.assertEqual(result["status"], "Solicitado")
        self.assertEqual(result["veterinarian_name"], veterinarian_name)

    @patch('app.services.lab_result_service.get_firestore_db')
    def test_get_lab_results_by_pet(self, mock_get_db):
        """Prueba que se obtengan los resultados de laboratorio ordenados de una mascota."""
        mock_get_db.return_value = self.mock_db
        
        mock_collection = MagicMock()
        self.mock_db.collection.return_value = mock_collection
        mock_collection.where.return_value = mock_collection
        
        mock_doc1 = MagicMock()
        mock_doc1.id = "result_1"
        mock_doc1.to_dict.return_value = {
            "test_type": "Hemograma",
            "priority": "Urgente",
            "status": "Solicitado",
            "requested_at": "2026-08-27",
            "created_at": "2026-08-27T10:00:00Z",
            "pet_id": "pet_123",
            "owner_id": "owner_123",
        }
        mock_collection.stream.return_value = [mock_doc1]

        result = asyncio.run(self.service.get_lab_results_by_pet("pet_123"))
        
        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["test_type"], "Hemograma")

    @patch('app.services.lab_result_service.get_firestore_db')
    def test_update_lab_result_upload_details(self, mock_get_db):
        """Prueba que se actualice el resultado con los datos cargados por el veterinario (Fase 2)."""
        mock_get_db.return_value = self.mock_db
        
        mock_collection = MagicMock()
        self.mock_db.collection.return_value = mock_collection
        mock_doc_ref = MagicMock()
        mock_collection.document.return_value = mock_doc_ref

        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "id": "result_123",
            "pet_id": "pet_123",
            "owner_id": "owner_123",
            "test_type": "Hemograma",
            "status": "Resultado disponible",
            "summary": "Hematocrito 28%",
            "observations": "Anemia normocítica",
            "recommendation": "Suplemento de hierro",
            "file_name": "report.pdf",
        }
        mock_doc_ref.get.return_value = mock_snapshot

        update_data = MagicMock()
        update_data.model_dump.return_value = {
            "result_date": "2026-08-28",
            "summary": "Hematocrito 28%",
            "observations": "Anemia normocítica",
            "recommendation": "Suplemento de hierro",
            "status": "Resultado disponible",
            "file_url": "https://storage.googleapis.com/bucket/report.pdf",
            "file_name": "report.pdf",
        }

        result = asyncio.run(self.service.update_lab_result("result_123", update_data))
        
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "Resultado disponible")
        self.assertEqual(result["summary"], "Hematocrito 28%")
        self.assertEqual(result["file_name"], "report.pdf")

    @patch('app.services.lab_result_service.get_firestore_db')
    def test_delete_lab_result_success(self, mock_get_db):
        """Prueba que se elimine un resultado de laboratorio correctamente."""
        mock_get_db.return_value = self.mock_db
        
        mock_collection = MagicMock()
        self.mock_db.collection.return_value = mock_collection
        mock_doc_ref = MagicMock()
        mock_collection.document.return_value = mock_doc_ref

        result = asyncio.run(self.service.delete_lab_result("result_123"))
        
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()