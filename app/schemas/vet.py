"""Schemas for veterinarian registration (admin only)."""

from typing import Optional
from pydantic import BaseModel, EmailStr


class VetRegister(BaseModel):
    """Esquema para registrar un nuevo veterinario (solo administradores)."""
    email: EmailStr
    password: str
    full_name: str
    phone: Optional[str] = None
    specialty: Optional[str] = None
    license_number: Optional[str] = None


class VetResponse(BaseModel):
    """Respuesta para la creación de un veterinario."""
    id: str
    email: str
    full_name: str
    role: str
    phone: Optional[str] = None
    specialty: Optional[str] = None
    license_number: Optional[str] = None
    created_at: Optional[str] = None