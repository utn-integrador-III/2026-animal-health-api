import json
import sys
import types
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.api.v1.endpoints import ai_routes
from app.constant import Collections, UserRole
from app.services import ai_service


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

    def set(self, data):
        self.collection.data[self.id] = dict(data)


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


class AIRecommendationsTests(unittest.TestCase):
    def test_service_parses_mocked_gemini_response(self):
        ai_payload = {
            "alerts": [
                {
                    "title": "Respiratory sensitivity",
                    "description": "Ninfa birds can be sensitive to air quality changes.",
                    "severity": "moderate",
                    "recommendation": "Review ventilation and respiratory signs.",
                }
            ],
            "preventive_recommendations": ["Schedule regular checkups"],
            "non_diagnostic_warning": "Informational only.",
        }
        fake_response = Mock(text=json.dumps(ai_payload))
        fake_client = Mock()
        fake_client.models.generate_content.return_value = fake_response

        fake_genai = types.SimpleNamespace(Client=Mock(return_value=fake_client))
        fake_google = types.SimpleNamespace(genai=fake_genai)

        with (
            patch.object(ai_service, "GEMINI_API_KEY", "test-key"),
            patch.object(ai_service, "AI_PROVIDER", "gemini"),
            patch.dict(sys.modules, {"google": fake_google, "google.genai": fake_genai}),
        ):
            result = ai_service.generate_breed_risk_alerts(
                {
                    "name": "Lola",
                    "species": "Bird",
                    "breed_primary": "Ninfa",
                    "breed_secondary": None,
                    "age_years": 2,
                    "age_months": 1,
                    "age_days": 0,
                    "weight_kg": 0.085,
                },
                language="en",
            )

        self.assertEqual(result["alerts"][0]["title"], "Respiratory sensitivity")
        self.assertEqual(result["preventive_recommendations"], ["Schedule regular checkups"])
        self.assertEqual(result["non_diagnostic_warning"], "Informational only.")

    def test_veterinarian_gets_breed_risk_alerts_for_pet(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {
            "name": "Lola",
            "species": "Bird",
            "breed_primary": "Ninfa",
            "breed_secondary": "Cockatiel",
            "birth_date": "2024-07-13",
            "weight_kg": 0.085,
            "owner_id": "client-1",
        }
        mocked_ai = {
            "alerts": [
                {
                    "title": "Respiratory monitoring",
                    "description": "Consider breed and age context during review.",
                    "severity": "moderate",
                    "recommendation": "Ask about appetite and breathing changes.",
                }
            ],
            "preventive_recommendations": ["Keep annual wellness checks"],
            "non_diagnostic_warning": "AI guidance is not a diagnosis.",
            "generated_by": "gemini",
        }

        with (
            patch.object(ai_routes, "get_firestore_db", return_value=db),
            patch.object(ai_routes.ai_service, "generate_breed_risk_alerts", return_value=mocked_ai),
        ):
            response = ai_routes.get_breed_risk_alerts(
                "pet-1",
                language="en",
                current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
            )

        self.assertEqual(response.pet_id, "pet-1")
        self.assertEqual(response.name, "Lola")
        self.assertEqual(response.breed_primary, "Ninfa")
        self.assertEqual(response.breed_secondary, "Cockatiel")
        self.assertGreaterEqual(response.age_years, 1)
        self.assertEqual(response.alerts[0].title, "Respiratory monitoring")
        self.assertEqual(response.non_diagnostic_warning, "AI guidance is not a diagnosis.")
        self.assertIn("pet-1_en", db.collection(Collections.AI_RECOMMENDATIONS).data)
        stored_doc = db.collection(Collections.AI_RECOMMENDATIONS).data["pet-1_en"]
        self.assertEqual(stored_doc["versions"][0]["alerts"][0]["title"], "Respiratory monitoring")
        self.assertEqual(response.history[0].alerts[0].title, "Respiratory monitoring")

    def test_breed_risk_alerts_reuses_stored_response(self):
        db = FakeFirestore()
        age_years, age_months, age_days = ai_routes._calculate_age("2024-06-01")
        pet_context = {
            "pet_id": "pet-1",
            "name": "Bonny",
            "species": "Rabbit",
            "breed_primary": "Gigante de Flandes",
            "breed_secondary": "Angora",
            "birth_date": "2024-06-01",
            "age_years": age_years,
            "age_months": age_months,
            "age_days": age_days,
            "weight_kg": 10,
        }
        db.collection(Collections.PETS).data["pet-1"] = {
            "name": pet_context["name"],
            "species": pet_context["species"],
            "breed_primary": pet_context["breed_primary"],
            "breed_secondary": pet_context["breed_secondary"],
            "birth_date": pet_context["birth_date"],
            "weight_kg": pet_context["weight_kg"],
            "owner_id": "client-1",
        }
        db.collection(Collections.AI_RECOMMENDATIONS).data["pet-1_es"] = {
            "alerts": [
                {
                    "title": "Stored risk",
                    "description": "Stored response should remain stable.",
                    "severity": "moderate",
                    "recommendation": "Use stored recommendation.",
                }
            ],
            "preventive_recommendations": ["Stored preventive recommendation"],
            "non_diagnostic_warning": "Stored warning.",
            "generated_by": "gemini",
            "generated_at": "2026-08-21T00:00:00+00:00",
            "context_hash": ai_routes._context_hash(pet_context),
        }

        with (
            patch.object(ai_routes, "get_firestore_db", return_value=db),
            patch.object(ai_routes.ai_service, "generate_breed_risk_alerts") as mocked_ai,
        ):
            response = ai_routes.get_breed_risk_alerts(
                "pet-1",
                language="es",
                refresh=False,
                current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
            )

        mocked_ai.assert_not_called()
        self.assertEqual(response.alerts[0].title, "Stored risk")
        self.assertEqual(response.preventive_recommendations, ["Stored preventive recommendation"])
        self.assertEqual(response.history[0].recommendation_id, "2026-08-21T00:00:00+00:00")
        self.assertEqual(response.history[0].alerts[0].title, "Stored risk")

    def test_breed_risk_alerts_refreshes_stored_response(self):
        db = FakeFirestore()
        age_years, age_months, age_days = ai_routes._calculate_age("2024-06-01")
        pet_context = {
            "pet_id": "pet-1",
            "name": "Bonny",
            "species": "Rabbit",
            "breed_primary": "Gigante de Flandes",
            "breed_secondary": "Angora",
            "birth_date": "2024-06-01",
            "age_years": age_years,
            "age_months": age_months,
            "age_days": age_days,
            "weight_kg": 10,
        }
        db.collection(Collections.PETS).data["pet-1"] = {
            "name": pet_context["name"],
            "species": pet_context["species"],
            "breed_primary": pet_context["breed_primary"],
            "breed_secondary": pet_context["breed_secondary"],
            "birth_date": pet_context["birth_date"],
            "weight_kg": pet_context["weight_kg"],
            "owner_id": "client-1",
        }
        db.collection(Collections.AI_RECOMMENDATIONS).data["pet-1_es"] = {
            "alerts": [
                {
                    "title": "Stored risk",
                    "description": "Stored response should be replaced.",
                    "severity": "moderate",
                    "recommendation": "Use stored recommendation.",
                }
            ],
            "preventive_recommendations": ["Stored preventive recommendation"],
            "non_diagnostic_warning": "Stored warning.",
            "generated_by": "gemini",
            "context_hash": ai_routes._context_hash(pet_context),
        }
        refreshed_ai = {
            "alerts": [
                {
                    "title": "Refreshed risk",
                    "description": "Fresh AI response.",
                    "severity": "high",
                    "recommendation": "Review refreshed recommendation.",
                }
            ],
            "preventive_recommendations": ["Fresh preventive recommendation"],
            "non_diagnostic_warning": "Fresh warning.",
            "generated_by": "gemini",
        }

        with (
            patch.object(ai_routes, "get_firestore_db", return_value=db),
            patch.object(ai_routes.ai_service, "generate_breed_risk_alerts", return_value=refreshed_ai) as mocked_ai,
        ):
            response = ai_routes.get_breed_risk_alerts(
                "pet-1",
                language="es",
                refresh=True,
                current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
            )

        mocked_ai.assert_called_once()
        self.assertEqual(response.alerts[0].title, "Refreshed risk")
        stored_doc = db.collection(Collections.AI_RECOMMENDATIONS).data["pet-1_es"]
        self.assertEqual(stored_doc["versions"][0]["alerts"][0]["title"], "Stored risk")
        self.assertEqual(stored_doc["versions"][1]["alerts"][0]["title"], "Refreshed risk")
        self.assertEqual(response.history[0].alerts[0].title, "Refreshed risk")
        self.assertEqual(response.history[1].alerts[0].title, "Stored risk")

    def test_breed_risk_alerts_return_404_when_pet_does_not_exist(self):
        db = FakeFirestore()
        with patch.object(ai_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as context:
                ai_routes.get_breed_risk_alerts(
                    "missing-pet",
                    current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
                )
        self.assertEqual(context.exception.status_code, 404)

    def test_client_gets_pet_care_recommendations_for_owned_pet(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {
            "name": "Nino",
            "species": "Dog",
            "breed_primary": "Cairn terrier",
            "breed_secondary": "Chihuahua",
            "birth_date": "2024-04-10",
            "weight_kg": 6,
            "owner_id": "client-1",
        }
        mocked_ai = {
            "nutrition_recommendations": ["Offer balanced small-breed portions"],
            "activity_recommendations": ["Use short daily walks"],
            "preventive_recommendations": ["Schedule dental checkups"],
            "non_diagnostic_warning": "Informational care guidance only.",
            "generated_by": "gemini",
        }

        with (
            patch.object(ai_routes, "get_firestore_db", return_value=db),
            patch.object(ai_routes.ai_service, "generate_pet_care_recommendations", return_value=mocked_ai),
        ):
            response = ai_routes.get_pet_care_recommendations(
                "pet-1",
                language="en",
                current_user={"id": "client-1", "role": UserRole.CLIENT},
            )

        self.assertEqual(response.pet_id, "pet-1")
        self.assertEqual(response.name, "Nino")
        self.assertEqual(response.breed_secondary, "Chihuahua")
        self.assertEqual(response.nutrition_recommendations, ["Offer balanced small-breed portions"])
        self.assertEqual(response.activity_recommendations, ["Use short daily walks"])
        self.assertEqual(response.preventive_recommendations, ["Schedule dental checkups"])
        stored_doc = db.collection(Collections.AI_RECOMMENDATIONS).data["client-care_pet-1_en"]
        self.assertEqual(stored_doc["type"], "client_care_recommendations")
        self.assertEqual(stored_doc["versions"][0]["nutrition_recommendations"][0], "Offer balanced small-breed portions")

    def test_client_care_recommendations_refresh_adds_history_version(self):
        db = FakeFirestore()
        age_years, age_months, age_days = ai_routes._calculate_age("2024-06-01")
        pet_context = {
            "pet_id": "pet-1",
            "name": "Bonny",
            "species": "Rabbit",
            "breed_primary": "Gigante de Flandes",
            "breed_secondary": "Angora",
            "birth_date": "2024-06-01",
            "age_years": age_years,
            "age_months": age_months,
            "age_days": age_days,
            "weight_kg": 10,
        }
        db.collection(Collections.PETS).data["pet-1"] = {
            "name": pet_context["name"],
            "species": pet_context["species"],
            "breed_primary": pet_context["breed_primary"],
            "breed_secondary": pet_context["breed_secondary"],
            "birth_date": pet_context["birth_date"],
            "weight_kg": pet_context["weight_kg"],
            "owner_id": "client-1",
        }
        db.collection(Collections.AI_RECOMMENDATIONS).data["client-care_pet-1_es"] = {
            "type": "client_care_recommendations",
            "context_hash": ai_routes._context_hash(pet_context),
            "versions": [
                {
                    "recommendation_id": "old",
                    "nutrition_recommendations": ["Old nutrition"],
                    "activity_recommendations": ["Old activity"],
                    "preventive_recommendations": ["Old prevention"],
                    "non_diagnostic_warning": "Old warning.",
                    "generated_by": "gemini",
                    "generated_at": "2026-08-20T00:00:00+00:00",
                }
            ],
        }
        refreshed_ai = {
            "nutrition_recommendations": ["New nutrition"],
            "activity_recommendations": ["New activity"],
            "preventive_recommendations": ["New prevention"],
            "non_diagnostic_warning": "New warning.",
            "generated_by": "gemini",
        }

        with (
            patch.object(ai_routes, "get_firestore_db", return_value=db),
            patch.object(ai_routes.ai_service, "generate_pet_care_recommendations", return_value=refreshed_ai),
        ):
            response = ai_routes.get_pet_care_recommendations(
                "pet-1",
                language="es",
                refresh=True,
                current_user={"id": "client-1", "role": UserRole.CLIENT},
            )

        self.assertEqual(response.nutrition_recommendations, ["New nutrition"])
        stored_doc = db.collection(Collections.AI_RECOMMENDATIONS).data["client-care_pet-1_es"]
        self.assertEqual(len(stored_doc["versions"]), 2)
        self.assertEqual(response.history[0].nutrition_recommendations, ["New nutrition"])
        self.assertEqual(response.history[1].nutrition_recommendations, ["Old nutrition"])

    def test_client_cannot_get_care_recommendations_for_another_owner_pet(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {
            "name": "Nino",
            "species": "Dog",
            "breed_primary": "Cairn terrier",
            "birth_date": "2024-04-10",
            "weight_kg": 6,
            "owner_id": "client-1",
        }

        with patch.object(ai_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as context:
                ai_routes.get_pet_care_recommendations(
                    "pet-1",
                    current_user={"id": "client-2", "role": UserRole.CLIENT},
                )

        self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()

