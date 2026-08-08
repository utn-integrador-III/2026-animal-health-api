"""
Authentication routes:
- POST /api/auth/register  — Register a new client user
- POST /api/auth/login     — Authenticate and receive a JWT
- POST /api/auth/logout    — End the session (client-side token invalidation)
- GET  /api/auth/profile   — Return the current authenticated user's data
- PUT  /api/auth/profile   — Update the current user's profile
"""

from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from .... import schemas
from ....auth import (
    verify_password,
    password_needs_rehash,
    hash_password,
    create_access_token,
    get_current_user,
)
from ....firebase_config import get_firestore_db, get_storage_bucket
from ....constant import Collections, UserRole, ApiPrefix
from ....services.registration_service import register_client_with_pet

router = APIRouter(prefix=ApiPrefix.AUTH, tags=["Authentication"])

PROFILE_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_PROFILE_IMAGE_BYTES = 5 * 1024 * 1024


def _user_response(user_id: str, user_data: dict) -> schemas.UserResponse:
    return schemas.UserResponse(
        id=user_id,
        email=user_data["email"],
        full_name=user_data["full_name"],
        role=user_data.get("role", UserRole.CLIENT),
        phone=user_data.get("phone"),
        profile_image_url=user_data.get("profile_image_url"),
        unread_notifications=user_data.get("unread_notifications", 0),
    )


@router.post("/register", response_model=schemas.RegistrationResponse, status_code=201)
def register(user_data: schemas.UserRegister):
    """
    Registers a new user in Firestore with the 'client' role and returns a JWT.
    Veterinarian accounts must be created by an admin via the admin panel.
    """
    db = get_firestore_db()
    user_id, pet_id, created_at = register_client_with_pet(db, user_data)
    pet_data = user_data.initial_pet

    token = create_access_token({"sub": user_id})

    return schemas.RegistrationResponse(
        access_token=token,
        user=schemas.UserResponse(
            id=user_id,
            email=user_data.email,
            full_name=user_data.full_name,
            role=UserRole.CLIENT,
            phone=user_data.phone,
            unread_notifications=0,
        ),
        pet=schemas.PetResponse(
            id=pet_id,
            name=pet_data.name,
            birth_date=pet_data.birth_date,
            species=pet_data.species,
            sex=pet_data.sex,
            breed_primary=pet_data.breed_primary,
            breed_secondary=pet_data.breed_secondary,
            mixed_breed=pet_data.mixed_breed,
            weight_kg=pet_data.weight_kg,
            owner_id=user_id,
            created_at=created_at,
        ),
    )


@router.post("/login", response_model=schemas.TokenResponse)
def login(credentials: schemas.UserLogin):
    """Authenticates a user by email and password, returns a JWT on success."""
    db = get_firestore_db()
    users_ref = db.collection(Collections.USERS)

    results = users_ref.where("email", "==", credentials.email).limit(1).get()

    if len(results) == 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    user_doc  = results[0]
    user_data = user_doc.to_dict()

    if (
        not user_data.get("is_active", True)
        or not verify_password(credentials.password, user_data.get("hashed_password", ""))
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if user_data.get("role") not in UserRole.AUTHENTICATED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User role is not authorized",
        )

    if password_needs_rehash(user_data["hashed_password"]):
        user_doc.reference.update({
            "hashed_password": hash_password(credentials.password),
        })

    token = create_access_token({"sub": user_doc.id})

    return schemas.TokenResponse(
        access_token=token,
        user=_user_response(user_doc.id, user_data),
    )


@router.post("/logout", status_code=204)
def logout():
    """
    Ends the user's session.
    Token invalidation is handled client-side (remove token from localStorage).
    Returns 204 No Content on success.
    """
    # JWT tokens are stateless; the client must discard the token.
    # Future enhancement: maintain a server-side token denylist if needed.
    return None


@router.get("/profile", response_model=schemas.UserResponse)
def get_profile(current_user: dict = Depends(get_current_user)):
    """Returns the profile data of the currently authenticated user."""
    return _user_response(current_user["id"], current_user)


@router.put("/profile", response_model=schemas.UserResponse)
def update_profile(
    profile_data: schemas.UserProfileUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Updates the authenticated user's personal information."""
    db = get_firestore_db()
    user_ref = db.collection(Collections.USERS).document(current_user["id"])

    update_fields = profile_data.model_dump(exclude_unset=True)

    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields provided for update",
        )

    # Prevent email duplication if the email is being changed
    if "email" in update_fields and update_fields["email"] != current_user["email"]:
        existing = (
            db.collection(Collections.USERS)
            .where("email", "==", update_fields["email"])
            .limit(1)
            .get()
        )
        if len(existing) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email address is already in use",
            )

    user_ref.update(update_fields)

    updated = user_ref.get().to_dict()
    return _user_response(current_user["id"], updated)


@router.put("/profile/password", status_code=204)
def update_password(
    password_data: schemas.UserPasswordUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Updates the authenticated user's password after verifying the current one."""
    if not verify_password(
        password_data.current_password,
        current_user.get("hashed_password", ""),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    db = get_firestore_db()
    user_ref = db.collection(Collections.USERS).document(current_user["id"])
    user_ref.update({"hashed_password": hash_password(password_data.new_password)})
    return None


@router.post("/profile/photo", response_model=schemas.UserResponse)
async def upload_profile_photo(
    photo: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Uploads a client profile image to Firebase Storage."""
    extension = PROFILE_IMAGE_TYPES.get(photo.content_type)
    if not extension:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Profile image must be JPEG, PNG, or WebP",
        )

    content = await photo.read(MAX_PROFILE_IMAGE_BYTES + 1)
    if len(content) > MAX_PROFILE_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Profile image cannot exceed 5 MB",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Profile image is empty",
        )

    try:
        bucket = get_storage_bucket()
        object_name = (
            f"profile-images/{current_user['id']}/{uuid4().hex}.{extension}"
        )
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

    db = get_firestore_db()
    user_ref = db.collection(Collections.USERS).document(current_user["id"])
    user_ref.update({"profile_image_url": image_url})
    updated = user_ref.get().to_dict()
    return _user_response(current_user["id"], updated)
