from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import ALLOWED_ORIGINS
from .api.v1.endpoints import appointment_routes, auth_routes, pet_routes, notification_routes, lab_results
from .utils.scheduler import start_scheduler

app = FastAPI(
    title="Animal Health Pet Profiles API",
    description="Backend for the Animal Health Management System — UTN Integrador III",
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

# ─── Auth ────────────────────────────────────────────────────────────────────
app.include_router(auth_routes)  

# ─── Pets (CRUD + history) ───────────────────────────────────────────────────
app.include_router(pet_routes)   

# ─── Appointments ──────────────────────────────────────────────────────────
app.include_router(appointment_routes)  

# ─── Notifications ──────────────────────────────────────────────────────────
app.include_router(notification_routes)

# ─── Lab Results ──────────────────────────────────────────────────────────
app.include_router(lab_results)  # ← CORREGIDO (sin .router)


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