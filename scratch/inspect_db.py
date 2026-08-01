import os
import sys
from pathlib import Path

# Add root folder to sys.path
root_dir = Path(__file__).resolve().parents[1]
sys.path.append(str(root_dir))

from app.firebase_config import get_firestore_db
from app.constant import Collections

def inspect():
    db = get_firestore_db()
    print("=== MEDICATIONS ===")
    meds = db.collection(Collections.MEDICATIONS).stream()
    for med in meds:
        print(f"ID: {med.id} -> {str(med.to_dict()).encode('ascii', 'replace').decode('ascii')}")
        
    print("\n=== NOTIFICATIONS ===")
    notifs = db.collection(Collections.NOTIFICATIONS).stream()
    for notif in notifs:
        print(f"ID: {notif.id} -> {str(notif.to_dict()).encode('ascii', 'replace').decode('ascii')}")

if __name__ == "__main__":
    inspect()
