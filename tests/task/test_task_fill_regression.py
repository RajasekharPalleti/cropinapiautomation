"""Task fill — regression / idempotency scenarios (TC_TF_401 - TC_TF_403)."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.utils.task_fill_assertions import (
    assert_complete,
    assert_fill_succeeded,
    assert_not_complete,
    assert_not_server_error,
    is_2xx,
)
from src.utils.task_fill_payload import TaskFillPayload

pytestmark = [pytest.mark.task, pytest.mark.task_fill, pytest.mark.regression]


def test_fill_already_completed_task_again(filled_task, fill_ctx, attempt, plan_task_count, fill_expectations):
    """TC_TF_401 — a second fill (new clientId) of a completed task is either
    accepted as an edit or refused as locked (still to be confirmed), but it
    must never leave a duplicate task behind."""
    assert_fill_succeeded(filled_task.response)
    before = plan_task_count()
    payload = TaskFillPayload.base(filled_task.before, fill_ctx)
    attempt(payload, fill_expectations["TC_TF_401"], "TC_TF_401")
    assert plan_task_count() == before, "Filling an already completed task changed the number of tasks"


def test_same_client_id_sent_twice(task_service, fresh_task, fill_ctx, attempt, plan_task_count, fill_expectations):
    """TC_TF_402 — replaying an identical request (same clientId): handled
    idempotently or rejected, with one completion recorded either way."""
    before = plan_task_count()
    payload = TaskFillPayload.base(fresh_task.body, fill_ctx)
    first = attempt(payload, ["200", "201"], "TC_TF_402 (first request)")
    assert_fill_succeeded(first)
    attempt(payload, fill_expectations["TC_TF_402_second"], "TC_TF_402 (replay, same clientId)")
    assert_complete(task_service.get_task(fresh_task.id).json())
    assert plan_task_count() == before, "Replaying the same clientId created an extra task"


def test_concurrent_fill_requests(task_service, fresh_task, fill_ctx):
    """TC_TF_403 — two fills of the same task in parallel (different
    clientIds): no server error, and the task ends in a consistent state."""
    base = TaskFillPayload.base(fresh_task.body, fill_ctx)
    bodies = [base.to_dict(), base.with_new_client_id().to_dict()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(task_service.fill, bodies))
    for response in responses:
        assert_not_server_error(response, "TC_TF_403")
    after = task_service.get_task(fresh_task.id).json()
    if any(is_2xx(response) for response in responses):
        assert_complete(after)
    else:
        assert_not_complete(after)
