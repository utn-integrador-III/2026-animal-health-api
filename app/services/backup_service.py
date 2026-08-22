"""Backup and Restoration Service for Firestore & Firebase Storage (DB-US-07)."""

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from google.cloud import firestore as google_firestore

from app.constant import Collections
from app.firebase_config import get_firestore_db, get_storage_bucket

logger = logging.getLogger(__name__)

# List of collections to back up by default
ALL_COLLECTIONS = [
    Collections.USERS,
    Collections.PETS,
    Collections.APPOINTMENTS,
    Collections.VACCINES,
    Collections.MEDICAL_RECORDS,
    Collections.MEDICATIONS,
    Collections.CONSULTATIONS,
    Collections.DIAGNOSES,
    Collections.NOTIFICATIONS,
    Collections.LAB_RESULTS,
    Collections.ALLERGIES,
]

LOCAL_BACKUP_DIR = Path("storage/backups")


def serialize_firestore_data(data: Any) -> Any:
    """Recursively serializes Firestore data types to JSON-compatible primitives."""
    if isinstance(data, datetime):
        return {"__type__": "datetime", "value": data.isoformat()}
    elif hasattr(data, "path") and hasattr(data, "id"):
        # DocumentReference
        return {"__type__": "DocumentReference", "path": data.path}
    elif isinstance(data, dict):
        return {k: serialize_firestore_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_firestore_data(item) for item in data]
    elif isinstance(data, bytes):
        import base64

        return {"__type__": "bytes", "value": base64.b64encode(data).decode("utf-8")}
    return data


def deserialize_firestore_data(data: Any, db: Any = None) -> Any:
    """Recursively deserializes JSON primitive structures back to Python/Firestore types."""
    if isinstance(data, dict):
        if "__type__" in data:
            data_type = data["__type__"]
            if data_type == "datetime":
                return datetime.fromisoformat(data["value"])
            elif data_type == "DocumentReference":
                path = data["path"]
                if db:
                    return db.doc(path)
                return path
            elif data_type == "bytes":
                import base64

                return base64.b64decode(data["value"])
        return {k: deserialize_firestore_data(v, db) for k, v in data.items()}
    elif isinstance(data, list):
        return [deserialize_firestore_data(item, db) for item in data]
    return data


class BackupService:
    """Service to create, list, restore, and purge Firestore database backups."""

    def __init__(self, db: Any = None, bucket: Any = None):
        self._db = db
        self._bucket = bucket

    @property
    def db(self):
        if self._db is None:
            try:
                self._db = get_firestore_db()
            except Exception as e:
                logger.warning("Firestore DB client unavailable: %s", e)
        return self._db

    @property
    def bucket(self):
        if self._bucket is None:
            try:
                self._bucket = get_storage_bucket()
            except Exception as e:
                logger.warning("Storage bucket client unavailable: %s", e)
        return self._bucket

    def create_backup(
        self,
        collections: Optional[List[str]] = None,
        backup_id: Optional[str] = None,
        purge_retention_days: int = 30,
    ) -> Dict[str, Any]:
        """Exports Firestore collections and metadata to Firebase Storage or local fallback.

        :param collections: Optional list of collection names. Defaults to ALL_COLLECTIONS.
        :param backup_id: Optional custom identifier. Defaults to timestamp string.
        :param purge_retention_days: Days after which old backups will be purged.
        :return: Summary dictionary of the backup result.
        """
        now = datetime.now(timezone.utc)
        if not backup_id:
            backup_id = f"backup_{now.strftime('%Y%m%d_%H%M%S')}"

        target_collections = collections or ALL_COLLECTIONS
        collection_stats: Dict[str, int] = {}
        total_documents = 0

        logger.info("Starting backup '%s' for collections: %s", backup_id, target_collections)

        for col_name in target_collections:
            docs_data = []
            if self.db:
                try:
                    col_ref = self.db.collection(col_name)
                    for doc in col_ref.stream():
                        doc_dict = doc.to_dict() or {}
                        serialized_doc = serialize_firestore_data(doc_dict)
                        docs_data.append({"id": doc.id, "data": serialized_doc})
                except Exception as err:
                    logger.error("Error reading collection '%s' for backup: %s", col_name, err)

            doc_count = len(docs_data)
            collection_stats[col_name] = doc_count
            total_documents += doc_count

            # Write collection JSON
            content_json = json.dumps(docs_data, indent=2, ensure_ascii=False)
            self._save_file(f"backups/{backup_id}/{col_name}.json", content_json)

        metadata = {
            "backup_id": backup_id,
            "created_at": now.isoformat(),
            "collections": collection_stats,
            "total_documents": total_documents,
            "status": "completed",
        }

        self._save_file(f"backups/{backup_id}/metadata.json", json.dumps(metadata, indent=2))

        logger.info(
            "Backup '%s' completed successfully. Total docs: %d", backup_id, total_documents
        )

        # Execute 30-day retention purge if requested
        purged_summary = {}
        if purge_retention_days > 0:
            try:
                purged_summary = self.purge_old_backups(retention_days=purge_retention_days)
            except Exception as exc:
                logger.error("Error purging old backups during backup job: %s", exc)

        return {
            "backup_id": backup_id,
            "created_at": metadata["created_at"],
            "total_documents": total_documents,
            "collections": collection_stats,
            "purged_old_backups": purged_summary,
            "status": "success",
        }

    def list_backups(self) -> List[Dict[str, Any]]:
        """Lists all available backups in Storage and local fallback."""
        backups_meta: Dict[str, Dict[str, Any]] = {}

        # 1. Check Cloud Storage bucket
        if self.bucket:
            try:
                blobs = self.bucket.list_blobs(prefix="backups/")
                for blob in blobs:
                    if blob.name.endswith("metadata.json"):
                        parts = blob.name.split("/")
                        if len(parts) >= 3:
                            b_id = parts[1]
                            try:
                                content = blob.download_as_text()
                                backups_meta[b_id] = json.loads(content)
                            except Exception as e:
                                logger.warning("Could not parse metadata for %s: %s", blob.name, e)
            except Exception as err:
                logger.warning("Error listing backups from Firebase Storage: %s", err)

        # 2. Check Local Storage fallback
        if LOCAL_BACKUP_DIR.exists():
            for b_dir in LOCAL_BACKUP_DIR.iterdir():
                if b_dir.is_dir():
                    meta_file = b_dir / "metadata.json"
                    if meta_file.exists() and b_dir.name not in backups_meta:
                        try:
                            content = meta_file.read_text(encoding="utf-8")
                            backups_meta[b_dir.name] = json.loads(content)
                        except Exception as e:
                            logger.warning("Could not parse local metadata for %s: %s", b_dir.name, e)

        # Sort by creation date descending
        resultList = list(backups_meta.values())
        resultList.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return resultList

    def purge_old_backups(self, retention_days: int = 30) -> Dict[str, Any]:
        """Purges backup snapshots older than the specified retention period (default: 30 days)."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        purged_backups: List[str] = []
        purged_files_count = 0

        logger.info("Purging backups older than %d days (cutoff: %s)", retention_days, cutoff_date.isoformat())

        backups = self.list_backups()
        for b_meta in backups:
            b_id = b_meta.get("backup_id")
            created_at_str = b_meta.get("created_at")
            if not b_id or not created_at_str:
                continue

            try:
                created_at = datetime.fromisoformat(created_at_str)
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            if created_at < cutoff_date:
                # Delete from Cloud Storage
                if self.bucket:
                    try:
                        blobs = list(self.bucket.list_blobs(prefix=f"backups/{b_id}/"))
                        for blob in blobs:
                            blob.delete()
                            purged_files_count += 1
                        purged_backups.append(b_id)
                    except Exception as err:
                        logger.error("Failed to delete backup '%s' from Storage: %s", b_id, err)

                # Delete from Local Storage fallback
                local_b_dir = LOCAL_BACKUP_DIR / b_id
                if local_b_dir.exists():
                    try:
                        for child in local_b_dir.iterdir():
                            child.unlink()
                            purged_files_count += 1
                        local_b_dir.rmdir()
                        if b_id not in purged_backups:
                            purged_backups.append(b_id)
                    except Exception as err:
                        logger.error("Failed to delete local backup '%s': %s", b_id, err)

        logger.info("Purged %d expired backup snapshots (%d total files)", len(purged_backups), purged_files_count)
        return {
            "retention_days": retention_days,
            "cutoff_date": cutoff_date.isoformat(),
            "purged_backups": purged_backups,
            "files_deleted": purged_files_count,
        }

    def restore_backup(
        self,
        backup_id: str,
        dry_run: bool = False,
        collections: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Restores Firestore collections from a specified backup snapshot with integrity checks.

        :param backup_id: Backup ID to restore.
        :param dry_run: If True, performs integrity check without writing to Firestore.
        :param collections: Optional filter for specific collections to restore.
        :return: Summary report of the restoration process.
        """
        logger.info("Starting restore process for backup '%s' (dry_run=%s)", backup_id, dry_run)

        # 1. Fetch metadata
        meta_content = self._read_file(f"backups/{backup_id}/metadata.json")
        if not meta_content:
            raise FileNotFoundError(f"Backup metadata for '{backup_id}' not found.")

        metadata = json.loads(meta_content)
        backup_collections: Dict[str, int] = metadata.get("collections", {})

        target_collections = collections or list(backup_collections.keys())
        validation_report: Dict[str, Dict[str, Any]] = {}
        restored_stats: Dict[str, int] = {}
        total_restored_docs = 0

        # 2. Inspect and validate data integrity for each collection
        for col_name in target_collections:
            file_content = self._read_file(f"backups/{backup_id}/{col_name}.json")
            if not file_content:
                validation_report[col_name] = {
                    "status": "missing_backup_file",
                    "expected_count": backup_collections.get(col_name, 0),
                    "found_count": 0,
                    "valid": False,
                }
                continue

            try:
                raw_docs = json.loads(file_content)
            except json.JSONDecodeError as err:
                validation_report[col_name] = {
                    "status": "corrupted_json",
                    "error": str(err),
                    "valid": False,
                }
                continue

            found_count = len(raw_docs)
            expected_count = backup_collections.get(col_name, found_count)
            is_valid = found_count == expected_count

            validation_report[col_name] = {
                "status": "valid" if is_valid else "count_mismatch",
                "expected_count": expected_count,
                "found_count": found_count,
                "valid": is_valid,
            }

            if not dry_run and self.db:
                # 3. Perform Batch Writes to Firestore
                try:
                    col_ref = self.db.collection(col_name)
                    # Firestore batches support max 500 writes per batch
                    batch = self.db.batch()
                    batch_count = 0

                    for item in raw_docs:
                        doc_id = item["id"]
                        doc_data = deserialize_firestore_data(item["data"], self.db)
                        doc_ref = col_ref.document(doc_id)
                        batch.set(doc_ref, doc_data)
                        batch_count += 1

                        if batch_count >= 400:
                            batch.commit()
                            batch = self.db.batch()
                            batch_count = 0

                    if batch_count > 0:
                        batch.commit()

                    restored_stats[col_name] = found_count
                    total_restored_docs += found_count
                except Exception as exc:
                    logger.error("Error committing restore batch for collection '%s': %s", col_name, exc)
                    validation_report[col_name]["restore_error"] = str(exc)

        is_all_valid = all(info.get("valid", False) for info in validation_report.values())

        return {
            "backup_id": backup_id,
            "dry_run": dry_run,
            "metadata": metadata,
            "validation_report": validation_report,
            "integrity_check_passed": is_all_valid,
            "restored_collections": restored_stats if not dry_run else {},
            "total_documents_restored": total_restored_docs if not dry_run else 0,
            "status": "success" if (is_all_valid and not dry_run) else ("validated" if dry_run else "partial_success"),
        }

    # Helper methods for dual Cloud Storage / Local Storage persistence
    def _save_file(self, relative_path: str, content: str) -> None:
        saved_to_cloud = False
        if self.bucket:
            try:
                blob = self.bucket.blob(relative_path)
                blob.upload_from_string(content, content_type="application/json")
                saved_to_cloud = True
            except Exception as err:
                logger.warning("Cloud Storage upload failed for %s: %s. Using local fallback.", relative_path, err)

        if not saved_to_cloud:
            local_path = Path("storage") / relative_path
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text(content, encoding="utf-8")

    def _read_file(self, relative_path: str) -> Optional[str]:
        if self.bucket:
            try:
                blob = self.bucket.blob(relative_path)
                if blob.exists():
                    return blob.download_as_text()
            except Exception as err:
                logger.warning("Cloud Storage download failed for %s: %s. Checking local fallback.", relative_path, err)

        local_path = Path("storage") / relative_path
        if local_path.exists():
            return local_path.read_text(encoding="utf-8")

        return None
