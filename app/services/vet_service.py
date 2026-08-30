"""Service for veterinarian registration (admin only)."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from google.api_core.exceptions import AlreadyExists

from .. import schemas
from ..auth import email_document_id, hash_password
from ..constant import Collections, UserRole
from ..firebase_config import get_firestore_db


def register_veterinarian(
    vet_data: schemas.VetRegister,
    admin_id: str,
) -> dict:
    """
    Registra un nuevo veterinario en Firestore (solo administradores).
    Retorna los datos del usuario creado.
    """
    db = get_firestore_db()
    users_ref = db.collection(Collections.USERS)
    
    # Verificar que el email no esté registrado
    existing = users_ref.where("email", "==", vet_data.email).limit(1).get()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email address is already registered",
        )

    now = datetime.now(timezone.utc).isoformat()
    user_id = email_document_id(vet_data.email)
    user_ref = users_ref.document(user_id)

    user_doc = {
        "email": vet_data.email,
        "hashed_password": hash_password(vet_data.password),
        "full_name": vet_data.full_name,
        "phone": vet_data.phone,
        "role": UserRole.VETERINARIAN,
        "is_active": True,
        "created_by": admin_id,
        "created_at": now,
        "specialty": vet_data.specialty,
        "license_number": vet_data.license_number,
    }

    try:
        user_ref.create(user_doc)
    except AlreadyExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email address is already registered",
        ) from exc

    # Obtener el usuario recién creado
    created_user = user_ref.get().to_dict()
    created_user["id"] = user_id

    return created_user


def list_veterinarians() -> list[dict]:
    """
    Lista todos los usuarios con rol veterinario.
    SOLO ACCESIBLE PARA ADMINISTRADORES.
    """
    db = get_firestore_db()
    docs = db.collection(Collections.USERS).where(
        "role", "==", UserRole.VETERINARIAN
    ).get()

    veterinarians = []
    for doc in docs:
        vet = doc.to_dict()
        vet["id"] = doc.id
        veterinarians.append(vet)

    return veterinarians