from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import ALLOWED_ORIGINS
from .api.v1.endpoints import appointment_routes, auth_routes, pet_routes

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

# ─── Auth ────────────────────────────────────────────────────────────────────
# POST /api/auth/register, POST /api/auth/login,
# POST /api/auth/logout, GET /api/auth/profile, PUT /api/auth/profile
app.include_router(auth_routes.router)


# ─── Pets (CRUD + history) ───────────────────────────────────────────────────
# POST/GET/PUT/DELETE /api/pets, GET /api/pets/{id}/history
app.include_router(pet_routes.router)


# Appointments: schedule, reschedule, cancel, and veterinarian daily lists.
app.include_router(appointment_routes.router)

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
