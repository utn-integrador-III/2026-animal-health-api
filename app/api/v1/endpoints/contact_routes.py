"""Public contact form endpoint."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from .... import schemas
from ....constant import ApiPrefix
from ....services.email_service import EmailServiceError, send_contact_email

router = APIRouter(prefix=ApiPrefix.CONTACT, tags=["Contact"])


@router.post("", response_model=schemas.ContactMessageResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_contact_form(payload: schemas.ContactMessageCreate):
    """Receives public website contact requests and sends them by email."""
    try:
        send_contact_email(
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            subject=payload.subject,
            message=payload.message,
        )
    except EmailServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return schemas.ContactMessageResponse(
        id=str(uuid4()),
        status="sent",
        created_at=datetime.now(UTC).isoformat(),
    )
