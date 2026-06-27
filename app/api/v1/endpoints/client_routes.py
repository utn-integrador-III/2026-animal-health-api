"""
Client account routes:
- GET    /api/clients/{id}    — Get client by ID
- PUT    /api/clients/{id}    — Update client info
- DELETE /api/clients/{id}    — Deactivate client account
"""

from fastapi import APIRouter, Depends, HTTPException, status

from .. import schemas
from auth import get_current_user
from firebase_config import get_firestore_db
from constant import Collections, UserRole, ApiPrefix

router = APIRouter(prefix=ApiPrefix.CLIENTS, tags=["Clients"])


def _veterinarian_has_client_access(db, veterinarian_id: str, client_id: str) -> bool:
    appointments = (
        db.collection(Collections.APPOINTMENTS)
        .where("vet_id", "==", veterinarian_id)
        .get()
    )
    for appointment in appointments:
        appointment_data = appointment.to_dict()
        if appointment_data.get("status") == "canceled":
            continue
        pet = (
            db.collection(Collections.PETS)
            .document(appointment_data.get("pet_id"))
            .get()
        )
        if pet.exists and pet.to_dict().get("owner_id") == client_id:
            return True
    return False


@router.get("/{client_id}", response_model=schemas.ClientResponse)
def get_client(
    client_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Returns full information for a specific client."""
    db = get_firestore_db()
    doc = db.collection(Collections.USERS).document(client_id).get()

    if not doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    data = doc.to_dict()

    # Clients see their profile; vets only see owners of assigned patients.
    if (
        current_user.get("role") == UserRole.CLIENT
        and current_user["id"] != client_id
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if (
        current_user.get("role") == UserRole.VETERINARIAN
        and not _veterinarian_has_client_access(db, current_user["id"], client_id)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return schemas.ClientResponse(
        id=doc.id,
        email=data["email"],
        full_name=data["full_name"],
        role=data.get("role", UserRole.CLIENT),
        phone=data.get("phone"),
        is_active=data.get("is_active", True),
        created_at=data["created_at"],
    )


@router.put("/{client_id}", response_model=schemas.ClientResponse)
def update_client(
    client_id: str,
    client_data: schemas.ClientUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Updates a client's personal information. Only the client themselves can do this."""
    if current_user["id"] != client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    db = get_firestore_db()
    ref = db.collection(Collections.USERS).document(client_id)
    doc = ref.get()

    if not doc.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    update_fields = client_data.model_dump(exclude_unset=True)
    if update_fields:
        ref.update(update_fields)

    updated = ref.get().to_dict()
    return schemas.ClientResponse(
        id=client_id,
        email=updated["email"],
        full_name=updated["full_name"],
        role=updated.get("role", UserRole.CLIENT),
        phone=updated.get("phone"),
        is_active=updated.get("is_active", True),
        created_at=updated["created_at"],
    )


@router.delete("/{client_id}", status_code=204)
def deactivate_client(
    client_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Deactivates a client account (soft delete). Only the client themselves can do this."""
    if current_user["id"] != client_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    db = get_firestore_db()
    ref = db.collection(Collections.USERS).document(client_id)

    if not ref.get().exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    ref.update({"is_active": False})
