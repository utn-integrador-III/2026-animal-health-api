"""Allergy model for Firestore."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AllergyBase(BaseModel):
    """Base Allergy model."""
    pet_id: str
    allergen: str
    category: str  # food, environmental, medication, other
    severity: str  # mild, moderate, severe
    reaction: Optional[str] = None
    notes: Optional[str] = None


class AllergyCreate(AllergyBase):
    """Allergy creation model."""
    pass


class AllergyUpdate(BaseModel):
    """Allergy update model."""
    allergen: Optional[str] = None
    category: Optional[str] = None
    severity: Optional[str] = None
    reaction: Optional[str] = None
    notes: Optional[str] = None


class AllergyInDB(AllergyBase):
    """Allergy model as stored in Firestore."""
    id: str
    registered_by: str  # "client" or "veterinarian"
    veterinarian_id: Optional[str] = None
    veterinarian_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
