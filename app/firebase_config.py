"""Lazy Firebase Admin, Firestore, and Storage initialization."""

import json
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, storage
from google.cloud import firestore as google_firestore
from google.oauth2 import service_account

from .config import (
    FIREBASE_SERVICE_ACCOUNT,
    FIREBASE_SERVICE_ACCOUNT_JSON,
    FIREBASE_STORAGE_BUCKET,
)

_firestore_client = None
_storage_bucket = None


def _load_service_account_info():
    """Loads Firebase credentials from Render secrets or a local JSON file."""
    if FIREBASE_SERVICE_ACCOUNT_JSON:
        try:
            return json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
        except ValueError as exc:
            raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is invalid") from exc

    service_account_path = Path(FIREBASE_SERVICE_ACCOUNT)
    if not service_account_path.is_file():
        raise RuntimeError(
            "Firebase service account not found. Set FIREBASE_SERVICE_ACCOUNT_JSON, "
            "set FIREBASE_SERVICE_ACCOUNT, or place the file at: "
            f"{service_account_path}"
        )

    try:
        return json.loads(service_account_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"Firebase service account is invalid: {service_account_path}"
        ) from exc


def initialize_firebase_app():
    """Initializes Firebase Admin SDK with Storage support."""
    if firebase_admin._apps:
        return firebase_admin.get_app()

    service_account_info = _load_service_account_info()
    return firebase_admin.initialize_app(
        credentials.Certificate(service_account_info),
        {
            "storageBucket": FIREBASE_STORAGE_BUCKET,
        },
    )


def get_firestore_db():
    """Returns a cached Firestore client with readable setup errors."""
    global _firestore_client

    if _firestore_client is not None:
        return _firestore_client

    try:
        service_account_info = _load_service_account_info()
        project_id = service_account_info["project_id"]

        initialize_firebase_app()

        google_credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=[
                "https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/datastore",
            ],
        )

        _firestore_client = google_firestore.Client(
            project=project_id,
            credentials=google_credentials,
        )
        return _firestore_client

    except (ValueError, KeyError) as exc:
        raise RuntimeError("Firebase service account is invalid") from exc


def get_storage_bucket():
    """Returns a cached Firebase Storage bucket client."""
    global _storage_bucket

    if _storage_bucket is not None:
        return _storage_bucket

    initialize_firebase_app()

    try:
        _storage_bucket = storage.bucket(FIREBASE_STORAGE_BUCKET)
        return _storage_bucket
    except Exception as exc:
        raise RuntimeError("Firebase Storage is not available") from exc