"""Lab result service for managing laboratory results."""

import logging
from datetime import datetime

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

    async def create_lab_result(self, pet_id: str, owner_id: str, data: LabResultCreate) -> dict:
        """Create a new lab result."""
        try:
            lab_data = data.model_dump()
            lab_data["pet_id"] = pet_id
            lab_data["owner_id"] = owner_id
            lab_data["created_at"] = datetime.now().isoformat()
            lab_data["updated_at"] = datetime.now().isoformat()

            doc_ref = self._get_collection().add(lab_data)
            doc_id = doc_ref[1].id

            return {
                "id": doc_id,
                **lab_data
            }
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
                results.append(data)

            return {
                "results": results,
                "total": len(results)
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
            return data
        except Exception as e:
            logger.error(f"Error getting lab result {result_id}: {e}")
            raise

    async def update_lab_result(self, result_id: str, data: LabResultUpdate) -> dict:
        """Update a lab result."""
        try:
            update_data = data.model_dump(exclude_unset=True)
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