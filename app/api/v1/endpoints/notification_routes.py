"""Notification endpoints for users."""

from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import require_roles
from app.constant import ApiPrefix, Collections, UserRole
from app.firebase_config import get_firestore_db
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
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN))
):
    """Get all notifications for the authenticated user."""
    try:
        user_id = current_user.get("uid") or current_user.get("id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found")

        service = NotificationService()
        try:
            await service.check_medications_due_for_notification(check_time=False)
        except Exception:
            pass

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
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN))
):
    """Mark a specific notification as read."""
    try:
        user_id = current_user.get("uid") or current_user.get("id")
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
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN))
):
    """Mark all notifications for the authenticated user as read."""
    try:
        user_id = current_user.get("uid") or current_user.get("id")
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
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN))
):
    """Delete a specific notification."""
    try:
        user_id = current_user.get("uid") or current_user.get("id")
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
    current_user: dict = Depends(require_roles(UserRole.CLIENT, UserRole.VETERINARIAN))
):
    """Get the number of unread notifications for the authenticated user."""
    try:
        user_id = current_user.get("uid") or current_user.get("id")
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


@router.post("/check-medications", status_code=status.HTTP_200_OK)
async def trigger_medication_check():
    """Manually check medications and create notifications for today."""
    try:
        service = NotificationService()
        result = await service.check_medications_due_for_notification()
        return result
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{notification_id}/take", status_code=status.HTTP_200_OK)
async def take_medication_notification(
    notification_id: str,
    current_user: dict = Depends(require_roles(UserRole.CLIENT))
):
    """Mark notification as read and add today's date to medication checked_dates."""
    try:
        user_id = current_user.get("uid") or current_user.get("id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found")

        db = get_firestore_db()
        notif_ref = db.collection(Collections.NOTIFICATIONS).document(notification_id)
        notif_snapshot = notif_ref.get()

        if not notif_snapshot.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

        notif_data = notif_snapshot.to_dict()
        if notif_data.get("user_id") != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

        notif_ref.update({
            "read": True,
            "read_at": datetime.now().isoformat()
        })

        medication_id = notif_data.get("medication_id")
        pet_id = notif_data.get("pet_id")
        if medication_id and pet_id:
            med_ref = db.collection(Collections.MEDICATIONS).document(medication_id)
            med_snapshot = med_ref.get()
            if med_snapshot.exists:
                med_data = med_snapshot.to_dict()
                checked_dates = med_data.get("checked_dates", [])
                today_str = date.today().isoformat()
                if today_str not in checked_dates:
                    checked_dates.append(today_str)
                    med_ref.update({"checked_dates": checked_dates})

        return {"message": "Medication marked as taken and notification read"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{notification_id}/remind-later", status_code=status.HTTP_200_OK)
async def remind_later_notification(
    notification_id: str,
    delay_minutes: int = Query(15, ge=1, le=1440),
    current_user: dict = Depends(require_roles(UserRole.CLIENT))
):
    """Snooze notification by scheduling or postponing it."""
    try:
        user_id = current_user.get("uid") or current_user.get("id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found")

        db = get_firestore_db()
        notif_ref = db.collection(Collections.NOTIFICATIONS).document(notification_id)
        notif_snapshot = notif_ref.get()

        if not notif_snapshot.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

        notif_data = notif_snapshot.to_dict()
        if notif_data.get("user_id") != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

        notif_ref.update({
            "read": True,
            "read_at": datetime.now().isoformat()
        })

        remind_time = datetime.now() + timedelta(minutes=delay_minutes)
        snoozed_data = {
            **notif_data,
            "read": False,
            "title": f"🔔 Recordatorio (Pospuesto): {notif_data.get('title')}",
            "created_at": remind_time.isoformat(),
            "remind_at": remind_time.isoformat()
        }
        snoozed_data.pop("id", None)
        db.collection(Collections.NOTIFICATIONS).add(snoozed_data)

        return {
            "message": f"Remind later scheduled in {delay_minutes} minutes",
            "remind_at": remind_time.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))