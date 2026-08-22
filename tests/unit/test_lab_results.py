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
    def test_create_lab_result_success(self, mock_get_db):
        """Prueba que se cree un resultado de laboratorio correctamente."""
        mock_get_db.return_value = self.mock_db
        
        # Mockear colección
        mock_collection = MagicMock()
        self.mock_db.collection.return_value = mock_collection
        mock_doc_ref = MagicMock()
        mock_doc_ref.id = "lab_result_123"
        mock_collection.add.return_value = (None, mock_doc_ref)

        # Datos de prueba
        pet_id = "pet_123"
        owner_id = "owner_123"
        lab_data = MagicMock()
        lab_data.model_dump.return_value = {
            "pet_id": pet_id,
            "owner_id": owner_id,
            "test_type": "Blood Test",
            "test_date": "2026-07-18",
            "clinical_observations": "Normal",
            "result_summary": "Normal",
            "attachments": [],
            "veterinarian_name": "Dr. Pérez"
        }

        # EJECUTAR CON asyncio.run()
        result = asyncio.run(self.service.create_lab_result(pet_id, owner_id, lab_data))
        
        # Verificar
        self.assertEqual(result["pet_id"], pet_id)
        self.assertEqual(result["owner_id"], owner_id)
        self.assertEqual(result["test_type"], "Blood Test")

    @patch('app.services.lab_result_service.get_firestore_db')
    def test_get_lab_results_by_pet(self, mock_get_db):
        """Prueba que se obtengan los resultados de laboratorio de una mascota."""
        mock_get_db.return_value = self.mock_db
        
        # Mockear colección
        mock_collection = MagicMock()
        self.mock_db.collection.return_value = mock_collection
        mock_collection.where.return_value = mock_collection
        
        # Mockear resultados
        mock_doc1 = MagicMock()
        mock_doc1.id = "result_1"
        mock_doc1.to_dict.return_value = {
            "test_type": "Blood Test",
            "test_date": "2026-07-18",
            "clinical_observations": "Normal",
            "pet_id": "pet_123",
            "owner_id": "owner_123"
        }
        mock_collection.stream.return_value = [mock_doc1]

        # EJECUTAR CON asyncio.run()
        result = asyncio.run(self.service.get_lab_results_by_pet("pet_123"))
        
        # Verificar
        self.assertEqual(result["total"], 1)

    @patch('app.services.lab_result_service.get_firestore_db')
    def test_delete_lab_result_success(self, mock_get_db):
        """Prueba que se elimine un resultado de laboratorio correctamente."""
        mock_get_db.return_value = self.mock_db
        
        # Mockear colección
        mock_collection = MagicMock()
        self.mock_db.collection.return_value = mock_collection
        mock_doc_ref = MagicMock()
        mock_collection.document.return_value = mock_doc_ref

        # EJECUTAR CON asyncio.run()
        result = asyncio.run(self.service.delete_lab_result("result_123"))
        
        # Verificar
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()