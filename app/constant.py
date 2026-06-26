"""Constants required by the pet profile and pet registration stories."""


class Collections:
    USERS = "users"
    PETS = "pets"


class UserRole:
    CLIENT = "client"
    AUTHENTICATED = (CLIENT,)


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


class AuthToken:
    LOGIN_URL = f"{ApiPrefix.AUTH}/login"
    BEARER = "Bearer"
    JWT_CLAIM_SUB = "sub"
    JWT_CLAIM_EXP = "exp"