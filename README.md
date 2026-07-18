# Animal Health API - Release 1

FastAPI backend connected to Firebase Firestore.

## Release 1 scope

- Client registration creates the account and mandatory first pet atomically.
- Public registration always assigns the `client` role.
- Veterinarians are created with the administrative script.
- Login accepts clients and veterinarians and returns a JWT.
- Passwords use PBKDF2-HMAC-SHA256.
- Protected endpoints return `401` for invalid authentication and `403` for invalid roles or ownership.
- Clients can manage their own pets.
- Veterinarians can view patients assigned through appointments.

Clinical records, diagnoses, allergies, medications and laboratory PDFs belong to later releases.

## Configuration

Copy the repository `.env.example` values into your environment. In production:

- `ENVIRONMENT=production`
- `SECRET_KEY` is mandatory.
- `FIREBASE_SERVICE_ACCOUNT` must point to a valid Firebase Admin JSON file.

Never commit the service account file.

## Installation

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

## Run

```powershell
uvicorn app.main:app --reload --port 8000
```

Swagger UI: `http://localhost:8000/docs`

## Create a veterinarian

Veterinarians cannot register publicly:

```powershell
python app/schemas/create_veterinarian.py `
  --email vet@example.com `
  --password "secure-password" `
  --name "Andrea Vargas" `
  --phone "8888-8888"
```


## Tests

The included suite can run without connecting to Firebase:

```powershell
python -m unittest discover -s tests -v
```
