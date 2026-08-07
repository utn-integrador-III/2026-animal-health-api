"""Diagnosis model for Firestore."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DiagnosisBase(BaseModel):
    """Base Diagnosis model."""
    pet_id: str
    diagnosis: str
    consultation_id: Optional[str] = None
    clinical_notes: Optional[str] = None
    presumptive_diagnosis: Optional[str] = None
    differential_diagnoses: Optional[str] = None
    status: Optional[str] = "Presuntivo"
    treatment: Optional[str] = None
    notes: Optional[str] = None
    consultation_date: Optional[str] = None
    reason: Optional[str] = None
    symptoms: Optional[str] = None
    physical_exam: Optional[str] = None
    clinical_plan: Optional[str] = None
    owner_instructions: Optional[str] = None
    follow_up: Optional[str] = None
    weight_kg: Optional[str] = None
    temperature_c: Optional[str] = None
    heart_rate_bpm: Optional[str] = None
    respiratory_rate_rpm: Optional[str] = None
    systems_eval: Optional[dict] = None
    follow_up_date: Optional[str] = None
    follow_up_reason: Optional[str] = None


class DiagnosisCreate(DiagnosisBase):
    """Diagnosis creation model."""
    pass


class DiagnosisUpdate(BaseModel):
    """Diagnosis update model."""
    diagnosis: Optional[str] = None
    presumptive_diagnosis: Optional[str] = None
    differential_diagnoses: Optional[str] = None
    status: Optional[str] = None
    treatment: Optional[str] = None
    notes: Optional[str] = None
    consultation_date: Optional[str] = None
    reason: Optional[str] = None
    symptoms: Optional[str] = None
    physical_exam: Optional[str] = None
    clinical_plan: Optional[str] = None
    owner_instructions: Optional[str] = None
    follow_up: Optional[str] = None
    weight_kg: Optional[str] = None
    temperature_c: Optional[str] = None
    heart_rate_bpm: Optional[str] = None
    respiratory_rate_rpm: Optional[str] = None
    systems_eval: Optional[dict] = None
    follow_up_date: Optional[str] = None
    follow_up_reason: Optional[str] = None


class DiagnosisInDB(DiagnosisBase):
    """Diagnosis model as stored in Firestore."""
    id: str
    registered_by: str  # "veterinarian"
    veterinarian_id: Optional[str] = None
    veterinarian_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
