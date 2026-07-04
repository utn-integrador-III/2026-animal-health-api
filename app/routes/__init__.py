from app.api.v1.endpoints.auth_routes import login, get_profile, register
from app.api.v1.endpoints.pet_routes import create_pet, list_pets, get_pet, update_pet, delete_pet

__all__ = [
    "auth_routes",
    "pet_routes",
]

from app.api.v1.endpoints import auth_routes as auth_routes_module
from app.api.v1.endpoints import pet_routes as pet_routes_module

auth_routes = auth_routes_module
pet_routes = pet_routes_module
