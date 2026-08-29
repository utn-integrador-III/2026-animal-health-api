"""Lab result service for managing laboratory results."""

import logging
from datetime import datetime, date
from typing import Optional, Union

from app.constant import Collections
from app.firebase_config import get_firestore_db
from app.models.lab_result import LabResultCreate, LabResultUpdate

logger = logging.getLogger(__name__)


class LabResultService:
    """Service for managing laboratory results."""

    def __init__(self):
        self.db = get_firestore_db()

    def _get_collection(self):
        return self.db.collection(Collections.LAB_RESULTS)

    async def create_lab_result(
        self,
        pet_id: str,
        owner_id: str,
        data: Union[LabResultCreate, dict],
        veterinarian_id: Optional[str] = None,
        veterinarian_name: Optional[str] = None,
    ) -> dict:
        """Create a new lab result or exam request."""
        try:
            if hasattr(data, "model_dump"):
                lab_data = data.model_dump(exclude_unset=False)
            elif isinstance(data, dict):
                lab_data = dict(data)
            else:
                lab_data = {}

            # Conversion: date to ISO string
            for date_key in ("test_date", "requested_at", "result_date"):
                if date_key in lab_data and isinstance(lab_data[date_key], (date, datetime)):
                    lab_data[date_key] = lab_data[date_key].isoformat()

            lab_data["pet_id"] = pet_id
            lab_data["owner_id"] = owner_id

            if veterinarian_id and not lab_data.get("veterinarian_id"):
                lab_data["veterinarian_id"] = veterinarian_id
            if veterinarian_name and not lab_data.get("veterinarian_name"):
                lab_data["veterinarian_name"] = veterinarian_name

            if not lab_data.get("status"):
                lab_data["status"] = "Solicitado"
            if not lab_data.get("priority"):
                lab_data["priority"] = "Normal"
            if not lab_data.get("requested_at"):
                lab_data["requested_at"] = datetime.now().isoformat()

            test_type = lab_data.get("test_type") or lab_data.get("exam_type") or "Examen de laboratorio"
            lab_data["test_type"] = test_type
            lab_data["exam_type"] = test_type

            now_iso = datetime.now().isoformat()
            lab_data["created_at"] = now_iso
            lab_data["updated_at"] = now_iso

            doc_ref = self._get_collection().add(lab_data)
            doc_id = doc_ref[1].id
            lab_data["id"] = doc_id

            return lab_data
        except Exception as e:
            logger.error(f"Error creating lab result: {e}")
            raise

    async def get_lab_results_by_pet(self, pet_id: str) -> dict:
        """Get all lab results for a specific pet."""
        try:
            query = self._get_collection().where("pet_id", "==", pet_id)
            snapshot = query.stream()

            results = []
            for doc in snapshot:
                data = doc.to_dict()
                data["id"] = doc.id
                # Format dates
                for date_key in ("test_date", "requested_at", "result_date", "created_at", "updated_at"):
                    if date_key in data and hasattr(data[date_key], "isoformat"):
                        data[date_key] = data[date_key].isoformat()
                results.append(data)

            # Sort descending by requested_at / created_at / test_date
            results.sort(
                key=lambda x: str(x.get("requested_at") or x.get("created_at") or x.get("test_date") or ""),
                reverse=True,
            )

            return {
                "results": results,
                "total": len(results),
            }
        except Exception as e:
            logger.error(f"Error getting lab results for pet {pet_id}: {e}")
            raise

    async def get_lab_result(self, result_id: str) -> dict:
        """Get a single lab result by ID."""
        try:
            doc_ref = self._get_collection().document(result_id)
            doc = doc_ref.get()

            if not doc.exists:
                return None

            data = doc.to_dict()
            data["id"] = doc.id
            for date_key in ("test_date", "requested_at", "result_date", "created_at", "updated_at"):
                if date_key in data and hasattr(data[date_key], "isoformat"):
                    data[date_key] = data[date_key].isoformat()
            return data
        except Exception as e:
            logger.error(f"Error getting lab result {result_id}: {e}")
            raise

    async def update_lab_result(self, result_id: str, data: Union[LabResultUpdate, dict]) -> dict:
        """Update a lab result."""
        try:
            if hasattr(data, "model_dump"):
                update_data = data.model_dump(exclude_unset=True)
            elif isinstance(data, dict):
                update_data = dict(data)
            else:
                update_data = {}

            for date_key in ("test_date", "requested_at", "result_date"):
                if date_key in update_data and isinstance(update_data[date_key], (date, datetime)):
                    update_data[date_key] = update_data[date_key].isoformat()

            update_data["updated_at"] = datetime.now().isoformat()

            doc_ref = self._get_collection().document(result_id)
            doc_ref.update(update_data)

            updated = await self.get_lab_result(result_id)
            return updated
        except Exception as e:
            logger.error(f"Error updating lab result {result_id}: {e}")
            raise

    async def delete_lab_result(self, result_id: str) -> bool:
        """Delete a lab result."""
        try:
            doc_ref = self._get_collection().document(result_id)
            doc_ref.delete()
            return True
        except Exception as e:
            logger.error(f"Error deleting lab result {result_id}: {e}")
            raise