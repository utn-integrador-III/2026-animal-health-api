"""Lab result endpoints for clients and veterinarians."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_roles
from app.constant import ApiPrefix, UserRole
from app.models.lab_result import LabResultCreate, LabResultUpdate
from app.schemas.lab_result import LabResultResponse
from app.services.lab_result_service import LabResultService

router = APIRouter(
    prefix=ApiPrefix.LAB_RESULTS,
    tags=["Lab Results"]
)


@router.post("/pet/{pet_id}", response_model=LabResultResponse, status_code=201)
async def create_lab_result(
    pet_id: str,
    data: LabResultCreate,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN, UserRole.ADMIN))
):
    """Create a new lab result for a pet (Veterinarian only)."""
    try:
        service = LabResultService()
        result = await service.create_lab_result(
            pet_id=pet_id,
            owner_id=current_user.get("id"),
            data=data
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/pet/{pet_id}", response_model=dict)
async def get_lab_results_by_pet(
    pet_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN, UserRole.ADMIN))
):
    """Get all lab results for a pet."""
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
    """Update a lab result (Veterinarian only)."""
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


@router.delete("/{result_id}", status_code=204)
async def delete_lab_result(
    result_id: str,
    current_user: dict = Depends(require_roles(UserRole.VETERINARIAN, UserRole.ADMIN))
):
    """Delete a lab result (Veterinarian only)."""
    try:
        service = LabResultService()
        await service.delete_lab_result(result_id)
        return None
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    #  endpoints para /pets/{pet_id}/lab-results 
@router.get("/pets/{pet_id}/lab-results", response_model=dict)
async def get_lab_results_by_pet_id(
    pet_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN, UserRole.ADMIN)),
):
    
    """
    Obtiene todos los resultados de laboratorio de una mascota.
    - Cliente: solo si es el dueño.
    - Veterinario: solo si tiene una cita asignada.
    - Admin: acceso total.
    """
    from app.firebase_config import get_firestore_db
    from app.constant import Collections

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
    
    """
    Crea un nuevo resultado de laboratorio para una mascota.
    - Solo veterinarios o administradores pueden crear.
    - Verifica que la mascota exista.
    """
    from app.firebase_config import get_firestore_db
    from app.constant import Collections

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

    service = LabResultService()
    result = await service.create_lab_result(pet_id, owner_id, data)
    return result