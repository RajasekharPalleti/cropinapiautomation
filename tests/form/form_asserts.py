"""Assertions shared by the form tests: a form body (the create/update
response, or a GET) is compared with the form that was sent, a refused
request is checked against the statuses allowed in test data, and timestamps
are compared as parsed instants / UTC days, never as raw strings."""
import re
from datetime import datetime, timezone

from src.utils.task_fill_assertions import status_allowed

_OFFSET_WITHOUT_COLON = re.compile(r"([+-]\d{2})(\d{2})$")


def parse_instant(value):
    """ISO-8601 string -> timezone-aware UTC datetime, or None when it's
    missing, not a string, not parseable or has no offset (an offset-less
    value is ambiguous, so it isn't guessed at). The server writes timestamps
    in several styles — 2026-10-19T09:38:33.637+0000, ...Z, ...00Z — all
    handled; compare the parsed instants, not the strings."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    text = _OFFSET_WITHOUT_COLON.sub(r"\1:\2", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def utc_day(value):
    """The UTC calendar day ('2026-10-19') of a timestamp, or None."""
    parsed = parse_instant(value)
    return parsed.date().isoformat() if parsed else None


def utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def assert_on_utc_day(value, allowed_days, what: str, source: str) -> None:
    """`value` (a timestamp, in any of the server's styles) falls on one of
    `allowed_days` (UTC 'YYYY-MM-DD' strings). Callers pass the day the value
    was produced and today's day, so a UTC-midnight rollover between the call
    and the assertion can't fail the test."""
    found = utc_day(value)
    assert found in allowed_days, (
        f"{source}: expected {what} on UTC day {' or '.join(sorted(allowed_days))}, got {value!r}"
        + ("" if found else " (missing or not a parseable timestamp with an offset)")
    )


def day(value):
    """'2026-10-19T00:00:00.000Z' / '2026-10-19T00:00:00Z' -> '2026-10-19' — the
    server writes the same instant without milliseconds, so dates are
    compared by calendar day."""
    return str(value)[:10] if value else None


def assert_attributes_match(body: dict, sent: dict, source: str) -> None:
    """Every custom attribute that was sent comes back with the same values
    (matched by name, so list order doesn't matter). Only the sent keys are
    compared, so a field the server adds on its own isn't a failure."""
    sent_attributes = sent["data"]["customAttributes"]
    got_attributes = {a.get("name"): a for a in (body.get("data") or {}).get("customAttributes") or []}
    assert len(got_attributes) == len(sent_attributes), (
        f"{source}: expected {len(sent_attributes)} custom attributes "
        f"{[a['name'] for a in sent_attributes]}, got {list(got_attributes)}"
    )
    for sent_attribute in sent_attributes:
        got = got_attributes.get(sent_attribute["name"])
        assert got is not None, (
            f"{source}: custom attribute {sent_attribute['name']!r} missing, got {list(got_attributes)}"
        )
        for key, expected in sent_attribute.items():
            assert got.get(key) == expected, (
                f"{source}: attribute {sent_attribute['name']!r} field {key!r}: "
                f"expected {expected!r}, got {got.get(key)!r}"
            )


def assert_form_matches(body: dict, sent: dict, source: str) -> None:
    """The fields the form body set, as echoed by the create/update response
    or read back by a GET (`source` names which, for the failure message).
    `sent` is the form as it should now be — for an update, the create
    payload with the new name."""
    assert body.get("name") == sent["name"], (
        f"{source}: expected name {sent['name']!r}, got {body.get('name')!r}"
    )
    assert body.get("status") == sent["status"], (
        f"{source}: expected status {sent['status']!r}, got {body.get('status')!r}"
    )
    assert body.get("formTypeId") == sent["formTypeId"], (
        f"{source}: expected formTypeId {sent['formTypeId']!r}, got {body.get('formTypeId')!r}"
    )
    got_varieties = body.get("varietyId") or []
    assert all(variety in got_varieties for variety in sent["varietyId"]), (
        f"{source}: expected varietyId to contain {sent['varietyId']}, got {got_varieties}"
    )
    for field in ("validFrom", "validTo"):
        assert day(body.get(field)) == day(sent[field]), (
            f"{source}: expected {field} on {day(sent[field])}, got {body.get(field)!r}"
        )
    assert body.get("deleted") is False, f"{source}: expected deleted false, got {body.get('deleted')!r}"
    assert_attributes_match(body, sent, source)


def assert_rejected(response, allowed: list, what: str) -> None:
    """The request was refused: the status is one of `allowed` (exact codes
    and/or classes like '4xx' — form.expectations in test data, frozen to the
    exact code after the first real run), and the body carries no id, i.e. no
    record was created. A 2xx means the server accepted a request it should
    have refused (and may have created a record); a 5xx is a server error, not
    a validation failure — both fail the status check with the actual status
    and the body."""
    status = response.status
    accepted = " — DEFECT: the request was accepted and may have created a record" if 200 <= status < 300 else ""
    assert status_allowed(status, allowed), (
        f"{what}: expected status in {allowed}, got {status}{accepted}. Body: {response.text()}"
    )
    try:
        body = response.json()
    except ValueError:
        body = None
    created_id = body.get("id") if isinstance(body, dict) else None
    assert created_id is None, (
        f"{what}: the refused request's response carries an id ({created_id!r}), so a record may have "
        f"been created. Body: {response.text()}"
    )
