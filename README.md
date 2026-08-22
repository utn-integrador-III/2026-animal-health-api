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
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
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

## Database Backups & Disaster Recovery (DB-US-07)

### Automated Daily Backups
The backend uses **APScheduler** (`app/utils/scheduler.py`) to execute automated daily backups during off-peak hours at **03:00 AM UTC/CST**.
All core Firestore collections (`users`, `pets`, `appointments`, `vaccines`, `medical_records`, `medications`, `consultations`, `diagnoses`, `notifications`, `lab_results`, `allergies`) are exported and saved under `backups/backup_YYYYMMDD_HHMMSS/` in Firebase Storage.

### 30-Day Retention Policy
- **Automated Purging**: During each backup run, `BackupService().purge_old_backups(retention_days=30)` identifies and deletes backup folders/blobs older than 30 days.
- **GCP Cloud Storage Lifecycle Rule**:
  You can also enforce lifecycle rules at the Google Cloud Storage bucket level:
  ```json
  {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {
          "age": 30,
          "matchesPrefix": ["backups/"]
        }
      }
    ]
  }
  ```

### Disaster Recovery & Proven Restore Procedure
In case of data corruption or disaster recovery, follow this restoration procedure:

1. **List Available Backups**:
   ```bash
   python scripts/restore_backup.py --list
   # Or via API: GET /api/admin/backups
   ```

2. **Run Integrity Validation Check (Dry-Run)**:
   Verifies document counts and JSON structural integrity without modifying Firestore:
   ```bash
   python scripts/restore_backup.py --backup-id backup_20260822_030000 --dry-run
   # Or via API: POST /api/admin/backups/backup_20260822_030000/restore?dry_run=true
   ```

3. **Execute Data Restoration**:
   ```bash
   python scripts/restore_backup.py --backup-id backup_20260822_030000
   # Or via API: POST /api/admin/backups/backup_20260822_030000/restore
   ```

