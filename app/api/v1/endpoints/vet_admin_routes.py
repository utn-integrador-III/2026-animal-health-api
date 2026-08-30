"""Admin-only endpoints for managing veterinarians."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_roles
from app.constant import ApiPrefix, UserRole
from app.schemas.vet import VetRegister, VetResponse
from app.services.vet_service import list_veterinarians, register_veterinarian

router = APIRouter(
    prefix=ApiPrefix.ADMIN,
    tags=["Admin"]
)


@router.get("/veterinarians", response_model=List[VetResponse])
def get_veterinarians(
    current_user: dict = Depends(require_roles(UserRole.ADMIN)),
):
    """
    Lista todos los veterinarios registrados.
    SOLO ACCESIBLE PARA ADMINISTRADORES.
    """
    try:
        return list_veterinarians()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing veterinarians: {str(e)}",
        )


@router.post("/veterinarians", response_model=VetResponse, status_code=201)
def create_veterinarian(
    vet_data: VetRegister,
    current_user: dict = Depends(require_roles(UserRole.ADMIN)),
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


@router.post("/backups", status_code=201)
def trigger_backup(
    current_user: dict = Depends(require_roles(UserRole.ADMIN)),
):
    """
    Triggers an immediate database backup.
    ADMIN ONLY.
    """
    try:
        from app.services.backup_service import BackupService

        service = BackupService()
        result = service.create_backup(purge_retention_days=30)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating backup: {str(e)}",
        )


@router.get("/backups")
def list_backups(
    current_user: dict = Depends(require_roles(UserRole.ADMIN)),
):
    """
    Lists all available database backups with metadata.
    ADMIN ONLY.
    """
    try:
        from app.services.backup_service import BackupService

        service = BackupService()
        return service.list_backups()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing backups: {str(e)}",
        )


@router.post("/backups/{backup_id}/restore")
def restore_backup(
    backup_id: str,
    dry_run: bool = False,
    current_user: dict = Depends(require_roles(UserRole.ADMIN)),
):
    """
    Restores a database backup from a specific backup_id.
    Accepts `dry_run=true` query param to validate without writing.
    ADMIN ONLY.
    """
    try:
        from app.services.backup_service import BackupService

        service = BackupService()
        result = service.restore_backup(backup_id=backup_id, dry_run=dry_run)
        return result
    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(fnf),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error restoring backup: {str(e)}",
        )