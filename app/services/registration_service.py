"""Atomic client and first-pet registration."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from google.api_core.exceptions import AlreadyExists

from .. import schemas
from ..auth import email_document_id, hash_password
from ..constant import Collections, UserRole


def register_client_with_pet(
    db,
    user_data: schemas.UserRegister,
) -> tuple[str, str, str]:
    """Creates the client and mandatory first pet in one Firestore batch."""
    users_ref = db.collection(Collections.USERS)
    existing = users_ref.where("email", "==", user_data.email).limit(1).get()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email address is already registered",
        )

    now = datetime.now(timezone.utc).isoformat()
    user_id = email_document_id(user_data.email)
    user_ref = users_ref.document(user_id)
    pet_ref = db.collection(Collections.PETS).document()

    user_doc = {
        "email": user_data.email,
        "hashed_password": hash_password(user_data.password),
        "full_name": user_data.full_name,
        "phone": user_data.phone,
        "role": UserRole.CLIENT,
        "is_active": True,
        "created_at": now,
    }
    pet = user_data.initial_pet
    pet_doc = {
        "name": pet.name,
        "birth_date": pet.birth_date.isoformat(),
        "species": pet.species,
        "sex": pet.sex,
        "breed_primary": pet.breed_primary,
        "breed_secondary": pet.breed_secondary,
        "mixed_breed": pet.mixed_breed,
        "weight_kg": pet.weight_kg,
        "owner_id": user_id,
        "created_at": now,
    }

    try:
        batch = db.batch()
        batch.create(user_ref, user_doc)
        batch.create(pet_ref, pet_doc)
        batch.commit()
    except AlreadyExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email address is already registered",
        ) from exc

    return user_id, pet_ref.id, now
