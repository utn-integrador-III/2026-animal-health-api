"""Vaccine model for Firestore."""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class VaccineBase(BaseModel):
    """Base Vaccine model."""
    name: str
    type: Optional[str] = None
    brand: Optional[str] = None
    batch_number: Optional[str] = None
    dose: Optional[str] = None
    administration_date: date
    expiration_date: date  # ← ¡Importante! Para saber cuándo vence
    administration_route: Optional[str] = None
    next_dose: Optional[date] = None
    pet_id: str  # ← ¡Importante! Para saber a qué mascota pertenece
    veterinarian_id: Optional[str] = None
    veterinarian_name: Optional[str] = None
    status: str = "completed"
    notes: Optional[str] = None
    # Campos para control de notificaciones
    notification_sent: bool = False
    notification_date: Optional[datetime] = None


class VaccineCreate(VaccineBase):
    """Vaccine creation model."""
    pass


class VaccineUpdate(BaseModel):
    """Vaccine update model."""
    name: Optional[str] = None
    type: Optional[str] = None
    brand: Optional[str] = None
    batch_number: Optional[str] = None
    dose: Optional[str] = None
    administration_date: Optional[date] = None
    expiration_date: Optional[date] = None
    administration_route: Optional[str] = None
    next_dose: Optional[date] = None
    veterinarian_id: Optional[str] = None
    veterinarian_name: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    notification_sent: Optional[bool] = None


class VaccineInDB(VaccineBase):
    """Vaccine model as stored in Firestore."""
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None