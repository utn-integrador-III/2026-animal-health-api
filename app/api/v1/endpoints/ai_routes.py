"""AI-assisted endpoints for veterinary patient review."""

from datetime import date, datetime, timezone
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .... import schemas
from ....auth import require_roles
from ....constant import ApiPrefix, Collections, UserRole
from ....firebase_config import get_firestore_db
from ....services import ai_service

router = APIRouter(prefix=ApiPrefix.AI, tags=["AI Recommendations"])


def _calculate_age(birth_date: str | date) -> tuple[int, int, int]:
    if isinstance(birth_date, date):
        birth = birth_date
    else:
        birth = date.fromisoformat(str(birth_date)[:10])
    today = date.today()
    years = today.year - birth.year
    months = today.month - birth.month
    days = today.day - birth.day
    if days < 0:
        months -= 1
        if today.month == 1:
            previous_month = date(today.year - 1, 12, 1)
            next_month = date(today.year, 1, 1)
        else:
            previous_month = date(today.year, today.month - 1, 1)
            next_month = date(today.year, today.month, 1)
        days += (next_month - previous_month).days
    if months < 0:
        years -= 1
        months += 12
    return max(years, 0), max(months, 0), max(days, 0)


def _recommendation_document_id(
    pet_id: str,
    language: str,
    recommendation_type: str | None = None,
) -> str:
    prefix = f"{recommendation_type}_" if recommendation_type else ""
    return f"{prefix}{pet_id}_{language}"


def _context_hash(pet_context: dict) -> str:
    tracked_context = {
        "pet_id": pet_context["pet_id"],
        "species": pet_context["species"],
        "breed_primary": pet_context["breed_primary"],
        "breed_secondary": pet_context.get("breed_secondary"),
        "birth_date": str(pet_context.get("birth_date")),
        "weight_kg": pet_context.get("weight_kg"),
    }
    payload = json.dumps(tracked_context, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_versions(stored_result: dict) -> list[dict]:
    versions = stored_result.get("versions")
    if versions:
        return list(versions)

    if "alerts" not in stored_result:
        return []

    recommendation_id = (
        stored_result.get("recommendation_id")
        or stored_result.get("generated_at")
        or "legacy-recommendation"
    )
    return [
        {
            "recommendation_id": recommendation_id,
            "alerts": stored_result["alerts"],
            "preventive_recommendations": stored_result["preventive_recommendations"],
            "non_diagnostic_warning": stored_result["non_diagnostic_warning"],
            "generated_by": stored_result.get("generated_by", "gemini"),
            "generated_at": stored_result.get("generated_at"),
        }
    ]


def _extract_care_versions(stored_result: dict) -> list[dict]:
    versions = stored_result.get("versions")
    if versions:
        return list(versions)

    if "nutrition_recommendations" not in stored_result:
        return []

    recommendation_id = (
        stored_result.get("recommendation_id")
        or stored_result.get("generated_at")
        or "legacy-care-recommendation"
    )
    return [
        {
            "recommendation_id": recommendation_id,
            "nutrition_recommendations": stored_result["nutrition_recommendations"],
            "activity_recommendations": stored_result["activity_recommendations"],
            "preventive_recommendations": stored_result["preventive_recommendations"],
            "non_diagnostic_warning": stored_result["non_diagnostic_warning"],
            "generated_by": stored_result.get("generated_by", "gemini"),
            "generated_at": stored_result.get("generated_at"),
        }
    ]


def _build_response(
    pet_context: dict,
    ai_result: dict,
    history: list[dict] | None = None,
) -> schemas.BreedRiskAlertResponse:
    return schemas.BreedRiskAlertResponse(
        pet_id=pet_context["pet_id"],
        name=pet_context["name"],
        species=pet_context["species"],
        breed_primary=pet_context["breed_primary"],
        breed_secondary=pet_context["breed_secondary"],
        birth_date=pet_context["birth_date"],
        age_years=pet_context["age_years"],
        age_months=pet_context["age_months"],
        age_days=pet_context["age_days"],
        alerts=ai_result["alerts"],
        preventive_recommendations=ai_result["preventive_recommendations"],
        non_diagnostic_warning=ai_result["non_diagnostic_warning"],
        generated_by=ai_result.get("generated_by", "gemini"),
        generated_at=ai_result.get("generated_at"),
        recommendation_id=ai_result.get("recommendation_id"),
        history=history or [],
    )


def _build_care_response(
    pet_context: dict,
    ai_result: dict,
    history: list[dict] | None = None,
) -> schemas.PetCareRecommendationResponse:
    return schemas.PetCareRecommendationResponse(
        pet_id=pet_context["pet_id"],
        name=pet_context["name"],
        species=pet_context["species"],
        breed_primary=pet_context["breed_primary"],
        breed_secondary=pet_context["breed_secondary"],
        birth_date=pet_context["birth_date"],
        age_years=pet_context["age_years"],
        age_months=pet_context["age_months"],
        age_days=pet_context["age_days"],
        nutrition_recommendations=ai_result["nutrition_recommendations"],
        activity_recommendations=ai_result["activity_recommendations"],
        preventive_recommendations=ai_result["preventive_recommendations"],
        non_diagnostic_warning=ai_result["non_diagnostic_warning"],
        generated_by=ai_result.get("generated_by", "gemini"),
        generated_at=ai_result.get("generated_at"),
        recommendation_id=ai_result.get("recommendation_id"),
        history=history or [],
    )


def _build_pet_context(pet_id: str, pet: dict) -> dict:
    years, months, days = _calculate_age(pet["birth_date"])
    return {
        "pet_id": pet_id,
        "name": pet.get("name", "Pet"),
        "species": pet.get("species", "Unknown"),
        "breed_primary": pet.get("breed_primary", "Unknown"),
        "breed_secondary": pet.get("breed_secondary"),
        "birth_date": pet.get("birth_date"),
        "age_years": years,
        "age_months": months,
        "age_days": days,
        "weight_kg": pet.get("weight_kg"),
    }


@router.get(
    "/pets/{pet_id}/breed-risk-alerts",
    response_model=schemas.BreedRiskAlertResponse,
)
def get_breed_risk_alerts(
    pet_id: str,
    language: str = Query(default="en", pattern="^(en|es)$"),
    refresh: bool = Query(default=False),
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN)),
):
    """Return stored AI breed alerts or regenerate them when requested."""
    db = get_firestore_db()
    snapshot = db.collection(Collections.PETS).document(pet_id).get()
    if not snapshot.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pet not found")

    pet = snapshot.to_dict()
    pet_context = _build_pet_context(pet_id, pet)
    current_context_hash = _context_hash(pet_context)
    recommendation_ref = db.collection(Collections.AI_RECOMMENDATIONS).document(
        _recommendation_document_id(pet_id, language)
    )
    recommendation_snapshot = recommendation_ref.get()
    stored_versions: list[dict] = []

    if not refresh and recommendation_snapshot.exists:
        stored_result = recommendation_snapshot.to_dict()
        stored_versions = _extract_versions(stored_result)
        if stored_result.get("context_hash") == current_context_hash and stored_versions:
            return _build_response(
                pet_context,
                stored_versions[-1],
                list(reversed(stored_versions)),
            )
    elif recommendation_snapshot.exists:
        stored_versions = _extract_versions(recommendation_snapshot.to_dict())

    try:
        ai_result = ai_service.generate_breed_risk_alerts(pet_context, language=language)
    except ai_service.AIServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    generated_at = datetime.now(timezone.utc).isoformat()
    recommendation_id = generated_at.replace(":", "").replace(".", "")
    generated_version = {
        **ai_result,
        "recommendation_id": recommendation_id,
        "generated_at": generated_at,
        "generated_by": ai_result.get("generated_by", "gemini"),
    }
    updated_versions = [*stored_versions, generated_version]
    stored_result = {
        "pet_id": pet_id,
        "language": language,
        "context_hash": current_context_hash,
        "latest_recommendation_id": recommendation_id,
        "latest_generated_at": generated_at,
        "versions": updated_versions,
        "generated_by_user_id": current_user.get("id"),
        "updated_at": generated_at,
    }
    recommendation_ref.set(stored_result)

    return _build_response(
        pet_context,
        generated_version,
        list(reversed(updated_versions)),
    )


@router.get(
    "/pets/{pet_id}/care-recommendations",
    response_model=schemas.PetCareRecommendationResponse,
)
def get_pet_care_recommendations(
    pet_id: str,
    language: str = Query(default="en", pattern="^(en|es)$"),
    refresh: bool = Query(default=False),
    current_user: dict = Depends(require_roles(UserRole.CLIENT)),
):
    """Return stored client care recommendations or regenerate them when requested."""
    db = get_firestore_db()
    snapshot = db.collection(Collections.PETS).document(pet_id).get()
    if not snapshot.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pet not found")

    pet = snapshot.to_dict()
    if pet.get("owner_id") != current_user.get("id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view recommendations for your own pets",
        )

    pet_context = _build_pet_context(pet_id, pet)
    current_context_hash = _context_hash(pet_context)
    recommendation_ref = db.collection(Collections.AI_RECOMMENDATIONS).document(
        _recommendation_document_id(pet_id, language, "client-care")
    )
    recommendation_snapshot = recommendation_ref.get()
    stored_versions: list[dict] = []

    if not refresh and recommendation_snapshot.exists:
        stored_result = recommendation_snapshot.to_dict()
        stored_versions = _extract_care_versions(stored_result)
        if stored_result.get("context_hash") == current_context_hash and stored_versions:
            return _build_care_response(
                pet_context,
                stored_versions[-1],
                list(reversed(stored_versions)),
            )
    elif recommendation_snapshot.exists:
        stored_versions = _extract_care_versions(recommendation_snapshot.to_dict())

    try:
        ai_result = ai_service.generate_pet_care_recommendations(
            pet_context,
            language=language,
        )
    except ai_service.AIServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    generated_at = datetime.now(timezone.utc).isoformat()
    recommendation_id = generated_at.replace(":", "").replace(".", "")
    generated_version = {
        **ai_result,
        "recommendation_id": recommendation_id,
        "generated_at": generated_at,
        "generated_by": ai_result.get("generated_by", "gemini"),
    }
    updated_versions = [*stored_versions, generated_version]
    stored_result = {
        "type": "client_care_recommendations",
        "pet_id": pet_id,
        "language": language,
        "context_hash": current_context_hash,
        "latest_recommendation_id": recommendation_id,
        "latest_generated_at": generated_at,
        "versions": updated_versions,
        "generated_by_user_id": current_user.get("id"),
        "updated_at": generated_at,
    }
    recommendation_ref.set(stored_result)

    return _build_care_response(
        pet_context,
        generated_version,
        list(reversed(updated_versions)),
    )
