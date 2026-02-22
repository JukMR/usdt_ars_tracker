import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Final

from crypto_tracking.logging_config import logger
from crypto_tracking.metrics_server.backend.env_helper import EnvHelper
from crypto_tracking.metrics_server.backend.notifiers.notifier_abs import NotifierAbs


class EmailNotifier(NotifierAbs):
    """Class for sending email notifications via SMTP."""

    DEFAULT_SMTP_SERVER: Final[str] = "smtp.gmail.com"
    DEFAULT_SMTP_PORT: Final[int] = 587

    def __init__(
        self,
        smtp_server: str | None = None,
        smtp_port: int | None = None,
        sender_email: str | None = None,
        sender_password: str | None = None,
        recipient_email: str | None = None,
    ) -> None:
        self._env_helper = EnvHelper()

        self._smtp_server: str = smtp_server or self._env_helper.get_env_var("SMTP_SERVER", self.DEFAULT_SMTP_SERVER)
        self._smtp_port: int = smtp_port or int(self._env_helper.get_env_var("SMTP_PORT", str(self.DEFAULT_SMTP_PORT)))
        self._sender_email: str = sender_email or self._env_helper.get_env_var("SENDER_EMAIL")
        self._sender_password: str = sender_password or self._env_helper.get_env_var("SENDER_PASSWORD")
        self._recipient_email: str = recipient_email or self._env_helper.get_env_var("RECIPIENT_EMAIL")

    def send_alert(self, msg: str) -> None:
        """Send an email alert with the given message."""
        subject: str = "Crypto Alert: USDT/ARS Price Threshold"

        try:
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self._sender_email
            message["To"] = self._recipient_email

            text = f"""
            Crypto Price Alert
            
            {msg}
            
            This is an automated alert from the USDT/ARS Crypto Tracker.
            """

            html = f"""
            <html>
            <body>
                <h2>Crypto Price Alert</h2>
                <p>{msg}</p>
                <p><em>This is an automated alert from the USDT/ARS Crypto Tracker.</em></p>
            </body>
            </html>
            """

            part1 = MIMEText(text, "plain")
            part2 = MIMEText(html, "html")
            message.attach(part1)
            message.attach(part2)

            with smtplib.SMTP(self._smtp_server, self._smtp_port) as server:
                server.starttls()
                server.login(self._sender_email, self._sender_password)
                server.sendmail(self._sender_email, self._recipient_email, message.as_string())

            logger.info("Email alert sent successfully to %s", self._recipient_email)

        except smtplib.SMTPAuthenticationError as e:
            logger.error("SMTP authentication failed: %s", e)
            raise

        except smtplib.SMTPConnectError as e:
            logger.error("Failed to connect to SMTP server %s:%s: %s", self._smtp_server, self._smtp_port, e)
            raise

        except smtplib.SMTPException as e:
            logger.error("SMTP error while sending email: %s", e)
            raise

        except Exception as e:
            logger.error("Unexpected error sending email alert: %s", e)
            raise
