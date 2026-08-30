"""Pet model for Firestore."""

from datetime import date
from typing import Optional
from pydantic import BaseModel


class PetBase(BaseModel):
    """Base Pet model."""
    name: str
    species: str
    breed: Optional[str] = None
    sex: str
    birth_date: Optional[date] = None
    weight: Optional[float] = None
    color: Optional[str] = None
    microchip_id: Optional[str] = None
    owner_id: str  # ← ¡Importante! Para saber a quién notificar
    owner_name: Optional[str] = None
    profile_image: Optional[str] = None


class PetCreate(PetBase):
    """Pet creation model."""
    pass


class PetUpdate(BaseModel):
    """Pet update model."""
    name: Optional[str] = None
    species: Optional[str] = None
    breed: Optional[str] = None
    sex: Optional[str] = None
    birth_date: Optional[date] = None
    weight: Optional[float] = None
    color: Optional[str] = None
    microchip_id: Optional[str] = None
    owner_name: Optional[str] = None
    profile_image: Optional[str] = None


class PetInDB(PetBase):
    """Pet model as stored in Firestore."""
    id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None