"""Lab result endpoints for clients and veterinarians."""

from datetime import datetime
from typing import List, Optional
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.auth import require_roles
from app.constant import ApiPrefix, Collections, UserRole
from app.firebase_config import get_firestore_db, get_storage_bucket
from app.models.lab_result import LabResultCreate, LabResultUpdate
from app.schemas.lab_result import LabResultResponse
from app.services.lab_result_service import LabResultService

router = APIRouter(
    prefix=ApiPrefix.LAB_RESULTS,
    tags=["Lab Results"]
)

ALLOWED_FILE_TYPES = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB


@router.post("/pet/{pet_id}", response_model=LabResultResponse, status_code=201)
async def create_lab_result(
    pet_id: str,
    data: LabResultCreate,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN, UserRole.ADMIN))
):
    """Create a new lab exam request for a pet (Veterinarian/Admin only)."""
    try:
        db = get_firestore_db()
        pet_doc = db.collection(Collections.PETS).document(pet_id).get()
        owner_id = current_user.get("id")
        if pet_doc.exists:
            owner_id = pet_doc.to_dict().get("owner_id") or owner_id

        vet_id = current_user.get("id") or current_user.get("uid")
        vet_name = current_user.get("full_name") or current_user.get("name") or "Veterinario"

        service = LabResultService()
        result = await service.create_lab_result(
            pet_id=pet_id,
            owner_id=owner_id,
            data=data,
            veterinarian_id=vet_id,
            veterinarian_name=vet_name,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/pet/{pet_id}", response_model=dict)
async def get_lab_results_by_pet(
    pet_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN, UserRole.ADMIN))
):
    """Get all lab results and requests for a pet."""
    try:
        service = LabResultService()
        result = await service.get_lab_results_by_pet(pet_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{result_id}", response_model=LabResultResponse)
async def get_lab_result(
    result_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN, UserRole.ADMIN))
):
    """Get a single lab result by ID."""
    try:
        service = LabResultService()
        result = await service.get_lab_result(result_id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab result not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{result_id}", response_model=LabResultResponse)
async def update_lab_result(
    result_id: str,
    data: LabResultUpdate,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN, UserRole.ADMIN))
):
    """Update a lab result (Veterinarian/Admin only)."""
    try:
        service = LabResultService()
        result = await service.update_lab_result(result_id, data)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab result not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{result_id}/upload", response_model=LabResultResponse)
async def upload_lab_result_file(
    result_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN, UserRole.ADMIN))
):
    """Upload a PDF or image report for a lab result."""
    extension = ALLOWED_FILE_TYPES.get(file.content_type)
    if not extension:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File must be PDF, JPEG, PNG, or WebP",
        )

    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File cannot exceed 15 MB",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File is empty",
        )

    service = LabResultService()
    existing = await service.get_lab_result(result_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab result not found")

    pet_id = existing.get("pet_id", "unknown")

    try:
        bucket = get_storage_bucket()
        object_name = f"lab-results/{pet_id}/{result_id}/{uuid4().hex}.{extension}"
        download_token = str(uuid4())
        blob = bucket.blob(object_name)
        blob.metadata = {"firebaseStorageDownloadTokens": download_token}
        blob.upload_from_string(content, content_type=file.content_type)
        encoded_name = quote(object_name, safe="")
        file_url = (
            "https://firebasestorage.googleapis.com/v0/b/"
            f"{bucket.name}/o/{encoded_name}?alt=media&token={download_token}"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Storage error: {exc}",
        ) from exc

    update_payload = LabResultUpdate(
        file_url=file_url,
        file_name=file.filename,
        status="Resultado disponible",
        result_date=datetime.now().strftime("%Y-%m-%d"),
    )
    updated = await service.update_lab_result(result_id, update_payload)

    # Notify pet owner of result availability
    try:
        db = get_firestore_db()
        owner_id = existing.get("owner_id")
        test_name = existing.get("test_type") or existing.get("exam_type") or "Examen de laboratorio"
        if not owner_id and pet_id:
            pdoc = db.collection(Collections.PETS).document(pet_id).get()
            if pdoc.exists:
                owner_id = pdoc.to_dict().get("owner_id")
                pet_name = pdoc.to_dict().get("name", "Mascota")
            else:
                pet_name = "Mascota"
        else:
            pet_name = "Mascota"

        if owner_id:
            notif = {
                "user_id": owner_id,
                "pet_id": pet_id,
                "type": "lab_result_available",
                "title": f"📄 Resultado de laboratorio disponible ({pet_name})",
                "message": f"El resultado del examen '{test_name}' para {pet_name} ya está disponible para consultar y descargar.",
                "read": False,
                "urgency": "info",
                "link": f"/client/lab-results?petId={pet_id}",
                "created_at": datetime.now().isoformat(),
            }
            db.collection(Collections.NOTIFICATIONS).add(notif)
    except Exception as notif_err:
        pass

    return updated


@router.delete("/{result_id}", status_code=204)
async def delete_lab_result(
    result_id: str,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN, UserRole.ADMIN))
):
    """Delete a lab result (Veterinarian/Admin only)."""
    try:
        service = LabResultService()
        await service.delete_lab_result(result_id)
        return None
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ─── Additional compatibility routes for /pets/{pet_id}/lab-results ───────────

@router.get("/pets/{pet_id}/lab-results", response_model=dict)
async def get_lab_results_by_pet_id(
    pet_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN, UserRole.ADMIN)),
):
    """Obtiene todos los resultados de laboratorio de una mascota."""
    db = get_firestore_db()
    pet_doc = db.collection(Collections.PETS).document(pet_id).get()
    if not pet_doc.exists:
        raise HTTPException(status_code=404, detail="Pet not found")
    pet_data = pet_doc.to_dict()

    user_role = current_user.get("role")
    user_id = current_user.get("id")

    if user_role == UserRole.CLIENT:
        if pet_data.get("owner_id") != user_id:
            raise HTTPException(status_code=403, detail="You do not own this pet")
    elif user_role == UserRole.VETERINARIAN:
        appointments_ref = db.collection(Collections.APPOINTMENTS)
        query = appointments_ref.where("pet_id", "==", pet_id).where("veterinarian_id", "==", user_id).limit(1)
        if not list(query.stream()):
            raise HTTPException(status_code=403, detail="You are not assigned to this pet")

    service = LabResultService()
    result = await service.get_lab_results_by_pet(pet_id)
    return result


@router.post("/pets/{pet_id}/lab-results", response_model=LabResultResponse, status_code=201)
async def create_lab_result_for_pet(
    pet_id: str,
    data: LabResultCreate,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN, UserRole.ADMIN)),
):
    """Crea un nuevo resultado de laboratorio para una mascota."""
    db = get_firestore_db()
    pet_doc = db.collection(Collections.PETS).document(pet_id).get()
    if not pet_doc.exists:
        raise HTTPException(status_code=404, detail="Pet not found")

    if current_user.get("role") == UserRole.VETERINARIAN:
        appointments_ref = db.collection(Collections.APPOINTMENTS)
        query = appointments_ref.where("pet_id", "==", pet_id).where("veterinarian_id", "==", current_user.get("id")).limit(1)
        if not list(query.stream()):
            raise HTTPException(status_code=403, detail="You are not assigned to this pet")

    owner_id = pet_doc.to_dict().get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=400, detail="Pet has no owner")

    vet_id = current_user.get("id") or current_user.get("uid")
    vet_name = current_user.get("full_name") or current_user.get("name") or "Veterinario"

    service = LabResultService()
    result = await service.create_lab_result(
        pet_id=pet_id,
        owner_id=owner_id,
        data=data,
        veterinarian_id=vet_id,
        veterinarian_name=vet_name,
    )
    return result