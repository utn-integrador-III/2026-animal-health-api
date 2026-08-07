"""Unit tests for the diagnosis endpoints in pet_routes.py."""

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app import schemas
from app.constant import Collections, UserRole
from app.routes import pet_routes
from tests.unit.test_vaccines import (
    FakeFirestore,
    BASE_PET,
    BASE_APPOINTMENT,
    VET_USER,
    CLIENT_USER,
)


def _db_with_pet_and_appointment():
    """Returns a FakeFirestore with pet-1 and a vet-1 appointment."""
    db = FakeFirestore()
    db.collection(Collections.PETS).data["pet-1"] = dict(BASE_PET)
    db.collection(Collections.APPOINTMENTS).data["appt-1"] = dict(BASE_APPOINTMENT)
    return db


DIAGNOSIS_CREATE_PAYLOAD = schemas.DiagnosisCreate(
    diagnosis="Dermatitis alérgica",
    presumptive_diagnosis="Dermatitis atópica",
    differential_diagnoses="Alergia alimentaria, Dermatitis por pulgas",
    status="Presuntivo",
    treatment="Antihistamínico y champú medicado",
    notes="Rascado persistente y eritema en orejas",
    reason="Rascado persistente",
    symptoms="Eritema en piel, Secreción en oídos",
)


class DiagnosisEndpointTests(unittest.TestCase):

    # GET /api/pets/{pet_id}/diagnoses — client reads their own pet's diagnoses
    def test_get_diagnoses_client_success(self):
        db = _db_with_pet_and_appointment()
        db.collection(Collections.DIAGNOSES).data["diag-1"] = {
            "pet_id": "pet-1",
            "diagnosis": "Dermatitis alérgica",
            "status": "Presuntivo",
            "treatment": "Antihistamínicos",
            "registered_by": "veterinarian",
            "created_at": "2026-07-10T12:00:00+00:00",
            "updated_at": "2026-07-10T12:00:00+00:00",
        }
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.list_diagnoses("pet-1", current_user=CLIENT_USER)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].diagnosis, "Dermatitis alérgica")

    # GET /api/pets/{pet_id}/diagnoses — empty list for pet without diagnoses
    def test_get_diagnoses_empty_list(self):
        db = _db_with_pet_and_appointment()
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.list_diagnoses("pet-1", current_user=CLIENT_USER)
        self.assertEqual(result, [])

    # GET /api/pets/{pet_id}/diagnoses — vet not assigned is forbidden
    def test_get_diagnoses_vet_not_assigned_forbidden(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = dict(BASE_PET)
        other_vet = {"id": "vet-99", "role": UserRole.VETERINARIAN, "full_name": "Dr. X"}
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.list_diagnoses("pet-1", current_user=other_vet)
        self.assertEqual(ctx.exception.status_code, 403)

    # GET /api/pets/{pet_id}/diagnoses — client cannot read another client's pet
    def test_get_diagnoses_client_wrong_owner_not_found(self):
        db = _db_with_pet_and_appointment()
        other_client = {"id": "client-99", "role": UserRole.CLIENT}
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.list_diagnoses("pet-1", current_user=other_client)
        self.assertEqual(ctx.exception.status_code, 404)

    # POST /api/pets/{pet_id}/diagnoses — vet creates diagnosis success
    def test_create_diagnosis_vet_success(self):
        db = _db_with_pet_and_appointment()
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.create_diagnosis(
                "pet-1",
                DIAGNOSIS_CREATE_PAYLOAD,
                current_user=VET_USER,
            )
        self.assertEqual(result.diagnosis, "Dermatitis alérgica")
        self.assertEqual(result.registered_by, "veterinarian")
        self.assertEqual(result.veterinarian_id, "vet-1")
        self.assertEqual(result.veterinarian_name, "Dr. Smith")

        stored = db.collection(Collections.DIAGNOSES).data
        self.assertEqual(len(stored), 1)

    # POST /api/pets/{pet_id}/diagnoses — validation error when mandatory diagnosis field is empty
    def test_create_diagnosis_validation_error(self):
        with self.assertRaises(ValidationError):
            schemas.DiagnosisCreate(diagnosis="")

    # GET /api/pets/{pet_id}/diagnoses/{diagnosis_id} — get specific diagnosis
    def test_get_specific_diagnosis_success(self):
        db = _db_with_pet_and_appointment()
        db.collection(Collections.DIAGNOSES).data["diag-1"] = {
            "pet_id": "pet-1",
            "diagnosis": "Otitis externa",
            "status": "Confirmado",
            "registered_by": "veterinarian",
            "created_at": "2026-07-10T12:00:00+00:00",
            "updated_at": "2026-07-10T12:00:00+00:00",
        }
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.get_diagnosis("pet-1", "diag-1", current_user=CLIENT_USER)
        self.assertEqual(result.diagnosis, "Otitis externa")

    # GET /api/pets/{pet_id}/diagnoses/{diagnosis_id} — non-existent diagnosis
    def test_get_specific_diagnosis_not_found(self):
        db = _db_with_pet_and_appointment()
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.get_diagnosis("pet-1", "non-existent", current_user=CLIENT_USER)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
