import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app import schemas
from app.constant import Collections, UserRole
from app.api.v1.endpoints.pet_routes import (
    create_pet,
    list_pets,
    upload_pet_photo,
)


# ─── Fake Firestore Infrastructure ────────────────────────────────

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


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, FakeCollection())


class FakeUploadFile:
    def __init__(self, content, content_type="image/png"):
        self.content = content
        self.content_type = content_type

    async def read(self, size=-1):
        return self.content[:size] if size and size > 0 else self.content


class FakeBlob:
    def __init__(self, name):
        self.name = name
        self.metadata = {}
        self.content = None
        self.content_type = None

    def upload_from_string(self, content, content_type=None):
        self.content = content
        self.content_type = content_type


class FakeBucket:
    name = "animalhealth-fe1e8.firebasestorage.app"

    def __init__(self):
        self.blobs = {}

    def blob(self, name):
        blob = FakeBlob(name)
        self.blobs[name] = blob
        return blob


def pet_payload():
    return schemas.PetCreate(
        name="Luna",
        birth_date="2024-01-01",
        species="Dog",
        sex="Female",
        breed_primary="Mixed",
        weight_kg=8.5,
        owner_id="client-1",
        owner_name="Client Test",
    )


# ─── Tests ────────────────────────────────────────────────────────

class PetProfileTests(unittest.TestCase):
    def test_pet_validation_rejects_unsupported_species_and_weight(self):
        with self.assertRaises(ValidationError):
            schemas.PetCreate(
                name="Luna",
                birth_date="2024-01-01",
                species="Snake",
                sex="Female",
                breed_primary="Mixed",
                weight_kg=8,
            )
        with self.assertRaises(ValidationError):
            schemas.PetCreate(
                name="Luna",
                birth_date="2024-01-01",
                species="Dog",
                sex="Female",
                breed_primary="Mixed",
                weight_kg=0,
            )

    def test_create_pet_assigns_authenticated_owner(self):
        db = FakeFirestore()

        with patch('app.api.v1.endpoints.pet_routes.get_firestore_db', return_value=db):
            response = create_pet(
                pet_payload(),
                current_user={"id": "client-1", "role": UserRole.CLIENT},
            )
        stored = db.collection(Collections.PETS).data[response.id]
        self.assertEqual(stored["owner_id"], "client-1")

    def test_clients_only_list_their_own_pets(self):
        db = FakeFirestore()
        pets = db.collection(Collections.PETS)
        base = {
            **pet_payload().model_dump(),
            "birth_date": "2024-01-01",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        pets.data["pet-1"] = {**base, "owner_id": "client-1"}
        pets.data["pet-2"] = {**base, "owner_id": "client-2"}

        with patch('app.api.v1.endpoints.pet_routes.get_firestore_db', return_value=db):
            response = list_pets(
                current_user={"id": "client-1", "role": UserRole.CLIENT},
            )
        self.assertEqual([pet.id for pet in response], ["pet-1"])

    def test_upload_pet_photo_rejects_unsupported_type(self):
        with self.assertRaises(HTTPException) as context:
            import asyncio

            asyncio.run(
                upload_pet_photo(
                    "pet-1",
                    FakeUploadFile(b"image", content_type="image/gif"),
                    current_user={"id": "client-1", "role": UserRole.CLIENT},
                )
            )
        self.assertEqual(context.exception.status_code, 415)

    def test_upload_pet_photo_updates_pet_photo_url(self):
        import asyncio

        db = FakeFirestore()
        pet_data = {
            **pet_payload().model_dump(),
            "birth_date": "2024-01-01",
            "owner_id": "client-1",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        db.collection(Collections.PETS).data["pet-1"] = pet_data
        bucket = FakeBucket()

        with (
            patch('app.api.v1.endpoints.pet_routes.get_firestore_db', return_value=db),
            patch('app.api.v1.endpoints.pet_routes.get_storage_bucket', return_value=bucket),
        ):
            response = asyncio.run(
                upload_pet_photo(
                    "pet-1",
                    FakeUploadFile(b"image-bytes", content_type="image/png"),
                    current_user={"id": "client-1", "role": UserRole.CLIENT},
                )
            )

        self.assertIn("firebasestorage.googleapis.com", response.photo_url)
        self.assertEqual(
            db.collection(Collections.PETS).data["pet-1"]["photo_url"],
            response.photo_url,
        )


if __name__ == "__main__":
    unittest.main()