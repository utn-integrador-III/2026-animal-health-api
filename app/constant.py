"""Constants required by the pet profile and pet registration stories."""

class Collections:
    USERS = "users"
    PETS = "pets"
    APPOINTMENTS = "appointments"
    VACCINES = "vaccines"
    MEDICAL_RECORDS = "medical_records"
    MEDICATIONS = "medications"
    CONSULTATIONS = "consultations"
    DIAGNOSES = "diagnoses"


class UserRole:
    CLIENT = "client"
    VETERINARIAN = "veterinarian"
    ADMIN = "admin"
    AUTHENTICATED = (CLIENT, VETERINARIAN)


class PetSpecies:
    ALLOWED = (
        "Dog",
        "Cat",
        "Rabbit",
        "Hamster",
        "Guinea Pig",
        "Fish",
        "Bird",
        "Turtle",
        "Ferret",
        "Chinchilla",
        "Gerbil",
        "Rat",
        "Mouse",
    )


class PetSex:
    ALLOWED = ("Female", "Male")


class ApiPrefix:
    AUTH = "/api/auth"
    PETS = "/api/pets"
    CLIENTS = "/api/clients"
    APPOINTMENTS = "/api/appointments"
    CONTACT = "/api/contact"
    CONSULTATIONS = "/api/consultations"


class AuthToken:
    LOGIN_URL = f"{ApiPrefix.AUTH}/login"
    BEARER = "Bearer"
    JWT_CLAIM_SUB = "sub"
    JWT_CLAIM_EXP = "exp"
