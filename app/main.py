from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import ALLOWED_ORIGINS
from .api.v1.endpoints import (
    appointment_routes,
    auth_routes,
    pet_routes,
    notification_routes,
    lab_results,
    vet_admin_routes,  
)
from .utils.scheduler import start_scheduler

app = FastAPI(
    title="Animal Health Pet Profiles API",
    description="Backend for the Animal Health Management System” UTN Integrador III",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ─── Iniciar scheduler de notificaciones ────────────────────────────────────
scheduler = start_scheduler()
# POST /api/auth/register, POST /api/auth/login,
# POST /api/auth/logout, GET /api/auth/profile, PUT /api/auth/profile
app.include_router(auth_routes.router)

# POST/GET/PUT/DELETE /api/pets, GET /api/pets/{id}/history
app.include_router(pet_routes.router)

# ─── Appointments ──────────────────────────────────────────────────────────
app.include_router(appointment_routes.router)  

# ─── Notifications ──────────────────────────────────────────────────────────
app.include_router(notification_routes.router)

# ─── Lab Results ──────────────────────────────────────────────────────────
app.include_router(lab_results.router)

# Public contact form.
app.include_router(contact_routes.router)

# External walk-in consultations and diagnoses.
app.include_router(consultation_routes.router)

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


# ─── Shutdown event ─────────────────────────────────────────────────────────
@app.on_event("shutdown")
def shutdown_scheduler():
    """Shutdown the scheduler when the app stops."""
    if scheduler and scheduler.running:
        scheduler.shutdown()
        print("Scheduler shut down")
