"""CRUD endpoints for pet profiles owned by the authenticated client."""

from datetime import datetime, timezone
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
