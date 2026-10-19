"""Task fill — data-integrity scenarios (TC_TF_301 - TC_TF_306).

302-306 read the shared happy-path fill (filled_task); 301 sends a
deliberately wrong chemical total on a task of its own.
"""
import pytest

from src.utils.task_fill_assertions import (
    assert_fill_succeeded,
    assert_filled_by,
    assert_identifiers_unchanged,
    assert_last_modified_advanced,
    assert_not_complete,
    is_2xx,
)
from src.utils.task_fill_payload import TaskFillPayload, audited_area, get_path, multiply

pytestmark = [pytest.mark.task, pytest.mark.task_fill, pytest.mark.regression, pytest.mark.integrity]

TOTAL_PATH = "data.planHeaderAttributesEntered[0].totalChemicalQuantity.count"


def test_total_chemical_mismatch_is_not_stored_as_sent(task_service, fresh_task, fill_ctx):
    """TC_TF_301 — a total that doesn't equal quantity x audited area. The
    server either recalculates it or rejects the request; storing the wrong
    figure is a defect. (Per the spec notes the server doesn't validate the
    total today, so that case is reported as an expected failure — it is the
    reason the client has to compute the total itself — rather than a hard
    fail; recalculation or rejection would pass.)"""
    correct_total = multiply(fill_ctx.cfg["chemical"]["quantity"]["count"], audited_area(fill_ctx.ca))
    # Derived from the correct figure (never a fixed number), so it can't
    # accidentally equal it whatever area the croppable area has.
    wrong_total = correct_total + 1000
    payload = TaskFillPayload.base(fresh_task.body, fill_ctx).with_(TOTAL_PATH, wrong_total)
    response = task_service.fill(payload.to_dict())
    assert response.status < 500, f"Server error {response.status}. Body: {response.text()}"
    after = task_service.get_task(fresh_task.id).json()

    if not is_2xx(response):
        assert_not_complete(after)
        return
    stored = get_path(after, TOTAL_PATH)
    if stored == correct_total:
        return
    if stored == wrong_total:
        pytest.xfail(
            f"Server stored the client-supplied total ({wrong_total}) instead of {correct_total} — "
            "it doesn't validate or recalculate totalChemicalQuantity"
        )
    pytest.fail(f"Unexpected stored total {stored!r} (sent {wrong_total}, correct {correct_total})")


def test_identifiers_unchanged_after_fill(filled_task):
    """TC_TF_302."""
    assert_fill_succeeded(filled_task.response)
    assert_identifiers_unchanged(filled_task.before, filled_task.after)


def test_direct_adhoc_task_preserved(filled_task):
    """TC_TF_303 — the request sends null; the stored value must not change."""
    assert_fill_succeeded(filled_task.response)
    assert filled_task.after.get("directAdhocTask") == filled_task.before.get("directAdhocTask"), (
        f"directAdhocTask changed from {filled_task.before.get('directAdhocTask')!r} "
        f"to {filled_task.after.get('directAdhocTask')!r}"
    )


def test_created_date_not_overwritten(filled_task, plan_service, fill_ctx):
    """TC_TF_304 — the fill body carries the current date as createdDate, but
    that must not overwrite what the plan (or the task) already stores."""
    assert_fill_succeeded(filled_task.response)
    plan = plan_service.get_by_id(filled_task.before["planId"])
    assert plan.status == 200, f"Plan GET failed: HTTP {plan.status}: {plan.text()}"
    stored = plan.json().get("createdDate")
    assert stored == fill_ctx.plan_stored_created_date, (
        f"Plan createdDate changed from {fill_ctx.plan_stored_created_date!r} to {stored!r} "
        f"after a fill that sent createdDate={fill_ctx.plan_created_date!r}"
    )
    if filled_task.before.get("createdDate"):
        assert filled_task.after.get("createdDate") == filled_task.before.get("createdDate"), (
            "The task's createdDate changed"
        )


def test_last_modified_date_updated(filled_task):
    """TC_TF_305."""
    assert_fill_succeeded(filled_task.response)
    assert_last_modified_advanced(filled_task.before, filled_task.after)


def test_filled_by_and_filled_date_set(filled_task, task_fill_config):
    """TC_TF_306 — filledBy is what was sent; filledDate is stamped by the
    server (to be confirmed on the first real run)."""
    assert_fill_succeeded(filled_task.response)
    assert_filled_by(filled_task.after, task_fill_config["filled_by"])
    assert filled_task.after.get("filledDate"), "Expected the server to set filledDate on completion"
