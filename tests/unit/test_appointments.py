import unittest
from datetime import date, time, datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException

from app import schemas
from app.constant import Collections, UserRole
from app.routes import appointment_routes


class FakeSnapshot:
    def __init__(self, document_id, data=None):
        self.id = document_id
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class FakeDocument:
    def __init__(self, collection, document_id):
        self.collection = collection
        self.id = document_id

    def get(self):
        return FakeSnapshot(self.id, self.collection.data.get(self.id))

    def create(self, data):
        self.collection.data[self.id] = dict(data)

    def update(self, data):
        if self.id in self.collection.data:
            self.collection.data[self.id].update(data)

    def delete(self):
        self.collection.data.pop(self.id, None)


class FakeQuery:
    def __init__(self, collection, filters=None):
        self.collection = collection
        self.filters = filters or []
        self.limit_count = None

    def where(self, field, op_or_val, val=None):
        target_val = val if val is not None else op_or_val
        new_filters = self.filters + [(field, target_val)]
        return FakeQuery(self.collection, new_filters)

    def limit(self, count):
        self.limit_count = count
        return self

    def get(self):
        matches = []
        for doc_id, data in self.collection.data.items():
            match = True
            for field, target_val in self.filters:
                if data.get(field) != target_val:
                    match = False
                    break
            if match:
                snap = FakeSnapshot(doc_id, data)
                snap.reference = FakeDocument(self.collection, doc_id)
                matches.append(snap)
        return matches[: self.limit_count] if self.limit_count else matches


class FakeCollection:
    def __init__(self):
        self.data = {}
        self.next_id = 1

    def document(self, document_id=None):
        if document_id is None:
            document_id = f"gen-{self.next_id}"
            self.next_id += 1
        return FakeDocument(self, document_id)

    def where(self, field, op_or_val, val=None):
        return FakeQuery(self).where(field, op_or_val, val)

    def add(self, data):
        doc = self.document()
        doc.create(data)
        return None, doc


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return self.collections.setdefault(name, FakeCollection())


def valid_future_weekday():
    target = date.today() + timedelta(days=1)
    while target.weekday() == 6:  # Skip Sunday
        target += timedelta(days=1)
    return target


def sunday_date():
    target = date.today() + timedelta(days=1)
    while target.weekday() != 6:
        target += timedelta(days=1)
    return target


def appointment_document():
    return {
        "pet_id": "pet-1",
        "pet_name": "Lola",
        "pet_species": "Bird",
        "pet_sex": "Female",
        "pet_birth_date": "2024-07-13",
        "pet_weight_kg": 0.085,
        "pet_breed": "Ninfa",
        "pet_photo_url": "https://example.com/lola.png",
        "owner_id": "client-1",
        "owner_name": "Abby Ramirez",
        "last_visit": "--",
        "appointment_date": valid_future_weekday().isoformat(),
        "appointment_time": "09:00",
        "duration_blocks": 1,
        "reason": "Pulido de pico y revision general",
        "veterinarian_id": "vet-1",
        "veterinarian_name": "Maria Sanchez",
        "status": schemas.AppointmentStatus.SCHEDULED,
        "created_at": "2026-07-16T08:00:00+00:00",
    }


class AppointmentTests(unittest.TestCase):
    def test_list_veterinarians(self):
        db = FakeFirestore()
        db.collection(Collections.USERS).data["vet-1"] = {
            "full_name": "Dr. Smith",
            "email": "smith@example.com",
            "role": UserRole.VETERINARIAN,
        }
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            vets = appointment_routes.list_veterinarians(current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(len(vets), 1)
            self.assertEqual(vets[0].full_name, "Dr. Smith")

    def test_available_slots_valid_and_sunday(self):
        db = FakeFirestore()
        db.collection(Collections.USERS).data["vet-1"] = {"role": UserRole.VETERINARIAN}

        # Vet missing -> 404
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                appointment_routes.available_slots(
                    appointment_date=valid_future_weekday().isoformat(),
                    veterinarian_id="nonexistent-vet",
                    duration_blocks=1,
                    current_user={"id": "client-1", "role": UserRole.CLIENT},
                )
            self.assertEqual(ctx.exception.status_code, 404)

        # Sunday -> 0 slots
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            res_sun = appointment_routes.available_slots(
                appointment_date=sunday_date().isoformat(),
                veterinarian_id="vet-1",
                duration_blocks=1,
                current_user={"id": "client-1", "role": UserRole.CLIENT},
            )
            self.assertEqual(res_sun.slots, [])

        # Valid weekday -> returns slots
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            res_valid = appointment_routes.available_slots(
                appointment_date=valid_future_weekday().isoformat(),
                veterinarian_id="vet-1",
                duration_blocks=1,
                current_user={"id": "client-1", "role": UserRole.CLIENT},
            )
            self.assertIn("09:00", res_valid.slots)

    def test_list_appointments(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {
            "name": "Lola",
            "owner_id": "client-1",
            "breed_primary": "Poodle",
            "breed_secondary": "Golden",
        }
        db.collection(Collections.APPOINTMENTS).data["app-1"] = appointment_document()

        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            # Client listing owned appointments
            apps = appointment_routes.list_appointments(
                pet_id="pet-1",
                appointment_date=valid_future_weekday().isoformat(),
                current_user={"id": "client-1", "role": UserRole.CLIENT},
            )
            self.assertEqual(len(apps), 1)

            # Vet listing appointments
            vet_apps = appointment_routes.list_appointments(
                current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
            )
            self.assertEqual(len(vet_apps), 1)

    def test_create_appointment_success_and_errors(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {"name": "Lola", "species": "Dog", "owner_id": "client-1"}
        db.collection(Collections.USERS).data["vet-1"] = {"full_name": "Dr. Smith", "role": UserRole.VETERINARIAN}

        valid_date = valid_future_weekday()

        payload = schemas.AppointmentCreate(
            pet_id="pet-1",
            appointment_date=valid_date,
            appointment_time=time(9, 0),
            duration_blocks=1,
            reason="Checkup",
            veterinarian_id="vet-1",
        )

        # Success
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            res = appointment_routes.create_appointment(payload, current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(res.pet_id, "pet-1")
            self.assertEqual(res.status, schemas.AppointmentStatus.SCHEDULED)

        # Slot taken -> 409 Conflict
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                appointment_routes.create_appointment(payload, current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(ctx.exception.status_code, 409)

        # Sunday date -> 422
        sunday_payload = schemas.AppointmentCreate(
            pet_id="pet-1",
            appointment_date=sunday_date(),
            appointment_time=time(9, 0),
            reason="Checkup",
            veterinarian_id="vet-1",
        )
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                appointment_routes.create_appointment(sunday_payload, current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(ctx.exception.status_code, 422)

        # Outside business hours slot -> 422
        bad_time_payload = schemas.AppointmentCreate(
            pet_id="pet-1",
            appointment_date=valid_date,
            appointment_time=time(12, 0),  # Lunch break
            reason="Checkup",
            veterinarian_id="vet-1",
        )
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                appointment_routes.create_appointment(bad_time_payload, current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(ctx.exception.status_code, 422)

    def test_create_follow_up_appointment(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {"name": "Lola", "species": "Dog", "owner_id": "client-1"}
        db.collection(Collections.USERS).data["client-1"] = {"full_name": "Client One", "role": UserRole.CLIENT}

        valid_date = valid_future_weekday()
        follow_payload = schemas.AppointmentFollowUpCreate(
            pet_id="pet-1",
            appointment_date=valid_date,
            appointment_time=time(10, 0),
            duration_blocks=1,
            reason="Follow up visit",
        )

        # Unassigned vet fails -> 403
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                appointment_routes.create_follow_up_appointment(follow_payload, current_user={"id": "vet-1", "role": UserRole.VETERINARIAN})
            self.assertEqual(ctx.exception.status_code, 403)

        # Assign vet
        db.collection(Collections.APPOINTMENTS).data["prev-app"] = {
            "pet_id": "pet-1",
            "veterinarian_id": "vet-1",
            "status": schemas.AppointmentStatus.COMPLETED,
        }

        # Success
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            res = appointment_routes.create_follow_up_appointment(follow_payload, current_user={"id": "vet-1", "role": UserRole.VETERINARIAN, "full_name": "Dr. Smith"})
            self.assertEqual(res.pet_id, "pet-1")
            self.assertEqual(res.veterinarian_id, "vet-1")

    def test_reschedule_appointment(self):
        db = FakeFirestore()
        db.collection(Collections.USERS).data["vet-2"] = {"full_name": "Dr. Jones", "role": UserRole.VETERINARIAN}
        db.collection(Collections.APPOINTMENTS).data["app-1"] = appointment_document()

        valid_date = valid_future_weekday()
        upd_payload = schemas.AppointmentUpdate(
            appointment_date=valid_date,
            appointment_time=time(10, 30),
            veterinarian_id="vet-2",
        )

        # Reschedule success
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            res = appointment_routes.reschedule_appointment("app-1", upd_payload, current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(res.appointment_time, time(10, 30))
            self.assertEqual(res.veterinarian_id, "vet-2")

        # Reschedule completed appointment -> 409
        db.collection(Collections.APPOINTMENTS).data["app-1"]["status"] = schemas.AppointmentStatus.COMPLETED
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                appointment_routes.reschedule_appointment("app-1", upd_payload, current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(ctx.exception.status_code, 409)

    def test_veterinarian_completes_appointment_with_observation(self):
        db = FakeFirestore()
        db.collection(Collections.APPOINTMENTS).data["appointment-1"] = appointment_document()

        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            response = appointment_routes.complete_appointment(
                "appointment-1",
                schemas.AppointmentComplete(
                    clinical_observation=(
                        "Se realizo el pulido de pico anual del ave, "
                        "se observa en buenas condiciones."
                    ),
                ),
                current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
            )

        stored = db.collection(Collections.APPOINTMENTS).data["appointment-1"]
        self.assertEqual(response.status, schemas.AppointmentStatus.COMPLETED)
        self.assertEqual(stored["status"], schemas.AppointmentStatus.COMPLETED)

    def test_veterinarian_cannot_complete_another_vets_appointment(self):
        db = FakeFirestore()
        db.collection(Collections.APPOINTMENTS).data["appointment-1"] = appointment_document()

        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as context:
                appointment_routes.complete_appointment(
                    "appointment-1",
                    schemas.AppointmentComplete(clinical_observation="Observation"),
                    current_user={"id": "vet-2", "role": UserRole.VETERINARIAN},
                )

        self.assertEqual(context.exception.status_code, 404)

    def test_completed_appointment_cannot_be_completed_again(self):
        db = FakeFirestore()
        completed = {
            **appointment_document(),
            "status": schemas.AppointmentStatus.COMPLETED,
            "completed_at": "2026-07-16T09:30:00+00:00",
        }
        db.collection(Collections.APPOINTMENTS).data["appointment-1"] = completed

        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as context:
                appointment_routes.complete_appointment(
                    "appointment-1",
                    schemas.AppointmentComplete(clinical_observation="Observation"),
                    current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
                )

        self.assertEqual(context.exception.status_code, 409)

    def test_cancel_appointment(self):
        db = FakeFirestore()
        db.collection(Collections.APPOINTMENTS).data["app-1"] = appointment_document()

        # Cancel success
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            res = appointment_routes.cancel_appointment("app-1", current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(res.status, schemas.AppointmentStatus.CANCELLED)

        # Cancel non-scheduled (already cancelled) -> 409
        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as ctx:
                appointment_routes.cancel_appointment("app-1", current_user={"id": "client-1", "role": UserRole.CLIENT})
            self.assertEqual(ctx.exception.status_code, 409)

    def test_past_scheduled_appointment_without_clinical_data_becomes_no_show(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {
            "name": "Lola",
            "species": "Bird",
            "owner_id": "client-1",
        }
        db.collection(Collections.APPOINTMENTS).data["appointment-past"] = {
            **appointment_document(),
            "appointment_date": (date.today() - timedelta(days=2)).isoformat(),
            "appointment_time": "09:00",
            "status": schemas.AppointmentStatus.SCHEDULED,
        }

        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            appointments = appointment_routes.list_appointments(
                current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
            )

        self.assertEqual(appointments[0].status, schemas.AppointmentStatus.NO_SHOW)
        self.assertEqual(
            db.collection(Collections.APPOINTMENTS).data["appointment-past"]["status"],
            schemas.AppointmentStatus.NO_SHOW,
        )

    def test_past_scheduled_appointment_with_clinical_data_becomes_completed(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {
            "name": "Lola",
            "species": "Bird",
            "owner_id": "client-1",
        }
        db.collection(Collections.APPOINTMENTS).data["appointment-past"] = {
            **appointment_document(),
            "appointment_date": (date.today() - timedelta(days=2)).isoformat(),
            "appointment_time": "09:00",
            "status": schemas.AppointmentStatus.SCHEDULED,
            "clinical_observation": "The pet received veterinary care.",
        }

        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            appointments = appointment_routes.list_appointments(
                current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
            )

        self.assertEqual(appointments[0].status, schemas.AppointmentStatus.COMPLETED)
        self.assertEqual(
            db.collection(Collections.APPOINTMENTS).data["appointment-past"]["status"],
            schemas.AppointmentStatus.COMPLETED,
        )
    def test_same_day_scheduled_appointment_stays_scheduled(self):
        db = FakeFirestore()
        db.collection(Collections.PETS).data["pet-1"] = {
            "name": "Lola",
            "species": "Bird",
            "owner_id": "client-1",
        }
        db.collection(Collections.APPOINTMENTS).data["appointment-today"] = {
            **appointment_document(),
            "appointment_date": date.today().isoformat(),
            "appointment_time": "00:00",
            "status": schemas.AppointmentStatus.SCHEDULED,
        }

        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            appointments = appointment_routes.list_appointments(
                current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
            )

        self.assertEqual(appointments[0].status, schemas.AppointmentStatus.SCHEDULED)
        self.assertEqual(
            db.collection(Collections.APPOINTMENTS).data["appointment-today"]["status"],
            schemas.AppointmentStatus.SCHEDULED,
        )

    def test_veterinarian_can_mark_scheduled_appointment_as_no_show(self):
        db = FakeFirestore()
        db.collection(Collections.USERS).data["vet-1"] = {"role": UserRole.VETERINARIAN}
        db.collection(Collections.APPOINTMENTS).data["appointment-1"] = appointment_document()

        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            response = appointment_routes.mark_appointment_no_show(
                "appointment-1",
                current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
            )
            slots = appointment_routes.available_slots(
                appointment_date=response.appointment_date.isoformat(),
                veterinarian_id="vet-1",
                duration_blocks=1,
                current_user={"id": "client-1", "role": UserRole.CLIENT},
            )

        stored = db.collection(Collections.APPOINTMENTS).data["appointment-1"]
        self.assertEqual(response.status, schemas.AppointmentStatus.NO_SHOW)
        self.assertEqual(stored["status"], schemas.AppointmentStatus.NO_SHOW)
        self.assertIn("no_show_at", stored)
        self.assertIn("09:00", slots.slots)

    def test_veterinarian_cannot_mark_attended_appointment_as_no_show(self):
        db = FakeFirestore()
        db.collection(Collections.APPOINTMENTS).data["appointment-1"] = appointment_document()
        db.collection(Collections.MEDICATIONS).data["medication-1"] = {
            "appointment_id": "appointment-1",
            "pet_id": "pet-1",
            "name": "Vitamina B12",
        }

        with patch.object(appointment_routes, "get_firestore_db", return_value=db):
            with self.assertRaises(HTTPException) as context:
                appointment_routes.mark_appointment_no_show(
                    "appointment-1",
                    current_user={"id": "vet-1", "role": UserRole.VETERINARIAN},
                )

        self.assertEqual(context.exception.status_code, 409)
