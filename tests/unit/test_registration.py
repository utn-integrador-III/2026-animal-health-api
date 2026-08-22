import unittest
from unittest.mock import patch, MagicMock

from fastapi import HTTPException
from google.api_core.exceptions import AlreadyExists

from app import schemas
from app.auth import hash_password, verify_password
from app.constant import Collections, UserRole
from app.routes import auth_routes
from app.services.registration_service import register_client_with_pet


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
            raise AlreadyExists("Document already exists")
        self.collection.data[self.id] = dict(data)

    def update(self, data):
        if self.id in self.collection.data:
            self.collection.data[self.id].update(data)

    def delete(self):
        self.collection.data.pop(self.id, None)


class FakeQuery:
    def __init__(self, collection, field, value):
        self.collection = collection
        self.field = field
        self.value = value
        self.limit_count = None

    def limit(self, count):
        self.limit_count = count
        return self

    def get(self):
        matches = [
            FakeSnapshot(document_id, data)
            for document_id, data in self.collection.data.items()
            if data.get(self.field) == self.value
        ]
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
        return FakeQuery(self, field, value)

    def add(self, data):
        document = self.document()
        document.create(data)
        return None, document


class FakeBatch:
    def __init__(self):
        self.operations = []

    def create(self, reference, data):
        self.operations.append((reference, dict(data)))

    def commit(self):
        for reference, data in self.operations:
            reference.create(data)


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, FakeCollection())

    def batch(self):
        return FakeBatch()


def pet_payload():
    return schemas.PetCreate(
        name="Luna",
        birth_date="2024-01-01",
        species="Dog",
        sex="Female",
        breed_primary="Poodle",
        breed_secondary="Golden Retriever",
        mixed_breed=True,
        weight_kg=8.5,
    )


def registration_payload(email="owner@example.com"):
    return schemas.UserRegister(
        email=email,
        password="password123",
        full_name="Test Owner",
        phone="8888-8888",
        initial_pet=pet_payload(),
    )


class RegistrationTests(unittest.TestCase):
    def test_password_is_hashed_and_verifiable(self):
        password_hash = hash_password("password123")
        self.assertTrue(verify_password("password123", password_hash))
        self.assertFalse(verify_password("incorrect", password_hash))

    def test_registration_links_first_pet_to_owner(self):
        db = FakeFirestore()
        user_id, pet_id, _ = register_client_with_pet(db, registration_payload())

        user = db.collection(Collections.USERS).data[user_id]
        pet = db.collection(Collections.PETS).data[pet_id]
        self.assertEqual(user["role"], UserRole.CLIENT)
        self.assertEqual(pet["owner_id"], user_id)
        self.assertEqual(pet["breed_secondary"], "Golden Retriever")
        self.assertTrue(pet["mixed_breed"])

    def test_registration_rejects_duplicate_email_query(self):
        db = FakeFirestore()
        db.collection(Collections.USERS).data["existing-user"] = {
            "email": "owner@example.com",
        }
        with self.assertRaises(HTTPException) as ctx:
            register_client_with_pet(db, registration_payload("owner@example.com"))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail, "Email address is already registered")

    def test_registration_handles_already_exists_on_commit(self):
        db = FakeFirestore()
        mock_batch = MagicMock()
        mock_batch.commit.side_effect = AlreadyExists("Conflict")

        with patch.object(db, "batch", return_value=mock_batch):
            with self.assertRaises(HTTPException) as ctx:
                register_client_with_pet(db, registration_payload())
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail, "Email address is already registered")

    def test_login_rejects_invalid_password(self):
        db = FakeFirestore()
        db.collection(Collections.USERS).data["client-1"] = {
            "email": "owner@example.com",
            "hashed_password": hash_password("password123"),
            "full_name": "Test Owner",
            "phone": "8888-8888",
            "role": UserRole.CLIENT,
            "is_active": True,
        }
        with patch.object(auth_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as context:
                auth_routes.login(
                    schemas.UserLogin(
                        email="owner@example.com",
                        password="incorrect",
                    )
                )
        self.assertEqual(context.exception.status_code, 401)
