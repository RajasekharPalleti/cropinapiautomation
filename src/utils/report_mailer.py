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


def format_results_summary(results: list[dict], max_reason_chars: int = 200) -> str:
    """The email body's result block: how many tests ran / passed / failed
    (and errored, skipped), then every failed or errored test case by name
    with the first line of why (pytest's own "assert x == y / where ..." lines
    below it are left out). `results` is conftest.py's run log — one
    dict per recorded outcome: {"test": nodeid, "outcome": passed | failed |
    error | skipped | xfailed | xpassed, "reason": str}. A teardown error on
    a test that already passed is its own entry (pytest reports it the same
    way), so the tally can add up to more than the number of tests."""
    counts = {key: 0 for key in ("passed", "failed", "error", "skipped", "xfailed", "xpassed")}
    for result in results:
        counts[result["outcome"]] += 1
    tests_run = len({result["test"] for result in results})

    line = (
        f"Result: {tests_run} tests run - {counts['passed']} passed, {counts['failed']} failed, "
        f"{counts['error']} errors, {counts['skipped']} skipped"
    )
    if counts["xfailed"] or counts["xpassed"]:
        line += f" ({counts['xfailed']} expected failures, {counts['xpassed']} unexpected passes)"
    line += "."

    broken = [result for result in results if result["outcome"] in ("failed", "error")]
    if not broken:
        return f"{line}\nFailed test cases: none."

    lines = [line, f"Failed test cases ({len(broken)}):"]
    for number, result in enumerate(broken, start=1):
        reason = next((text.strip() for text in (result.get("reason") or "").splitlines() if text.strip()), "")
        if len(reason) > max_reason_chars:
            reason = reason[: max_reason_chars - 3] + "..."
        label = result["test"] if result["outcome"] == "failed" else f"{result['test']} [error]"
        lines.append(f"{number}. {label}" + (f" - {reason}" if reason else ""))
    return "\n".join(lines)


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
