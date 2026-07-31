"""Admin-only endpoints for managing veterinarians."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_roles
from app.constant import ApiPrefix, UserRole
from app.schemas.vet import VetRegister, VetResponse
from app.services.vet_service import register_veterinarian

router = APIRouter(
    prefix=ApiPrefix.ADMIN,
    tags=["Admin"]
)


@router.post("/veterinarians", response_model=VetResponse, status_code=201)
def create_veterinarian(
    vet_data: VetRegister,
    current_user: dict = Depends(require_roles([UserRole.ADMIN])),
):
    """
    Registra un nuevo veterinario.
    SOLO ACCESIBLE PARA ADMINISTRADORES.
    """
    try:
        admin_id = current_user.get("id")
        if not admin_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Admin ID not found",
            )
        
        result = register_veterinarian(vet_data, admin_id)
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating veterinarian: {str(e)}",
        )