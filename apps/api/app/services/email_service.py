# Transactional email (SHELL-3): an EmailService port plus swappable provider adapters, selected
# from EMAIL_PROVIDER. Keeping the provider behind the port means swapping Resend for another
# sender is a one-line mapping change, with zero callers touched.

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.config import EmailProvider, settings

logger = logging.getLogger(__name__)

# Timeout for outbound provider HTTP calls.
_SEND_TIMEOUT_SECONDS = 10.0


# A ready-to-send message: one recipient, a subject, and HTML + plain-text bodies.
@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    html: str
    text: str


# Port: the contract every provider adapter implements.
class EmailService(ABC):
    # Sends the message; raises on a provider failure so the caller can react.
    @abstractmethod
    async def send(self, message: EmailMessage) -> None: ...


# Adapter: logs the message instead of sending it. Default for local dev and tests, where no
# real provider is configured; the verification/reset links are visible in the API logs.
class ConsoleEmailService(EmailService):
    # Logs the recipient, subject, and text body at INFO.
    async def send(self, message: EmailMessage) -> None:
        logger.info("[email:console] to=%s subject=%s\n%s", message.to, message.subject, message.text)


# Adapter: sends via the Resend HTTP API (https://resend.com/docs/api-reference/emails/send-email).
class ResendEmailService(EmailService):
    _API_URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, sender: str) -> None:
        self._api_key = api_key
        self._sender = sender

    # Posts the message to Resend; raises httpx.HTTPError on a non-2xx response.
    async def send(self, message: EmailMessage) -> None:
        async with httpx.AsyncClient(timeout=_SEND_TIMEOUT_SECONDS) as client:
            response = await client.post(
                self._API_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "from": self._sender,
                    "to": [message.to],
                    "subject": message.subject,
                    "html": message.html,
                    "text": message.text,
                },
            )
            response.raise_for_status()


# Builds the email service for the configured provider (Mapcraft's selector pattern). Cached so
# every caller shares one adapter instance.
@lru_cache(maxsize=1)
def get_email_service() -> EmailService:
    if settings.email_provider == EmailProvider.resend:
        # The config validator guarantees email_api_key is set when the provider is resend.
        return ResendEmailService(api_key=settings.email_api_key, sender=settings.email_from)
    return ConsoleEmailService()
