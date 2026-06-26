"""
Authentication utilities.
- PBKDF2-HMAC-SHA256 password hashing
- JWT token creation and verification
- FastAPI dependency for retrieving the current authenticated user
"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from .firebase_config import get_firestore_db
from .constants import Collections, UserRole, AuthToken

# OAuth2 scheme: extracts the Bearer token from the Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=AuthToken.LOGIN_URL)


PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 600_000


def hash_password(password: str, salt: str = None) -> str:
    """
    Hashes a password with PBKDF2-HMAC-SHA256 and a random salt.
    """
    if salt is None:
        salt = secrets.token_hex(16)
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt}${derived_key}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """
    Verifies PBKDF2 hashes and supports the legacy salted SHA-256 format.
    """
    try:
        parts = stored_hash.split("$")
        if len(parts) == 4 and parts[0] == PBKDF2_ALGORITHM:
            _, iterations, salt, expected = parts
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt.encode("utf-8"),
                int(iterations),
            ).hex()
            return hmac.compare_digest(actual, expected)

        if len(parts) == 2:
            salt, expected = parts
            actual = hashlib.sha256(f"{salt}{plain_password}".encode()).hexdigest()
            return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False

    return False


def password_needs_rehash(stored_hash: str) -> bool:
    parts = stored_hash.split("$")
    return not (
        len(parts) == 4
        and parts[0] == PBKDF2_ALGORITHM
        and parts[1] == str(PBKDF2_ITERATIONS)
    )


def email_document_id(email: str) -> str:
    """Creates a stable, non-plain-text Firestore ID for a normalized email."""
    normalized_email = email.strip().lower()
    return hashlib.sha256(normalized_email.encode("utf-8")).hexdigest()


def create_access_token(data: dict) -> str:
    """
    Creates a signed JWT containing the provided payload plus an expiry claim.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({AuthToken.JWT_CLAIM_EXP: expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    FastAPI dependency: decodes the JWT and returns the user document from Firestore.
    Raises HTTP 401 if the token is invalid, expired, or the user does not exist.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": AuthToken.BEARER},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get(AuthToken.JWT_CLAIM_SUB)
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Look up the user in Firestore using the collection name constant
    db = get_firestore_db()
    user_doc = db.collection(Collections.USERS).document(user_id).get()

    if not user_doc.exists:
        raise credentials_exception

    user_data = user_doc.to_dict()
    if not user_data.get("is_active", True):
        raise credentials_exception

    if user_data.get("role") not in UserRole.AUTHENTICATED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User role is not authorized",
        )

    user_data["id"] = user_doc.id
    return user_data


def require_roles(*allowed_roles: str):
    """Builds a dependency that only permits the supplied roles."""
    def role_dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return role_dependency
