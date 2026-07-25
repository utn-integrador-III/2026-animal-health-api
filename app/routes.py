"""Compatibility exports for the application routers."""

from importlib import import_module

appointment_routes = import_module("app.api.v1.endpoints.appointment_routes")
auth_routes = import_module("app.api.v1.endpoints.auth_routes")
pet_routes = import_module("app.api.v1.endpoints.pet_routes")

__all__ = ["appointment_routes", "auth_routes", "pet_routes"]
