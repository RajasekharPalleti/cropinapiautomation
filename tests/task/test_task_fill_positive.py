"""Task fill — positive scenarios (TC_TF_001-003, 005-011).

TC_TF_001-007 and the integrity scenarios in test_task_fill_integrity.py all
read the SAME fill (the filled_task fixture does it exactly once); TC_TF_008
and TC_TF_009 share the save-as-draft-then-complete flow. Only 008 and 009 —
the happy path — also carry the sanity marker (on top of regression);
everything else in this suite is regression only.
"""
import pytest

from src.utils.task_fill_assertions import (
    assert_chemical,
    assert_complete,
    assert_custom_attributes,
    assert_execution_dates,
    assert_fill_fast,
    assert_fill_succeeded,
    assert_not_complete,
    assert_task_filled_correctly,
    assert_total_chemical,
    is_2xx,
    response_task,
)
from src.utils.task_fill_payload import TaskFillPayload, date_part, get_path

pytestmark = [pytest.mark.task, pytest.mark.task_fill, pytest.mark.regression]


def test_fill_task_with_all_valid_data(filled_task, fill_ctx, task_fill_config):
    """TC_TF_001 — fill a task with all valid data and verify A1-A12."""
    assert_task_filled_correctly(
        response=filled_task.response,
        before=filled_task.before,
        after=filled_task.after,
        payload=filled_task.payload,
        ca=fill_ctx.ca,
        exec_day=fill_ctx.exec_day,
        filled_by=task_fill_config["filled_by"],
    )
    assert_fill_fast(filled_task.response, task_fill_config["max_response_ms"])


def test_fill_response_body_reflects_submitted_data(filled_task, fill_ctx):
    """TC_TF_002 — the fill response itself echoes what was submitted."""
    assert_fill_succeeded(filled_task.response)
    body = response_task(filled_task.response)
    assert body.get("id") == filled_task.handle.id, f"Expected id {filled_task.handle.id}, got {body.get('id')!r}"
    assert str(body.get("status")).lower() == "complete", f"Expected status complete, got {body.get('status')!r}"
    assert date_part(body.get("executedOn")) == fill_ctx.exec_day.isoformat(), (
        f"Expected executedOn {fill_ctx.exec_day}, got {body.get('executedOn')!r}"
    )
    assert_custom_attributes(body, filled_task.payload["data"]["customAttributesEntered"])


def test_execution_date_is_today_plus_offset_in_every_date_field(filled_task, fill_ctx):
    """TC_TF_003 — executedOn, expExecutedOn, startDate, endDate and the
    standard-attributes executedOn all carry the execution day."""
    assert_fill_succeeded(filled_task.response)
    assert_execution_dates(filled_task.after, fill_ctx.exec_day)


def test_total_chemical_quantity_is_quantity_times_audited_area(filled_task, fill_ctx, task_fill_config):
    """TC_TF_005 — the server doesn't compute the total, the request does:
    entered quantity x the croppable area's audited area."""
    assert_fill_succeeded(filled_task.response)
    chem = task_fill_config["chemical"]
    assert_total_chemical(filled_task.after, chem["quantity"]["count"], fill_ctx.ca, chem["total_unit"])


def test_custom_attributes_persisted(filled_task, fill_ctx, task_fill_config):
    """TC_TF_006 — text, dropdown and smart-compute (the task's land name)."""
    assert_fill_succeeded(filled_task.response)
    names = fill_ctx.attr_names
    stored = get_path(filled_task.after, "data.customAttributesEntered") or {}
    assert stored.get(names["text"]) == task_fill_config["custom_attributes"]["text_value"]
    assert stored.get(names["dropdown"]) == task_fill_config["custom_attributes"]["dropdown_value"]
    assert stored.get(names["smart"]) == filled_task.before.get("landName")


def test_chemical_details_persisted(filled_task, task_fill_config):
    """TC_TF_007."""
    assert_fill_succeeded(filled_task.response)
    chem = task_fill_config["chemical"]
    assert_chemical(
        filled_task.after,
        {
            "typeId": chem["type_id"],
            "chemicalName": chem["chemical_id"],
            "perQuantity": chem["per_quantity"],
            "chemicalQuantity": chem["quantity"],
            "chemicalConcentration": chem["concentration"],
        },
    )


@pytest.mark.sanity
def test_save_task_as_draft(draft_then_completed, task_fill_config):
    """TC_TF_008 — a task saved as a draft isn't completed, and what was
    entered is kept."""
    flow = draft_then_completed
    assert is_2xx(flow.draft_response), (
        f"Expected 2xx saving the draft, got {flow.draft_response.status}. Body: {flow.draft_response.text()}"
    )
    assert_fill_fast(flow.draft_response, task_fill_config["max_response_ms"])
    assert_not_complete(flow.after_draft)
    assert_custom_attributes(flow.after_draft, flow.draft_payload["data"]["customAttributesEntered"])


@pytest.mark.sanity
def test_complete_task_previously_saved_as_draft(draft_then_completed, fill_ctx, task_fill_config):
    """TC_TF_009 — complete the task that TC_TF_008 saved as a draft."""
    flow = draft_then_completed
    if flow.complete_response is None:
        pytest.skip("The draft step failed (see TC_TF_008), so there is no draft to complete")
    assert_task_filled_correctly(
        response=flow.complete_response,
        before=flow.before,
        after=flow.after_complete,
        payload=flow.complete_payload,
        ca=fill_ctx.ca,
        exec_day=fill_ctx.exec_day,
        filled_by=task_fill_config["filled_by"],
    )
    assert_fill_fast(flow.complete_response, task_fill_config["max_response_ms"])


def test_fill_without_optional_chemical_section(
    task_service, fresh_task, fill_ctx, attempt, fill_expectations
):
    """TC_TF_010 — an empty chemical list is accepted if chemical is optional,
    rejected if it's mandatory (confirm on first run). Either way the task's
    state has to agree with the response."""
    payload = TaskFillPayload.base(fresh_task.body, fill_ctx).with_("data.planHeaderAttributesEntered", [])
    response = attempt(payload, fill_expectations["TC_TF_010"], "TC_TF_010")
    after = task_service.get_task(fresh_task.id).json()
    if is_2xx(response):
        assert_complete(after)
        assert not get_path(after, "data.planHeaderAttributesEntered"), (
            f"Expected no chemical entries, got {get_path(after, 'data.planHeaderAttributesEntered')!r}"
        )
    else:
        assert_not_complete(after)


def test_optional_standard_attributes_filled(task_service, fresh_task, fill_ctx, attempt):
    """TC_TF_011 — costPerArea and totalCost are persisted as sent."""
    payload = (
        TaskFillPayload.base(fresh_task.body, fill_ctx)
        .with_("data.standardAttributesEntered.costPerArea", 10)
        .with_("data.standardAttributesEntered.totalCost", 29.8)
    )
    response = attempt(payload, ["200", "201"], "TC_TF_011")
    assert_fill_succeeded(response)
    after = task_service.get_task(fresh_task.id).json()
    assert get_path(after, "data.standardAttributesEntered.costPerArea") == 10
    assert get_path(after, "data.standardAttributesEntered.totalCost") == 29.8
