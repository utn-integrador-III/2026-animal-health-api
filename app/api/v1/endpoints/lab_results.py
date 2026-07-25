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
    current_user: dict = Depends(require_roles([UserRole.VETERINARIAN, UserRole.ADMIN]))
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
    current_user: dict = Depends(require_roles([UserRole.CLIENT, UserRole.VETERINARIAN, UserRole.ADMIN]))
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
    current_user: dict = Depends(require_roles([UserRole.CLIENT, UserRole.VETERINARIAN, UserRole.ADMIN]))
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
    current_user: dict = Depends(require_roles([UserRole.VETERINARIAN, UserRole.ADMIN]))
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
    current_user: dict = Depends(require_roles([UserRole.VETERINARIAN, UserRole.ADMIN]))
):
    """Delete a lab result (Veterinarian only)."""
    try:
        service = LabResultService()
        await service.delete_lab_result(result_id)
        return None
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))