"""Emails the generated HTML report via SMTP.

Recipients and the on/off switch are test data (test_data/prod.json ->
settings.email_report), not env vars, so they can be edited without
touching secrets — see conftest.py's pytest_sessionfinish hook, the only
caller. SMTP server/credentials are env vars (src/config/settings.py)
since those ARE secrets.
"""
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from src.config.settings import Settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


def send_report_email(
    settings: Settings, report_path: Path, recipients: list[str], summary_text: str = ""
) -> None:
    """Sends report_path as an attachment to recipients via SMTP, using
    settings.smtp_*. Raises on missing config/send failure — the caller is
    responsible for catching and logging rather than letting this break
    the test run."""
    if not settings.smtp_host:
        raise RuntimeError("SMTP_HOST is not configured — cannot send the report email")
    if not recipients:
        raise RuntimeError("No recipients configured for the report email")
    if not report_path.exists():
        raise RuntimeError(f"Report file not found at {report_path}")

    message = MIMEMultipart()
    message["Subject"] = f"Cropin API Automation Report — {settings.env.upper()}"
    message["From"] = settings.smtp_from_email
    message["To"] = ", ".join(recipients)
    message.attach(MIMEText(summary_text or "See the attached HTML report.", "plain"))

    with open(report_path, "rb") as f:
        attachment = MIMEApplication(f.read(), _subtype="html")
    attachment.add_header("Content-Disposition", "attachment", filename=report_path.name)
    message.attach(attachment)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, recipients, message.as_string())

    logger.info("Report emailed to %s", ", ".join(recipients))
