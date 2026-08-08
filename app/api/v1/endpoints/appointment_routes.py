"""Appointment management endpoints for clients and veterinarians."""

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .... import schemas
from ....auth import require_roles
from ....constant import ApiPrefix, Collections, UserRole
from ....firebase_config import get_firestore_db

router = APIRouter(prefix=ApiPrefix.APPOINTMENTS, tags=["Appointments"])

BUSINESS_SLOTS = (
    "08:00",
    "08:30",
    "09:00",
    "09:30",
    "10:00",
    "10:30",
    "11:00",
    "11:30",
    "13:00",
    "13:30",
    "14:00",
    "14:30",
    "15:00",
    "15:30",
    "16:00",
    "16:30",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _time_to_string(value: time) -> str:
    return value.strftime("%H:%M")


def _normalize_time(value: str) -> str:
    return value[:5]


def _is_sunday(value: str) -> bool:
    return date.fromisoformat(value).weekday() == 6


def _future_slots_for_date(appointment_date: str) -> tuple[str, ...]:
    if _is_sunday(appointment_date):
        return ()
    if appointment_date != date.today().isoformat():
        return BUSINESS_SLOTS

    now_time = datetime.now().time()
    return tuple(
        slot for slot in BUSINESS_SLOTS
        if time.fromisoformat(slot) > now_time
    )


def _required_slots(start_time: str, duration_blocks: int = 1) -> tuple[str, ...]:
    start_time = _normalize_time(start_time)
    if start_time not in BUSINESS_SLOTS:
        return ()
    start_datetime = datetime.combine(date.today(), time.fromisoformat(start_time))
    expected_slots = tuple(
        (start_datetime + timedelta(minutes=30 * index)).time().strftime("%H:%M")
        for index in range(duration_blocks)
    )
    if all(slot in BUSINESS_SLOTS for slot in expected_slots):
        return expected_slots
    return ()


def _appointment_response(document_id: str, data: dict) -> schemas.AppointmentResponse:
    if data.get("appointment_time"):
        data["appointment_time"] = _normalize_time(data["appointment_time"])
    return schemas.AppointmentResponse(id=document_id, **data)


def _pet_breed_summary(pet: dict, fallback: str = "Not specified") -> str:
    primary = str(pet.get("breed_primary") or "").strip()
    secondary = str(pet.get("breed_secondary") or "").strip()
    if primary and secondary:
        return f"{primary} / {secondary}"
    return primary or secondary or fallback

def _hydrate_pet_summary(db, data: dict) -> dict:
    pet_id = data.get("pet_id")
    if not pet_id:
        return data

    snapshot = db.collection(Collections.PETS).document(pet_id).get()
    if not snapshot.exists:
        return data

    pet = snapshot.to_dict()
    return {
        **data,
        "pet_name": pet.get("name", data.get("pet_name")),
        "pet_species": pet.get("species", data.get("pet_species")),
        "pet_sex": pet.get("sex"),
        "pet_birth_date": pet.get("birth_date"),
        "pet_weight_kg": pet.get("weight_kg"),
        "pet_breed": _pet_breed_summary(pet, data.get("pet_breed", "Not specified")),
        "pet_photo_url": pet.get("photo_url"),
    }


def _last_completed_visit(db, pet_id: str, current_appointment_id: Optional[str] = None) -> str:
    snapshots = (
        db.collection(Collections.APPOINTMENTS)
        .where("pet_id", "==", pet_id)
        .where("status", "==", schemas.AppointmentStatus.COMPLETED)
        .get()
    )
    completed_dates = [
        snapshot.to_dict().get("appointment_date")
        for snapshot in snapshots
        if snapshot.id != current_appointment_id
        and snapshot.to_dict().get("appointment_date")
    ]
    return max(completed_dates) if completed_dates else "--"


def _owned_pet(db, pet_id: str, owner_id: str):
    snapshot = db.collection(Collections.PETS).document(pet_id).get()
    if not snapshot.exists or snapshot.to_dict().get("owner_id") != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pet not found",
        )
    return snapshot


def _assigned_pet(db, pet_id: str, veterinarian_id: str):
    snapshot = db.collection(Collections.PETS).document(pet_id).get()
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
    return snapshot


def _veterinarian(db, veterinarian_id: str):
    snapshot = db.collection(Collections.USERS).document(veterinarian_id).get()
    if not snapshot.exists or snapshot.to_dict().get("role") != UserRole.VETERINARIAN:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Veterinarian not found",
        )
    return snapshot


def _reserved_slots(db, veterinarian_id: str, appointment_date: str, exclude_id: Optional[str] = None) -> set[str]:
    snapshots = (
        db.collection(Collections.APPOINTMENTS)
        .where("veterinarian_id", "==", veterinarian_id)
        .where("appointment_date", "==", appointment_date)
        .where("status", "==", schemas.AppointmentStatus.SCHEDULED)
        .get()
    )
    reserved = set()
    for snapshot in snapshots:
        if snapshot.id == exclude_id:
            continue
        data = snapshot.to_dict()
        duration_blocks = int(data.get("duration_blocks", 1))
        reserved.update(_required_slots(data.get("appointment_time", ""), duration_blocks))
    return reserved


def _slot_taken(
    db,
    veterinarian_id: str,
    appointment_date: str,
    appointment_time: str,
    duration_blocks: int = 1,
    exclude_id: Optional[str] = None,
):
    required_slots = set(_required_slots(appointment_time, duration_blocks))
    if len(required_slots) != duration_blocks:
        return True
    return bool(required_slots & _reserved_slots(db, veterinarian_id, appointment_date, exclude_id))


def _appointment_for_client(db, appointment_id: str, owner_id: str):
    reference = db.collection(Collections.APPOINTMENTS).document(appointment_id)
    snapshot = reference.get()
    if not snapshot.exists or snapshot.to_dict().get("owner_id") != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )
    return reference, snapshot


def _appointment_for_veterinarian(db, appointment_id: str, veterinarian_id: str):
    reference = db.collection(Collections.APPOINTMENTS).document(appointment_id)
    snapshot = reference.get()
    if not snapshot.exists or snapshot.to_dict().get("veterinarian_id") != veterinarian_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )
    return reference, snapshot


@router.get("/veterinarians", response_model=List[schemas.VeterinarianOption])
def list_veterinarians(
    current_user: dict = Depends(require_roles(UserRole.CLIENT)),
):
    db = get_firestore_db()
    snapshots = (
        db.collection(Collections.USERS)
        .where("role", "==", UserRole.VETERINARIAN)
        .get()
    )
    return [
        schemas.VeterinarianOption(
            id=snapshot.id,
            full_name=snapshot.to_dict().get("full_name", "Veterinarian"),
            email=snapshot.to_dict().get("email", ""),
        )
        for snapshot in snapshots
    ]


@router.get("/available-slots", response_model=schemas.AvailableSlotsResponse)
def available_slots(
    appointment_date: str = Query(...),
    veterinarian_id: str = Query(...),
    duration_blocks: int = Query(1, ge=1, le=4),
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN)),
):
    db = get_firestore_db()
    _veterinarian(db, veterinarian_id)
    available_base_slots = _future_slots_for_date(appointment_date)
    taken = _reserved_slots(db, veterinarian_id, appointment_date)
    return schemas.AvailableSlotsResponse(
        date=appointment_date,
        veterinarian_id=veterinarian_id,
        slots=[
            slot for slot in available_base_slots
            if not set(_required_slots(slot, duration_blocks)) & taken
            and len(_required_slots(slot, duration_blocks)) == duration_blocks
        ],
    )


@router.get("", response_model=List[schemas.AppointmentResponse])
def list_appointments(
    pet_id: Optional[str] = None,
    appointment_date: Optional[str] = None,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN)),
):
    db = get_firestore_db()
    query = db.collection(Collections.APPOINTMENTS)
    if current_user["role"] == UserRole.CLIENT:
        query = query.where("owner_id", "==", current_user["id"])
        if pet_id:
            _owned_pet(db, pet_id, current_user["id"])
            query = query.where("pet_id", "==", pet_id)
    else:
        query = query.where("veterinarian_id", "==", current_user["id"])
    if appointment_date:
        query = query.where("appointment_date", "==", appointment_date)

    snapshots = query.get()
    responses = []
    for snapshot in snapshots:
        data = _hydrate_pet_summary(db, snapshot.to_dict())
        data.setdefault("last_visit", _last_completed_visit(db, data["pet_id"], snapshot.id))
        responses.append(_appointment_response(snapshot.id, data))
    return responses


@router.post("", response_model=schemas.AppointmentResponse, status_code=201)
def create_appointment(
    appointment_data: schemas.AppointmentCreate,
    current_user: dict = Depends(require_roles(UserRole.CLIENT)),
):
    db = get_firestore_db()
    pet_snapshot = _owned_pet(db, appointment_data.pet_id, current_user["id"])
    pet = pet_snapshot.to_dict()
    vet_snapshot = _veterinarian(db, appointment_data.veterinarian_id)
    veterinarian = vet_snapshot.to_dict()
    appointment_date = appointment_data.appointment_date.isoformat()
    appointment_time = _time_to_string(appointment_data.appointment_time)
    duration_blocks = appointment_data.duration_blocks

    if _is_sunday(appointment_date):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Appointments cannot be scheduled on Sundays",
        )
    if appointment_time not in _future_slots_for_date(appointment_date):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Selected time is outside available appointment slots",
        )
    if _slot_taken(
        db,
        appointment_data.veterinarian_id,
        appointment_date,
        appointment_time,
        duration_blocks,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Selected appointment slot is no longer available",
        )

    document = {
        "pet_id": appointment_data.pet_id,
        "pet_name": pet["name"],
        "pet_species": pet["species"],
        "pet_sex": pet.get("sex"),
        "pet_birth_date": pet.get("birth_date"),
        "pet_weight_kg": pet.get("weight_kg"),
        "pet_breed": _pet_breed_summary(pet),
        "pet_photo_url": pet.get("photo_url"),
        "owner_id": current_user["id"],
        "owner_name": current_user.get("full_name", "Client"),
        "last_visit": _last_completed_visit(db, appointment_data.pet_id),
        "appointment_date": appointment_date,
        "appointment_time": appointment_time,
        "duration_blocks": duration_blocks,
        "reason": appointment_data.reason,
        "veterinarian_id": appointment_data.veterinarian_id,
        "veterinarian_name": veterinarian.get("full_name", "Veterinarian"),
        "status": schemas.AppointmentStatus.SCHEDULED,
        "created_at": _now(),
    }
    reference = db.collection(Collections.APPOINTMENTS).add(document)
    return schemas.AppointmentResponse(id=reference[1].id, **document)


@router.post("/follow-up", response_model=schemas.AppointmentResponse, status_code=201)
def create_follow_up_appointment(
    appointment_data: schemas.AppointmentFollowUpCreate,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN)),
):
    db = get_firestore_db()
    pet_snapshot = _assigned_pet(db, appointment_data.pet_id, current_user["id"])
    pet = pet_snapshot.to_dict()
    owner_snapshot = db.collection(Collections.USERS).document(pet["owner_id"]).get()
    owner = owner_snapshot.to_dict() if owner_snapshot.exists else {}
    appointment_date = appointment_data.appointment_date.isoformat()
    appointment_time = _time_to_string(appointment_data.appointment_time)
    duration_blocks = appointment_data.duration_blocks

    if _is_sunday(appointment_date):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Appointments cannot be scheduled on Sundays",
        )
    if appointment_time not in _future_slots_for_date(appointment_date):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Selected time is outside available appointment slots",
        )
    if _slot_taken(
        db,
        current_user["id"],
        appointment_date,
        appointment_time,
        duration_blocks,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Selected appointment slot is no longer available",
        )

    document = {
        "pet_id": appointment_data.pet_id,
        "pet_name": pet["name"],
        "pet_species": pet["species"],
        "pet_sex": pet.get("sex"),
        "pet_birth_date": pet.get("birth_date"),
        "pet_weight_kg": pet.get("weight_kg"),
        "pet_breed": _pet_breed_summary(pet),
        "pet_photo_url": pet.get("photo_url"),
        "owner_id": pet["owner_id"],
        "owner_name": owner.get("full_name", "Client"),
        "last_visit": _last_completed_visit(db, appointment_data.pet_id),
        "appointment_date": appointment_date,
        "appointment_time": appointment_time,
        "duration_blocks": duration_blocks,
        "reason": appointment_data.reason,
        "veterinarian_id": current_user["id"],
        "veterinarian_name": current_user.get("full_name", "Veterinarian"),
        "status": schemas.AppointmentStatus.SCHEDULED,
        "created_by_role": UserRole.VETERINARIAN,
        "created_at": _now(),
    }
    reference = db.collection(Collections.APPOINTMENTS).add(document)
    return schemas.AppointmentResponse(id=reference[1].id, **document)


@router.put("/{appointment_id}", response_model=schemas.AppointmentResponse)
def reschedule_appointment(
    appointment_id: str,
    appointment_data: schemas.AppointmentUpdate,
    current_user: dict = Depends(require_roles(UserRole.CLIENT)),
):
    db = get_firestore_db()
    reference, snapshot = _appointment_for_client(db, appointment_id, current_user["id"])
    current = snapshot.to_dict()
    if current.get("status") != schemas.AppointmentStatus.SCHEDULED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only scheduled appointments can be rescheduled",
        )

    update_data = appointment_data.model_dump(exclude_unset=True)
    if "appointment_date" in update_data:
        update_data["appointment_date"] = update_data["appointment_date"].isoformat()
    if "appointment_time" in update_data:
        update_data["appointment_time"] = _time_to_string(update_data["appointment_time"])
    if "veterinarian_id" in update_data:
        veterinarian = _veterinarian(db, update_data["veterinarian_id"]).to_dict()
        update_data["veterinarian_name"] = veterinarian.get("full_name", "Veterinarian")

    next_vet = update_data.get("veterinarian_id", current["veterinarian_id"])
    next_date = update_data.get("appointment_date", current["appointment_date"])
    next_time = update_data.get("appointment_time", current["appointment_time"])
    next_duration = int(update_data.get("duration_blocks", current.get("duration_blocks", 1)))
    if _is_sunday(next_date):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Appointments cannot be scheduled on Sundays",
        )
    if next_time not in _future_slots_for_date(next_date):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Selected time is outside available appointment slots",
        )
    if _slot_taken(db, next_vet, next_date, next_time, next_duration, exclude_id=appointment_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Selected appointment slot is no longer available",
        )

    update_data["updated_at"] = _now()
    reference.update(update_data)
    updated = reference.get()
    return _appointment_response(updated.id, updated.to_dict())


@router.post("/{appointment_id}/complete", response_model=schemas.AppointmentResponse)
def complete_appointment(
    appointment_id: str,
    appointment_data: schemas.AppointmentComplete,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN)),
):
    db = get_firestore_db()
    reference, snapshot = _appointment_for_veterinarian(db, appointment_id, current_user["id"])
    if snapshot.to_dict().get("status") != schemas.AppointmentStatus.SCHEDULED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only scheduled appointments can be completed",
        )

    reference.update({
        "status": schemas.AppointmentStatus.COMPLETED,
        "clinical_observation": appointment_data.clinical_observation,
        "completed_at": _now(),
        "updated_at": _now(),
    })
    updated = reference.get()
    return _appointment_response(updated.id, updated.to_dict())


@router.post("/{appointment_id}/cancel", response_model=schemas.AppointmentResponse)
def cancel_appointment(
    appointment_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT)),
):
    db = get_firestore_db()
    reference, snapshot = _appointment_for_client(db, appointment_id, current_user["id"])
    if snapshot.to_dict().get("status") != schemas.AppointmentStatus.SCHEDULED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only scheduled appointments can be cancelled",
        )
    reference.update({
        "status": schemas.AppointmentStatus.CANCELLED,
        "cancelled_at": _now(),
        "updated_at": _now(),
    })
    updated = reference.get()
    return _appointment_response(updated.id, updated.to_dict())


