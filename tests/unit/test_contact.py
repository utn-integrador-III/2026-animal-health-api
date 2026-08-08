import pytest
from fastapi import HTTPException
from unittest.mock import patch

from app import schemas
from app.api.v1.endpoints import contact_routes


def contact_payload():
    return schemas.ContactMessageCreate(
        name="Abby Ramirez",
        email="abbyra@gmail.com",
        phone="45871263",
        subject="Consulta veterinaria",
        message="Quisiera consultar horarios disponibles para una revision.",
    )


def test_submit_contact_form_sends_email():
    payload = contact_payload()

    with patch.object(contact_routes, "send_contact_email") as send_contact_email:
        response = contact_routes.submit_contact_form(payload)

    send_contact_email.assert_called_once_with(
        name="Abby Ramirez",
        email="abbyra@gmail.com",
        phone="45871263",
        subject="Consulta veterinaria",
        message="Quisiera consultar horarios disponibles para una revision.",
    )
    assert response.status == "sent"
    assert response.id
    assert response.created_at


def test_submit_contact_form_returns_503_when_email_fails():
    payload = contact_payload()

    with patch.object(
        contact_routes,
        "send_contact_email",
        side_effect=contact_routes.EmailServiceError("Brevo configuration is incomplete."),
    ):
        with pytest.raises(HTTPException) as exc_info:
            contact_routes.submit_contact_form(payload)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Brevo configuration is incomplete."
