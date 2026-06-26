"""Minimal authentication required to register owners and manage their pets."""

from fastapi import APIRouter, Depends, HTTPException, status

from .. import schemas
from ..auth import (
    create_access_token,
    get_current_user,
    password_needs_rehash,
    hash_password,
    verify_password,
)
from ..constants import ApiPrefix, Collections, UserRole
from ..firebase_config import get_firestore_db
from ..services.registration_service import register_client_with_pet

router = APIRouter(prefix=ApiPrefix.AUTH, tags=["Authentication"])


@router.post("/register", response_model=schemas.RegistrationResponse, status_code=201)
def register(user_data: schemas.UserRegister):
    db = get_firestore_db()
    user_id, pet_id, created_at = register_client_with_pet(db, user_data)
    token = create_access_token({"sub": user_id})
    pet = user_data.initial_pet

    return schemas.RegistrationResponse(
        access_token=token,
        user=schemas.UserResponse(
            id=user_id,
            email=user_data.email,
            full_name=user_data.full_name,
            role=UserRole.CLIENT,
            phone=user_data.phone,
        ),
        pet=schemas.PetResponse(
            id=pet_id,
            name=pet.name,
            birth_date=pet.birth_date,
            species=pet.species,
            sex=pet.sex,
            breed_primary=pet.breed_primary,
            breed_secondary=pet.breed_secondary,
            mixed_breed=pet.mixed_breed,
            weight_kg=pet.weight_kg,
            owner_id=user_id,
            created_at=created_at,
        ),
    )


@router.post("/login", response_model=schemas.TokenResponse)
def login(credentials: schemas.UserLogin):
    db = get_firestore_db()
    results = (
        db.collection(Collections.USERS)
        .where("email", "==", credentials.email)
        .limit(1)
        .get()
    )
    if not results:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    user_doc = results[0]
    user_data = user_doc.to_dict()
    if (
        not user_data.get("is_active", True)
        or user_data.get("role") != UserRole.CLIENT
        or not verify_password(credentials.password, user_data.get("hashed_password", ""))
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if password_needs_rehash(user_data["hashed_password"]):
        user_doc.reference.update({
            "hashed_password": hash_password(credentials.password),
        })

    return schemas.TokenResponse(
        access_token=create_access_token({"sub": user_doc.id}),
        user=schemas.UserResponse(
            id=user_doc.id,
            email=user_data["email"],
            full_name=user_data["full_name"],
            role=UserRole.CLIENT,
            phone=user_data.get("phone"),
        ),
    )


@router.get("/profile", response_model=schemas.UserResponse)
def get_profile(current_user: dict = Depends(get_current_user)):
    return schemas.UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        full_name=current_user["full_name"],
        role=UserRole.CLIENT,
        phone=current_user.get("phone"),
    )
