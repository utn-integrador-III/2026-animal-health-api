"""CRUD endpoints for pet profiles owned by the authenticated client."""

from datetime import date, datetime, timezone
from typing import List
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from .... import schemas
from ....auth import require_roles
from ....constant import ApiPrefix, Collections, UserRole
from ....firebase_config import get_firestore_db, get_storage_bucket

router = APIRouter(prefix=ApiPrefix.PETS, tags=["Pet Profiles"])

PET_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_PET_IMAGE_BYTES = 5 * 1024 * 1024


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _owned_pet(db, pet_id: str, owner_id: str):
    """Ensures a pet exists and belongs to the requesting client."""
    reference = db.collection(Collections.PETS).document(pet_id)
    snapshot = reference.get()
    if not snapshot.exists or snapshot.to_dict().get("owner_id") != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found",
        )
    return reference, snapshot


def _assigned_pet(db, pet_id: str, veterinarian_id: str):
    """Ensures a pet exists and the requesting veterinarian has been assigned
    to at least one appointment for that pet."""
    reference = db.collection(Collections.PETS).document(pet_id)
    snapshot = reference.get()
    if not snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found",
        )

    assignments = (
        db.collection(Collections.APPOINTMENTS)
        .where("pet_id", "==", pet_id)
        .where("veterinarian_id", "==", veterinarian_id)
        .limit(1)
        .get()
    )
    if len(assignments) == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Veterinarian is not assigned to this pet",
        )
    return reference, snapshot


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Pet CRUD ────────────────────────────────────────────────────────────────

@router.post("", response_model=schemas.PetResponse, status_code=201)
def create_pet(
    pet_data: schemas.PetCreate,
    current_user: dict = Depends(require_roles(UserRole.CLIENT)),
):
    db = get_firestore_db()
    document = {
        **pet_data.model_dump(),
        "birth_date": pet_data.birth_date.isoformat(),
        "owner_id": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    reference = db.collection(Collections.PETS).add(document)
    return schemas.PetResponse(id=reference[1].id, **document)


@router.get("", response_model=List[schemas.PetResponse])
def list_pets(
    current_user: dict = Depends(require_roles(UserRole.CLIENT)),
):
    db = get_firestore_db()
    snapshots = (
        db.collection(Collections.PETS)
        .where("owner_id", "==", current_user["id"])
        .get()
    )
    return [
        schemas.PetResponse(id=snapshot.id, **snapshot.to_dict())
        for snapshot in snapshots
    ]


def _owned_pet(db, pet_id: str, owner_id: str):
    reference = db.collection(Collections.PETS).document(pet_id)
    snapshot = reference.get()
    if not snapshot.exists or snapshot.to_dict().get("owner_id") != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found",
        )
    return reference, snapshot


@router.get("/{pet_id}", response_model=schemas.PetResponse)
def get_pet(
    pet_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN)),
):
    db = get_firestore_db()
    if current_user["role"] == UserRole.CLIENT:
        _, snapshot = _owned_pet(db, pet_id, current_user["id"])
    else:
        _, snapshot = _assigned_pet(db, pet_id, current_user["id"])
    return schemas.PetResponse(id=snapshot.id, **snapshot.to_dict())


@router.put("/{pet_id}", response_model=schemas.PetResponse)
def update_pet(
    pet_id: str,
    pet_data: schemas.PetUpdate,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN)),
):
    db = get_firestore_db()
    if current_user["role"] == UserRole.CLIENT:
        reference, _ = _owned_pet(db, pet_id, current_user["id"])
    else:
        reference, _ = _assigned_pet(db, pet_id, current_user["id"])
    update_data = pet_data.model_dump(exclude_unset=True)
    if "birth_date" in update_data:
        update_data["birth_date"] = update_data["birth_date"].isoformat()
    if update_data:
        reference.update(update_data)
    updated = reference.get()
    return schemas.PetResponse(id=updated.id, **updated.to_dict())


@router.post("/{pet_id}/photo", response_model=schemas.PetResponse)
async def upload_pet_photo(
    pet_id: str,
    photo: UploadFile = File(...),
    current_user: dict = Depends(require_roles(UserRole.CLIENT)),
):
    """Uploads a pet profile image to Firebase Storage."""
    extension = PET_IMAGE_TYPES.get(photo.content_type)
    if not extension:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Pet image must be JPEG, PNG, or WebP",
        )

    content = await photo.read(MAX_PET_IMAGE_BYTES + 1)
    if len(content) > MAX_PET_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Pet image cannot exceed 5 MB",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Pet image is empty",
        )

    db = get_firestore_db()
    reference, _ = _owned_pet(db, pet_id, current_user["id"])

    try:
        bucket = get_storage_bucket()
        object_name = f"pet-images/{current_user['id']}/{pet_id}/{uuid4().hex}.{extension}"
        download_token = str(uuid4())
        blob = bucket.blob(object_name)
        blob.metadata = {"firebaseStorageDownloadTokens": download_token}
        blob.upload_from_string(content, content_type=photo.content_type)
        encoded_name = quote(object_name, safe="")
        image_url = (
            "https://firebasestorage.googleapis.com/v0/b/"
            f"{bucket.name}/o/{encoded_name}?alt=media&token={download_token}"
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    reference.update({"photo_url": image_url})
    updated = reference.get()
    return schemas.PetResponse(id=updated.id, **updated.to_dict())


@router.delete("/{pet_id}", status_code=204)
def delete_pet(
    pet_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT)),
):
    db = get_firestore_db()
    reference, _ = _owned_pet(db, pet_id, current_user["id"])
    reference.delete()


# ─── Vaccine Endpoints ────────────────────────────────────────────────────────

def _raw_status_to_status(raw_status: str) -> str:
    """Maps the vet-facing raw_status label to the client-facing status value."""
    completed_statuses = {"Aplicada correctamente", "Esquema completo", "completed"}
    return "completed" if raw_status in completed_statuses else "upcoming"


@router.get("/{pet_id}/vaccines", response_model=List[schemas.VaccineResponse])
def list_vaccines(
    pet_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN)),
):
    """Returns the full vaccination history for a pet.

    - Clients: can only read their own pet's vaccines.
    - Veterinarians: can only read vaccines for pets they are assigned to.
    """
    db = get_firestore_db()
    if current_user["role"] == UserRole.CLIENT:
        _owned_pet(db, pet_id, current_user["id"])
    else:
        _assigned_pet(db, pet_id, current_user["id"])

    snapshots = (
        db.collection(Collections.VACCINES)
        .where("pet_id", "==", pet_id)
        .get()
    )
    return [
        schemas.VaccineResponse(id=snapshot.id, **snapshot.to_dict())
        for snapshot in snapshots
    ]


@router.post(
    "/{pet_id}/vaccines",
    response_model=schemas.VaccineResponse,
    status_code=201,
)
def create_vaccine(
    pet_id: str,
    vaccine_data: schemas.VaccineCreate,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN)),
):
    """Records a vaccine applied by the authenticated veterinarian.

    Only veterinarians that have at least one appointment for the pet are allowed.
    """
    db = get_firestore_db()
    _assigned_pet(db, pet_id, current_user["id"])

    document = {
        "pet_id": pet_id,
        "name": vaccine_data.name,
        "type": vaccine_data.type,
        "brand": vaccine_data.brand,
        "batch_number": vaccine_data.batch_number,
        "scheduled_date": vaccine_data.scheduled_date.isoformat(),
        "expiration_date": vaccine_data.expiration_date.isoformat()
            if vaccine_data.expiration_date else None,
        "next_dose": vaccine_data.next_dose.isoformat()
            if vaccine_data.next_dose else None,
        "administration_route": vaccine_data.administration_route,
        "dose": vaccine_data.dose,
        "unit": vaccine_data.unit,
        "raw_status": vaccine_data.raw_status,
        "status": _raw_status_to_status(vaccine_data.raw_status),
        "notes": vaccine_data.notes,
        "veterinarian_id": current_user["id"],
        "veterinarian_name": current_user.get("full_name", "Veterinarian"),
        "created_at": _now(),
    }
    reference = db.collection(Collections.VACCINES).add(document)
    return schemas.VaccineResponse(id=reference[1].id, **document)


# ─── Clinical Records Endpoints ──────────────────────────────────────────────

@router.get("/{pet_id}/clinical-records", response_model=List[schemas.ClinicalRecordResponse])
def list_clinical_records(
    pet_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN)),
):
    """Returns the clinical medical history for a pet.

    - Clients: can only read their own pet's history.
    - Veterinarians: can only read history for pets they are assigned to.
    """
    db = get_firestore_db()
    if current_user["role"] == UserRole.CLIENT:
        _owned_pet(db, pet_id, current_user["id"])
    else:
        _assigned_pet(db, pet_id, current_user["id"])

    snapshots = (
        db.collection(Collections.MEDICAL_RECORDS)
        .where("pet_id", "==", pet_id)
        .get()
    )
    records = []
    for snapshot in snapshots:
        data = snapshot.to_dict()
        records.append(schemas.ClinicalRecordResponse(id=snapshot.id, **data))
    
    records.sort(key=lambda x: x.date, reverse=True)
    return records


@router.post(
    "/{pet_id}/clinical-records",
    response_model=schemas.ClinicalRecordResponse,
    status_code=201,
)
def create_clinical_record(
    pet_id: str,
    record_data: schemas.ClinicalRecordCreate,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN)),
):
    """Records a clinical medical record (diagnosis, treatment, observations) for a pet.

    Only veterinarians that have at least one appointment for the pet are allowed.
    """
    db = get_firestore_db()
    _assigned_pet(db, pet_id, current_user["id"])

    document = {
        "pet_id": pet_id,
        "diagnosis": record_data.diagnosis,
        "treatment": record_data.treatment,
        "weight_kg": record_data.weight_kg,
        "notes": record_data.notes,
        "date": record_data.date.isoformat(),
        "veterinarian_id": current_user["id"],
        "veterinarian_name": current_user.get("full_name", "Veterinarian"),
        "created_at": _now(),
    }
    reference = db.collection(Collections.MEDICAL_RECORDS).add(document)
    return schemas.ClinicalRecordResponse(id=reference[1].id, **document)


# ─── Medications Endpoints ───────────────────────────────────────────────────

@router.get("/{pet_id}/medications", response_model=List[schemas.MedicationResponse])
def list_medications(
    pet_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN)),
):
    """Returns the medication list (active treatments and history) for a pet.

    - Clients: can only read their own pet's medications.
    - Veterinarians: can only read medications for pets they are assigned to.
    """
    db = get_firestore_db()
    if current_user["role"] == UserRole.CLIENT:
        _owned_pet(db, pet_id, current_user["id"])
    else:
        _assigned_pet(db, pet_id, current_user["id"])

    snapshots = (
        db.collection(Collections.MEDICATIONS)
        .where("pet_id", "==", pet_id)
        .get()
    )
    
    medications = []
    today_str = date.today().isoformat()
    
    for snapshot in snapshots:
        data = snapshot.to_dict()
        end_date_str = data.get("end_date")
        computed_status = "active"
        if end_date_str and end_date_str < today_str:
            computed_status = "completed"
            
        data["status"] = data.get("status", computed_status)
        medications.append(schemas.MedicationResponse(id=snapshot.id, **data))
        
    medications.sort(key=lambda x: (x.status != "active", x.end_date), reverse=True)
    return medications


@router.post(
    "/{pet_id}/medications",
    response_model=schemas.MedicationResponse,
    status_code=201,
)
def create_medication(
    pet_id: str,
    medication_data: schemas.MedicationCreate,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN)),
):
    """Prescribes a new medication treatment for a pet.

    Only veterinarians that have at least one appointment for the pet are allowed.
    """
    db = get_firestore_db()
    _assigned_pet(db, pet_id, current_user["id"])

    today_str = date.today().isoformat()
    end_date_str = medication_data.end_date.isoformat()
    computed_status = "active"
    if end_date_str < today_str:
        computed_status = "completed"

    document = {
        "pet_id": pet_id,
        "name": medication_data.name,
        "dosage": medication_data.dosage,
        "frequency": medication_data.frequency,
        "start_date": medication_data.start_date.isoformat(),
        "end_date": end_date_str,
        "administration_time": medication_data.administration_time,
        "notes": medication_data.notes,
        "status": computed_status,
        "checked_dates": [],
        "veterinarian_id": current_user["id"],
        "veterinarian_name": current_user.get("full_name", "Veterinarian"),
        "created_at": _now(),
    }
    reference = db.collection(Collections.MEDICATIONS).add(document)
    return schemas.MedicationResponse(id=reference[1].id, **document)


@router.post(
    "/{pet_id}/medications/{medication_id}/toggle-check",
    response_model=schemas.MedicationResponse,
)
def toggle_medication_check(
    pet_id: str,
    medication_id: str,
    toggle_data: schemas.MedicationCheckToggle,
    current_user: dict = Depends(require_roles(UserRole.CLIENT)),
):
    """Toggles (adds/removes) a specific date in the medication's checked_dates list.

    Only the pet owner client is allowed to check off medication logs.
    """
    db = get_firestore_db()
    _owned_pet(db, pet_id, current_user["id"])

    reference = db.collection(Collections.MEDICATIONS).document(medication_id)
    snapshot = reference.get()
    if not snapshot.exists or snapshot.to_dict().get("pet_id") != pet_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found",
        )

    data = snapshot.to_dict()
    checked_dates = data.get("checked_dates", [])
    date_str = toggle_data.date.isoformat()

    is_checking = date_str not in checked_dates

    if not is_checking:
        checked_dates.remove(date_str)
    else:
        checked_dates.append(date_str)

    reference.update({"checked_dates": checked_dates})

    # Sync with notifications for this medication for today
    notif_query = db.collection(Collections.NOTIFICATIONS) \
        .where("medication_id", "==", medication_id) \
        .where("scheduled_date", "==", date_str) \
        .stream()

    for notif_doc in notif_query:
        if is_checking:
            notif_doc.reference.update({
                "read": True,
                "read_at": datetime.now(timezone.utc).isoformat()
            })
        else:
            notif_doc.reference.update({
                "read": False,
                "read_at": None
            })

    updated = reference.get()
    
    updated_data = updated.to_dict()
    today_str = date.today().isoformat()
    end_date_str = updated_data.get("end_date")
    computed_status = "active"
    if end_date_str and end_date_str < today_str:
        computed_status = "completed"
    updated_data["status"] = updated_data.get("status", computed_status)

    return schemas.MedicationResponse(id=updated.id, **updated_data)


@router.delete("/{pet_id}/medications/{medication_id}", status_code=204)
def delete_medication(
    pet_id: str,
    medication_id: str,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN)),
):
    """Deletes a prescribed medication for a pet.

    Only veterinarians assigned to the pet are allowed to delete a medication.
    """
    db = get_firestore_db()
    _assigned_pet(db, pet_id, current_user["id"])

    reference = db.collection(Collections.MEDICATIONS).document(medication_id)
    snapshot = reference.get()
    if not snapshot.exists or snapshot.to_dict().get("pet_id") != pet_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found",
        )

    reference.delete()
    return None


# ─── Allergy Endpoints ────────────────────────────────────────────────────────

@router.get("/{pet_id}/allergies", response_model=List[schemas.AllergyResponse])
def list_allergies(
    pet_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN)),
):
    """Returns all allergies for a pet.

    - Clients: can only read their own pet's allergies.
    - Veterinarians: can only read allergies for pets they are assigned to.
    """
    db = get_firestore_db()
    if current_user["role"] == UserRole.CLIENT:
        _owned_pet(db, pet_id, current_user["id"])
    else:
        _assigned_pet(db, pet_id, current_user["id"])

    snapshots = (
        db.collection(Collections.ALLERGIES)
        .where("pet_id", "==", pet_id)
        .get()
    )
    return [
        schemas.AllergyResponse(id=snapshot.id, **snapshot.to_dict())
        for snapshot in snapshots
    ]


@router.post(
    "/{pet_id}/allergies",
    response_model=schemas.AllergyResponse,
    status_code=201,
)
def create_allergy(
    pet_id: str,
    allergy_data: schemas.AllergyCreate,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN)),
):
    """Registers a new allergy for a pet."""
    db = get_firestore_db()
    if current_user["role"] == UserRole.CLIENT:
        _owned_pet(db, pet_id, current_user["id"])
    else:
        _assigned_pet(db, pet_id, current_user["id"])

    now_str = _now()
    document = {
        "pet_id": pet_id,
        "allergen": allergy_data.allergen,
        "category": allergy_data.category,
        "severity": allergy_data.severity,
        "reaction": allergy_data.reaction,
        "notes": allergy_data.notes,
        "registered_by": current_user["role"],
        "veterinarian_id": current_user["id"] if current_user["role"] == UserRole.VETERINARIAN else None,
        "veterinarian_name": current_user.get("full_name") if current_user["role"] == UserRole.VETERINARIAN else None,
        "created_at": now_str,
        "updated_at": now_str,
    }
    reference = db.collection(Collections.ALLERGIES).add(document)
    return schemas.AllergyResponse(id=reference[1].id, **document)


@router.get("/{pet_id}/allergies/{allergy_id}", response_model=schemas.AllergyResponse)
def get_allergy(
    pet_id: str,
    allergy_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN)),
):
    """Retrieves a specific allergy record."""
    db = get_firestore_db()
    if current_user["role"] == UserRole.CLIENT:
        _owned_pet(db, pet_id, current_user["id"])
    else:
        _assigned_pet(db, pet_id, current_user["id"])

    reference = db.collection(Collections.ALLERGIES).document(allergy_id)
    snapshot = reference.get()
    if not snapshot.exists or snapshot.to_dict().get("pet_id") != pet_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allergy not found",
        )
    return schemas.AllergyResponse(id=snapshot.id, **snapshot.to_dict())


@router.put("/{pet_id}/allergies/{allergy_id}", response_model=schemas.AllergyResponse)
def update_allergy(
    pet_id: str,
    allergy_id: str,
    allergy_data: schemas.AllergyUpdate,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN)),
):
    """Updates an existing allergy record (Veterinarian only)."""
    db = get_firestore_db()
    _assigned_pet(db, pet_id, current_user["id"])

    reference = db.collection(Collections.ALLERGIES).document(allergy_id)
    snapshot = reference.get()
    if not snapshot.exists or snapshot.to_dict().get("pet_id") != pet_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allergy not found",
        )

    update_data = allergy_data.model_dump(exclude_unset=True)
    update_data["updated_at"] = _now()
    update_data["veterinarian_id"] = current_user["id"]
    update_data["veterinarian_name"] = current_user.get("full_name", "Veterinarian")

    reference.update(update_data)
    updated = reference.get()
    return schemas.AllergyResponse(id=updated.id, **updated.to_dict())


@router.delete("/{pet_id}/allergies/{allergy_id}", status_code=204)
def delete_allergy(
    pet_id: str,
    allergy_id: str,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN)),
):
    """Deletes an allergy record (Veterinarian only)."""
    db = get_firestore_db()
    _assigned_pet(db, pet_id, current_user["id"])

    reference = db.collection(Collections.ALLERGIES).document(allergy_id)
    snapshot = reference.get()
    if not snapshot.exists or snapshot.to_dict().get("pet_id") != pet_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allergy not found",
        )

    reference.delete()
    return None



