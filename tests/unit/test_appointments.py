import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import schemas
from app.constant import Collections, UserRole
from app.routes import appointment_routes


class FakeSnapshot:
    def __init__(self, document_id, data=None):
        self.id = document_id
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class FakeDocument:
    def __init__(self, collection, document_id):
        self.collection = collection
        self.id = document_id

    def get(self):
        return FakeSnapshot(self.id, self.collection.data.get(self.id))

    def update(self, data):
        self.collection.data[self.id].update(data)


class FakeCollection:
    def __init__(self):
        self.data = {}

    def document(self, document_id):
        return FakeDocument(self, document_id)


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, FakeCollection())


def appointment_document():
    return {
        "pet_id": "pet-1",
        "pet_name": "Lola",
        "pet_species": "Bird",
        "pet_sex": "Female",
        "pet_birth_date": "2024-07-13",
        "pet_weight_kg": 0.085,
        "pet_breed": "Ninfa",
        "pet_photo_url": "https://example.com/lola.png",
        "owner_id": "client-1",
        "owner_name": "Abby Ramirez",
        "last_visit": "--",
        "appointment_date": "2026-07-16",
        "appointment_time": "09:00",
        "duration_blocks": 1,
        "reason": "Pulido de pico y revision general",
        "veterinarian_id": "vet-1",
        "veterinarian_name": "Maria Sanchez",
        "status": schemas.AppointmentStatus.SCHEDULED,
        "created_at": "2026-07-16T08:00:00+00:00",
    }


class AppointmentTests(unittest.TestCase):
    def test_veterinarian_completes_appointment_with_observation(self):
        db = FakeFirestore()
        db.collection(Collections.APPOINTMENTS).data["appointment-1"] = appointment_document()

        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            response = appointment_routes.complete_appointment(
                "appointment-1",
                schemas.AppointmentComplete(
                    clinical_observation=(
                        "Se realizo el pulido de pico anual del ave, "
                        "se observa en buenas condiciones."
                    ),
                ),
                current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
            )

        stored = db.collection(Collections.APPOINTMENTS).data["appointment-1"]
        self.assertEqual(response.status, schemas.AppointmentStatus.COMPLETED)
        self.assertEqual(stored["status"], schemas.AppointmentStatus.COMPLETED)
        self.assertEqual(
            stored["clinical_observation"],
            "Se realizo el pulido de pico anual del ave, se observa en buenas condiciones.",
        )
        self.assertIn("completed_at", stored)
        self.assertIn("updated_at", stored)

    def test_veterinarian_cannot_complete_another_vets_appointment(self):
        db = FakeFirestore()
        db.collection(Collections.APPOINTMENTS).data["appointment-1"] = appointment_document()

        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as context:
                appointment_routes.complete_appointment(
                    "appointment-1",
                    schemas.AppointmentComplete(clinical_observation="Observation"),
                    current_user={"id": "vet-2", "role": UserRole.VETERINARIAN},
                )

        self.assertEqual(context.exception.status_code, 404)

    def test_completed_appointment_cannot_be_completed_again(self):
        db = FakeFirestore()
        completed = {
            **appointment_document(),
            "status": schemas.AppointmentStatus.COMPLETED,
            "completed_at": "2026-07-16T09:30:00+00:00",
        }
        db.collection(Collections.APPOINTMENTS).data["appointment-1"] = completed

        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as context:
                appointment_routes.complete_appointment(
                    "appointment-1",
                    schemas.AppointmentComplete(clinical_observation="Observation"),
                    current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
                )

        self.assertEqual(context.exception.status_code, 409)

