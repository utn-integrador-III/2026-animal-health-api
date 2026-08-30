from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import ALLOWED_ORIGINS
from .api.v1.endpoints import (
    appointment_routes,
    ai_routes,
    auth_routes,
    pet_routes,
    notification_routes,
    lab_results,
    vet_admin_routes,
    contact_routes,
    consultation_routes,
)
from .utils.scheduler import start_scheduler

app = FastAPI(
    title="Animal Health Pet Profiles API",
    description="Backend for the Animal Health Management Systemâ€ UTN Integrador III",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# â”€â”€â”€ Iniciar scheduler de notificaciones â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
scheduler = start_scheduler()
# POST /api/auth/register, POST /api/auth/login,
# POST /api/auth/logout, GET /api/auth/profile, PUT /api/auth/profile
app.include_router(auth_routes.router)

# POST/GET/PUT/DELETE /api/pets, GET /api/pets/{id}/history
app.include_router(pet_routes.router)

# â”€â”€â”€ Appointments â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
app.include_router(appointment_routes.router)  

# â”€â”€â”€ Notifications â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
app.include_router(notification_routes.router)

# â”€â”€â”€ Lab Results â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
app.include_router(lab_results.router)

# AI-assisted breed risk alerts.
app.include_router(ai_routes.router)

# Public contact form.
app.include_router(contact_routes.router)

# External walk-in consultations and diagnoses.
app.include_router(consultation_routes.router)

# â”€â”€â”€ Admin: veterinarian management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
app.include_router(vet_admin_routes)

@app.get("/")
def root():
    return {
        "message": "Animal Health API",
        "docs": "/docs",
        "version": "1.0.0",
    }



@app.get("/health")
def health_check():
    return {"status": "ok"}


# â”€â”€â”€ Shutdown event â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.on_event("shutdown")
def shutdown_scheduler():
    """Shutdown the scheduler when the app stops."""
    if scheduler and scheduler.running:
        scheduler.shutdown()
        print("Scheduler shut down")

