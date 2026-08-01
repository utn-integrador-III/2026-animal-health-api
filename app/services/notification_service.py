"""Notification service for managing user notifications."""

import logging
from datetime import date, datetime
from typing import List, Optional

from google.cloud.firestore import CollectionReference

from app.constant import Collections
from app.firebase_config import get_firestore_db

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing notifications."""

    def __init__(self):
        self.db = get_firestore_db()

    def _get_notifications_collection(self) -> CollectionReference:
        return self.db.collection(Collections.NOTIFICATIONS)

    def _get_vaccines_collection(self) -> CollectionReference:
        return self.db.collection(Collections.VACCINES)

    def _get_pets_collection(self) -> CollectionReference:
        return self.db.collection(Collections.PETS)

    def _get_users_collection(self) -> CollectionReference:
        return self.db.collection(Collections.USERS)

    async def check_vaccines_due_for_notification(self) -> dict:
        """Check vaccines due for notification (7 days or less to expiration)."""
        try:
            logger.info("Checking vaccines due for notification...")

            vaccines_ref = self._get_vaccines_collection()
            vaccines_query = vaccines_ref.where("notification_sent", "==", False)
            vaccines_snapshot = vaccines_query.stream()

            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            notifications_created = 0
            errors = []

            for vaccine_doc in vaccines_snapshot:
                vaccine_data = vaccine_doc.to_dict()
                vaccine_data["id"] = vaccine_doc.id

                try:
                    expiration_date = vaccine_data.get("expiration_date")
                    if not expiration_date:
                        logger.warning(f"Vaccine {vaccine_doc.id} has no expiration date")
                        continue

                    if isinstance(expiration_date, str):
                        expiration_date = datetime.fromisoformat(expiration_date)
                    elif isinstance(expiration_date, datetime):
                        pass
                    else:
                        logger.warning(f"Vaccine {vaccine_doc.id} has invalid expiration date format")
                        continue

                    expiration_date = expiration_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    days_until_expiration = (expiration_date - today).days

                    if 0 <= days_until_expiration <= 7:
                        await self._create_vaccine_notification(
                            vaccine_data=vaccine_data,
                            days_until_expiration=days_until_expiration
                        )

                        vaccine_doc.reference.update({
                            "notification_sent": True,
                            "notification_date": datetime.now().isoformat()
                        })

                        notifications_created += 1
                        logger.info(f"Notification created for vaccine {vaccine_doc.id}")

                except Exception as e:
                    errors.append(f"Vaccine {vaccine_doc.id}: {str(e)}")
                    logger.error(f"Error processing vaccine {vaccine_doc.id}: {e}")

            return {
                "success": True,
                "notifications_created": notifications_created,
                "errors": errors if errors else None,
            }

        except Exception as e:
            logger.error(f"Error checking vaccines: {e}")
            return {"success": False, "error": str(e), "notifications_created": 0}

    async def check_medications_due_for_notification(self) -> dict:
        """Check active medications and create notifications for those due today."""
        try:
            logger.info("Checking medications due for notification...")
            db = get_firestore_db()
            medications_ref = db.collection(Collections.MEDICATIONS)
            active_medications = medications_ref.where("status", "==", "active").stream()

            today = date.today()
            today_str = today.isoformat()
            notifications_created = 0
            errors = []

            for med_doc in active_medications:
                med_data = med_doc.to_dict()
                med_data["id"] = med_doc.id

                try:
                    start_date_str = med_data.get("start_date")
                    end_date_str = med_data.get("end_date")

                    if not start_date_str or not end_date_str:
                        continue

                    start_date = date.fromisoformat(start_date_str)
                    end_date = date.fromisoformat(end_date_str)

                    if start_date <= today <= end_date:
                        pet_id = med_data.get("pet_id")
                        pet_doc = db.collection(Collections.PETS).document(pet_id).get()
                        if not pet_doc.exists:
                            continue
                        pet_data = pet_doc.to_dict()
                        owner_id = pet_data.get("owner_id")
                        pet_name = pet_data.get("name", "Mascota")

                        if not owner_id:
                            continue

                        # Check if a notification for this medication was already created for today
                        notif_query = db.collection(Collections.NOTIFICATIONS) \
                            .where("user_id", "==", owner_id) \
                            .where("medication_id", "==", med_doc.id) \
                            .where("scheduled_date", "==", today_str) \
                            .get()

                        if len(notif_query) == 0:
                            notification_data = {
                                "user_id": owner_id,
                                "pet_id": pet_id,
                                "medication_id": med_doc.id,
                                "type": "medication_reminder",
                                "title": f"💊 Hora de la medicina para {pet_name}",
                                "message": f"Es hora de darle a {pet_name} su medicamento: {med_data.get('name')}.",
                                "medication_name": med_data.get("name"),
                                "medication_dosage": med_data.get("dosage"),
                                "medication_time": med_data.get("administration_time") or "08:00",
                                "pet_name": pet_name,
                                "read": False,
                                "urgency": "info",
                                "scheduled_date": today_str,
                                "link": f"/pets/{pet_id}/medications",
                                "created_at": datetime.now().isoformat()
                            }
                            db.collection(Collections.NOTIFICATIONS).add(notification_data)
                            notifications_created += 1
                            logger.info(f"Notification created for medication {med_doc.id} (Pet: {pet_name})")

                except Exception as e:
                    errors.append(f"Medication {med_doc.id}: {str(e)}")
                    logger.error(f"Error processing medication {med_doc.id}: {e}")

            return {
                "success": True,
                "notifications_created": notifications_created,
                "errors": errors if errors else None
            }
        except Exception as e:
            logger.error(f"Error checking medications: {e}")
            return {"success": False, "error": str(e), "notifications_created": 0}

    async def _create_vaccine_notification(self, vaccine_data: dict, days_until_expiration: int):
        """Create a notification for a vaccine about to expire."""
        try:
            pet_id = vaccine_data.get("pet_id")
            if not pet_id:
                logger.warning(f"Vaccine {vaccine_data.get('id')} has no pet_id")
                return

            pet_doc = self._get_pets_collection().document(pet_id).get()
            if not pet_doc.exists:
                logger.warning(f"Pet {pet_id} not found")
                return

            pet_data = pet_doc.to_dict()
            owner_id = pet_data.get("owner_id")
            if not owner_id:
                logger.warning(f"Pet {pet_id} has no owner_id")
                return

            pet_name = pet_data.get("name", "Mascota")
            vaccine_name = vaccine_data.get("name", "Vacuna")
            expiration_date = vaccine_data.get("expiration_date")

            if days_until_expiration <= 2:
                urgency = "urgent"
                title = f"🚨 ¡URGENTE! Vacuna de {pet_name} por vencer"
                message = f"La vacuna {vaccine_name} de {pet_name} vence en {days_until_expiration} día(s). Agenda una cita ahora."
            elif days_until_expiration <= 5:
                urgency = "warning"
                title = f"⚠️ Vacuna de {pet_name} próxima a vencer"
                message = f"La vacuna {vaccine_name} de {pet_name} vence en {days_until_expiration} día(s). Recuerda programar su renovación."
            else:
                urgency = "info"
                title = f"💉 Recordatorio: Vacuna de {pet_name}"
                message = f"Recordatorio: La vacuna {vaccine_name} de {pet_name} vencerá el {expiration_date}. Programa tu cita con anticipación."

            notification_data = {
                "user_id": owner_id,
                "pet_id": pet_id,
                "vaccine_id": vaccine_data.get("id"),
                "type": "vaccine_expiration",
                "title": title,
                "message": message,
                "read": False,
                "urgency": urgency,
                "expiration_date": str(expiration_date) if expiration_date else None,
                "days_until": days_until_expiration,
                "link": f"/pets/{pet_id}/vaccines",
                "created_at": datetime.now().isoformat()
            }

            self._get_notifications_collection().add(notification_data)

        except Exception as e:
            logger.error(f"Error creating vaccine notification: {e}")
            raise

    async def get_user_notifications(self, user_id: str, only_unread: bool = False, limit: int = 50, offset: int = 0) -> dict:
        """Get notifications for a specific user."""
        try:
            notifications_ref = self._get_notifications_collection()
            query = notifications_ref.where("user_id", "==", user_id)

            if only_unread:
                query = query.where("read", "==", False)

            query = query.order_by("created_at", direction="DESCENDING")
            query = query.limit(limit).offset(offset)

            snapshot = query.stream()
            notifications = []
            unread_count = 0

            for doc in snapshot:
                data = doc.to_dict()
                data["id"] = doc.id
                notifications.append(data)
                if not data.get("read", True):
                    unread_count += 1

            total_query = notifications_ref.where("user_id", "==", user_id)
            if only_unread:
                total_query = total_query.where("read", "==", False)
            total_count = len(list(total_query.stream()))

            unread_query = notifications_ref.where("user_id", "==", user_id).where("read", "==", False)
            total_unread = len(list(unread_query.stream()))

            return {
                "notifications": notifications,
                "total": total_count,
                "unread_count": total_unread,
                "limit": limit,
                "offset": offset
            }

        except Exception as e:
            logger.error(f"Error getting notifications for user {user_id}: {e}")
            raise

    async def mark_notification_as_read(self, user_id: str, notification_id: str) -> dict:
        """Mark a specific notification as read."""
        try:
            doc_ref = self._get_notifications_collection().document(notification_id)
            doc = doc_ref.get()

            if not doc.exists:
                return {"success": False, "error": "Notification not found"}

            data = doc.to_dict()
            if data.get("user_id") != user_id:
                return {"success": False, "error": "Permission denied"}

            doc_ref.update({
                "read": True,
                "read_at": datetime.now().isoformat()
            })

            return {"success": True, "notification_id": notification_id}

        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            raise

    async def mark_all_notifications_as_read(self, user_id: str) -> dict:
        """Mark all notifications for a user as read."""
        try:
            notifications_ref = self._get_notifications_collection()
            query = notifications_ref.where("user_id", "==", user_id).where("read", "==", False)
            snapshot = query.stream()

            count = 0
            for doc in snapshot:
                doc.reference.update({
                    "read": True,
                    "read_at": datetime.now().isoformat()
                })
                count += 1

            return {"success": True, "marked_count": count}

        except Exception as e:
            logger.error(f"Error marking all notifications as read: {e}")
            raise

    async def delete_notification(self, user_id: str, notification_id: str) -> dict:
        """Delete a notification."""
        try:
            doc_ref = self._get_notifications_collection().document(notification_id)
            doc = doc_ref.get()

            if not doc.exists:
                return {"success": False, "error": "Notification not found"}

            data = doc.to_dict()
            if data.get("user_id") != user_id:
                return {"success": False, "error": "Permission denied"}

            doc_ref.delete()
            return {"success": True, "notification_id": notification_id}

        except Exception as e:
            logger.error(f"Error deleting notification: {e}")
            raise