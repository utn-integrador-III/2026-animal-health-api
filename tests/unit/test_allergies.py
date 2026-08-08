"""Unit tests for the allergy endpoints in pet_routes.py."""

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


ALLERGY_CREATE_PAYLOAD = schemas.AllergyCreate(
    allergen="Pollen",
    category="Environmental",
    severity="Moderate",
    reaction="Sneezing and itchy eyes",
    notes="Worse during spring",
)


class AllergyEndpointTests(unittest.TestCase):

    # GET /api/pets/{pet_id}/allergies — client reads their own pet
    def test_get_allergies_client_success(self):
        db = _db_with_pet_and_appointment()
        db.collection(Collections.ALLERGIES).data["all-1"] = {
            "pet_id": "pet-1",
            "allergen": "Chicken",
            "category": "Food",
            "severity": "Mild",
            "reaction": "Itchy skin",
            "notes": "Avoid chicken kibble",
            "registered_by": "client",
            "created_at": "2026-07-10T12:00:00+00:00",
            "updated_at": "2026-07-10T12:00:00+00:00",
        }
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.list_allergies("pet-1", current_user=CLIENT_USER)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].allergen, "Chicken")
        self.assertEqual(result[0].registered_by, "client")

    # GET /api/pets/{pet_id}/allergies — vet reads assigned pet
    def test_get_allergies_vet_success(self):
        db = _db_with_pet_and_appointment()
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.list_allergies("pet-1", current_user=VET_USER)
        self.assertEqual(result, [])  # empty but no error

    # GET /api/pets/{pet_id}/allergies — vet not assigned is forbidden
    def test_get_allergies_vet_not_assigned_forbidden(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = dict(BASE_PET)
        other_vet = {"id": "vet-99", "role": UserRole.VETERINARIAN, "full_name": "Dr. X"}
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.list_allergies("pet-1", current_user=other_vet)
        self.assertEqual(ctx.exception.status_code, 403)

    # GET /api/pets/{pet_id}/allergies — client cannot read another client's pet
    def test_get_allergies_client_wrong_owner_not_found(self):
        db = _db_with_pet_and_appointment()
        other_client = {"id": "client-99", "role": UserRole.CLIENT}
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.list_allergies("pet-1", current_user=other_client)
        self.assertEqual(ctx.exception.status_code, 404)

    # POST /api/pets/{pet_id}/allergies — client registers an allergy
    def test_create_allergy_client_success(self):
        db = _db_with_pet_and_appointment()
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.create_allergy(
                "pet-1",
                ALLERGY_CREATE_PAYLOAD,
                current_user=CLIENT_USER,
            )
        self.assertEqual(result.allergen, "Pollen")
        self.assertEqual(result.registered_by, "client")
        self.assertIsNone(result.veterinarian_id)

        stored = db.collection(Collections.ALLERGIES).data
        self.assertEqual(len(stored), 1)

    # POST /api/pets/{pet_id}/allergies — vet registers an allergy
    def test_create_allergy_vet_success(self):
        db = _db_with_pet_and_appointment()
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.create_allergy(
                "pet-1",
                ALLERGY_CREATE_PAYLOAD,
                current_user=VET_USER,
            )
        self.assertEqual(result.allergen, "Pollen")
        self.assertEqual(result.registered_by, "veterinarian")
        self.assertEqual(result.veterinarian_id, "vet-1")
        self.assertEqual(result.veterinarian_name, "Dr. Smith")

    # POST /api/pets/{pet_id}/allergies — validation error on empty fields
    def test_create_allergy_invalid_data(self):
        with self.assertRaises(ValidationError):
            schemas.AllergyCreate(
                allergen="",  # min_length=1
                category="Food",
                severity="Mild",
            )

    # GET /api/pets/{pet_id}/allergies/{allergy_id} — get specific allergy
    def test_get_specific_allergy_success(self):
        db = _db_with_pet_and_appointment()
        db.collection(Collections.ALLERGIES).data["all-1"] = {
            "pet_id": "pet-1",
            "allergen": "Chicken",
            "category": "Food",
            "severity": "Mild",
            "registered_by": "client",
            "created_at": "2026-07-10T12:00:00+00:00",
            "updated_at": "2026-07-10T12:00:00+00:00",
        }
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.get_allergy("pet-1", "all-1", current_user=CLIENT_USER)
        self.assertEqual(result.allergen, "Chicken")

    # GET /api/pets/{pet_id}/allergies/{allergy_id} — non-existent allergy
    def test_get_specific_allergy_not_found(self):
        db = _db_with_pet_and_appointment()
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.get_allergy("pet-1", "non-existent", current_user=CLIENT_USER)
        self.assertEqual(ctx.exception.status_code, 404)

    # PUT /api/pets/{pet_id}/allergies/{allergy_id} — update allergy by vet
    def test_update_allergy_vet_success(self):
        db = _db_with_pet_and_appointment()
        db.collection(Collections.ALLERGIES).data["all-1"] = {
            "pet_id": "pet-1",
            "allergen": "Pollen",
            "category": "Environmental",
            "severity": "Mild",
            "registered_by": "client",
            "created_at": "2026-07-10T12:00:00+00:00",
            "updated_at": "2026-07-10T12:00:00+00:00",
        }
        update_payload = schemas.AllergyUpdate(
            severity="Severe",
            reaction="Anaphylactic shock",
        )
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.update_allergy(
                "pet-1",
                "all-1",
                update_payload,
                current_user=VET_USER,
            )
        self.assertEqual(result.severity, "Severe")
        self.assertEqual(result.reaction, "Anaphylactic shock")
        self.assertEqual(result.allergen, "Pollen")  # unchanged
        self.assertEqual(result.veterinarian_name, "Dr. Smith")

    # PUT /api/pets/{pet_id}/allergies/{allergy_id} — non-existent allergy
    def test_update_allergy_not_found(self):
        db = _db_with_pet_and_appointment()
        update_payload = schemas.AllergyUpdate(severity="Severe")
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.update_allergy(
                    "pet-1",
                    "non-existent",
                    update_payload,
                    current_user=VET_USER,
                )
        self.assertEqual(ctx.exception.status_code, 404)

    # DELETE /api/pets/{pet_id}/allergies/{allergy_id} — delete allergy by vet
    def test_delete_allergy_vet_success(self):
        db = _db_with_pet_and_appointment()
        db.collection(Collections.ALLERGIES).data["all-1"] = {
            "pet_id": "pet-1",
            "allergen": "Pollen",
            "category": "Environmental",
            "severity": "Mild",
            "registered_by": "client",
        }
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.delete_allergy("pet-1", "all-1", current_user=VET_USER)
        self.assertIsNone(result)
        stored = db.collection(Collections.ALLERGIES).data
        self.assertNotIn("all-1", stored)

    # DELETE /api/pets/{pet_id}/allergies/{allergy_id} — non-existent allergy
    def test_delete_allergy_not_found(self):
        db = _db_with_pet_and_appointment()
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.delete_allergy("pet-1", "non-existent", current_user=VET_USER)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
