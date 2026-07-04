"""Create or update a pre-authorized veterinarian account."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from app.auth import email_document_id, hash_password  # noqa: E402
from app.constant import Collections, UserRole  # noqa: E402
from app.firebase_config import get_firestore_db  # noqa: E402
from app.schemas import EMAIL_PATTERN  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create a veterinarian account without public registration."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--phone", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    email = args.email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(email):
        raise SystemExit("Invalid email address")
    if len(args.password) < 8:
        raise SystemExit("Password must contain at least 8 characters")

    db = get_firestore_db()
    user_id = email_document_id(email)
    user_ref = db.collection(Collections.USERS).document(user_id)
    existing = user_ref.get()

    data = {
        "email": email,
        "hashed_password": hash_password(args.password),
        "full_name": args.name.strip(),
        "phone": args.phone.strip(),
        "role": UserRole.VETERINARIAN,
        "is_active": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if existing.exists:
        existing_data = existing.to_dict()
        if existing_data.get("role") != UserRole.VETERINARIAN:
            raise SystemExit("An account with this email exists with another role")
        user_ref.update(data)
        action = "updated"
    else:
        data["created_at"] = data["updated_at"]
        user_ref.create(data)
        action = "created"

    print(f"Veterinarian {action}: {email}")


if __name__ == "__main__":
    main()