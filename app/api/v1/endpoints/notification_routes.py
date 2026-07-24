"""Notification endpoints for users."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import require_roles
from app.constant import ApiPrefix, UserRole
from app.schemas.notification import NotificationListResponse
from app.services.notification_service import NotificationService

router = APIRouter(
    prefix=ApiPrefix.NOTIFICATIONS,
    tags=["Notifications"]
)


@router.get("/", response_model=NotificationListResponse)
async def get_user_notifications(
    only_unread: bool = Query(False, description="Filter by unread only"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_roles([UserRole.CLIENT, UserRole.VETERINARIAN]))
):
    """Get all notifications for the authenticated user."""
    try:
        user_id = current_user.get("uid")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found")

        service = NotificationService()
        result = await service.get_user_notifications(
            user_id=user_id,
            only_unread=only_unread,
            limit=limit,
            offset=offset
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: str,
    current_user: dict = Depends(require_roles([UserRole.CLIENT, UserRole.VETERINARIAN]))
):
    """Mark a specific notification as read."""
    try:
        user_id = current_user.get("uid")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found")

        service = NotificationService()
        result = await service.mark_notification_as_read(
            user_id=user_id,
            notification_id=notification_id
        )

        if not result.get("success"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.get("error"))

        return {"message": "Notification marked as read"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/read-all")
async def mark_all_notifications_as_read(
    current_user: dict = Depends(require_roles([UserRole.CLIENT, UserRole.VETERINARIAN]))
):
    """Mark all notifications for the authenticated user as read."""
    try:
        user_id = current_user.get("uid")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found")

        service = NotificationService()
        result = await service.mark_all_notifications_as_read(user_id=user_id)

        return {
            "message": f"{result.get('marked_count', 0)} notifications marked as read",
            "marked_count": result.get("marked_count", 0)
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: dict = Depends(require_roles([UserRole.CLIENT, UserRole.VETERINARIAN]))
):
    """Delete a specific notification."""
    try:
        user_id = current_user.get("uid")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found")

        service = NotificationService()
        result = await service.delete_notification(
            user_id=user_id,
            notification_id=notification_id
        )

        if not result.get("success"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.get("error"))

        return {"message": "Notification deleted"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/unread-count")
async def get_unread_notification_count(
    current_user: dict = Depends(require_roles([UserRole.CLIENT, UserRole.VETERINARIAN]))
):
    """Get the number of unread notifications for the authenticated user."""
    try:
        user_id = current_user.get("uid")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found")

        service = NotificationService()
        result = await service.get_user_notifications(
            user_id=user_id,
            only_unread=True,
            limit=1
        )

        return {"unread_count": result.get("unread_count", 0)}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))