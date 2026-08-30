import asyncio
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch, MagicMock

from fastapi import HTTPException
from pydantic import ValidationError

from app import schemas
from app.constant import Collections, UserRole
from app.routes import pet_routes


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
        if self.id in self.collection.data:
            self.collection.data[self.id].update(data)

    def delete(self):
        self.collection.data.pop(self.id, None)


class FakeQuery:
    def __init__(self, collection, filters=None):
        self.collection = collection
        self.filters = filters or []
        self.limit_count = None

    def where(self, field, op_or_val, val=None):
        target_val = val if val is not None else op_or_val
        new_filters = self.filters + [(field, target_val)]
        return FakeQuery(self.collection, new_filters)

    def limit(self, count):
        self.limit_count = count
        return self

    def get(self):
        matches = []
        for doc_id, data in self.collection.data.items():
            match = True
            for field, target_val in self.filters:
                if data.get(field) != target_val:
                    match = False
                    break
            if match:
                snap = FakeSnapshot(doc_id, data)
                snap.reference = FakeDocument(self.collection, doc_id)
                matches.append(snap)
        return matches[: self.limit_count] if self.limit_count else matches

    def stream(self):
        return self.get()


class FakeCollection:
    def __init__(self):
        self.data = {}
        self.next_id = 1

    def document(self, document_id=None):
        if document_id is None:
            document_id = f"generated-{self.next_id}"
            self.next_id += 1
        return FakeDocument(self, document_id)

    def where(self, field, op_or_val, val=None):
        return FakeQuery(self).where(field, op_or_val, val)

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
    )


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

        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            response = pet_routes.create_pet(
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
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            response = pet_routes.list_pets(
                current_user={"id": "client-1", "role": UserRole.CLIENT},
            )
        self.assertEqual([pet.id for pet in response], ["pet-1"])

    def test_get_pet_for_client_and_vet(self):
        db = FakeFirestore()
        pet_data = {
            **pet_payload().model_dump(),
            "birth_date": "2024-01-01",
            "owner_id": "client-1",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        db.collection(Collections.PETS).data["pet-1"] = pet_data

        # Client owner succeeds
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            res_client = pet_routes.get_pet("pet-1", current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(res_client.id, "pet-1")

        # Client non-owner fails 404
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.get_pet("pet-1", current_user={"id": "client-other", "role": UserRole.CLIENT})
            self.assertEqual(ctx.exception.status_code, 404)

        # Vet not assigned fails 403
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.get_pet("pet-1", current_user={"id": "vet-1", "role": UserRole.VETERINARIAN})
            self.assertEqual(ctx.exception.status_code, 403)

        # Vet assigned succeeds
        db.collection(Collections.APPOINTMENTS).data["app-1"] = {"pet_id": "pet-1", "veterinarian_id": "vet-1"}
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            res_vet = pet_routes.get_pet("pet-1", current_user={"id": "vet-1", "role": UserRole.VETERINARIAN})
            self.assertEqual(res_vet.id, "pet-1")

    def test_update_pet_and_delete_pet(self):
        db = FakeFirestore()
        pet_data = {
            **pet_payload().model_dump(),
            "birth_date": "2024-01-01",
            "owner_id": "client-1",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        db.collection(Collections.PETS).data["pet-1"] = pet_data

        update_payload = schemas.PetUpdate(name="Luna Updated", weight_kg=9.0, birth_date=date(2024, 2, 1))

        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            updated = pet_routes.update_pet("pet-1", update_payload, current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(updated.name, "Luna Updated")
            self.assertEqual(updated.weight_kg, 9.0)

        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            pet_routes.delete_pet("pet-1", current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertNotIn("pet-1", db.collection(Collections.PETS).data)

    def test_upload_pet_photo_errors(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {"owner_id": "client-1"}

        # Unsupported type (415)
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(pet_routes.upload_pet_photo("pet-1", FakeUploadFile(b"data", "image/gif"), current_user={"id": "client-1", "role": UserRole.CLIENT}))
        self.assertEqual(ctx.exception.status_code, 415)

        # Empty file (422)
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(pet_routes.upload_pet_photo("pet-1", FakeUploadFile(b"", "image/png"), current_user={"id": "client-1", "role": UserRole.CLIENT}))
        self.assertEqual(ctx.exception.status_code, 422)

        # Oversized file (413)
        large_content = b"x" * (5 * 1024 * 1024 + 1)
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(pet_routes.upload_pet_photo("pet-1", FakeUploadFile(large_content, "image/png"), current_user={"id": "client-1", "role": UserRole.CLIENT}))
        self.assertEqual(ctx.exception.status_code, 413)

        # Storage bucket error (503)
        with patch.object(pet_routes, "get_firestore_db", return_value=db), \
             patch.object(pet_routes, "get_storage_bucket", side_effect=RuntimeError("Bucket error")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(pet_routes.upload_pet_photo("pet-1", FakeUploadFile(b"valid image", "image/png"), current_user={"id": "client-1", "role": UserRole.CLIENT}))
            self.assertEqual(ctx.exception.status_code, 503)

    def test_upload_pet_photo_updates_pet_photo_url(self):
        db = FakeFirestore()
        pet_data = {
            **pet_payload().model_dump(),
            "birth_date": "2024-01-01",
            "owner_id": "client-1",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        db.collection(Collections.PETS).data["pet-1"] = pet_data
        bucket = FakeBucket()

        with patch.object(pet_routes, "get_firestore_db", return_value=db), \
             patch.object(pet_routes, "get_storage_bucket", return_value=bucket):
            response = asyncio.run(
                pet_routes.upload_pet_photo(
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

    def test_vaccines_endpoints(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {"owner_id": "client-1"}
        db.collection(Collections.APPOINTMENTS).data["app-1"] = {"pet_id": "pet-1", "veterinarian_id": "vet-1"}

        vaccine_create = schemas.VaccineCreate(
            name="Rabia",
            type="Virus",
            brand="Nobivac",
            batch_number="B123",
            scheduled_date=date(2026, 1, 1),
            expiration_date=date(2027, 1, 1),
            next_dose=date(2027, 1, 1),
            administration_route="Subcutánea",
            dose="1.0",
            unit="ml",
            raw_status="Aplicada correctamente",
            notes="Sin reacciones",
        )

        # Create vaccine by vet
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            created = pet_routes.create_vaccine("pet-1", vaccine_create, current_user={"id": "vet-1", "role": UserRole.VETERINARIAN, "full_name": "Dr. Smith"})
            self.assertEqual(created.name, "Rabia")
            self.assertEqual(created.status, "completed")

        # List vaccines by client owner
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            v_list = pet_routes.list_vaccines("pet-1", current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(len(v_list), 1)

    def test_clinical_records_endpoints(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {"owner_id": "client-1"}
        db.collection(Collections.APPOINTMENTS).data["app-1"] = {"pet_id": "pet-1", "veterinarian_id": "vet-1"}

        rec_create = schemas.ClinicalRecordCreate(
            diagnosis="Otitis",
            treatment="Gotas",
            weight_kg=8.5,
            notes="Revisión en 10 días",
            date=date(2026, 5, 1),
        )

        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            created = pet_routes.create_clinical_record("pet-1", rec_create, current_user={"id": "vet-1", "role": UserRole.VETERINARIAN})
            self.assertEqual(created.diagnosis, "Otitis")

        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            records = pet_routes.list_clinical_records("pet-1", current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(len(records), 1)

    def test_medications_endpoints(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {"owner_id": "client-1"}
        db.collection(Collections.APPOINTMENTS).data["app-1"] = {"pet_id": "pet-1", "veterinarian_id": "vet-1"}

        med_create = schemas.MedicationCreate(
            name="Amoxicilina",
            dosage="250mg",
            frequency="Cada 8h",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 10),
            administration_time="08:00",
            notes="Vía oral",
        )

        # Create medication
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            created = pet_routes.create_medication("pet-1", med_create, current_user={"id": "vet-1", "role": UserRole.VETERINARIAN})
            self.assertEqual(created.name, "Amoxicilina")

        med_id = created.id

        # List medications
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            meds = pet_routes.list_medications("pet-1", current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(len(meds), 1)

        # Toggle check
        db.collection(Collections.NOTIFICATIONS).data["notif-1"] = {
            "medication_id": med_id,
            "scheduled_date": "2026-01-05",
            "read": False,
        }
        toggle_payload = schemas.MedicationCheckToggle(date=date(2026, 1, 5))

        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            toggled = pet_routes.toggle_medication_check("pet-1", med_id, toggle_payload, current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertIn("2026-01-05", toggled.checked_dates)

            # Untoggle check
            untoggled = pet_routes.toggle_medication_check("pet-1", med_id, toggle_payload, current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertNotIn("2026-01-05", untoggled.checked_dates)

        # Delete medication
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            pet_routes.delete_medication("pet-1", med_id, current_user={"id": "vet-1", "role": UserRole.VETERINARIAN})
            self.assertNotIn(med_id, db.collection(Collections.MEDICATIONS).data)

    def test_allergies_endpoints(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {"owner_id": "client-1"}
        db.collection(Collections.APPOINTMENTS).data["app-1"] = {"pet_id": "pet-1", "veterinarian_id": "vet-1"}

        allergy_create = schemas.AllergyCreate(
            allergen="Polen",
            category="Ambiental",
            severity="Moderada",
            reaction="Estornudos",
            notes="Primavera",
        )

        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            created = pet_routes.create_allergy("pet-1", allergy_create, current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(created.allergen, "Polen")

        allergy_id = created.id

        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            fetched = pet_routes.get_allergy("pet-1", allergy_id, current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(fetched.id, allergy_id)

            updated = pet_routes.update_allergy("pet-1", allergy_id, schemas.AllergyUpdate(notes="Actualizado"), current_user={"id": "vet-1", "role": UserRole.VETERINARIAN})
            self.assertEqual(updated.notes, "Actualizado")

            pet_routes.delete_allergy("pet-1", allergy_id, current_user={"id": "vet-1", "role": UserRole.VETERINARIAN})
            self.assertNotIn(allergy_id, db.collection(Collections.ALLERGIES).data)

    def test_diagnoses_and_lab_results_endpoints(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {"owner_id": "client-1"}
        db.collection(Collections.APPOINTMENTS).data["app-1"] = {"pet_id": "pet-1", "veterinarian_id": "vet-1"}

        diag_create = schemas.DiagnosisCreate(
            diagnosis="Dermatitis",
            presumptive_diagnosis="Alergia",
            differential_diagnoses="Parasitosis",
            status="Confirmado",
            treatment="Champú medicado",
            notes="Control en 15 días",
            consultation_date="2026-06-01",
            reason="Picazón",
            symptoms="Eritema",
            physical_exam="Lesiones cutáneas",
            clinical_plan="Baño semanal",
            owner_instructions="Evitar contacto con césped",
            follow_up="15 días",
        )

        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            created_diag = pet_routes.create_diagnosis("pet-1", diag_create, current_user={"id": "vet-1", "role": UserRole.VETERINARIAN})
            self.assertEqual(created_diag.diagnosis, "Dermatitis")

            fetched_diag = pet_routes.get_diagnosis("pet-1", created_diag.id, current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(fetched_diag.id, created_diag.id)

            diag_list = pet_routes.list_diagnoses("pet-1", current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(len(diag_list), 1)

        # Lab results
        db.collection(Collections.LAB_RESULTS).data["lab-1"] = {
            "pet_id": "pet-1",
            "test_name": "Hemograma",
            "test_date": date(2026, 6, 1),
        }
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            labs = pet_routes.list_lab_results("pet-1", current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(len(labs), 1)
            self.assertEqual(labs[0]["test_name"], "Hemograma")

    def test_subresources_error_branches(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {"owner_id": "client-1"}
        db.collection(Collections.APPOINTMENTS).data["app-1"] = {"pet_id": "pet-1", "veterinarian_id": "vet-1"}

        # Subresource for nonexistent pet -> 404
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.list_vaccines("nonexistent-pet", current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(ctx.exception.status_code, 404)

        # Vet subresource for non-assigned pet -> 403
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.list_vaccines("pet-1", current_user={"id": "vet-unassigned", "role": UserRole.VETERINARIAN})
            self.assertEqual(ctx.exception.status_code, 403)

        # Medication toggle check for non-existing medication -> 404
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.toggle_medication_check("pet-1", "nonexistent-med", schemas.MedicationCheckToggle(date=date(2026, 1, 1)), current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(ctx.exception.status_code, 404)

        # Delete medication non-existing -> 404
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.delete_medication("pet-1", "nonexistent-med", current_user={"id": "vet-1", "role": UserRole.VETERINARIAN})
            self.assertEqual(ctx.exception.status_code, 404)

        # Get allergy non-existing -> 404
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.get_allergy("pet-1", "nonexistent-allergy", current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(ctx.exception.status_code, 404)

        # Update allergy non-existing -> 404
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.update_allergy("pet-1", "nonexistent-allergy", schemas.AllergyUpdate(notes="x"), current_user={"id": "vet-1", "role": UserRole.VETERINARIAN})
            self.assertEqual(ctx.exception.status_code, 404)

        # Delete allergy non-existing -> 404
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.delete_allergy("pet-1", "nonexistent-allergy", current_user={"id": "vet-1", "role": UserRole.VETERINARIAN})
            self.assertEqual(ctx.exception.status_code, 404)

        # Get diagnosis non-existing -> 404
        with patch.object(pet_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                pet_routes.get_diagnosis("pet-1", "nonexistent-diag", current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(ctx.exception.status_code, 404)
