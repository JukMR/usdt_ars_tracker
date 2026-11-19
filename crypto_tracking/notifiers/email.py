"""SMTP email notifier."""

from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage

from crypto_tracking.domain import Notification
from crypto_tracking.notifiers.base import Notifier, NotifierNotConfigured

DEFAULT_SMTP_SERVER = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587


class EmailNotifier(Notifier):
    channel = "email"

    def __init__(
        self,
        *,
        smtp_server: str | None = None,
        smtp_port: int | None = None,
        sender_email: str | None = None,
        sender_password: str | None = None,
        recipients: list[str] | None = None,
        use_tls: bool | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.smtp_server = smtp_server or os.environ.get("SMTP_SERVER", DEFAULT_SMTP_SERVER)
        self.smtp_port = smtp_port or int(os.environ.get("SMTP_PORT", str(DEFAULT_SMTP_PORT)))
        self.sender_email = sender_email or os.environ.get("SENDER_EMAIL", "")
        self.sender_password = sender_password or os.environ.get("SENDER_PASSWORD", "")
        self.recipients = recipients or _split_recipients(os.environ.get("RECIPIENT_EMAIL", ""))
        self.use_tls = use_tls if use_tls is not None else _env_bool("SMTP_USE_TLS", default=True)
        self.timeout = timeout

        if not self.sender_email or not self.sender_password:
            raise NotifierNotConfigured("Email requires SENDER_EMAIL and SENDER_PASSWORD")
        if not self.recipients:
            raise NotifierNotConfigured("Email requires RECIPIENT_EMAIL")

    def send(self, notification: Notification) -> None:
        message = EmailMessage()
        message["Subject"] = notification.title
        message["From"] = self.sender_email
        message["To"] = ", ".join(self.recipients)
        message.set_content(f"{notification.title}\n\n{notification.message}")
        message.add_alternative(
            (
                "<html><body>"
                f"<h2>{html.escape(notification.title)}</h2>"
                f"<p>{html.escape(notification.message)}</p>"
                "<p><em>Automated message from crypto_tracking.</em></p>"
                "</body></html>"
            ),
            subtype="html",
        )

        with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=self.timeout) as server:
            if self.use_tls:
                server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.send_message(message, from_addr=self.sender_email, to_addrs=self.recipients)


def _split_recipients(raw: str) -> list[str]:
    return [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
