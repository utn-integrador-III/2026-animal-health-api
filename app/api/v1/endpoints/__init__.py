# Animal Health API Routes
from .vet_admin_routes import router as vet_admin_routes
__all__ = [
    "appointment_routes",
    "auth_routes",
    "client_routes",
    "pet_routes",
    "notification_routes",
    "lab_results",
    "vet_admin_routes",  
]