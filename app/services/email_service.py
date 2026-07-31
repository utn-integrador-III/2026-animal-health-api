"""Email delivery helpers for public contact messages."""

from html import escape

import httpx

from ..config import (
    BREVO_API_KEY,
    BREVO_FROM_EMAIL,
    BREVO_FROM_NAME,
    CONTACT_RECEIVER_EMAIL,
)

BREVO_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


class EmailServiceError(Exception):
    """Raised when the contact email cannot be sent."""


def send_contact_email(
    *,
    name: str,
    email: str,
    phone: str | None,
    subject: str,
    message: str,
) -> None:
    """Sends a public contact message to the configured receiver email using Brevo."""
    if not BREVO_API_KEY or not BREVO_FROM_EMAIL:
        raise EmailServiceError("Brevo configuration is incomplete.")

    phone_value = phone or "Not provided"
    html_content = f"""
    <h2>New Animal Health contact request</h2>
    <p><strong>Name:</strong> {escape(name)}</p>
    <p><strong>Email:</strong> {escape(email)}</p>
    <p><strong>Phone:</strong> {escape(phone_value)}</p>
    <p><strong>Subject:</strong> {escape(subject)}</p>
    <hr />
    <p><strong>Message:</strong></p>
    <p>{escape(message).replace(chr(10), '<br />')}</p>
    """

    payload = {
        "sender": {"name": BREVO_FROM_NAME, "email": BREVO_FROM_EMAIL},
        "to": [{"email": CONTACT_RECEIVER_EMAIL}],
        "replyTo": {"email": email, "name": name},
        "subject": f"Animal Health contact: {subject}",
        "htmlContent": html_content,
        "textContent": (
            "New Animal Health contact request\n\n"
            f"Name: {name}\n"
            f"Email: {email}\n"
            f"Phone: {phone_value}\n"
            f"Subject: {subject}\n\n"
            f"Message:\n{message}"
        ),
    }
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }

    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(BREVO_EMAIL_URL, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise EmailServiceError("The contact email could not be sent.") from exc

    if response.status_code not in {200, 201, 202}:
        raise EmailServiceError(f"Brevo returned status {response.status_code}.")