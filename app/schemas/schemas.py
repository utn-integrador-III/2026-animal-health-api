"""Schemas required by DB-US-02 and FE-US-02."""

from datetime import date, time
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
    photo_url: Optional[str] = None


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
    """PUT /auth/profile editable fields only."""

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


class UserPasswordUpdate(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_password_confirmation(self):
        if self.new_password != self.confirm_password:
            raise ValueError("New password and confirmation do not match")
        return self


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class ClientUpdate(BaseModel):
    """PUT /clients/{id} partial update."""

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


class AppointmentStatus:
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class AppointmentCreate(BaseModel):
    pet_id: str = Field(min_length=1)
    appointment_date: date
    appointment_time: time
    duration_blocks: int = Field(default=1, ge=1, le=4)
    reason: str = Field(min_length=3, max_length=300)
    veterinarian_id: str = Field(min_length=1)

    @field_validator("appointment_date")
    @classmethod
    def validate_appointment_date(cls, value: date) -> date:
        if value < date.today():
            raise ValueError("Appointment date cannot be in the past")
        return value

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class AppointmentFollowUpCreate(BaseModel):
    pet_id: str = Field(min_length=1)
    appointment_date: date
    appointment_time: time
    duration_blocks: int = Field(default=1, ge=1, le=4)
    reason: str = Field(min_length=3, max_length=300)

    @field_validator("appointment_date")
    @classmethod
    def validate_appointment_date(cls, value: date) -> date:
        if value < date.today():
            raise ValueError("Appointment date cannot be in the past")
        return value

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class AppointmentUpdate(BaseModel):
    appointment_date: Optional[date] = None
    appointment_time: Optional[time] = None
    duration_blocks: Optional[int] = Field(default=None, ge=1, le=4)
    reason: Optional[str] = Field(default=None, min_length=3, max_length=300)
    veterinarian_id: Optional[str] = Field(default=None, min_length=1)

    @field_validator("appointment_date")
    @classmethod
    def validate_appointment_date(cls, value: Optional[date]) -> Optional[date]:
        if value is not None and value < date.today():
            raise ValueError("Appointment date cannot be in the past")
        return value

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value


class AppointmentComplete(BaseModel):
    clinical_observation: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("clinical_observation")
    @classmethod
    def strip_clinical_observation(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value


class AppointmentResponse(BaseModel):
    id: str
    pet_id: str
    pet_name: str
    pet_species: str
    pet_sex: Optional[str] = None
    pet_birth_date: Optional[date] = None
    pet_weight_kg: Optional[float] = None
    owner_id: str
    owner_name: Optional[str] = None
    pet_breed: Optional[str] = None
    pet_photo_url: Optional[str] = None
    last_visit: Optional[str] = "--"
    appointment_date: date
    appointment_time: time
    duration_blocks: int = 1
    reason: str
    veterinarian_id: str
    veterinarian_name: str
    status: str
    created_at: str
    updated_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    completed_at: Optional[str] = None
    clinical_observation: Optional[str] = None


class VeterinarianOption(BaseModel):
    id: str
    full_name: str
    email: str


class AvailableSlotsResponse(BaseModel):
    date: date
    veterinarian_id: str
    slots: List[str]


class VaccineCreate(BaseModel):
    """Payload sent by the vet when applying a vaccine to a pet."""

    name: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=200)           # disease it prevents
    brand: str = Field(min_length=1, max_length=120)
    batch_number: Optional[str] = Field(default=None, max_length=80)
    scheduled_date: date                                       # application date
    expiration_date: Optional[date] = None
    next_dose: Optional[date] = None
    administration_route: str = Field(default="SubcutÃ¡nea", max_length=80)
    dose: str = Field(default="1", max_length=20)
    unit: str = Field(default="dosis", max_length=30)
    raw_status: str = Field(default="Aplicada correctamente", max_length=80)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("name", "type", "brand", "administration_route")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


class VaccineResponse(BaseModel):
    """Full vaccine record returned from Firestore."""

    id: str
    pet_id: str
    name: str
    type: str
    brand: str
    batch_number: Optional[str] = None
    scheduled_date: str
    expiration_date: Optional[str] = None
    next_dose: Optional[str] = None
    administration_route: str
    dose: str
    unit: str
    raw_status: str
    status: str                        
    notes: Optional[str] = None
    veterinarian_id: str
    veterinarian_name: str
    created_at: str


class ClinicalRecordCreate(BaseModel):
    diagnosis: str = Field(min_length=2, max_length=300)
    treatment: str = Field(min_length=2, max_length=500)
    weight_kg: Optional[float] = Field(default=None, gt=0, le=999)
    notes: Optional[str] = Field(default=None, max_length=2000)
    date: date

    @field_validator("diagnosis", "treatment")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


class ClinicalRecordResponse(BaseModel):
    id: str
    pet_id: str
    veterinarian_id: str
    veterinarian_name: str
    diagnosis: str
    treatment: str
    weight_kg: Optional[float] = None
    notes: Optional[str] = None
    date: str
    created_at: str



class WalkInClientPet(BaseModel):
    id: str
    name: str
    species: str
    sex: str
    breed_primary: str
    birth_date: date
    weight_kg: float
    photo_url: Optional[str] = None


class WalkInClientLookupResponse(BaseModel):
    client: Optional[UserResponse] = None
    pets: List[WalkInClientPet] = []


class WalkInConsultationCreate(BaseModel):
    client_id: Optional[str] = None
    client_name: str = Field(min_length=3, max_length=120)
    client_email: str = Field(min_length=5, max_length=254)
    client_phone: Optional[str] = Field(default=None, max_length=20)
    pet_id: Optional[str] = None
    pet_name: Optional[str] = Field(default=None, min_length=2, max_length=60)
    pet_birth_date: Optional[date] = None
    pet_species: Optional[str] = None
    pet_sex: Optional[str] = None
    pet_breed: Optional[str] = Field(default=None, min_length=2, max_length=80)
    pet_weight_kg: Optional[float] = Field(default=None, gt=0, le=999)
    reason: str = Field(min_length=3, max_length=300)

    @field_validator("client_email")
    @classmethod
    def normalize_client_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("Invalid email address")
        return value

    @field_validator("client_name", "reason")
    @classmethod
    def strip_required_walk_in_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("client_phone", "pet_name", "pet_breed")
    @classmethod
    def strip_optional_walk_in_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value and value.strip() else value

    @field_validator("pet_species")
    @classmethod
    def validate_walk_in_species(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in PetSpecies.ALLOWED:
            raise ValueError("Unsupported pet species")
        return value

    @field_validator("pet_sex")
    @classmethod
    def validate_walk_in_sex(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in PetSex.ALLOWED:
            raise ValueError("Sex must be Female or Male")
        return value

    @field_validator("pet_birth_date")
    @classmethod
    def validate_walk_in_birth_date(cls, value: Optional[date]) -> Optional[date]:
        if value is not None and value > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return value

    @model_validator(mode="after")
    def validate_existing_or_new_pet(self):
        if self.pet_id:
            return self
        missing = [
            field for field in ("pet_name", "pet_birth_date", "pet_species", "pet_sex", "pet_breed", "pet_weight_kg")
            if getattr(self, field) in (None, "")
        ]
        if missing:
            raise ValueError("New walk-in consultations require complete pet information")
        return self


class WalkInConsultationResponse(BaseModel):
    id: str
    client_id: str
    owner_name: str
    owner_email: str
    owner_phone: Optional[str] = None
    pet_id: str
    pet_name: str
    pet_species: str
    pet_sex: str
    pet_breed: str
    pet_weight_kg: float
    pet_photo_url: Optional[str] = None
    reason: str
    veterinarian_id: str
    veterinarian_name: str
    status: str
    source: str
    created_at: str


class DiagnosisCreate(BaseModel):
    consultation_id: str = Field(min_length=1)
    pet_id: str = Field(min_length=1)
    diagnosis: str = Field(min_length=2, max_length=300)
    clinical_notes: str = Field(min_length=2, max_length=2000)

    @field_validator("diagnosis", "clinical_notes")
    @classmethod
    def strip_diagnosis_text(cls, value: str) -> str:
        return value.strip()


class DiagnosisResponse(BaseModel):
    id: str
    consultation_id: str
    pet_id: str
    diagnosis: str
    clinical_notes: str
    veterinarian_id: str
    veterinarian_name: str
    created_at: str

class MedicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    dosage: str = Field(min_length=1, max_length=100)
    frequency: str = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date
    administration_time: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("name", "dosage", "frequency")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


class MedicationResponse(BaseModel):
    id: str
    pet_id: str
    veterinarian_id: str
    veterinarian_name: str
    name: str
    dosage: str
    frequency: str
    start_date: str
    end_date: str
    administration_time: Optional[str] = None
    notes: Optional[str] = None
    status: str  # "active" | "completed"
    checked_dates: List[str] = []
    created_at: str


class MedicationCheckToggle(BaseModel):
    date: date


class AllergyCreate(BaseModel):
    allergen: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=80)  # e.g., food, environmental, medication, other
    severity: str = Field(min_length=1, max_length=80)  # e.g., mild, moderate, severe
    reaction: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("allergen", "category", "severity")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


class AllergyUpdate(BaseModel):
    allergen: Optional[str] = Field(default=None, min_length=1, max_length=120)
    category: Optional[str] = Field(default=None, min_length=1, max_length=80)
    severity: Optional[str] = Field(default=None, min_length=1, max_length=80)
    reaction: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("allergen", "category", "severity")
    @classmethod
    def strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return value.strip()


class AllergyResponse(BaseModel):
    id: str
    pet_id: str
    allergen: str
    category: str
    severity: str
    reaction: Optional[str] = None
    notes: Optional[str] = None
    registered_by: str
    veterinarian_id: Optional[str] = None
    veterinarian_name: Optional[str] = None
    created_at: str
    updated_at: str
