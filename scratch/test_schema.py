import sys
from datetime import date
from pydantic import ValidationError

# Add backend code path to sys.path
sys.path.append(r"c:\Universidad\ProyectoIntegrador\2026-animal-health-api")

from app.schemas.schemas import VaccineCreate

payload = {
    "name": "Rabia",
    "type": "Rabia (Lyssavirus)",
    "brand": "Merial",
    "batch_number": None,
    "scheduled_date": "2026-07-17",
    "expiration_date": None,
    "next_dose": None,
    "administration_route": "Subcutánea",
    "dose": "1",
    "unit": "dosis",
    "raw_status": "Aplicada correctamente",
    "notes": "Sin reacciones"
}

try:
    v = VaccineCreate(**payload)
    print("Validation SUCCESS:", v)
except ValidationError as e:
    print("Validation ERROR:")
    print(e.json(indent=2))
