import asyncio
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from app import schemas
from app.api.v1.endpoints import auth_routes
from app.auth import hash_password
from app.constant import Collections, UserRole


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
        snapshot = FakeSnapshot(self.id, data)
        snapshot.reference = self
        return snapshot

    def create(self, data):
        if self.id in self.collection.data:
            raise RuntimeError("Document already exists")
        self.collection.data[self.id] = dict(data)

    def update(self, data):
        if self.id in self.collection.data:
            self.collection.data[self.id].update(data)

    def delete(self):
        self.collection.data.pop(self.id, None)


class FakeQuery:
    def __init__(self, collection, field, value):
        self.collection = collection
        self.field = field
        self.value = value
        self.limit_count = None

    def limit(self, count):
        self.limit_count = count
        return self

    def get(self):
        matches = []
        for doc_id, data in self.collection.data.items():
            if data.get(self.field) == self.value:
                snap = FakeSnapshot(doc_id, data)
                snap.reference = FakeDocumentRef(self.collection, doc_id)
                matches.append(snap)
        return matches[: self.limit_count] if self.limit_count else matches


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
        return FakeQuery(self, field, value)


class FakeFirestore:
    def __init__(self, collections=None):
        self.collections = collections or {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


def pet_payload():
    return schemas.PetCreate(
        name="Luna",
        birth_date="2024-01-01",
        species="Dog",
        sex="Female",
        breed_primary="Mixed",
        weight_kg=8.5,
    )


def register_payload():
    return schemas.UserRegister(
        email="newuser@example.com",
        password="password123",
        full_name="New User",
        phone="8888-8888",
        initial_pet=pet_payload(),
    )


# Tests for Register
def test_register_success():
    db = FakeFirestore()
    with patch.object(auth_routes, "get_firestore_db", return_value=db), \
         patch.object(auth_routes, "register_client_with_pet", return_value=("user-1", "pet-1", "2026-01-01T00:00:00Z")), \
         patch.object(auth_routes, "create_access_token", return_value="fake_jwt_token"):
        
        response = auth_routes.register(register_payload())

        assert response.access_token == "fake_jwt_token"
        assert response.user.id == "user-1"
        assert response.user.email == "newuser@example.com"
        assert response.pet.id == "pet-1"


# Tests for Login
def test_login_user_not_found():
    db = FakeFirestore()
    with patch.object(auth_routes, "get_firestore_db", return_value=db):
        with pytest.raises(HTTPException) as exc_info:
            auth_routes.login(schemas.UserLogin(email="nonexistent@example.com", password="password"))
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid credentials"


def test_login_user_inactive():
    user_data = {
        "email": "inactive@example.com",
        "hashed_password": hash_password("password123"),
        "full_name": "Inactive User",
        "role": UserRole.CLIENT,
        "is_active": False,
    }
    db = FakeFirestore({Collections.USERS: FakeCollection({"user-1": user_data})})

    with patch.object(auth_routes, "get_firestore_db", return_value=db):
        with pytest.raises(HTTPException) as exc_info:
            auth_routes.login(schemas.UserLogin(email="inactive@example.com", password="password123"))
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid credentials"


def test_login_invalid_password():
    user_data = {
        "email": "user@example.com",
        "hashed_password": hash_password("correctpassword"),
        "full_name": "Active User",
        "role": UserRole.CLIENT,
        "is_active": True,
    }
    db = FakeFirestore({Collections.USERS: FakeCollection({"user-1": user_data})})

    with patch.object(auth_routes, "get_firestore_db", return_value=db):
        with pytest.raises(HTTPException) as exc_info:
            auth_routes.login(schemas.UserLogin(email="user@example.com", password="wrongpassword"))
        assert exc_info.value.status_code == 401


def test_login_unauthorized_role():
    user_data = {
        "email": "badrole@example.com",
        "hashed_password": hash_password("password123"),
        "full_name": "Bad Role",
        "role": "unauthorized_role",
        "is_active": True,
    }
    db = FakeFirestore({Collections.USERS: FakeCollection({"user-1": user_data})})

    with patch.object(auth_routes, "get_firestore_db", return_value=db):
        with pytest.raises(HTTPException) as exc_info:
            auth_routes.login(schemas.UserLogin(email="badrole@example.com", password="password123"))
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "User role is not authorized"


def test_login_success_and_rehash():
    # Legacy password format triggers password_needs_rehash
    legacy_hash = "salt123$oldhashvalue"
    user_data = {
        "email": "rehash@example.com",
        "hashed_password": legacy_hash,
        "full_name": "Rehash User",
        "role": UserRole.CLIENT,
        "is_active": True,
    }
    db = FakeFirestore({Collections.USERS: FakeCollection({"user-rehash": user_data})})

    with patch.object(auth_routes, "get_firestore_db", return_value=db), \
         patch.object(auth_routes, "verify_password", return_value=True), \
         patch.object(auth_routes, "create_access_token", return_value="jwt_rehash_token"):
        
        response = auth_routes.login(schemas.UserLogin(email="rehash@example.com", password="password123"))

        assert response.access_token == "jwt_rehash_token"
        assert response.user.id == "user-rehash"
        # Check that stored hash was updated
        updated_user = db.collection(Collections.USERS).data["user-rehash"]
        assert updated_user["hashed_password"] != legacy_hash


# Tests for Logout
def test_logout():
    assert auth_routes.logout() is None


# Tests for Get Profile
def test_get_profile():
    current_user = {
        "id": "user-123",
        "email": "user@example.com",
        "full_name": "Test User",
        "role": UserRole.CLIENT,
        "phone": "8888-8888",
        "profile_image_url": "https://example.com/pic.jpg",
        "unread_notifications": 2,
    }
    response = auth_routes.get_profile(current_user=current_user)
    assert response.id == "user-123"
    assert response.email == "user@example.com"
    assert response.full_name == "Test User"
    assert response.unread_notifications == 2


# Tests for Update Profile
def test_update_profile_empty():
    current_user = {"id": "user-123", "email": "user@example.com"}
    db = FakeFirestore()

    with patch.object(auth_routes, "get_firestore_db", return_value=db):
        with pytest.raises(HTTPException) as exc_info:
            auth_routes.update_profile(schemas.UserProfileUpdate(), current_user=current_user)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "No fields provided for update"


def test_update_profile_email_already_in_use():
    current_user = {"id": "user-123", "email": "old@example.com"}
    db = FakeFirestore({
        Collections.USERS: FakeCollection({
            "user-123": {"email": "old@example.com", "full_name": "User 123"},
            "user-456": {"email": "existing@example.com", "full_name": "User 456"},
        })
    })

    update_payload = schemas.UserProfileUpdate(email="existing@example.com")

    with patch.object(auth_routes, "get_firestore_db", return_value=db):
        with pytest.raises(HTTPException) as exc_info:
            auth_routes.update_profile(update_payload, current_user=current_user)
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "Email address is already in use"


def test_update_profile_success():
    current_user = {"id": "user-123", "email": "old@example.com", "full_name": "Old Name"}
    db = FakeFirestore({
        Collections.USERS: FakeCollection({
            "user-123": {"email": "old@example.com", "full_name": "Old Name"},
        })
    })

    update_payload = schemas.UserProfileUpdate(full_name="New Name", phone="9999-9999")

    with patch.object(auth_routes, "get_firestore_db", return_value=db):
        response = auth_routes.update_profile(update_payload, current_user=current_user)

    assert response.full_name == "New Name"
    assert response.phone == "9999-9999"


# Tests for Update Password
def test_update_password_incorrect_current():
    current_user = {
        "id": "user-123",
        "hashed_password": hash_password("correct_old_pass"),
    }
    db = FakeFirestore()

    payload = schemas.UserPasswordUpdate(
        current_password="wrong_old_pass",
        new_password="new_password_123",
        confirm_password="new_password_123",
    )

    with patch.object(auth_routes, "get_firestore_db", return_value=db):
        with pytest.raises(HTTPException) as exc_info:
            auth_routes.update_password(payload, current_user=current_user)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Current password is incorrect"


def test_update_password_success():
    hashed = hash_password("old_password_123")
    current_user = {
        "id": "user-123",
        "hashed_password": hashed,
    }
    db = FakeFirestore({
        Collections.USERS: FakeCollection({
            "user-123": {"hashed_password": hashed},
        })
    })

    payload = schemas.UserPasswordUpdate(
        current_password="old_password_123",
        new_password="new_password_123",
        confirm_password="new_password_123",
    )

    with patch.object(auth_routes, "get_firestore_db", return_value=db):
        result = auth_routes.update_password(payload, current_user=current_user)

    assert result is None
    new_hashed = db.collection(Collections.USERS).data["user-123"]["hashed_password"]
    assert new_hashed != hashed


# Tests for Upload Profile Photo
def test_upload_profile_photo_invalid_media_type():
    current_user = {"id": "user-123"}
    upload_file = UploadFile(
        filename="doc.pdf",
        file=BytesIO(b"pdf content"),
        headers={"content-type": "application/pdf"},
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth_routes.upload_profile_photo(photo=upload_file, current_user=current_user))
    assert exc_info.value.status_code == 415


def test_upload_profile_photo_empty_file():
    current_user = {"id": "user-123"}
    upload_file = UploadFile(
        filename="empty.jpg",
        file=BytesIO(b""),
        headers={"content-type": "image/jpeg"},
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth_routes.upload_profile_photo(photo=upload_file, current_user=current_user))
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Profile image is empty"


def test_upload_profile_photo_file_too_large():
    current_user = {"id": "user-123"}
    large_content = b"x" * (5 * 1024 * 1024 + 1)
    upload_file = UploadFile(
        filename="large.png",
        file=BytesIO(large_content),
        headers={"content-type": "image/png"},
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth_routes.upload_profile_photo(photo=upload_file, current_user=current_user))
    assert exc_info.value.status_code == 413


def test_upload_profile_photo_storage_error():
    current_user = {"id": "user-123"}
    upload_file = UploadFile(
        filename="pic.webp",
        file=BytesIO(b"webp content"),
        headers={"content-type": "image/webp"},
    )

    with patch.object(auth_routes, "get_storage_bucket", side_effect=RuntimeError("Storage connection error")):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(auth_routes.upload_profile_photo(photo=upload_file, current_user=current_user))
        assert exc_info.value.status_code == 503


def test_upload_profile_photo_success():
    current_user = {"id": "user-123", "email": "user@example.com", "full_name": "Test User"}
    db = FakeFirestore({
        Collections.USERS: FakeCollection({
            "user-123": {
                "email": "user@example.com",
                "full_name": "Test User",
                "role": UserRole.CLIENT,
            }
        })
    })

    upload_file = UploadFile(
        filename="pic.jpg",
        file=BytesIO(b"valid jpeg image content"),
        headers={"content-type": "image/jpeg"},
    )

    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.name = "test-bucket"
    mock_bucket.blob.return_value = mock_blob

    with patch.object(auth_routes, "get_storage_bucket", return_value=mock_bucket), \
         patch.object(auth_routes, "get_firestore_db", return_value=db):
        
        response = asyncio.run(auth_routes.upload_profile_photo(photo=upload_file, current_user=current_user))

    assert "https://firebasestorage.googleapis.com" in response.profile_image_url
    stored_user = db.collection(Collections.USERS).data["user-123"]
    assert stored_user["profile_image_url"] == response.profile_image_url
