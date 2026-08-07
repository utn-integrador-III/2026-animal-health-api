"""Unit tests for walk-in consultations and diagnoses."""

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import schemas
from app.auth import email_document_id, verify_password
from app.constant import Collections, UserRole
from app.routes import consultation_routes, pet_routes
from tests.unit.test_vaccines import FakeFirestore, VET_USER, CLIENT_USER


class WalkInConsultationTests(unittest.TestCase):
    def _db_with_existing_client_pet(self):
        db = FakeFirestore()
        db.collection(Collections.USERS).data["client-1"] = {
            "email": "abby@example.com",
            "full_name": "Abby Ramirez",
            "phone": "8875-4545",
            "role": UserRole.CLIENT,
            "is_active": True,
            "created_at": "2026-07-01T00:00:00+00:00",
        }
        db.collection(Collections.PETS).data["pet-1"] = {
            "name": "Lola",
            "birth_date": "2024-07-13",
            "species": "Bird",
            "sex": "Female",
            "breed_primary": "Ninfa",
            "breed_secondary": None,
            "mixed_breed": False,
            "weight_kg": 0.085,
            "owner_id": "client-1",
            "created_at": "2026-07-01T00:00:00+00:00",
        }
        return db

    def test_vet_finds_existing_client_and_pets_by_email(self):
        db = FakeFirestore()
        client_id = email_document_id("abby@example.com")
        db.collection(Collections.USERS).data[client_id] = {
            "email": "abby@example.com",
            "full_name": "Abby Ramirez",
            "phone": "8875-4545",
            "role": UserRole.CLIENT,
            "is_active": True,
            "created_at": "2026-07-01T00:00:00+00:00",
        }
        db.collection(Collections.PETS).data["pet-1"] = {
            "name": "Lola",
            "birth_date": "2024-07-13",
            "species": "Bird",
            "sex": "Female",
            "breed_primary": "Ninfa",
            "weight_kg": 0.085,
            "owner_id": client_id,
            "created_at": "2026-07-01T00:00:00+00:00",
        }

        with patch.object(consultation_routes, "get_firestore_db", return_value=db):
            result = consultation_routes.find_client_by_email(
                email="abby@example.com",
                current_user=VET_USER,
            )

        self.assertEqual(result.client.id, client_id)
        self.assertEqual(len(result.pets), 1)
        self.assertEqual(result.pets[0].name, "Lola")

    def test_vet_creates_walk_in_for_existing_client_and_pet(self):
        db = self._db_with_existing_client_pet()
        payload = schemas.WalkInConsultationCreate(
            client_id="client-1",
            client_name="Abby Ramirez",
            client_email="abby@example.com",
            client_phone="8875-4545",
            pet_id="pet-1",
            reason="Consulta presencial por caida de plumas",
        )

        with patch.object(consultation_routes, "get_firestore_db", return_value=db), patch.object(
            consultation_routes, "send_temporary_password_email"
        ) as send_email:
            result = consultation_routes.create_walk_in_consultation(
                payload,
                current_user=VET_USER,
            )

        self.assertEqual(result.client_id, "client-1")
        self.assertEqual(result.pet_id, "pet-1")
        self.assertEqual(result.source, "walk_in")
        self.assertTrue(result.appointment_id)
        send_email.assert_not_called()
        self.assertEqual(len(db.collection(Collections.CONSULTATIONS).data), 1)
        self.assertEqual(len(db.collection(Collections.APPOINTMENTS).data), 1)

    def test_vet_creates_walk_in_for_new_client_and_new_pet(self):
        db = FakeFirestore()
        payload = schemas.WalkInConsultationCreate(
            client_name="Samuel Romero",
            client_email="samuel@example.com",
            client_phone="4781-3694",
            pet_name="Milo",
            pet_birth_date="2024-03-01",
            pet_species="Dog",
            pet_sex="Male",
            pet_breed="Mixed",
            pet_breed_primary="Mixed",
            pet_breed_secondary="Labrador",
            pet_mixed_breed=True,
            pet_weight_kg=12.5,
            reason="Consulta externa por irritacion",
        )

        with patch.object(consultation_routes, "get_firestore_db", return_value=db), patch.object(
            consultation_routes, "_temporary_password", return_value="TempPass2026!"
        ), patch.object(consultation_routes, "send_temporary_password_email") as send_email:
            result = consultation_routes.create_walk_in_consultation(
                payload,
                current_user=VET_USER,
            )

        client_id = email_document_id("samuel@example.com")
        self.assertIn(client_id, db.collection(Collections.USERS).data)
        self.assertEqual(db.collection(Collections.USERS).data[client_id]["must_set_password"], True)
        self.assertTrue(verify_password(
            "TempPass2026!",
            db.collection(Collections.USERS).data[client_id]["hashed_password"],
        ))
        self.assertEqual(result.owner_name, "Samuel Romero")
        self.assertEqual(result.pet_name, "Milo")
        self.assertEqual(len(db.collection(Collections.PETS).data), 1)
        pet = next(iter(db.collection(Collections.PETS).data.values()))
        self.assertEqual(pet["breed_secondary"], "Labrador")
        self.assertTrue(pet["mixed_breed"])
        self.assertIn(result.appointment_id, db.collection(Collections.APPOINTMENTS).data)
        send_email.assert_called_once_with(
            recipient_email="samuel@example.com",
            recipient_name="Samuel Romero",
            temporary_password="TempPass2026!",
        )

    def test_walk_in_rejects_a_client_id_from_another_email(self):
        db = self._db_with_existing_client_pet()
        payload = schemas.WalkInConsultationCreate(
            client_id="client-1",
            client_name="Carmen Fonseca",
            client_email="carmen@example.com",
            pet_name="Bonny",
            pet_birth_date="2024-06-06",
            pet_species="Rabbit",
            pet_sex="Female",
            pet_breed="Gigante de Flandes",
            pet_weight_kg=10,
            reason="No come y pasa dormida",
        )

        with patch.object(consultation_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as context:
                consultation_routes.create_walk_in_consultation(payload, current_user=VET_USER)

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(db.collection(Collections.USERS).data["client-1"]["email"], "abby@example.com")
        self.assertEqual(len(db.collection(Collections.PETS).data), 1)
        self.assertEqual(len(db.collection(Collections.CONSULTATIONS).data), 0)

    def test_vet_saves_diagnosis_and_client_sees_it_in_medical_history(self):
        db = self._db_with_existing_client_pet()
        db.collection(Collections.CONSULTATIONS).data["consultation-1"] = {
            "client_id": "client-1",
            "owner_name": "Abby Ramirez",
            "owner_email": "abby@example.com",
            "pet_id": "pet-1",
            "pet_name": "Lola",
            "pet_species": "Bird",
            "pet_sex": "Female",
            "pet_breed": "Ninfa",
            "pet_weight_kg": 0.085,
            "reason": "Pulido de pico",
            "veterinarian_id": "vet-1",
            "veterinarian_name": "Dr. Smith",
            "status": "open",
            "source": "walk_in",
            "created_at": "2026-07-27T10:00:00+00:00",
        }
        db.collection(Collections.APPOINTMENTS).data["appt-1"] = {
            "pet_id": "pet-1",
            "veterinarian_id": "vet-1",
            "status": schemas.AppointmentStatus.SCHEDULED,
        }
        payload = schemas.DiagnosisCreate(
            consultation_id="consultation-1",
            pet_id="pet-1",
            diagnosis="Desgaste de pico",
            clinical_notes="Se realiza pulido y se observa estable.",
        )

        with patch.object(consultation_routes, "get_firestore_db", return_value=db):
            result = consultation_routes.create_diagnosis(
                "consultation-1",
                payload,
                current_user=VET_USER,
            )

        self.assertEqual(result.diagnosis, "Desgaste de pico")
        self.assertEqual(len(db.collection(Collections.DIAGNOSES).data), 1)
        self.assertEqual(len(db.collection(Collections.MEDICAL_RECORDS).data), 1)

        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            history = pet_routes.list_clinical_records("pet-1", current_user=CLIENT_USER)

        self.assertEqual(history[0].diagnosis, "Desgaste de pico")
        self.assertEqual(history[0].notes, "Se realiza pulido y se observa estable.")

    def test_diagnosis_rejects_wrong_pet_for_consultation(self):
        db = self._db_with_existing_client_pet()
        db.collection(Collections.CONSULTATIONS).data["consultation-1"] = {
            "pet_id": "pet-1",
            "veterinarian_id": "vet-1",
        }
        payload = schemas.DiagnosisCreate(
            consultation_id="consultation-1",
            pet_id="pet-2",
            diagnosis="Otitis",
            clinical_notes="Notas clinicas",
        )

        with patch.object(consultation_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as context:
                consultation_routes.create_diagnosis(
                    "consultation-1",
                    payload,
                    current_user=VET_USER,
                )

        self.assertEqual(context.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()

