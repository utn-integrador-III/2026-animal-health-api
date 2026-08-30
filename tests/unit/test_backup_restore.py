"""Unit and Integration Tests for DB-US-07 Automatic Backups & Proven Restore."""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.vet_admin_routes import router
from app.auth import get_current_user
from app.constant import Collections, UserRole
from app.main import app
from app.services.backup_service import (
    BackupService,
    serialize_firestore_data,
    deserialize_firestore_data,
)
from app.utils.scheduler import start_scheduler, run_daily_backup


class MockDoc:
    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return self._data


class MockCollection:
    def __init__(self, name: str, docs: dict):
        self.name = name
        self.docs = docs  # doc_id -> dict

    def stream(self):
        for doc_id, data in self.docs.items():
            yield MockDoc(doc_id, data)

    def document(self, doc_id: str):
        mock_ref = MagicMock()
        mock_ref.id = doc_id
        return mock_ref


class MockBatch:
    def __init__(self):
        self.sets = []

    def set(self, doc_ref, doc_data):
        self.sets.append((doc_ref, doc_data))

    def commit(self):
        pass


class MockFirestoreDB:
    def __init__(self, initial_data: dict = None):
        self.data = initial_data or {}

    def collection(self, name: str):
        docs = self.data.get(name, {})
        return MockCollection(name, docs)

    def batch(self):
        return MockBatch()


class MockBlob:
    def __init__(self, name: str, content: str = ""):
        self.name = name
        self._content = content

    def upload_from_string(self, content: str, content_type: str = "application/json"):
        self._content = content

    def download_as_text(self):
        return self._content

    def exists(self):
        return True

    def delete(self):
        pass


class MockStorageBucket:
    def __init__(self):
        self.blobs = {}

    def blob(self, name: str):
        if name not in self.blobs:
            self.blobs[name] = MockBlob(name)
        return self.blobs[name]

    def list_blobs(self, prefix: str = ""):
        return [blob for name, blob in self.blobs.items() if name.startswith(prefix)]


@pytest.fixture
def mock_db():
    return MockFirestoreDB(
        {
            Collections.USERS: {
                "user_1": {"name": "Test User", "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc)},
            },
            Collections.PETS: {
                "pet_1": {"name": "Buddy", "species": "Dog"},
                "pet_2": {"name": "Mimi", "species": "Cat"},
            },
            Collections.APPOINTMENTS: {
                "app_1": {"reason": "Checkup", "status": "scheduled"},
            },
        }
    )


@pytest.fixture
def mock_bucket():
    return MockStorageBucket()


def test_serialization_and_deserialization():
    now = datetime(2026, 8, 22, 10, 0, 0, tzinfo=timezone.utc)
    sample_data = {
        "string": "hello",
        "number": 123,
        "date": now,
        "nested": {"inner_date": now},
        "bytes_field": b"binary_data",
    }

    serialized = serialize_firestore_data(sample_data)
    assert serialized["date"]["__type__"] == "datetime"
    assert serialized["date"]["value"] == now.isoformat()
    assert serialized["bytes_field"]["__type__"] == "bytes"

    deserialized = deserialize_firestore_data(serialized)
    assert deserialized["date"] == now
    assert deserialized["nested"]["inner_date"] == now
    assert deserialized["bytes_field"] == b"binary_data"


def test_create_backup_success(mock_db, mock_bucket, tmp_path):
    service = BackupService(db=mock_db, bucket=mock_bucket)

    with patch("app.services.backup_service.LOCAL_BACKUP_DIR", tmp_path):
        result = service.create_backup(
            collections=[Collections.USERS, Collections.PETS],
            backup_id="test_backup_001",
            purge_retention_days=0,
        )

    assert result["status"] == "success"
    assert result["backup_id"] == "test_backup_001"
    assert result["total_documents"] == 3
    assert result["collections"][Collections.USERS] == 1
    assert result["collections"][Collections.PETS] == 2

    # Verify bucket content
    meta_blob = mock_bucket.blob("backups/test_backup_001/metadata.json")
    meta_data = json.loads(meta_blob.download_as_text())
    assert meta_data["total_documents"] == 3


def test_purge_old_backups_30_day_retention(mock_bucket, tmp_path):
    service = BackupService(db=None, bucket=mock_bucket)

    now = datetime.now(timezone.utc)
    old_date = (now - timedelta(days=35)).isoformat()
    recent_date = (now - timedelta(days=5)).isoformat()

    # Create old metadata blob
    old_meta = {
        "backup_id": "old_backup_35d",
        "created_at": old_date,
        "total_documents": 10,
    }
    mock_bucket.blob("backups/old_backup_35d/metadata.json").upload_from_string(
        json.dumps(old_meta)
    )
    mock_bucket.blob("backups/old_backup_35d/users.json").upload_from_string("[]")

    # Create recent metadata blob
    recent_meta = {
        "backup_id": "recent_backup_5d",
        "created_at": recent_date,
        "total_documents": 5,
    }
    mock_bucket.blob("backups/recent_backup_5d/metadata.json").upload_from_string(
        json.dumps(recent_meta)
    )

    with patch("app.services.backup_service.LOCAL_BACKUP_DIR", tmp_path):
        purge_res = service.purge_old_backups(retention_days=30)

    assert "old_backup_35d" in purge_res["purged_backups"]
    assert "recent_backup_5d" not in purge_res["purged_backups"]


def test_restore_backup_dry_run_and_execution(mock_db, mock_bucket, tmp_path):
    service = BackupService(db=mock_db, bucket=mock_bucket)

    meta_data = {
        "backup_id": "restore_test_01",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "collections": {Collections.PETS: 2},
    }
    pets_data = [
        {"id": "p1", "data": {"name": "Max", "species": "Dog"}},
        {"id": "p2", "data": {"name": "Luna", "species": "Cat"}},
    ]

    mock_bucket.blob("backups/restore_test_01/metadata.json").upload_from_string(
        json.dumps(meta_data)
    )
    mock_bucket.blob("backups/restore_test_01/pets.json").upload_from_string(
        json.dumps(pets_data)
    )

    with patch("app.services.backup_service.LOCAL_BACKUP_DIR", tmp_path):
        # 1. Test Dry Run
        dry_res = service.restore_backup("restore_test_01", dry_run=True)
        assert dry_res["dry_run"] is True
        assert dry_res["integrity_check_passed"] is True
        assert dry_res["total_documents_restored"] == 0

        # 2. Test Execution
        restore_res = service.restore_backup("restore_test_01", dry_run=False)
        assert restore_res["dry_run"] is False
        assert restore_res["integrity_check_passed"] is True
        assert restore_res["total_documents_restored"] == 2
        assert restore_res["restored_collections"][Collections.PETS] == 2


def test_scheduler_backup_job_registration():
    scheduler = start_scheduler()
    job_ids = [job.id for job in scheduler.get_jobs()]
    assert "daily_database_backup" in job_ids

    job = scheduler.get_job("daily_database_backup")
    hour_field = next(f for f in job.trigger.fields if f.name == "hour")
    minute_field = next(f for f in job.trigger.fields if f.name == "minute")
    assert str(hour_field) == "3"     # 03:00 AM off-peak
    assert str(minute_field) == "0"
    scheduler.shutdown()


def test_run_daily_backup_execution():
    with patch("app.services.backup_service.BackupService.create_backup") as mock_create:
        mock_create.return_value = {"status": "success"}
        run_daily_backup()
        mock_create.assert_called_once_with(purge_retention_days=30)


def test_admin_backup_endpoints():
    admin_user = {
        "id": "admin_123",
        "email": "admin@example.com",
        "role": UserRole.ADMIN,
    }

    client = TestClient(app)
    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        with patch.object(BackupService, "create_backup") as mock_create, patch.object(
            BackupService, "list_backups"
        ) as mock_list, patch.object(BackupService, "restore_backup") as mock_restore:

            mock_create.return_value = {"backup_id": "b1", "status": "success"}
            mock_list.return_value = [{"backup_id": "b1", "total_documents": 10}]
            mock_restore.return_value = {
                "backup_id": "b1",
                "integrity_check_passed": True,
                "status": "success",
            }

            # 1. Create Backup Endpoint
            res_create = client.post("/api/admin/backups")
            assert res_create.status_code == 201
            assert res_create.json()["backup_id"] == "b1"

            # 2. List Backups Endpoint
            res_list = client.get("/api/admin/backups")
            assert res_list.status_code == 200
            assert len(res_list.json()) == 1

            # 3. Restore Backup Endpoint
            res_restore = client.post("/api/admin/backups/b1/restore?dry_run=true")
            assert res_restore.status_code == 200
            assert res_restore.json()["integrity_check_passed"] is True

    finally:
        app.dependency_overrides.clear()
