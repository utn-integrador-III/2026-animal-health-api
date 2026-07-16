"""Compatibility exports for the application routers."""

from .api.v1.endpoints import appointment_routes, auth_routes, pet_routes

__all__ = ["appointment_routes", "auth_routes", "pet_routes"]
