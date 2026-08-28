"""Lab result schemas for API requests and responses."""

from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel


class LabResultBase(BaseModel):
    """Base Lab Result schema."""
    pet_id: Optional[str] = None
    owner_id: Optional[str] = None
    veterinarian_id: Optional[str] = None
    veterinarian_name: Optional[str] = None
    request_id: Optional[str] = None
    test_type: str
    priority: Optional[str] = "Normal"
    reason: Optional[str] = None
    clinical_observations: Optional[str] = ""
    status: Optional[str] = "Solicitado"
    requested_at: Optional[str] = None
    test_date: Optional[date] = None
    result_date: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    summary: Optional[str] = None
    result_summary: Optional[str] = None
    observations: Optional[str] = None
    recommendation: Optional[str] = None
    attachments: Optional[List[str]] = None


class LabResultCreate(BaseModel):
    """Lab result creation schema."""
    pet_id: Optional[str] = None
    test_type: str
    priority: Optional[str] = "Normal"
    reason: Optional[str] = None
    clinical_observations: Optional[str] = ""
    status: Optional[str] = "Solicitado"
    requested_at: Optional[str] = None
    test_date: Optional[date] = None
    result_date: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    summary: Optional[str] = None
    result_summary: Optional[str] = None
    observations: Optional[str] = None
    recommendation: Optional[str] = None
    attachments: Optional[List[str]] = None
    veterinarian_id: Optional[str] = None
    veterinarian_name: Optional[str] = None


class LabResultUpdate(BaseModel):
    """Lab result update schema."""
    test_type: Optional[str] = None
    priority: Optional[str] = None
    reason: Optional[str] = None
    clinical_observations: Optional[str] = None
    status: Optional[str] = None
    requested_at: Optional[str] = None
    test_date: Optional[date] = None
    result_date: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    summary: Optional[str] = None
    result_summary: Optional[str] = None
    observations: Optional[str] = None
    recommendation: Optional[str] = None
    attachments: Optional[List[str]] = None
    veterinarian_id: Optional[str] = None
    veterinarian_name: Optional[str] = None


class LabResultResponse(LabResultBase):
    """Lab result response schema."""
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LabResultListResponse(BaseModel):
    """Response for list of lab results."""
    results: List[LabResultResponse]
    total: int