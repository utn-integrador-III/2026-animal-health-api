"""Compatibility exports for the application routers."""

from .api.v1.endpoints import auth_routes, pet_routes

__all__ = ["auth_routes", "pet_routes"]
