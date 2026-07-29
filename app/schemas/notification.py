"""Notification schemas for API requests and responses."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class NotificationBase(BaseModel):
    """Base Notification model."""
    user_id: str
    pet_id: str
    vaccine_id: str
    type: str = "vaccine_expiration"
    title: str
    message: str
    read: bool = False
    urgency: str = "info"
    expiration_date: Optional[str] = None
    days_until: Optional[int] = None
    link: Optional[str] = None


class NotificationCreate(NotificationBase):
    """Notification creation model."""
    pass


class NotificationUpdate(BaseModel):
    """Notification update model."""
    read: Optional[bool] = None


class NotificationInDB(NotificationBase):
    """Notification model as stored in Firestore."""
    id: str
    created_at: Optional[datetime] = None
    read_at: Optional[datetime] = None


class NotificationResponse(BaseModel):
    """Notification response model."""
    id: str
    user_id: str
    pet_id: str
    vaccine_id: str
    type: str
    title: str
    message: str
    read: bool
    urgency: str
    expiration_date: Optional[str] = None
    days_until: Optional[int] = None
    link: Optional[str] = None
    created_at: Optional[str] = None
    read_at: Optional[str] = None


class NotificationListResponse(BaseModel):
    """Response for list of notifications."""
    notifications: list[NotificationResponse]
    total: int
    unread_count: int