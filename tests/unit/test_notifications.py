"""Pruebas unitarias para el servicio de notificaciones."""

import asyncio
from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock

import pytest

from app.constant import Collections
from app.services.notification_service import NotificationService


class FakeSnapshot:
    def __init__(self, doc_id, data=None):
        self.id = doc_id
        self._data = data
        self.reference = None

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return self._data.copy() if self._data else None


class FakeDocumentRef:
    def __init__(self, collection, doc_id):
        self.collection = collection
        self.id = doc_id

    def get(self):
        data = self.collection.data.get(self.id)
        snap = FakeSnapshot(self.id, data)
        snap.reference = self
        return snap

    def update(self, data):
        if self.id in self.collection.data:
            self.collection.data[self.id].update(data)

    def delete(self):
        self.collection.data.pop(self.id, None)


class FakeQuery:
    def __init__(self, collection, filters=None):
        self.collection = collection
        self.filters = filters or []
        self.limit_val = None
        self.offset_val = None

    def where(self, field, op, value):
        new_filters = self.filters + [(field, op, value)]
        return FakeQuery(self.collection, new_filters)

    def order_by(self, field, direction="ASCENDING"):
        return self

    def limit(self, val):
        self.limit_val = val
        return self

    def offset(self, val):
        self.offset_val = val
        return self

    def _get_matches(self):
        matches = []
        for doc_id, data in self.collection.data.items():
            match = True
            for field, op, value in self.filters:
                if op == "==" and data.get(field) != value:
                    match = False
                    break
            if match:
                snap = FakeSnapshot(doc_id, data)
                snap.reference = FakeDocumentRef(self.collection, doc_id)
                matches.append(snap)
        return matches

    def stream(self):
        matches = self._get_matches()
        if self.offset_val:
            matches = matches[self.offset_val:]
        if self.limit_val:
            matches = matches[:self.limit_val]
        return matches

    def get(self):
        return self.stream()


class FakeCollection:
    def __init__(self, data=None):
        self.data = data or {}
        self.next_id = 1

    def document(self, doc_id=None):
        if doc_id is None:
            doc_id = f"gen-{self.next_id}"
            self.next_id += 1
        return FakeDocumentRef(self, doc_id)

    def where(self, field, op, value):
        return FakeQuery(self).where(field, op, value)

    def stream(self):
        return FakeQuery(self).stream()

    def get(self):
        return FakeQuery(self).get()

    def add(self, data):
        doc_id = f"gen-{self.next_id}"
        self.next_id += 1
        self.data[doc_id] = dict(data)
        return None, FakeDocumentRef(self, doc_id)


class FakeFirestore:
    def __init__(self, collections=None):
        self.collections = collections or {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


# --- Helper Fixtures ---
def create_service(db):
    with patch("app.services.notification_service.get_firestore_db", return_value=db):
        return NotificationService()


# --- Tests for check_vaccines_due_for_notification ---

def test_check_vaccines_empty():
    db = FakeFirestore()
    service = create_service(db)
    result = asyncio.run(service.check_vaccines_due_for_notification())
    assert result["success"] is True
    assert result["notifications_created"] == 0


def test_check_vaccines_various_scenarios():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    exp_urgent = (today + timedelta(days=1)).isoformat()
    exp_warning = (today + timedelta(days=4)).isoformat()
    exp_info = (today + timedelta(days=7)).isoformat()
    exp_datetime_obj = today + timedelta(days=2)
    exp_far = (today + timedelta(days=20)).isoformat()

    db = FakeFirestore({
        Collections.VACCINES: FakeCollection({
            "vac-no-exp": {"notification_sent": False, "name": "No Exp"},
            "vac-invalid-exp": {"notification_sent": False, "expiration_date": 12345},
            "vac-urgent": {"notification_sent": False, "name": "Rabia", "expiration_date": exp_urgent, "pet_id": "pet-1"},
            "vac-warning": {"notification_sent": False, "name": "Parvovirus", "expiration_date": exp_warning, "pet_id": "pet-1"},
            "vac-info": {"notification_sent": False, "name": "Triple", "expiration_date": exp_info, "pet_id": "pet-1"},
            "vac-datetime": {"notification_sent": False, "name": "Leptospira", "expiration_date": exp_datetime_obj, "pet_id": "pet-1"},
            "vac-far": {"notification_sent": False, "name": "Moquillo", "expiration_date": exp_far, "pet_id": "pet-1"},
        }),
        Collections.PETS: FakeCollection({
            "pet-1": {"name": "Max", "owner_id": "user-owner"}
        })
    })

    service = create_service(db)
    result = asyncio.run(service.check_vaccines_due_for_notification())

    assert result["success"] is True
    assert result["notifications_created"] == 4  # urgent, warning, info, datetime_obj

    notifications = db.collection(Collections.NOTIFICATIONS).data
    assert len(notifications) == 4

    urgencies = [n["urgency"] for n in notifications.values()]
    assert "urgent" in urgencies
    assert "warning" in urgencies
    assert "info" in urgencies


def test_check_vaccines_loop_error_and_top_level_exception():
    # Loop processing exception
    db = FakeFirestore({
        Collections.VACCINES: FakeCollection({
            "vac-err": {"notification_sent": False, "expiration_date": "invalid-date-string", "pet_id": "pet-1"}
        })
    })
    service = create_service(db)
    result = asyncio.run(service.check_vaccines_due_for_notification())
    assert result["success"] is True
    assert result["errors"] is not None
    assert len(result["errors"]) == 1

    # Top-level exception
    with patch.object(service, "_get_vaccines_collection", side_effect=RuntimeError("DB Error")):
        result_err = asyncio.run(service.check_vaccines_due_for_notification())
        assert result_err["success"] is False
        assert result_err["error"] == "DB Error"


# --- Tests for check_medications_due_for_notification ---

def test_check_medications_scenarios():
    today = date.today()
    start_active = (today - timedelta(days=1)).isoformat()
    end_active = (today + timedelta(days=2)).isoformat()

    db = FakeFirestore({
        Collections.MEDICATIONS: FakeCollection({
            "med-no-dates": {"status": "active"},
            "med-no-pet": {"status": "active", "start_date": start_active, "end_date": end_active, "pet_id": "nonexistent"},
            "med-no-owner": {"status": "active", "start_date": start_active, "end_date": end_active, "pet_id": "pet-no-owner"},
            "med-valid": {
                "status": "active",
                "start_date": start_active,
                "end_date": end_active,
                "pet_id": "pet-1",
                "name": "Antibiótico",
                "dosage": "1 pastilla",
            },
        }),
        Collections.PETS: FakeCollection({
            "pet-no-owner": {"name": "Ghost"},
            "pet-1": {"name": "Rocky", "owner_id": "user-rocky"},
        })
    })

    service = create_service(db)

    # First check: should create 1 notification
    with patch("app.services.notification_service.get_firestore_db", return_value=db):
        res1 = asyncio.run(service.check_medications_due_for_notification())
    assert res1["success"] is True
    assert res1["notifications_created"] == 1

    # Second check same day: notification already exists, so 0 created
    with patch("app.services.notification_service.get_firestore_db", return_value=db):
        res2 = asyncio.run(service.check_medications_due_for_notification())
    assert res2["success"] is True
    assert res2["notifications_created"] == 0


def test_check_medications_top_level_exception():
    db = FakeFirestore()
    service = create_service(db)
    with patch("app.services.notification_service.get_firestore_db", side_effect=RuntimeError("Firestore error")):
        res = asyncio.run(service.check_medications_due_for_notification())
        assert res["success"] is False
        assert res["error"] == "Firestore error"


# --- Tests for _create_vaccine_notification edge cases ---

def test_create_vaccine_notification_missing_fields():
    db = FakeFirestore({
        Collections.PETS: FakeCollection({
            "pet-no-owner": {"name": "No Owner"}
        })
    })
    service = create_service(db)

    # No pet_id
    asyncio.run(service._create_vaccine_notification({"id": "v1"}, days_until_expiration=1))
    assert len(db.collection(Collections.NOTIFICATIONS).data) == 0

    # Pet not found
    asyncio.run(service._create_vaccine_notification({"id": "v1", "pet_id": "nonexistent"}, days_until_expiration=1))
    assert len(db.collection(Collections.NOTIFICATIONS).data) == 0

    # Pet has no owner
    asyncio.run(service._create_vaccine_notification({"id": "v1", "pet_id": "pet-no-owner"}, days_until_expiration=1))
    assert len(db.collection(Collections.NOTIFICATIONS).data) == 0


def test_create_vaccine_notification_exception_raises():
    db = FakeFirestore()
    service = create_service(db)
    with patch.object(service, "_get_pets_collection", side_effect=RuntimeError("Collection error")):
        with pytest.raises(RuntimeError):
            asyncio.run(service._create_vaccine_notification({"id": "v1", "pet_id": "pet-1"}, days_until_expiration=1))


# --- Tests for get_user_notifications ---

def test_get_user_notifications_read_and_unread():
    db = FakeFirestore({
        Collections.NOTIFICATIONS: FakeCollection({
            "n1": {"user_id": "user-1", "read": False, "created_at": "2026-01-01T10:00:00"},
            "n2": {"user_id": "user-1", "read": True, "created_at": "2026-01-01T09:00:00"},
            "n3": {"user_id": "user-2", "read": False, "created_at": "2026-01-01T08:00:00"},
        })
    })
    service = create_service(db)

    # All notifications for user-1
    res_all = asyncio.run(service.get_user_notifications("user-1", only_unread=False))
    assert len(res_all["notifications"]) == 2
    assert res_all["unread_count"] == 1

    # Unread notifications only for user-1
    res_unread = asyncio.run(service.get_user_notifications("user-1", only_unread=True))
    assert len(res_unread["notifications"]) == 1

    # Exception path
    with patch.object(service, "_get_notifications_collection", side_effect=RuntimeError("Query error")):
        with pytest.raises(RuntimeError):
            asyncio.run(service.get_user_notifications("user-1"))


# --- Tests for mark_notification_as_read ---

def test_mark_notification_as_read():
    db = FakeFirestore({
        Collections.NOTIFICATIONS: FakeCollection({
            "n1": {"user_id": "user-1", "read": False},
        })
    })
    service = create_service(db)

    # Not found
    r1 = asyncio.run(service.mark_notification_as_read("user-1", "nonexistent"))
    assert r1["success"] is False
    assert r1["error"] == "Notification not found"

    # Permission denied
    r2 = asyncio.run(service.mark_notification_as_read("user-2", "n1"))
    assert r2["success"] is False
    assert r2["error"] == "Permission denied"

    # Success
    r3 = asyncio.run(service.mark_notification_as_read("user-1", "n1"))
    assert r3["success"] is True
    assert db.collection(Collections.NOTIFICATIONS).data["n1"]["read"] is True

    # Exception path
    with patch.object(service, "_get_notifications_collection", side_effect=RuntimeError("Doc error")):
        with pytest.raises(RuntimeError):
            asyncio.run(service.mark_notification_as_read("user-1", "n1"))


# --- Tests for mark_all_notifications_as_read ---

def test_mark_all_notifications_as_read():
    db = FakeFirestore({
        Collections.NOTIFICATIONS: FakeCollection({
            "n1": {"user_id": "user-1", "read": False},
            "n2": {"user_id": "user-1", "read": False},
            "n3": {"user_id": "user-1", "read": True},
        })
    })
    service = create_service(db)

    res = asyncio.run(service.mark_all_notifications_as_read("user-1"))
    assert res["success"] is True
    assert res["marked_count"] == 2
    assert db.collection(Collections.NOTIFICATIONS).data["n1"]["read"] is True
    assert db.collection(Collections.NOTIFICATIONS).data["n2"]["read"] is True

    # Exception path
    with patch.object(service, "_get_notifications_collection", side_effect=RuntimeError("Batch error")):
        with pytest.raises(RuntimeError):
            asyncio.run(service.mark_all_notifications_as_read("user-1"))


# --- Tests for delete_notification ---

def test_delete_notification():
    db = FakeFirestore({
        Collections.NOTIFICATIONS: FakeCollection({
            "n1": {"user_id": "user-1", "read": True},
        })
    })
    service = create_service(db)

    # Not found
    r1 = asyncio.run(service.delete_notification("user-1", "nonexistent"))
    assert r1["success"] is False
    assert r1["error"] == "Notification not found"

    # Permission denied
    r2 = asyncio.run(service.delete_notification("user-2", "n1"))
    assert r2["success"] is False
    assert r2["error"] == "Permission denied"

    # Success
    r3 = asyncio.run(service.delete_notification("user-1", "n1"))
    assert r3["success"] is True
    assert "n1" not in db.collection(Collections.NOTIFICATIONS).data

    # Exception path
    with patch.object(service, "_get_notifications_collection", side_effect=RuntimeError("Delete error")):
        with pytest.raises(RuntimeError):
            asyncio.run(service.delete_notification("user-1", "n1"))