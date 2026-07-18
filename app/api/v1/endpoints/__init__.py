from .appointment_routes import router as appointment_routes
from .auth_routes import router as auth_routes
from .client_routes import router as client_routes
from .pet_routes import router as pet_routes
from .notification_routes import router as notification_routes
from .lab_results import router as lab_results  # ← NUEVA LÍNEA

__all__ = [
    "appointment_routes",
    "auth_routes",
    "client_routes",
    "pet_routes",
    "notification_routes",
    "lab_results",  # ← NUEVA LÍNEA
]