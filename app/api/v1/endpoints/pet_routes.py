"""CRUD endpoints for pet profiles owned by the authenticated client."""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from .... import schemas
from ....auth import require_roles
from ....constant import ApiPrefix, Collections, UserRole
from ....firebase_config import get_firestore_db

router = APIRouter(prefix=ApiPrefix.PETS, tags=["Pet Profiles"])


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
    current_user: dict = Depends(require_roles(UserRole.CLIENT)),
):
    db = get_firestore_db()
    _, snapshot = _owned_pet(db, pet_id, current_user["id"])
    return schemas.PetResponse(id=snapshot.id, **snapshot.to_dict())


@router.put("/{pet_id}", response_model=schemas.PetResponse)
def update_pet(
    pet_id: str,
    pet_data: schemas.PetUpdate,
    current_user: dict = Depends(require_roles(UserRole.CLIENT)),
):
    db = get_firestore_db()
    reference, _ = _owned_pet(db, pet_id, current_user["id"])
    update_data = pet_data.model_dump(exclude_unset=True)
    if "birth_date" in update_data:
        update_data["birth_date"] = update_data["birth_date"].isoformat()
    if update_data:
        reference.update(update_data)
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
