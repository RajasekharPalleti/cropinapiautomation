"""Reusable task-fill assertions (spec section 8, A1-A12) plus the status /
response-time helpers every task-fill test shares.

The A-assertions take plain dicts (the post-fill GET response body, the
pre-fill GET body, the body that was sent) so each test can call just the
ones its scenario is about.
"""
from datetime import datetime
from typing import Any

from src.utils.task_fill_payload import audited_area, date_part, get_path, multiply


def _status(task: dict) -> str:
    return str(task.get("status") or "").lower()


# --- status codes -----------------------------------------------------------


def status_allowed(status: int, allowed: list[str]) -> bool:
    """allowed holds exact codes ('404') and/or classes ('4xx'). The lists
    live in test data (task.fill_expectations) so a 'confirm on first run'
    expectation can be frozen to an exact code there, with no code change."""
    for entry in allowed:
        entry = str(entry).lower()
        if entry.endswith("xx"):
            if status // 100 == int(entry[0]):
                return True
        elif status == int(entry):
            return True
    return False


def assert_status_in(response, allowed: list[str], what: str = "") -> None:
    assert status_allowed(response.status, allowed), (
        f"{what + ': ' if what else ''}expected status in {allowed}, got {response.status}. "
        f"Body: {response.text()}"
    )


def is_2xx(response) -> bool:
    return 200 <= response.status < 300


def response_task(response) -> dict:
    """The task object in a fill response (some endpoints wrap the
    single result in a one-item list)."""
    body = response.json()
    return body[0] if isinstance(body, list) and body else body


def assert_not_server_error(response, what: str = "") -> None:
    assert response.status < 500, (
        f"{what + ': ' if what else ''}server error {response.status}. Body: {response.text()}"
    )


def assert_fill_succeeded(response) -> None:
    """A1."""
    assert response.status in (200, 201), (
        f"A1: expected 200/201 from the fill request, got {response.status}. Body: {response.text()}"
    )


def assert_fill_fast(response, max_ms: float) -> None:
    """The response-time check from the spec (every fill request)."""
    duration = getattr(response, "duration_ms", None)
    if duration is None:
        return
    assert duration < max_ms, f"Fill request took {duration} ms, over the {max_ms} ms limit"


# --- post-fill task state (A2-A12) ------------------------------------------


def assert_complete(task: dict) -> None:
    """A2 — the request sends COMPLETE, the GET returns lowercase."""
    assert _status(task) == "complete", f"A2: expected status 'complete', got {task.get('status')!r}"


def assert_not_complete(task: dict) -> None:
    assert _status(task) != "complete", (
        f"Expected the task NOT to be complete, got status {task.get('status')!r}"
    )


def assert_outcome_consistent(response, after: dict) -> None:
    """For scenarios where either an accept or a reject is acceptable
    (expectation still to be frozen): the task's state has to agree with
    what the response said — accepted means completed, rejected means not."""
    if 200 <= response.status < 300:
        assert_complete(after)
    else:
        assert_not_complete(after)


def assert_open(task: dict) -> None:
    assert _status(task) == "open", f"Expected the task to remain 'open', got {task.get('status')!r}"


def assert_execution_dates(task: dict, exec_day) -> None:
    """A3 + A4 + A5 — every execution-date field carries the execution day."""
    expected = exec_day.isoformat()
    for field in ("executedOn", "expExecutedOn", "startDate", "endDate"):
        assert date_part(task.get(field)) == expected, (
            f"A3/A4: expected {field} date {expected}, got {task.get(field)!r}"
        )
    std = get_path(task, "data.standardAttributesEntered.executedOn")
    assert date_part(std) == date_part(task.get("executedOn")), (
        f"A5: data.standardAttributesEntered.executedOn {std!r} != executedOn {task.get('executedOn')!r}"
    )


def assert_custom_attributes(task: dict, sent: dict) -> None:
    """A7 — what was sent is what's stored, key for key."""
    stored = get_path(task, "data.customAttributesEntered") or {}
    for key, value in sent.items():
        assert stored.get(key) == value, (
            f"A7: custom attribute {key!r}: expected {value!r}, got {stored.get(key)!r}"
        )


def assert_chemical(task: dict, sent_item: dict) -> None:
    """A8 — chemical entry matches (everything except the total, which A9 owns)."""
    stored = get_path(task, "data.planHeaderAttributesEntered[0]") or {}
    for key in ("typeId", "chemicalName", "perQuantity", "chemicalQuantity", "chemicalConcentration"):
        assert stored.get(key) == sent_item.get(key), (
            f"A8: planHeaderAttributesEntered[0].{key}: expected {sent_item.get(key)!r}, "
            f"got {stored.get(key)!r}"
        )


def assert_total_chemical(task: dict, quantity_count: Any, ca: dict, unit: str) -> None:
    """A9 — total = entered quantity x audited area."""
    expected = multiply(quantity_count, audited_area(ca))
    stored = get_path(task, "data.planHeaderAttributesEntered[0].totalChemicalQuantity") or {}
    assert stored.get("count") == expected, (
        f"A9: totalChemicalQuantity.count expected {quantity_count} x {audited_area(ca)} = "
        f"{expected}, got {stored.get('count')!r}"
    )
    assert stored.get("unit") == unit, f"A9: expected total unit {unit}, got {stored.get('unit')!r}"


def assert_filled_by(task: dict, expected: str) -> None:
    """A10."""
    assert task.get("filledBy") == expected, f"A10: expected filledBy {expected!r}, got {task.get('filledBy')!r}"


IDENTIFIER_FIELDS = ("id", "planId", "parentPlanId", "planTypeId", "croppableAreaId", "landId", "projectId")


def assert_identifiers_unchanged(before: dict, after: dict) -> None:
    """A11."""
    for field in IDENTIFIER_FIELDS:
        assert after.get(field) == before.get(field), (
            f"A11: {field} changed from {before.get(field)!r} to {after.get(field)!r}"
        )


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value))


def assert_last_modified_advanced(before: dict, after: dict) -> None:
    """A12 — post-fill lastModifiedDate is later than the pre-fill one."""
    after_ts = _parse(after.get("lastModifiedDate"))
    before_ts = _parse(before.get("lastModifiedDate"))
    assert after_ts is not None, "A12: post-fill lastModifiedDate is missing"
    assert before_ts is None or after_ts > before_ts, (
        f"A12: lastModifiedDate did not advance ({before.get('lastModifiedDate')!r} -> "
        f"{after.get('lastModifiedDate')!r})"
    )


def assert_task_filled_correctly(
    *, response, before: dict, after: dict, payload: dict, ca: dict, exec_day, filled_by: str
) -> None:
    """A1-A12 in one call — what the happy-path tests assert. (A6, sowing/harvest
    dates vs the croppable area, is not checked: the task GET returns both as null.)"""
    assert_fill_succeeded(response)
    assert_complete(after)
    assert_execution_dates(after, exec_day)
    assert_custom_attributes(after, payload["data"]["customAttributesEntered"])
    sent_chem = payload["data"]["planHeaderAttributesEntered"][0]
    assert_chemical(after, sent_chem)
    assert_total_chemical(after, sent_chem["chemicalQuantity"]["count"], ca, sent_chem["totalChemicalQuantity"]["unit"])
    assert_filled_by(after, filled_by)
    assert_identifiers_unchanged(before, after)
    assert_last_modified_advanced(before, after)
