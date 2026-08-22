#!/usr/bin/env python3
"""CLI utility to create, list, purge, and restore Firestore backups (DB-US-07 Disaster Recovery)."""

import argparse
import json
import sys
from pathlib import Path

# Ensure root project directory is in sys.path
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.services.backup_service import BackupService


def main():
    parser = argparse.ArgumentParser(
        description="Animal Health Disaster Recovery & Backup Utility"
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create a new manual database backup snapshot.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available database backup snapshots.",
    )
    parser.add_argument(
        "--backup-id",
        type=str,
        help="Specific backup snapshot ID to restore.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform structural and document count validation without writing to Firestore.",
    )
    parser.add_argument(
        "--purge",
        type=int,
        metavar="DAYS",
        help="Purge backup snapshots older than specified DAYS (default retention: 30 days).",
    )
    parser.add_argument(
        "--collections",
        type=str,
        help="Comma-separated list of specific collections to backup/restore (e.g. 'users,pets').",
    )

    args = parser.parse_args()

    service = BackupService()
    target_collections = (
        [c.strip() for c in args.collections.split(",") if c.strip()]
        if args.collections
        else None
    )

    if args.create:
        print("Creating database backup...")
        res = service.create_backup(collections=target_collections)
        print(json.dumps(res, indent=2))
        return

    if args.list:
        print("Available database backups:")
        backups = service.list_backups()
        if not backups:
            print("No backup snapshots found.")
        else:
            print(json.dumps(backups, indent=2))
        return

    if args.purge is not None:
        days = args.purge if args.purge > 0 else 30
        print(f"Purging backups older than {days} days...")
        res = service.purge_old_backups(retention_days=days)
        print(json.dumps(res, indent=2))
        return

    if args.backup_id:
        print(f"Executing restoration for backup '{args.backup_id}' (dry_run={args.dry_run})...")
        try:
            res = service.restore_backup(
                backup_id=args.backup_id,
                dry_run=args.dry_run,
                collections=target_collections,
            )
            print(json.dumps(res, indent=2))
            if res.get("integrity_check_passed"):
                print("\nSUCCESS: Integrity validation checks passed!")
            else:
                print("\nWARNING: Some collections failed integrity validation checks.")
        except FileNotFoundError as err:
            print(f"\nERROR: {err}", file=sys.stderr)
            sys.exit(1)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
