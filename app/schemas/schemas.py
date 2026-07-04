"""Schemas required by DB-US-02 and FE-US-02."""

from datetime import date
import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from ..constant import PetSpecies, PetSex

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PetCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    birth_date: date
    species: str
    sex: str
    breed_primary: str = Field(min_length=2, max_length=80)
    breed_secondary: Optional[str] = Field(default=None, max_length=80)
    mixed_breed: bool = False
    weight_kg: float = Field(gt=0, le=999)

    @field_validator("name", "breed_primary")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("breed_secondary")
    @classmethod
    def normalize_secondary_breed(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value and value.strip() else None

    @field_validator("species")
    @classmethod
    def validate_species(cls, value: str) -> str:
        if value not in PetSpecies.ALLOWED:
            raise ValueError("Unsupported pet species")
        return value

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, value: str) -> str:
        if value not in PetSex.ALLOWED:
            raise ValueError("Sex must be Female or Male")
        return value

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return value

    @model_validator(mode="after")
    def normalize_mixed_breed(self):
        self.mixed_breed = bool(self.breed_secondary)
        return self

"""Partial update. Endpoint PUT /pets/{id}"""
class PetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=60)
    birth_date: Optional[date] = None
    species: Optional[str] = None
    sex: Optional[str] = None
    breed_primary: Optional[str] = Field(default=None, min_length=2, max_length=80)
    breed_secondary: Optional[str] = Field(default=None, max_length=80)
    mixed_breed: Optional[bool] = None
    weight_kg: Optional[float] = Field(default=None, gt=0, le=999)

    @field_validator("species")
    @classmethod
    def validate_species(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in PetSpecies.ALLOWED:
            raise ValueError("Unsupported pet species")
        return value

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in PetSex.ALLOWED:
            raise ValueError("Sex must be Female or Male")
        return value

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value: Optional[date]) -> Optional[date]:
        if value is not None and value > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return value

    @model_validator(mode="after")
    def normalize_mixed_breed(self):
        if self.breed_secondary is not None:
            self.breed_secondary = self.breed_secondary.strip() or None
            self.mixed_breed = bool(self.breed_secondary)
        return self

"""Full pet response including all fields and metadata."""
class PetResponse(BaseModel):
    id: str
    name: str
    birth_date: date
    species: str
    sex: str
    breed_primary: str
    breed_secondary: Optional[str] = None
    mixed_breed: bool
    weight_kg: float
    owner_id: str
    created_at: str


class UserRegister(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=3, max_length=120)
    phone: str = Field(min_length=8, max_length=20)
    initial_pet: PetCreate

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Invalid email address")
        return value

    @field_validator("full_name", "phone")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be empty")
        return value


class UserLogin(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Invalid email address")
        return value


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    phone: Optional[str] = None
    profile_image_url: Optional[str] = None
    unread_notifications: int = 0


class UserProfileUpdate(BaseModel):
    """PUT /auth/profile â€” editable fields only."""

    full_name: Optional[str] = Field(default=None, min_length=3, max_length=120)
    phone: Optional[str] = Field(default=None, min_length=8, max_length=20)
    email: Optional[str] = Field(default=None, min_length=5, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_optional_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Invalid email address")
        return value

    @field_validator("full_name", "phone")
    @classmethod
    def strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be empty")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class ClientUpdate(BaseModel):
    """PUT /clients/{id} â€” partial update."""

    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class ClientResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    phone: Optional[str] = None
    is_active: bool = True
    created_at: str


class ContactMessageCreate(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    phone: Optional[str] = Field(default=None, max_length=20)
    subject: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=10, max_length=2000)

    @field_validator("email")
    @classmethod
    def normalize_contact_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Invalid email address")
        return value

    @field_validator("name", "subject", "message")
    @classmethod
    def strip_contact_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("phone")
    @classmethod
    def strip_contact_phone(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value and value.strip() else None


class ContactMessageResponse(BaseModel):
    id: str
    status: str
    created_at: str
    
class RegistrationResponse(TokenResponse):
    pet: PetResponse

