"""Task fill — boundary scenarios (TC_TF_201 - TC_TF_210).

The execution-date boundaries are worked out from the task's own schedule
(its fixedExecutionDates) and the croppable area's sowing/harvest dates, so
they stay correct whenever the suite runs. Scenarios whose outcome is still
to be confirmed accept either an accept or a reject (allowed list in test
data) but insist the task's state agrees with whichever the server chose.
"""
from datetime import date, timedelta

import pytest

from src.utils.task_fill_assertions import (
    assert_complete,
    assert_execution_dates,
    assert_outcome_consistent,
    assert_total_chemical,
)
from src.utils.task_fill_payload import TaskFillPayload, ca_harvest_date, date_part, get_path, utc_today

pytestmark = [pytest.mark.task, pytest.mark.task_fill, pytest.mark.regression, pytest.mark.boundary]


def _schedule_days(task_body: dict) -> list[date]:
    dates = (task_body.get("schedule") or {}).get("fixedExecutionDates") or []
    return sorted(date.fromisoformat(date_part(d)) for d in dates if d)


def _sowing_day(ca: dict) -> date:
    return date.fromisoformat(date_part(ca["sowingDate"]))


def _harvest_day(ca: dict) -> date:
    return date.fromisoformat(date_part(ca_harvest_date(ca)))


def test_execution_date_is_today(task_service, fresh_task, fill_ctx, attempt):
    """TC_TF_201."""
    today = utc_today()
    if today not in _schedule_days(fresh_task.body):
        pytest.skip(f"Today ({today}) isn't one of the task's fixed execution dates")
    attempt(TaskFillPayload.base(fresh_task.body, fill_ctx).execution_day(today), ["200", "201"], "TC_TF_201")
    after = task_service.get_task(fresh_task.id).json()
    assert_complete(after)
    assert_execution_dates(after, today)


def test_execution_date_is_earliest_fixed_date(task_service, fresh_task, fill_ctx, attempt):
    """TC_TF_202."""
    earliest = _schedule_days(fresh_task.body)[0]
    attempt(TaskFillPayload.base(fresh_task.body, fill_ctx).execution_day(earliest), ["200", "201"], "TC_TF_202")
    after = task_service.get_task(fresh_task.id).json()
    assert_complete(after)
    assert_execution_dates(after, earliest)


def test_execution_date_is_latest_fixed_date(task_service, fresh_task, fill_ctx, attempt):
    """TC_TF_203."""
    latest = _schedule_days(fresh_task.body)[-1]
    attempt(TaskFillPayload.base(fresh_task.body, fill_ctx).execution_day(latest), ["200", "201"], "TC_TF_203")
    after = task_service.get_task(fresh_task.id).json()
    assert_complete(after)
    assert_execution_dates(after, latest)


@pytest.mark.negative
def test_execution_date_not_in_fixed_dates(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_204 — five days past the last fixed execution date."""
    beyond = _schedule_days(negative_target.body)[-1] + timedelta(days=5)
    attempt(
        TaskFillPayload.base(negative_target.body, fill_ctx).execution_day(beyond),
        fill_expectations["TC_TF_204"],
        "TC_TF_204",
    )
    assert_still_open(negative_target.id)


@pytest.mark.negative
def test_execution_date_before_sowing_date(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_205 — the day before the croppable area's sowing date."""
    before_sowing = _sowing_day(fill_ctx.ca) - timedelta(days=1)
    attempt(
        TaskFillPayload.base(negative_target.body, fill_ctx).execution_day(before_sowing),
        fill_expectations["TC_TF_205"],
        "TC_TF_205",
    )
    assert_still_open(negative_target.id)


def test_execution_date_after_harvest_date(task_service, fresh_task, fill_ctx, attempt, fill_expectations):
    """TC_TF_206 — the day after harvest; outcome still to be confirmed, but
    the task has to end up consistent with the response."""
    after_harvest = _harvest_day(fill_ctx.ca) + timedelta(days=1)
    response = attempt(
        TaskFillPayload.base(fresh_task.body, fill_ctx).execution_day(after_harvest),
        fill_expectations["TC_TF_206"],
        "TC_TF_206",
    )
    assert_outcome_consistent(response, task_service.get_task(fresh_task.id).json())


def test_chemical_quantity_zero(task_service, fresh_task, fill_ctx, attempt, fill_expectations):
    """TC_TF_207 — quantity 0 (total 0); outcome still to be confirmed."""
    response = attempt(
        TaskFillPayload.base(fresh_task.body, fill_ctx).chemical_quantity(0),
        fill_expectations["TC_TF_207"],
        "TC_TF_207",
    )
    assert_outcome_consistent(response, task_service.get_task(fresh_task.id).json())


def test_decimal_chemical_quantity(task_service, fresh_task, fill_ctx, attempt, task_fill_config):
    """TC_TF_208 — 12.5 x the audited area, persisted exactly."""
    attempt(TaskFillPayload.base(fresh_task.body, fill_ctx).chemical_quantity(12.5), ["200", "201"], "TC_TF_208")
    after = task_service.get_task(fresh_task.id).json()
    assert_total_chemical(after, 12.5, fill_ctx.ca, task_fill_config["chemical"]["total_unit"])


def test_text_attribute_max_length(task_service, fresh_task, fill_ctx, attempt, fill_expectations):
    """TC_TF_209 — 256 characters first (expected to be refused, leaving the
    task open for the next call), then 255 (expected to be accepted)."""
    base = TaskFillPayload.base(fresh_task.body, fill_ctx)
    attempt(base.custom_attribute("text", "x" * 256), fill_expectations["TC_TF_209_256"], "TC_TF_209 (256 chars)")
    attempt(
        base.custom_attribute("text", "x" * 255).with_new_client_id(),
        fill_expectations["TC_TF_209_255"],
        "TC_TF_209 (255 chars)",
    )
    after = task_service.get_task(fresh_task.id).json()
    stored = get_path(after, "data.customAttributesEntered") or {}
    assert stored.get(fill_ctx.attr_names["text"]) == "x" * 255


def test_text_attribute_special_characters_and_unicode(task_service, fresh_task, fill_ctx, attempt):
    """TC_TF_210 — persisted exactly, character for character."""
    value = "Tést @#&* తెలుగు 😀"
    attempt(TaskFillPayload.base(fresh_task.body, fill_ctx).custom_attribute("text", value), ["200", "201"], "TC_TF_210")
    after = task_service.get_task(fresh_task.id).json()
    stored = get_path(after, "data.customAttributesEntered") or {}
    assert stored.get(fill_ctx.attr_names["text"]) == value, (
        f"Expected {value!r}, got {stored.get(fill_ctx.attr_names['text'])!r}"
    )
