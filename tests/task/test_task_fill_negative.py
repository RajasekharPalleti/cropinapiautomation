"""Task fill — negative scenarios (TC_TF_101 - TC_TF_118).

Each starts from the happy-path body and changes exactly one thing. The
allowed statuses come from test data (task.fill_expectations — classes like
4xx, frozen to exact codes there after the first real run). A rejected
request must also leave the task untouched, so most of these finish by
checking it's still open. They aim at the shared negative_target task; if an
earlier scenario got its request accepted (completing it), a fresh one is
claimed.
"""
import json

import pytest

from src.utils.task_fill_assertions import (
    assert_complete,
    assert_fill_fast,
    assert_status_in,
    is_2xx,
)
from src.utils.task_fill_payload import TaskFillPayload, get_path

pytestmark = [pytest.mark.task, pytest.mark.task_fill, pytest.mark.regression, pytest.mark.negative]


def _base(task, ctx):
    return TaskFillPayload.base(task.body, ctx)


def test_task_id_does_not_exist(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_101."""
    response = attempt(_base(negative_target, fill_ctx).with_("id", 999999999), fill_expectations["TC_TF_101"], "TC_TF_101")
    assert response.text().strip(), "Expected an error message in the response body"
    assert_still_open(negative_target.id)


def test_missing_task_id(
    negative_target, fill_ctx, task_service, task_fill_config, plan_task_count, assert_still_open, fill_expectations
):
    """TC_TF_102 — must be rejected, and must not silently create a new task."""
    before = plan_task_count()
    payload = _base(negative_target, fill_ctx).without("id")
    response = task_service.fill(payload.to_dict())
    if is_2xx(response):
        pytest.fail(
            f"DEFECT: a fill without an id was accepted ({response.status}); the plan's task count went "
            f"{before} -> {plan_task_count()}"
        )
    assert_status_in(response, fill_expectations["TC_TF_102"], "TC_TF_102")
    assert_fill_fast(response, task_fill_config["max_response_ms"])
    assert plan_task_count() == before, "A rejected fill without an id still changed the number of tasks"
    assert_still_open(negative_target.id)


def test_invalid_status_value(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_103 — status 'DONE'."""
    attempt(_base(negative_target, fill_ctx).with_("status", "DONE"), fill_expectations["TC_TF_103"], "TC_TF_103")
    assert_still_open(negative_target.id)


def test_missing_executed_on_with_status_complete(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_104."""
    payload = (
        _base(negative_target, fill_ctx)
        .with_("executedOn", None)
        .with_("data.standardAttributesEntered.executedOn", None)
    )
    attempt(payload, fill_expectations["TC_TF_104"], "TC_TF_104")
    assert_still_open(negative_target.id)


def test_invalid_date_format_for_executed_on(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_105 — '20-10-2026'."""
    attempt(_base(negative_target, fill_ctx).with_("executedOn", "20-10-2026"), fill_expectations["TC_TF_105"], "TC_TF_105")
    assert_still_open(negative_target.id)


def test_mandatory_custom_attribute_missing(
    request, task_service, fill_ctx, attempt, assert_still_open, fill_expectations
):
    """TC_TF_106 — dropping the text attribute must be rejected IF the plan
    type marks it mandatory. This run's plan type says whether it does
    (validation.required), so the scenario follows it: mandatory -> rejected
    and the task stays open; not mandatory -> accepted, and the attribute is
    simply absent afterwards."""
    required = fill_ctx.attr_required["text"]
    task = request.getfixturevalue("negative_target" if required else "fresh_task")
    payload = _base(task, fill_ctx).without_custom_attribute("text")
    if required:
        attempt(payload, fill_expectations["TC_TF_106"], "TC_TF_106 (text attribute is mandatory)")
        assert_still_open(task.id)
    else:
        attempt(payload, ["200", "201"], "TC_TF_106 (text attribute is NOT mandatory in this plan type)")
        after = task_service.get_task(task.id).json()
        assert_complete(after)
        stored = get_path(after, "data.customAttributesEntered") or {}
        assert fill_ctx.attr_names["text"] not in stored, "The omitted attribute shouldn't have been stored"


def test_invalid_dropdown_option_value(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_107 — option '999' isn't one of the dropdown's options."""
    payload = _base(negative_target, fill_ctx).custom_attribute("dropdown", "999")
    attempt(payload, fill_expectations["TC_TF_107"], "TC_TF_107")
    assert_still_open(negative_target.id)


def test_unknown_custom_attribute_key(negative_target, fill_ctx, task_service, attempt, assert_still_open, fill_expectations):
    """TC_TF_108 — rejected, or accepted with the unknown key ignored (never persisted)."""
    payload = _base(negative_target, fill_ctx).with_("data.customAttributesEntered.UnknownAttr 000", "x")
    response = attempt(payload, fill_expectations["TC_TF_108"], "TC_TF_108")
    if is_2xx(response):
        after = task_service.get_task(negative_target.id).json()
        assert "UnknownAttr 000" not in (get_path(after, "data.customAttributesEntered") or {}), (
            "The unknown custom attribute key was persisted"
        )
    else:
        assert_still_open(negative_target.id)


def test_invalid_chemical_id(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_109."""
    payload = _base(negative_target, fill_ctx).with_("data.planHeaderAttributesEntered[0].chemicalName", 999999999)
    attempt(payload, fill_expectations["TC_TF_109"], "TC_TF_109")
    assert_still_open(negative_target.id)


def test_invalid_chemical_unit(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_110."""
    payload = _base(negative_target, fill_ctx).with_(
        "data.planHeaderAttributesEntered[0].chemicalQuantity.unit", "INVALID_UNIT"
    )
    attempt(payload, fill_expectations["TC_TF_110"], "TC_TF_110")
    assert_still_open(negative_target.id)


def test_negative_chemical_quantity(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_111 — quantity -10 (total recalculated to match)."""
    attempt(_base(negative_target, fill_ctx).chemical_quantity(-10), fill_expectations["TC_TF_111"], "TC_TF_111")
    assert_still_open(negative_target.id)


def test_plan_type_does_not_match_task(negative_target, fill_ctx, task_service, attempt, fill_expectations):
    """TC_TF_112 — planTypeId 1; the task's own plan type must be unchanged."""
    attempt(_base(negative_target, fill_ctx).with_("planTypeId", 1), fill_expectations["TC_TF_112"], "TC_TF_112")
    after = task_service.get_task(negative_target.id).json()
    assert after.get("planTypeId") == negative_target.body.get("planTypeId"), "The task's plan type was changed"


def test_croppable_area_does_not_match_task(negative_target, fill_ctx, task_service, attempt, fill_expectations):
    """TC_TF_113 — croppableAreaId 1; the task's own croppable area must be unchanged."""
    attempt(_base(negative_target, fill_ctx).with_("croppableAreaId", 1), fill_expectations["TC_TF_113"], "TC_TF_113")
    after = task_service.get_task(negative_target.id).json()
    assert after.get("croppableAreaId") == negative_target.body.get("croppableAreaId"), (
        "The task's croppable area was changed"
    )


def test_empty_request_body(negative_target, attempt, assert_still_open, fill_expectations):
    """TC_TF_114 — body {}."""
    attempt({}, fill_expectations["TC_TF_114"], "TC_TF_114")
    assert_still_open(negative_target.id)


def test_malformed_json(negative_target, attempt, assert_still_open, fill_expectations):
    """TC_TF_115 — a truncated body."""
    attempt(None, fill_expectations["TC_TF_115"], "TC_TF_115", raw_body=f'{{"id": {negative_target.id},')
    assert_still_open(negative_target.id)


def test_wrong_content_type(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_116 — a valid JSON body labelled text/plain."""
    payload = _base(negative_target, fill_ctx)
    attempt(
        None,
        fill_expectations["TC_TF_116"],
        "TC_TF_116",
        raw_body=json.dumps(payload.to_dict()),
        headers={"Content-Type": "text/plain"},
    )
    assert_still_open(negative_target.id)


def test_wrong_data_type_for_id(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_117 — id 'abc'."""
    attempt(_base(negative_target, fill_ctx).with_("id", "abc"), fill_expectations["TC_TF_117"], "TC_TF_117")
    assert_still_open(negative_target.id)


def test_get_typo_key_sent_instead_of_correct_key(
    negative_target, fill_ctx, attempt, assert_still_open, fill_expectations
):
    """TC_TF_118 — 'chemicalQuanity' (the GET response's spelling) in place of
    'chemicalQuantity': ignored, or rejected."""
    payload = _base(negative_target, fill_ctx).without("chemicalQuantity").with_("chemicalQuanity", {})
    response = attempt(payload, fill_expectations["TC_TF_118"], "TC_TF_118")
    if not is_2xx(response):
        assert_still_open(negative_target.id)
