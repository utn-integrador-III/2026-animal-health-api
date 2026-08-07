from unittest.mock import Mock, patch

import pytest

from app.services import email_service


def test_send_contact_email_requires_brevo_configuration():
    with patch.object(email_service, "BREVO_API_KEY", ""), patch.object(
        email_service, "BREVO_FROM_EMAIL", ""
    ):
        with pytest.raises(email_service.EmailServiceError) as exc_info:
            email_service.send_contact_email(
                name="Abby Ramirez",
                email="abbyra@gmail.com",
                phone=None,
                subject="Consulta",
                message="Necesito informacion sobre horarios.",
            )

    assert str(exc_info.value) == "Brevo configuration is incomplete."


def test_send_contact_email_posts_message_to_brevo():
    response = Mock(status_code=201)
    client = Mock()
    client.post.return_value = response
    client_context = Mock()
    client_context.__enter__ = Mock(return_value=client)
    client_context.__exit__ = Mock(return_value=None)

    with patch.object(email_service, "BREVO_API_KEY", "brevo-key"), patch.object(
        email_service, "BREVO_FROM_EMAIL", "verified@example.com"
    ), patch.object(email_service.httpx, "Client", return_value=client_context):
        email_service.send_contact_email(
            name="Abby Ramirez",
            email="abbyra@gmail.com",
            phone="45871263",
            subject="Consulta veterinaria",
            message="Quisiera consultar horarios disponibles para una revision.",
        )

    client.post.assert_called_once()
    _, kwargs = client.post.call_args
    assert kwargs["headers"]["api-key"] == "brevo-key"
    assert kwargs["json"]["sender"]["email"] == "verified@example.com"
    assert kwargs["json"]["to"] == [{"email": "ediloma21@gmail.com"}]
    assert kwargs["json"]["replyTo"] == {
        "email": "abbyra@gmail.com",
        "name": "Abby Ramirez",
    }
    assert kwargs["json"]["subject"] == "Animal Health contact: Consulta veterinaria"


def test_send_contact_email_raises_when_brevo_rejects_message():
    response = Mock(status_code=401)
    client = Mock()
    client.post.return_value = response
    client_context = Mock()
    client_context.__enter__ = Mock(return_value=client)
    client_context.__exit__ = Mock(return_value=None)

    with patch.object(email_service, "BREVO_API_KEY", "brevo-key"), patch.object(
        email_service, "BREVO_FROM_EMAIL", "verified@example.com"
    ), patch.object(email_service.httpx, "Client", return_value=client_context):
        with pytest.raises(email_service.EmailServiceError) as exc_info:
            email_service.send_contact_email(
                name="Abby Ramirez",
                email="abbyra@gmail.com",
                phone="45871263",
                subject="Consulta veterinaria",
                message="Quisiera consultar horarios disponibles para una revision.",
            )

    assert str(exc_info.value) == "Brevo returned status 401."


def test_send_temporary_password_email_targets_new_client():
    response = Mock(status_code=201)
    client = Mock()
    client.post.return_value = response
    client_context = Mock()
    client_context.__enter__ = Mock(return_value=client)
    client_context.__exit__ = Mock(return_value=None)

    with patch.object(email_service, "BREVO_API_KEY", "brevo-key"), patch.object(
        email_service, "BREVO_FROM_EMAIL", "verified@example.com"
    ), patch.object(email_service.httpx, "Client", return_value=client_context):
        email_service.send_temporary_password_email(
            recipient_email="samuel@example.com",
            recipient_name="Samuel Romero",
            temporary_password="TempPass2026!",
        )

    _, kwargs = client.post.call_args
    payload = kwargs["json"]
    assert payload["to"] == [{"email": "samuel@example.com", "name": "Samuel Romero"}]
    assert payload["subject"] == "Acceso temporal a Animal Health"
    assert "TempPass2026!" in payload["textContent"]
    assert "TempPass2026!" in payload["htmlContent"]
