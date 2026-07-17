"""Unit tests for the medical history and medications endpoints in pet_routes.py."""

import unittest
from unittest.mock import patch
from datetime import date

from fastapi import HTTPException

from app import schemas
from app.constant import Collections, UserRole
from app.routes import pet_routes
from tests.unit.test_vaccines import FakeFirestore, BASE_PET, BASE_APPOINTMENT, VET_USER, CLIENT_USER


def _db_with_pet_and_appointment():
    """Returns a FakeFirestore with pet-1 and a vet-1 appointment."""
    db = FakeFirestore()
    db.collection(Collections.PETS).data["pet-1"] = dict(BASE_PET)
    db.collection(Collections.APPOINTMENTS).data["appt-1"] = dict(BASE_APPOINTMENT)
    return db


class MedicalHistoryAndMedicationTests(unittest.TestCase):

    # ─── Clinical Records Tests ──────────────────────────────────────────────

    def test_get_clinical_records_client_success(self):
        db = _db_with_pet_and_appointment()
        db.collection(Collections.MEDICAL_RECORDS).data["record-1"] = {
            "pet_id": "pet-1",
            "diagnosis": "Gastritis",
            "treatment": "Ayuno de 12h y dieta blanda",
            "weight_kg": 8.5,
            "notes": "Evolución favorable",
            "date": "2026-07-16",
            "veterinarian_id": "vet-1",
            "veterinarian_name": "Dr. Smith",
            "created_at": "2026-07-16T12:00:00+00:00",
        }
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.list_clinical_records("pet-1", current_user=CLIENT_USER)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].diagnosis, "Gastritis")

    def test_get_clinical_records_vet_success(self):
        db = _db_with_pet_and_appointment()
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.list_clinical_records("pet-1", current_user=VET_USER)
        self.assertEqual(result, [])

    def test_get_clinical_records_vet_not_assigned_forbidden(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = dict(BASE_PET)
        other_vet = {"id": "vet-99", "role": UserRole.VETERINARIAN, "full_name": "Dr. X"}
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.list_clinical_records("pet-1", current_user=other_vet)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_create_clinical_record_vet_success(self):
        db = _db_with_pet_and_appointment()
        payload = schemas.ClinicalRecordCreate(
            diagnosis="Otitis",
            treatment="Limpieza de oído y gotas antibióticas",
            weight_kg=9.0,
            notes="Control en 10 días",
            date="2026-07-17",
        )
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.create_clinical_record(
                "pet-1",
                payload,
                current_user=VET_USER,
            )
        self.assertEqual(result.diagnosis, "Otitis")
        self.assertEqual(result.pet_id, "pet-1")
        self.assertEqual(result.veterinarian_id, "vet-1")
        
        # Verify persistence
        records_db = db.collection(Collections.MEDICAL_RECORDS).data
        self.assertEqual(len(records_db), 1)

    # ─── Medications Tests ───────────────────────────────────────────────────

    def test_get_medications_success(self):
        db = _db_with_pet_and_appointment()
        db.collection(Collections.MEDICATIONS).data["med-1"] = {
            "pet_id": "pet-1",
            "name": "Antibiótico",
            "dosage": "1 tableta",
            "frequency": "Cada 12 horas",
            "start_date": "2026-07-15",
            "end_date": "2026-07-22",
            "notes": "Con comida",
            "status": "active",
            "checked_dates": [],
            "veterinarian_id": "vet-1",
            "veterinarian_name": "Dr. Smith",
            "created_at": "2026-07-15T00:00:00+00:00",
        }
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.list_medications("pet-1", current_user=CLIENT_USER)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Antibiótico")

    def test_create_medication_vet_success(self):
        db = _db_with_pet_and_appointment()
        payload = schemas.MedicationCreate(
            name="Vitamina B12",
            dosage="0.5 ml",
            frequency="Diario",
            start_date="2026-07-17",
            end_date="2026-07-24",
            notes="Vía oral",
        )
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.create_medication(
                "pet-1",
                payload,
                current_user=VET_USER,
            )
        self.assertEqual(result.name, "Vitamina B12")
        self.assertEqual(result.status, "active")

    def test_toggle_medication_check(self):
        db = _db_with_pet_and_appointment()
        db.collection(Collections.MEDICATIONS).data["med-1"] = {
            "pet_id": "pet-1",
            "name": "Antibiótico",
            "dosage": "1 tableta",
            "frequency": "Cada 12 horas",
            "start_date": "2026-07-15",
            "end_date": "2026-07-22",
            "notes": "",
            "status": "active",
            "checked_dates": ["2026-07-16"],
            "veterinarian_id": "vet-1",
            "veterinarian_name": "Dr. Smith",
            "created_at": "2026-07-15T00:00:00+00:00",
        }
        
        # Toggle check for new date (add check)
        toggle_payload = schemas.MedicationCheckToggle(date="2026-07-17")
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.toggle_medication_check(
                "pet-1", "med-1", toggle_payload, current_user=CLIENT_USER
            )
        self.assertIn("2026-07-17", result.checked_dates)
        self.assertIn("2026-07-16", result.checked_dates)

        # Toggle check for existing date (remove check)
        toggle_payload_remove = schemas.MedicationCheckToggle(date="2026-07-16")
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.toggle_medication_check(
                "pet-1", "med-1", toggle_payload_remove, current_user=CLIENT_USER
            )
        self.assertNotIn("2026-07-16", result.checked_dates)
        self.assertIn("2026-07-17", result.checked_dates)

    # ─── Delete Medication Tests ─────────────────────────────────────────────

    def test_delete_medication_vet_success(self):
        db = _db_with_pet_and_appointment()
        db.collection(Collections.MEDICATIONS).data["med-1"] = {
            "pet_id": "pet-1",
            "name": "Antibiótico",
            "status": "active",
        }
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.delete_medication("pet-1", "med-1", current_user=VET_USER)
        self.assertIsNone(result)
        self.assertNotIn("med-1", db.collection(Collections.MEDICATIONS).data)

    def test_delete_medication_vet_not_assigned_forbidden(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = dict(BASE_PET)
        db.collection(Collections.MEDICATIONS).data["med-1"] = {
            "pet_id": "pet-1",
            "name": "Antibiótico",
        }
        other_vet = {"id": "vet-99", "role": UserRole.VETERINARIAN, "full_name": "Dr. X"}
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.delete_medication("pet-1", "med-1", current_user=other_vet)
        self.assertEqual(ctx.exception.status_code, 403)
        # Check not deleted
        self.assertIn("med-1", db.collection(Collections.MEDICATIONS).data)

    def test_delete_medication_not_found(self):
        db = _db_with_pet_and_appointment()
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.delete_medication("pet-1", "non-existent", current_user=VET_USER)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

