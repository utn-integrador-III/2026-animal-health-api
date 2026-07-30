"""Lab result schemas for API requests and responses."""

from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel


class LabResultBase(BaseModel):
    """Base Lab Result schema."""
    pet_id: str
    test_type: str
    test_date: date
    clinical_observations: str
    result_summary: Optional[str] = None
    attachments: Optional[List[str]] = None


class LabResultCreate(LabResultBase):
    """Lab result creation schema."""
    pass


class LabResultUpdate(BaseModel):
    """Lab result update schema."""
    test_type: Optional[str] = None
    test_date: Optional[date] = None
    clinical_observations: Optional[str] = None
    result_summary: Optional[str] = None
    attachments: Optional[List[str]] = None


class LabResultResponse(LabResultBase):
    """Lab result response schema."""
    id: str
    owner_id: str
    veterinarian_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LabResultListResponse(BaseModel):
    """Response for list of lab results."""
    results: List[LabResultResponse]
    total: int