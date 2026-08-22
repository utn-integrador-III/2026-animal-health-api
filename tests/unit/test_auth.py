import hashlib
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from jose import jwt

from app import auth
from app.config import ALGORITHM, SECRET_KEY
from app.constant import Collections, UserRole


class FakeSnapshot:
    def __init__(self, doc_id, data=None):
        self.id = doc_id
        self._data = data

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
        return FakeSnapshot(self.id, data)


class FakeCollection:
    def __init__(self, data=None):
        self.data = data or {}

    def document(self, doc_id):
        return FakeDocumentRef(self, doc_id)


class FakeFirestore:
    def __init__(self, collections=None):
        self.collections = collections or {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


# Tests for hash_password
def test_hash_password_default_salt():
    hashed = auth.hash_password("mysecretpassword")
    parts = hashed.split("$")
    assert len(parts) == 4
    assert parts[0] == auth.PBKDF2_ALGORITHM
    assert parts[1] == str(auth.PBKDF2_ITERATIONS)
    assert len(parts[2]) > 0
    assert len(parts[3]) > 0


def test_hash_password_custom_salt():
    salt = "customsalt123"
    hashed = auth.hash_password("mysecretpassword", salt=salt)
    parts = hashed.split("$")
    assert parts[2] == salt


# Tests for verify_password
def test_verify_password_pbkdf2_valid():
    hashed = auth.hash_password("correctpassword")
    assert auth.verify_password("correctpassword", hashed) is True


def test_verify_password_pbkdf2_invalid():
    hashed = auth.hash_password("correctpassword")
    assert auth.verify_password("wrongpassword", hashed) is False


def test_verify_password_legacy_sha256_valid():
    salt = "legacysalt"
    raw_pass = "legacypassword"
    expected_hash = hashlib.sha256(f"{salt}{raw_pass}".encode()).hexdigest()
    legacy_stored = f"{salt}${expected_hash}"

    assert auth.verify_password(raw_pass, legacy_stored) is True


def test_verify_password_legacy_sha256_invalid():
    salt = "legacysalt"
    raw_pass = "legacypassword"
    expected_hash = hashlib.sha256(f"{salt}{raw_pass}".encode()).hexdigest()
    legacy_stored = f"{salt}${expected_hash}"

    assert auth.verify_password("wrongpassword", legacy_stored) is False


def test_verify_password_malformed_hash():
    assert auth.verify_password("password", "invalid_format") is False
    assert auth.verify_password("password", "part1$part2$part3") is False
    assert auth.verify_password("password", f"{auth.PBKDF2_ALGORITHM}$invalid_iterations$salt$hash") is False


# Tests for password_needs_rehash
def test_password_needs_rehash():
    current_hash = auth.hash_password("password")
    assert auth.password_needs_rehash(current_hash) is False

    legacy_hash = "salt$hash"
    assert auth.password_needs_rehash(legacy_hash) is True

    old_iter_hash = f"{auth.PBKDF2_ALGORITHM}$100000$salt$hash"
    assert auth.password_needs_rehash(old_iter_hash) is True


# Tests for email_document_id
def test_email_document_id():
    email = " User@Example.COM "
    expected = hashlib.sha256("user@example.com".encode("utf-8")).hexdigest()
    assert auth.email_document_id(email) == expected


# Tests for create_access_token
def test_create_access_token():
    payload = {"sub": "user-123", "role": UserRole.CLIENT}
    token = auth.create_access_token(payload)

    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["sub"] == "user-123"
    assert decoded["role"] == UserRole.CLIENT
    assert "exp" in decoded


# Tests for get_current_user
def test_get_current_user_success():
    payload = {"sub": "user-123"}
    token = auth.create_access_token(payload)

    user_data = {
        "email": "user@example.com",
        "role": UserRole.CLIENT,
        "is_active": True,
    }
    db = FakeFirestore({
        Collections.USERS: FakeCollection({
            "user-123": user_data
        })
    })

    with patch.object(auth, "get_firestore_db", return_value=db):
        current_user = auth.get_current_user(token)

    assert current_user["id"] == "user-123"
    assert current_user["email"] == "user@example.com"
    assert current_user["role"] == UserRole.CLIENT


def test_get_current_user_invalid_token():
    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user("invalid.jwt.token")
    assert exc_info.value.status_code == 401


def test_get_current_user_missing_sub_claim():
    token = jwt.encode({"other": "claim"}, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(token)
    assert exc_info.value.status_code == 401


def test_get_current_user_not_found_in_db():
    payload = {"sub": "user-nonexistent"}
    token = auth.create_access_token(payload)
    db = FakeFirestore()

    with patch.object(auth, "get_firestore_db", return_value=db):
        with pytest.raises(HTTPException) as exc_info:
            auth.get_current_user(token)
    assert exc_info.value.status_code == 401


def test_get_current_user_inactive():
    payload = {"sub": "user-inactive"}
    token = auth.create_access_token(payload)

    user_data = {
        "email": "inactive@example.com",
        "role": UserRole.CLIENT,
        "is_active": False,
    }
    db = FakeFirestore({
        Collections.USERS: FakeCollection({
            "user-inactive": user_data
        })
    })

    with patch.object(auth, "get_firestore_db", return_value=db):
        with pytest.raises(HTTPException) as exc_info:
            auth.get_current_user(token)
    assert exc_info.value.status_code == 401


def test_get_current_user_unauthorized_role():
    payload = {"sub": "user-unauthorized"}
    token = auth.create_access_token(payload)

    user_data = {
        "email": "badrole@example.com",
        "role": "unauthorized_role",
        "is_active": True,
    }
    db = FakeFirestore({
        Collections.USERS: FakeCollection({
            "user-unauthorized": user_data
        })
    })

    with patch.object(auth, "get_firestore_db", return_value=db):
        with pytest.raises(HTTPException) as exc_info:
            auth.get_current_user(token)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "User role is not authorized"


# Tests for require_roles
def test_require_roles_allowed():
    dep = auth.require_roles(UserRole.VETERINARIAN, UserRole.ADMIN)
    user = {"id": "vet-1", "role": UserRole.VETERINARIAN}
    result = dep(current_user=user)
    assert result == user


def test_require_roles_forbidden():
    dep = auth.require_roles(UserRole.ADMIN)
    user = {"id": "client-1", "role": UserRole.CLIENT}
    with pytest.raises(HTTPException) as exc_info:
        dep(current_user=user)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "You do not have permission to perform this action"
