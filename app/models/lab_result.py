"""Lab result model for Firestore."""

from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel


class LabResultBase(BaseModel):
    """Base Lab Result model."""
    pet_id: str
    test_type: str
    test_date: date
    clinical_observations: str
    result_summary: Optional[str] = None
    attachments: Optional[List[str]] = None
    veterinarian_id: Optional[str] = None
    veterinarian_name: Optional[str] = None


class LabResultCreate(LabResultBase):
    """Lab result creation model."""
    pass


class LabResultUpdate(BaseModel):
    """Lab result update model."""
    test_type: Optional[str] = None
    test_date: Optional[date] = None
    clinical_observations: Optional[str] = None
    result_summary: Optional[str] = None
    attachments: Optional[List[str]] = None
    veterinarian_name: Optional[str] = None


class LabResultInDB(LabResultBase):
    """Lab result model as stored in Firestore."""
    id: str
    owner_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None