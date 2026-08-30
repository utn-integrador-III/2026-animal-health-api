from datetime import date, timedelta
import pytest
from pydantic import ValidationError

from app.schemas import schemas


def test_pet_create_validators():
    # Valid pet
    pet = schemas.PetCreate(
        name="  Luna  ",
        birth_date=date.today(),
        species="Dog",
        sex="Female",
        breed_primary="  Poodle  ",
        breed_secondary="  Golden Retriever  ",
        weight_kg=5.0,
    )
    assert pet.name == "Luna"
    assert pet.breed_primary == "Poodle"
    assert pet.breed_secondary == "Golden Retriever"
    assert pet.mixed_breed is True

    # Secondary breed whitespace only
    pet2 = schemas.PetCreate(
        name="Luna",
        birth_date=date.today(),
        species="Dog",
        sex="Female",
        breed_primary="Poodle",
        breed_secondary="   ",
        weight_kg=5.0,
    )
    assert pet2.breed_secondary is None
    assert pet2.mixed_breed is False

    # Invalid sex
    with pytest.raises(ValidationError) as exc:
        schemas.PetCreate(
            name="Luna",
            birth_date=date.today(),
            species="Dog",
            sex="Unknown",
            breed_primary="Poodle",
            weight_kg=5.0,
        )
    assert "Sex must be Female or Male" in str(exc.value)

    # Birth date in future
    future_date = date.today() + timedelta(days=5)
    with pytest.raises(ValidationError) as exc:
        schemas.PetCreate(
            name="Luna",
            birth_date=future_date,
            species="Dog",
            sex="Female",
            breed_primary="Poodle",
            weight_kg=5.0,
        )
    assert "Date of birth cannot be in the future" in str(exc.value)


def test_pet_update_validators():
    # Unsupported species
    with pytest.raises(ValidationError) as exc:
        schemas.PetUpdate(species="Alien")
    assert "Unsupported pet species" in str(exc.value)

    # Invalid sex
    with pytest.raises(ValidationError) as exc:
        schemas.PetUpdate(sex="Other")
    assert "Sex must be Female or Male" in str(exc.value)

    # Birth date in future
    future_date = date.today() + timedelta(days=5)
    with pytest.raises(ValidationError) as exc:
        schemas.PetUpdate(birth_date=future_date)
    assert "Date of birth cannot be in the future" in str(exc.value)

    # Normalize mixed breed on update
    upd = schemas.PetUpdate(breed_secondary="   ")
    assert upd.breed_secondary is None
    assert upd.mixed_breed is False


def test_user_register_validators():
    # Invalid email
    with pytest.raises(ValidationError) as exc:
        schemas.UserRegister(
            email="invalid-email",
            password="password123",
            full_name="User",
            phone="12345678",
            initial_pet=schemas.PetCreate(
                name="Luna", birth_date=date.today(), species="Dog", sex="Female", breed_primary="Poodle", weight_kg=5.0
            ),
        )
    assert "Invalid email address" in str(exc.value)

    # Empty full name
    with pytest.raises(ValidationError) as exc:
        schemas.UserRegister(
            email="valid@example.com",
            password="password123",
            full_name="   ",
            phone="12345678",
            initial_pet=schemas.PetCreate(
                name="Luna", birth_date=date.today(), species="Dog", sex="Female", breed_primary="Poodle", weight_kg=5.0
            ),
        )
    assert "Field cannot be empty" in str(exc.value)


def test_user_login_validators():
    with pytest.raises(ValidationError) as exc:
        schemas.UserLogin(email="not-an-email", password="password123")
    assert "Invalid email address" in str(exc.value)


def test_user_profile_update_validators():
    # None email & phone
    upd = schemas.UserProfileUpdate(email=None, phone=None, full_name=None)
    assert upd.email is None
    assert upd.phone is None
    assert upd.full_name is None

    # Invalid email
    with pytest.raises(ValidationError) as exc:
        schemas.UserProfileUpdate(email="bademail")
    assert "Invalid email address" in str(exc.value)

    # Empty name
    with pytest.raises(ValidationError) as exc:
        schemas.UserProfileUpdate(full_name="   ")
    assert "Field cannot be empty" in str(exc.value)


def test_user_password_update_validators():
    with pytest.raises(ValidationError) as exc:
        schemas.UserPasswordUpdate(
            current_password="oldpass",
            new_password="newpassword123",
            confirm_password="differentpassword123",
        )
    assert "New password and confirmation do not match" in str(exc.value)


def test_contact_message_create_validators():
    with pytest.raises(ValidationError) as exc:
        schemas.ContactMessageCreate(
            name="Test User",
            email="invalidemail",
            subject="Consulta",
            message="Mensaje de prueba de al menos 10 caracteres",
        )
    assert "Invalid email address" in str(exc.value)


def test_appointment_create_validators():
    past_date = date.today() - timedelta(days=5)
    with pytest.raises(ValidationError) as exc:
        schemas.AppointmentCreate(
            pet_id="pet-1",
            appointment_date=past_date,
            appointment_time="09:00",
            reason="Consulta general",
            veterinarian_id="vet-1",
        )
    assert "Appointment date cannot be in the past" in str(exc.value)

    app = schemas.AppointmentCreate(
        pet_id="pet-1",
        appointment_date=date.today(),
        appointment_time="09:00",
        reason="   Consulta general   ",
        veterinarian_id="vet-1",
    )
    assert app.reason == "Consulta general"


def test_appointment_follow_up_create_validators():
    past_date = date.today() - timedelta(days=5)
    with pytest.raises(ValidationError) as exc:
        schemas.AppointmentFollowUpCreate(
            pet_id="pet-1",
            appointment_date=past_date,
            appointment_time="09:00",
            reason="Seguimiento",
        )
    assert "Appointment date cannot be in the past" in str(exc.value)

    follow_up = schemas.AppointmentFollowUpCreate(
        pet_id="pet-1",
        appointment_date=date.today(),
        appointment_time="09:00",
        reason="  Seguimiento  ",
    )
    assert follow_up.reason == "Seguimiento"


def test_appointment_update_validators():
    past_date = date.today() - timedelta(days=5)
    with pytest.raises(ValidationError) as exc:
        schemas.AppointmentUpdate(appointment_date=past_date)
    assert "Appointment date cannot be in the past" in str(exc.value)

    app_upd = schemas.AppointmentUpdate(reason="  Motivo actualizado  ")
    assert app_upd.reason == "Motivo actualizado"


def test_appointment_complete_validators():
    comp = schemas.AppointmentComplete(clinical_observation="  Observación clínica  ")
    assert comp.clinical_observation == "Observación clínica"


def test_walk_in_consultation_create_validators():
    # Invalid email
    with pytest.raises(ValidationError) as exc:
        schemas.WalkInConsultationCreate(
            client_name="Walkin Client",
            client_email="bademail",
            reason="Urgencia",
            pet_id="pet-1",
        )
    assert "Invalid email address" in str(exc.value)

    # Invalid species
    with pytest.raises(ValidationError) as exc:
        schemas.WalkInConsultationCreate(
            client_name="Walkin Client",
            client_email="walkin@example.com",
            reason="Urgencia",
            pet_species="UnknownSpecies",
            pet_id="pet-1",
        )
    assert "Unsupported pet species" in str(exc.value)

    # Invalid sex
    with pytest.raises(ValidationError) as exc:
        schemas.WalkInConsultationCreate(
            client_name="Walkin Client",
            client_email="walkin@example.com",
            reason="Urgencia",
            pet_sex="UnknownSex",
            pet_id="pet-1",
        )
    assert "Sex must be Female or Male" in str(exc.value)

    # Future birth date
    future_date = date.today() + timedelta(days=5)
    with pytest.raises(ValidationError) as exc:
        schemas.WalkInConsultationCreate(
            client_name="Walkin Client",
            client_email="walkin@example.com",
            reason="Urgencia",
            pet_birth_date=future_date,
            pet_id="pet-1",
        )
    assert "Date of birth cannot be in the future" in str(exc.value)

    # Missing pet info for new pet (no pet_id)
    with pytest.raises(ValidationError) as exc:
        schemas.WalkInConsultationCreate(
            client_name="Walkin Client",
            client_email="walkin@example.com",
            reason="Urgencia",
        )
    assert "New walk-in consultations require complete pet information" in str(exc.value)

    # Missing secondary breed for mixed breed
    with pytest.raises(ValidationError) as exc:
        schemas.WalkInConsultationCreate(
            client_name="Walkin Client",
            client_email="walkin@example.com",
            reason="Urgencia",
            pet_name="Firulais",
            pet_birth_date=date.today(),
            pet_species="Dog",
            pet_sex="Male",
            pet_breed="Mestizo",
            pet_weight_kg=10.0,
            pet_mixed_breed=True,
            pet_breed_secondary=None,
        )
    assert "Mixed-breed pets require a secondary breed" in str(exc.value)


def test_allergy_update_validators():
    upd = schemas.AllergyUpdate(allergen=None, category="  Ambiental  ")
    assert upd.allergen is None
    assert upd.category == "Ambiental"
