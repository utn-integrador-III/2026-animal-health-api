"""Unit tests for models in app/models and schemas in app/schemas."""

import unittest
from datetime import date, datetime
from app.models.diagnosis import (
    DiagnosisBase,
    DiagnosisCreate,
    DiagnosisUpdate,
    DiagnosisInDB,
)
from app.models.vaccine import (
    VaccineBase,
    VaccineCreate,
    VaccineUpdate,
    VaccineInDB,
)
from app.models.allergy import (
    AllergyBase,
    AllergyCreate,
    AllergyUpdate,
    AllergyInDB,
)
from app.models.pet import (
    PetBase,
    PetCreate,
    PetUpdate,
    PetInDB,
)
from app.schemas.lab_result import (
    LabResultCreate,
    LabResultUpdate,
    LabResultResponse,
    LabResultListResponse,
)
from app.schemas.notification import (
    NotificationCreate,
    NotificationUpdate,
    NotificationInDB,
    NotificationResponse,
    NotificationListResponse,
)


class TestDiagnosisModels(unittest.TestCase):
    def test_diagnosis_base_and_create(self):
        diag = DiagnosisCreate(
            pet_id="pet-123",
            diagnosis="Canine Parvovirus",
            consultation_id="cons-1",
            clinical_notes="Fever and lethargy",
            presumptive_diagnosis="Parvovirus",
            differential_diagnoses="Gastroenteritis",
            status="Presuntivo",
            treatment="IV Fluids",
            weight_kg="10.5",
            temperature_c="39.2",
            heart_rate_bpm="110",
            respiratory_rate_rpm="24",
            systems_eval={"digestive": "abnormal"},
        )
        self.assertEqual(diag.pet_id, "pet-123")
        self.assertEqual(diag.diagnosis, "Canine Parvovirus")
        self.assertEqual(diag.status, "Presuntivo")
        self.assertEqual(diag.weight_kg, "10.5")

    def test_diagnosis_update(self):
        update = DiagnosisUpdate(
            diagnosis="Confirmed Parvovirus",
            status="Definitivo",
            treatment="Rest and medication",
        )
        self.assertEqual(update.diagnosis, "Confirmed Parvovirus")
        self.assertEqual(update.status, "Definitivo")

    def test_diagnosis_in_db(self):
        now = datetime.now()
        diag_db = DiagnosisInDB(
            id="diag-001",
            pet_id="pet-123",
            diagnosis="Otitis",
            registered_by="veterinarian",
            veterinarian_id="vet-1",
            veterinarian_name="Dr. Smith",
            created_at=now,
            updated_at=now,
        )
        self.assertEqual(diag_db.id, "diag-001")
        self.assertEqual(diag_db.registered_by, "veterinarian")
        self.assertEqual(diag_db.veterinarian_name, "Dr. Smith")
        self.assertEqual(diag_db.created_at, now)


class TestVaccineModels(unittest.TestCase):
    def test_vaccine_base_and_create(self):
        vaccine = VaccineCreate(
            name="Rabies",
            type="Viral",
            brand="Nobivac",
            batch_number="B12345",
            dose="1ml",
            administration_date=date(2026, 1, 15),
            expiration_date=date(2027, 1, 15),
            administration_route="Subcutaneous",
            next_dose=date(2027, 1, 15),
            pet_id="pet-123",
            veterinarian_id="vet-1",
            veterinarian_name="Dr. Smith",
            status="completed",
            notes="No adverse reactions",
            notification_sent=False,
        )
        self.assertEqual(vaccine.name, "Rabies")
        self.assertEqual(vaccine.administration_date, date(2026, 1, 15))
        self.assertEqual(vaccine.status, "completed")
        self.assertFalse(vaccine.notification_sent)

    def test_vaccine_update(self):
        update = VaccineUpdate(
            name="Rabies Booster",
            notes="Scheduled for next year",
            notification_sent=True,
        )
        self.assertEqual(update.name, "Rabies Booster")
        self.assertTrue(update.notification_sent)

    def test_vaccine_in_db(self):
        now = datetime.now()
        v_db = VaccineInDB(
            id="vac-1",
            name="Distemper",
            administration_date=date(2026, 2, 1),
            expiration_date=date(2027, 2, 1),
            pet_id="pet-123",
            created_at=now,
            updated_at=now,
        )
        self.assertEqual(v_db.id, "vac-1")
        self.assertEqual(v_db.name, "Distemper")
        self.assertEqual(v_db.created_at, now)


class TestAllergyModels(unittest.TestCase):
    def test_allergy_base_and_create(self):
        allergy = AllergyCreate(
            pet_id="pet-123",
            allergen="Pollen",
            category="environmental",
            severity="moderate",
            reaction="Skin redness and itching",
            notes="Worse during spring season",
        )
        self.assertEqual(allergy.pet_id, "pet-123")
        self.assertEqual(allergy.allergen, "Pollen")
        self.assertEqual(allergy.category, "environmental")
        self.assertEqual(allergy.severity, "moderate")

    def test_allergy_update(self):
        update = AllergyUpdate(
            allergen="Dust Mites",
            severity="severe",
            notes="Requires antihistamines",
        )
        self.assertEqual(update.allergen, "Dust Mites")
        self.assertEqual(update.severity, "severe")

    def test_allergy_in_db(self):
        now = datetime.now()
        a_db = AllergyInDB(
            id="all-1",
            pet_id="pet-123",
            allergen="Chicken",
            category="food",
            severity="mild",
            registered_by="client",
            veterinarian_id=None,
            veterinarian_name=None,
            created_at=now,
            updated_at=now,
        )
        self.assertEqual(a_db.id, "all-1")
        self.assertEqual(a_db.registered_by, "client")
        self.assertEqual(a_db.category, "food")
        self.assertEqual(a_db.created_at, now)


class TestPetModels(unittest.TestCase):
    def test_pet_base_and_create(self):
        pet = PetCreate(
            name="Max",
            species="Dog",
            breed="Golden Retriever",
            sex="Male",
            birth_date=date(2020, 5, 10),
            weight=30.5,
            color="Golden",
            microchip_id="985141000123456",
            owner_id="owner-1",
            owner_name="John Doe",
        )
        self.assertEqual(pet.name, "Max")
        self.assertEqual(pet.owner_id, "owner-1")
        self.assertEqual(pet.weight, 30.5)

    def test_pet_update(self):
        update = PetUpdate(
            weight=31.2,
            color="Dark Golden",
        )
        self.assertEqual(update.weight, 31.2)
        self.assertEqual(update.color, "Dark Golden")

    def test_pet_in_db(self):
        pet_db = PetInDB(
            id="pet-001",
            name="Bella",
            species="Cat",
            sex="Female",
            owner_id="owner-2",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        self.assertEqual(pet_db.id, "pet-001")
        self.assertEqual(pet_db.species, "Cat")


class TestExtraSchemas(unittest.TestCase):
    def test_lab_result_schemas(self):
        create = LabResultCreate(
            pet_id="pet-1",
            test_type="Blood Test",
            test_date=date(2026, 3, 1),
            clinical_observations="Normal CBC",
        )
        update = LabResultUpdate(result_summary="All values within reference range")
        resp = LabResultResponse(
            id="lr-1",
            owner_id="owner-1",
            pet_id="pet-1",
            test_type="Blood Test",
            test_date=date(2026, 3, 1),
            clinical_observations="Normal CBC",
        )
        list_resp = LabResultListResponse(results=[resp], total=1)
        self.assertEqual(create.test_type, "Blood Test")
        self.assertEqual(update.result_summary, "All values within reference range")
        self.assertEqual(list_resp.total, 1)

    def test_notification_schemas(self):
        notif_create = NotificationCreate(
            user_id="u-1",
            pet_id="pet-1",
            title="Vaccine Due",
            message="Rabies vaccine is due in 3 days",
        )
        notif_update = NotificationUpdate(read=True)
        now = datetime.now()
        notif_db = NotificationInDB(
            id="n-1",
            user_id="u-1",
            pet_id="pet-1",
            title="Vaccine Due",
            message="Rabies vaccine due",
            created_at=now,
        )
        notif_resp = NotificationResponse(
            id="n-1",
            user_id="u-1",
            pet_id="pet-1",
            type="vaccine_expiration",
            title="Vaccine Due",
            message="Rabies vaccine due",
            read=False,
            urgency="info",
        )
        list_resp = NotificationListResponse(
            notifications=[notif_resp], total=1, unread_count=1
        )
        self.assertEqual(notif_create.title, "Vaccine Due")
        self.assertTrue(notif_update.read)
        self.assertEqual(notif_db.id, "n-1")
        self.assertEqual(list_resp.unread_count, 1)


if __name__ == "__main__":
    unittest.main()
