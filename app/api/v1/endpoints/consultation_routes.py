"""External walk-in consultation and diagnosis endpoints."""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .... import schemas
from ....auth import email_document_id, require_roles
from ....constant import ApiPrefix, Collections, UserRole
from ....firebase_config import get_firestore_db

router = APIRouter(prefix=ApiPrefix.CONSULTATIONS, tags=["Consultations"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client_response(snapshot) -> schemas.UserResponse:
    data = snapshot.to_dict()
    return schemas.UserResponse(
        id=snapshot.id,
        email=data.get("email", ""),
        full_name=data.get("full_name", "Client"),
        role=data.get("role", UserRole.CLIENT),
        phone=data.get("phone"),
        profile_image_url=data.get("profile_image_url"),
        unread_notifications=data.get("unread_notifications", 0),
    )


def _pet_lookup_response(snapshot) -> schemas.WalkInClientPet:
    data = snapshot.to_dict()
    return schemas.WalkInClientPet(
        id=snapshot.id,
        name=data.get("name", ""),
        species=data.get("species", ""),
        sex=data.get("sex", ""),
        breed_primary=data.get("breed_primary", ""),
        birth_date=data.get("birth_date"),
        weight_kg=data.get("weight_kg", 0),
        photo_url=data.get("photo_url"),
    )


def _require_client(db, client_id: str):
    snapshot = db.collection(Collections.USERS).document(client_id).get()
    if not snapshot.exists or snapshot.to_dict().get("role") != UserRole.CLIENT:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return snapshot


def _require_pet_for_client(db, pet_id: str, client_id: str):
    snapshot = db.collection(Collections.PETS).document(pet_id).get()
    if not snapshot.exists or snapshot.to_dict().get("owner_id") != client_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pet not found")
    return snapshot


def _require_consultation_for_vet(db, consultation_id: str, veterinarian_id: str):
    reference = db.collection(Collections.CONSULTATIONS).document(consultation_id)
    snapshot = reference.get()
    if not snapshot.exists or snapshot.to_dict().get("veterinarian_id") != veterinarian_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
    return reference, snapshot


@router.get("/clients", response_model=schemas.WalkInClientLookupResponse)
def find_client_by_email(
    email: str = Query(..., min_length=5),
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN)),
):
    db = get_firestore_db()
    client_id = email_document_id(email)
    snapshot = db.collection(Collections.USERS).document(client_id).get()
    if not snapshot.exists or snapshot.to_dict().get("role") != UserRole.CLIENT:
        return schemas.WalkInClientLookupResponse(client=None, pets=[])

    pet_snapshots = (
        db.collection(Collections.PETS)
        .where("owner_id", "==", client_id)
        .get()
    )
    return schemas.WalkInClientLookupResponse(
        client=_client_response(snapshot),
        pets=[_pet_lookup_response(pet) for pet in pet_snapshots],
    )


@router.post("/walk-in", response_model=schemas.WalkInConsultationResponse, status_code=201)
def create_walk_in_consultation(
    consultation_data: schemas.WalkInConsultationCreate,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN)),
):
    db = get_firestore_db()
    client_id = consultation_data.client_id or email_document_id(consultation_data.client_email)
    client_ref = db.collection(Collections.USERS).document(client_id)
    client_snapshot = client_ref.get()

    if client_snapshot.exists:
        client = client_snapshot.to_dict()
        if client.get("role") != UserRole.CLIENT:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is not a client account")
        client_ref.update({
            "full_name": consultation_data.client_name,
            "phone": consultation_data.client_phone,
            "email": consultation_data.client_email,
            "updated_at": _now(),
        })
        client.update({
            "full_name": consultation_data.client_name,
            "phone": consultation_data.client_phone,
            "email": consultation_data.client_email,
        })
    else:
        client = {
            "email": consultation_data.client_email,
            "full_name": consultation_data.client_name,
            "phone": consultation_data.client_phone,
            "role": UserRole.CLIENT,
            "is_active": True,
            "registration_source": "walk_in",
            "must_set_password": True,
            "password_hash": "",
            "created_at": _now(),
        }
        client_ref.create(client)

    if consultation_data.pet_id:
        pet_snapshot = _require_pet_for_client(db, consultation_data.pet_id, client_id)
        pet = pet_snapshot.to_dict()
        pet_id = pet_snapshot.id
    else:
        pet = {
            "name": consultation_data.pet_name,
            "birth_date": consultation_data.pet_birth_date.isoformat(),
            "species": consultation_data.pet_species,
            "sex": consultation_data.pet_sex,
            "breed_primary": consultation_data.pet_breed,
            "breed_secondary": None,
            "mixed_breed": False,
            "weight_kg": consultation_data.pet_weight_kg,
            "owner_id": client_id,
            "created_at": _now(),
        }
        pet_ref = db.collection(Collections.PETS).document()
        pet_ref.create(pet)
        pet_id = pet_ref.id

    document = {
        "client_id": client_id,
        "owner_name": client.get("full_name", consultation_data.client_name),
        "owner_email": client.get("email", consultation_data.client_email),
        "owner_phone": client.get("phone"),
        "pet_id": pet_id,
        "pet_name": pet.get("name", consultation_data.pet_name),
        "pet_species": pet.get("species", consultation_data.pet_species),
        "pet_sex": pet.get("sex", consultation_data.pet_sex),
        "pet_breed": pet.get("breed_primary", consultation_data.pet_breed),
        "pet_weight_kg": pet.get("weight_kg", consultation_data.pet_weight_kg),
        "pet_photo_url": pet.get("photo_url"),
        "reason": consultation_data.reason,
        "veterinarian_id": current_user["id"],
        "veterinarian_name": current_user.get("full_name", "Veterinarian"),
        "status": "open",
        "source": "walk_in",
        "created_at": _now(),
    }
    reference = db.collection(Collections.CONSULTATIONS).add(document)

    appointment_document = {
        "pet_id": pet_id,
        "pet_name": document["pet_name"],
        "pet_species": document["pet_species"],
        "pet_sex": document["pet_sex"],
        "pet_birth_date": pet.get("birth_date"),
        "pet_weight_kg": document["pet_weight_kg"],
        "pet_breed": document["pet_breed"],
        "pet_photo_url": document["pet_photo_url"],
        "owner_id": client_id,
        "owner_name": document["owner_name"],
        "last_visit": "--",
        "appointment_date": datetime.now().date().isoformat(),
        "appointment_time": datetime.now().strftime("%H:%M"),
        "duration_blocks": 1,
        "reason": consultation_data.reason,
        "veterinarian_id": current_user["id"],
        "veterinarian_name": current_user.get("full_name", "Veterinarian"),
        "status": schemas.AppointmentStatus.SCHEDULED,
        "created_by_role": UserRole.VETERINARIAN,
        "source": "walk_in",
        "consultation_id": reference[1].id,
        "created_at": _now(),
    }
    db.collection(Collections.APPOINTMENTS).add(appointment_document)
    return schemas.WalkInConsultationResponse(id=reference[1].id, **document)


@router.post("/{consultation_id}/diagnoses", response_model=schemas.DiagnosisResponse, status_code=201)
def create_diagnosis(
    consultation_id: str,
    diagnosis_data: schemas.DiagnosisCreate,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN)),
):
    if consultation_id != diagnosis_data.consultation_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Consultation id mismatch")

    db = get_firestore_db()
    _, consultation_snapshot = _require_consultation_for_vet(db, consultation_id, current_user["id"])
    consultation = consultation_snapshot.to_dict()
    if consultation.get("pet_id") != diagnosis_data.pet_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Diagnosis pet does not match consultation")

    document = {
        "consultation_id": consultation_id,
        "pet_id": diagnosis_data.pet_id,
        "diagnosis": diagnosis_data.diagnosis,
        "clinical_notes": diagnosis_data.clinical_notes,
        "veterinarian_id": current_user["id"],
        "veterinarian_name": current_user.get("full_name", "Veterinarian"),
        "created_at": _now(),
    }
    reference = db.collection(Collections.DIAGNOSES).add(document)

    db.collection(Collections.MEDICAL_RECORDS).add({
        "pet_id": diagnosis_data.pet_id,
        "diagnosis": diagnosis_data.diagnosis,
        "treatment": "Pending treatment plan",
        "weight_kg": consultation.get("pet_weight_kg"),
        "notes": diagnosis_data.clinical_notes,
        "date": datetime.now().date().isoformat(),
        "consultation_id": consultation_id,
        "diagnosis_id": reference[1].id,
        "veterinarian_id": current_user["id"],
        "veterinarian_name": current_user.get("full_name", "Veterinarian"),
        "created_at": document["created_at"],
    })

    return schemas.DiagnosisResponse(id=reference[1].id, **document)
