"""Unit tests for the vaccine endpoints in pet_routes.py."""

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import schemas
from app.constant import Collections, UserRole
from app.routes import pet_routes


# ─── Fake Firestore Infrastructure (reused from test_pets.py) ────────────────

class FakeSnapshot:
    def __init__(self, document_id, data=None):
        self.id = document_id
        self._data = data
        self.reference = None

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
        snapshot = FakeSnapshot(self.id, self.collection.data.get(self.id))
        snapshot.reference = self
        return snapshot

    def create(self, data):
        if self.id in self.collection.data:
            raise RuntimeError("Document already exists")
        self.collection.data[self.id] = dict(data)

    def update(self, data):
        self.collection.data[self.id].update(data)

    def delete(self):
        self.collection.data.pop(self.id, None)


class FakeQuery:
    def __init__(self, collection, filters=None):
        self.collection = collection
        self.filters = filters or []
        self.limit_count = None

    def where(self, field, operator, value):
        return FakeQuery(self.collection, self.filters + [(field, value)])

    def limit(self, count):
        q = FakeQuery(self.collection, self.filters)
        q.limit_count = count
        return q

    def get(self):
        matches = []
        for document_id, data in self.collection.data.items():
            if all(data.get(f) == v for f, v in self.filters):
                matches.append(FakeSnapshot(document_id, data))
        return matches[: self.limit_count] if self.limit_count else matches


class FakeCollection:
    def __init__(self):
        self.data = {}
        self.next_id = 1

    def document(self, document_id=None):
        if document_id is None:
            document_id = f"generated-{self.next_id}"
            self.next_id += 1
        return FakeDocument(self, document_id)

    def where(self, field, operator, value):
        return FakeQuery(self, [(field, value)])

    def add(self, data):
        document = self.document()
        document.create(data)
        return None, document


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, FakeCollection())


# ─── Helpers ─────────────────────────────────────────────────────────────────

BASE_PET = {
    "name": "Luna",
    "birth_date": "2024-01-01",
    "species": "Dog",
    "sex": "Female",
    "breed_primary": "Mixed",
    "weight_kg": 8.5,
    "owner_id": "client-1",
    "created_at": "2026-01-01T00:00:00+00:00",
}

BASE_APPOINTMENT = {
    "pet_id": "pet-1",
    "veterinarian_id": "vet-1",
    "status": "scheduled",
}

VACCINE_CREATE_PAYLOAD = schemas.VaccineCreate(
    name="Parvovirus",
    type="Parvovirosis Canina",
    brand="Nobivac",
    batch_number="LOTE-2309X",
    scheduled_date="2026-07-15",
    administration_route="Subcutánea",
    dose="1",
    unit="ml",
    raw_status="Aplicada correctamente",
    notes="Sin reacciones adversas",
)

VET_USER = {"id": "vet-1", "role": UserRole.VETERINARIAN, "full_name": "Dr. Smith"}
CLIENT_USER = {"id": "client-1", "role": UserRole.CLIENT}


def _db_with_pet_and_appointment():
    """Returns a FakeFirestore with pet-1 and a vet-1 appointment."""
    db = FakeFirestore()
    db.collection(Collections.PETS).data["pet-1"] = dict(BASE_PET)
    db.collection(Collections.APPOINTMENTS).data["appt-1"] = dict(BASE_APPOINTMENT)
    return db


# ─── Test Cases ───────────────────────────────────────────────────────────────

class VaccineEndpointTests(unittest.TestCase):

    # GET /api/pets/{pet_id}/vaccines — client reads their own pet
    def test_get_vaccines_client_success(self):
        db = _db_with_pet_and_appointment()
        db.collection(Collections.VACCINES).data["vac-1"] = {
            "pet_id": "pet-1",
            "name": "Rabia",
            "type": "Rabia",
            "brand": "Merial",
            "batch_number": None,
            "scheduled_date": "2026-07-10",
            "expiration_date": None,
            "next_dose": None,
            "administration_route": "Subcutánea",
            "dose": "1",
            "unit": "dosis",
            "raw_status": "Aplicada correctamente",
            "status": "completed",
            "notes": None,
            "veterinarian_id": "vet-1",
            "veterinarian_name": "Dr. Smith",
            "created_at": "2026-07-10T12:00:00+00:00",
        }
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.list_vaccines("pet-1", current_user=CLIENT_USER)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Rabia")
        self.assertEqual(result[0].status, "completed")

    # GET /api/pets/{pet_id}/vaccines — vet reads assigned pet
    def test_get_vaccines_vet_success(self):
        db = _db_with_pet_and_appointment()
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.list_vaccines("pet-1", current_user=VET_USER)
        self.assertEqual(result, [])  # no vaccines yet, but no error

    # GET /api/pets/{pet_id}/vaccines — vet with no assignment is forbidden
    def test_get_vaccines_vet_not_assigned_forbidden(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = dict(BASE_PET)
        # No appointments → vet-1 not assigned
        other_vet = {"id": "vet-99", "role": UserRole.VETERINARIAN, "full_name": "Dr. X"}
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.list_vaccines("pet-1", current_user=other_vet)
        self.assertEqual(ctx.exception.status_code, 403)

    # GET /api/pets/{pet_id}/vaccines — client cannot read another client's pet
    def test_get_vaccines_client_wrong_owner_not_found(self):
        db = _db_with_pet_and_appointment()
        other_client = {"id": "client-99", "role": UserRole.CLIENT}
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.list_vaccines("pet-1", current_user=other_client)
        self.assertEqual(ctx.exception.status_code, 404)

    # POST /api/pets/{pet_id}/vaccines — vet successfully saves a vaccine
    def test_create_vaccine_vet_success(self):
        db = _db_with_pet_and_appointment()
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.create_vaccine(
                "pet-1",
                VACCINE_CREATE_PAYLOAD,
                current_user=VET_USER,
            )
        self.assertEqual(result.name, "Parvovirus")
        self.assertEqual(result.pet_id, "pet-1")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.veterinarian_id, "vet-1")
        # Verify it was persisted in Firestore
        vaccines_in_db = db.collection(Collections.VACCINES).data
        self.assertEqual(len(vaccines_in_db), 1)
        stored = list(vaccines_in_db.values())[0]
        self.assertEqual(stored["name"], "Parvovirus")
        self.assertEqual(stored["brand"], "Nobivac")
        self.assertEqual(stored["batch_number"], "LOTE-2309X")

    # POST /api/pets/{pet_id}/vaccines — vet not assigned is forbidden
    def test_create_vaccine_vet_not_assigned_forbidden(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = dict(BASE_PET)
        other_vet = {"id": "vet-99", "role": UserRole.VETERINARIAN, "full_name": "Dr. X"}
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.create_vaccine(
                    "pet-1",
                    VACCINE_CREATE_PAYLOAD,
                    current_user=other_vet,
                )
        self.assertEqual(ctx.exception.status_code, 403)

    # POST — raw_status other than completed maps to "upcoming"
    def test_create_vaccine_status_mapping_upcoming(self):
        db = _db_with_pet_and_appointment()
        pending_payload = schemas.VaccineCreate(
            name="Moquillo",
            type="Distémper Canino",
            brand="Zoetis",
            scheduled_date="2026-07-15",
            raw_status="Refuerzo pendiente",
        )
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            result = pet_routes.create_vaccine(
                "pet-1", pending_payload, current_user=VET_USER
            )
        self.assertEqual(result.status, "upcoming")

    # VaccineCreate schema validation — future date is accepted (for upcoming/booster scheduling)
    def test_vaccine_create_schema_accepts_future_date(self):
        v = schemas.VaccineCreate(
            name="Rabia",
            type="Rabia",
            brand="Merial",
            scheduled_date="2099-01-01",
        )
        self.assertEqual(v.scheduled_date.isoformat(), "2099-01-01")


if __name__ == "__main__":
    unittest.main()
