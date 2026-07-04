"""Lazy Firebase Admin and Firestore initialization."""

import json
from pathlib import Path

import firebase_admin
from firebase_admin import credentials
from google.cloud import firestore
from google.oauth2 import service_account

from .config import FIREBASE_SERVICE_ACCOUNT

_firestore_client = None
_storage_bucket = None


def get_firestore_db():
    """Returns a cached Firestore REST client with readable setup errors."""
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client

    service_account_path = Path(FIREBASE_SERVICE_ACCOUNT)
    if not service_account_path.is_file():
        raise RuntimeError(
            "Firebase service account not found. Set FIREBASE_SERVICE_ACCOUNT "
            f"or place the file at: {service_account_path}"
        )

    try:
        service_account_info = json.loads(
            service_account_path.read_text(encoding="utf-8")
        )
        project_id = service_account_info["project_id"]

        if not firebase_admin._apps:
            firebase_admin.initialize_app(
                credentials.Certificate(str(service_account_path)),
            )

        google_credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=[
                "https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/datastore",
            ],
        )
        _firestore_client = firestore.Client(
            project=project_id,
            credentials=google_credentials,
        )
        return _firestore_client
    except (OSError, ValueError, KeyError) as exc:
        raise RuntimeError(
            f"Firebase service account is invalid: {service_account_path}"
        ) from exc


def get_storage_bucket():
    """Returns a cached Firebase Storage bucket client if available."""
    global _storage_bucket
    if _storage_bucket is not None:
        return _storage_bucket

    if not firebase_admin._apps:
        raise RuntimeError("Firebase Admin SDK is not initialized")

    try:
        from firebase_admin import storage

        _storage_bucket = storage.bucket()
        return _storage_bucket
    except Exception as exc:  # pragma: no cover - runtime compatibility fallback
        raise RuntimeError("Firebase Storage is not available") from exc
