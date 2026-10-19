"""Fixtures for the task-fill tests.

The tasks being filled are the ones the suite's own plan generated on the
suite's own croppable area (GET .../tasks/croppablearea/{id}) — session ids
only, never an id from test data. Every fill that succeeds consumes a task
(it's completed), so tests draw from a TaskPool of the plan's open tasks:
one task per fixed execution date in the plan (plan.create_valid
.fixed_execution_day_offsets in test data sets how many). Tests that all
assert on the SAME fill share one session fixture that performs it exactly
once (filled_task, draft_then_completed), the same one-call-many-readers
pattern the rest of the suite uses; every other scenario claims its own.
"""
from datetime import timedelta

import pytest

from src.utils.task_fill_assertions import (
    assert_fill_fast,
    assert_open,
    assert_status_in,
)
from src.utils.task_fill_payload import (
    TaskFillContext,
    TaskFillPayload,
    audited_area,
    current_created_date,
    date_part,
    utc_today,
)
from src.utils.test_data_loader import load_test_data
from tests.conftest import tracked_fixture


class TaskHandle:
    """A claimed task: its id and its GET body from just before the test."""

    def __init__(self, task_id, body):
        self.id = task_id
        self.body = body


class FillResult:
    """One fill performed by a session fixture, for many tests to assert on."""

    def __init__(self, handle, payload, response, after):
        self.handle = handle
        self.before = handle.body
        self.payload = payload
        self.response = response
        self.after = after


class DraftFlow:
    """Save-as-draft, then complete the same task (two requests, one task)."""

    def __init__(self, handle, draft_payload, draft_response, after_draft,
                 complete_payload, complete_response, after_complete):
        self.handle = handle
        self.before = handle.body
        self.draft_payload = draft_payload
        self.draft_response = draft_response
        self.after_draft = after_draft
        self.complete_payload = complete_payload
        self.complete_response = complete_response
        self.after_complete = after_complete


class TaskPool:
    def __init__(self, task_ids):
        self._ids = list(task_ids)
        self._next = 0
        self._negative_target_id = None

    @property
    def total(self):
        return len(self._ids)

    def _claim(self):
        if self._next >= len(self._ids):
            return None
        task_id = self._ids[self._next]
        self._next += 1
        return task_id

    def claim_open(self, task_service, ctx):
        """Next unused task that is still open and can take ctx.exec_day
        (rule R8: the execution day must be one of the task's fixed
        execution dates). Skips the test when there's nothing left."""
        while True:
            task_id = self._claim()
            if task_id is None:
                pytest.skip(
                    f"No unused open task left in the plan's pool of {self.total} — raise the number of "
                    "dates in test data plan.create_valid.fixed_execution_day_offsets (each date is one "
                    "task) or run with PLAN_TASK_COUNT_OVERRIDE=<n>, or provide a create-task API for "
                    "isolated tasks."
                )
            response = task_service.get_task(task_id)
            if response.status != 200:
                continue
            body = response.json()
            if str(body.get("status") or "").lower() != "open" or body.get("deleted"):
                continue
            dates = {date_part(d) for d in (body.get("schedule") or {}).get("fixedExecutionDates") or []}
            if ctx.exec_day.isoformat() not in dates:
                pytest.skip(
                    f"R8: execution day {ctx.exec_day} isn't in task {task_id}'s fixedExecutionDates "
                    f"{sorted(d for d in dates if d)} — the plan's fixed dates must include it "
                    "(plan.create_valid.fixed_execution_day_offsets in test data)."
                )
            return TaskHandle(task_id, body)

    def negative_target(self, task_service, ctx):
        """The shared task that rejected-request tests aim at. Re-checked
        every time: if an earlier test unexpectedly got its request accepted
        (completing the task), a fresh one is claimed instead."""
        if self._negative_target_id is not None:
            response = task_service.get_task(self._negative_target_id)
            if response.status == 200:
                body = response.json()
                if str(body.get("status") or "").lower() == "open":
                    return TaskHandle(self._negative_target_id, body)
        handle = self.claim_open(task_service, ctx)
        self._negative_target_id = handle.id
        return handle


# --- config ------------------------------------------------------------------


@pytest.fixture(scope="session")
def task_fill_config():
    return load_test_data("task", "fill")


@pytest.fixture(scope="session")
def fill_expectations():
    """Allowed statuses per scenario (exact codes and/or classes like 4xx) —
    test data, so a 'confirm on first run' expectation gets frozen by editing
    task.fill_expectations in test_data/<env>.json, not code."""
    return load_test_data("task", "fill_expectations")


# --- the plan's tasks ----------------------------------------------------------


@pytest.fixture(scope="session")
@tracked_fixture
def task_pool(project_service, croppable_area_ids, created_plan_id, croppable_area_update_response):
    """The open tasks this run's plan generated on the croppable area.
    (created_plan_id is listed before croppable_area_update_response on
    purpose: the plan exists before the variety is assigned to the
    croppable area, same as in the full suite's test order, even when only
    this folder is run.)"""
    if "error" in croppable_area_update_response:
        pytest.skip(
            "Croppable area update failed this run, so no plan tasks were pulled onto it — "
            f"skipping task fill: {croppable_area_update_response['error']}"
        )
    response = project_service.list_tasks_for_croppable_area(croppable_area_ids[0])
    if response.status != 200:
        pytest.skip(f"Could not list tasks for the croppable area (HTTP {response.status}) — skipping task fill")
    open_task_ids = sorted(
        task["id"]
        for task in response.json()
        if task.get("planId") == created_plan_id and str(task.get("status") or "").lower() == "open"
    )
    if not open_task_ids:
        pytest.skip("The plan has no open tasks on the croppable area — nothing to fill")
    return TaskPool(open_task_ids)


@pytest.fixture(scope="session")
@tracked_fixture
def task_fill_context(
    project_service, plantype_service, plan_service, croppable_area_ids,
    created_plantype_id, created_plan_id, task_pool, task_fill_config,
):
    """Everything a fill body needs beyond the task itself: the croppable
    area (sowing/expected harvest dates, audited area), the createdDate, this
    run's custom attribute names (they carry a unique suffix per run, so
    they're read off the plan type rather than hardcoded), and the
    execution day."""
    ca_response = project_service.get_croppable_area(croppable_area_ids[0])
    if ca_response.status != 200:
        pytest.skip(f"Could not read the croppable area (HTTP {ca_response.status}) — skipping task fill")
    ca = ca_response.json()
    if audited_area(ca) is None:
        pytest.skip(
            "The croppable area response has neither auditedArea nor declaredArea, which the "
            "chemical total needs — check the field names against a real response (spec item 2)"
        )

    plantype_response = plantype_service.get_by_id(created_plantype_id)
    if plantype_response.status != 200:
        pytest.skip(f"Could not read the plan type (HTTP {plantype_response.status}) — skipping task fill")
    attributes = ((plantype_response.json().get("data") or {}).get("customAttributes")) or []
    if len(attributes) < 3:
        pytest.skip(f"Expected 3 custom attributes on the plan type, found {len(attributes)} — skipping task fill")
    attr_names = {"text": attributes[0]["name"], "dropdown": attributes[1]["name"], "smart": attributes[2]["name"]}
    attr_required = {
        role: bool((attribute.get("validation") or {}).get("required"))
        for role, attribute in zip(("text", "dropdown", "smart"), attributes[:3])
    }

    # The body's createdDate is the current date. What the plan itself stores is
    # read once up front (prod reports null for API-created plans) so TC_TF_304
    # can prove the fill leaves it alone.
    plan_response = plan_service.get_by_id(created_plan_id)
    plan_stored_created_date = plan_response.json().get("createdDate") if plan_response.status == 200 else None

    return TaskFillContext(
        ca=ca,
        plan_created_date=current_created_date(),
        plan_stored_created_date=plan_stored_created_date,
        attr_names=attr_names,
        attr_required=attr_required,
        cfg=task_fill_config,
        exec_day=utc_today() + timedelta(days=task_fill_config["execution_day_offset"]),
    )


@pytest.fixture(scope="session")
def fill_ctx(task_fill_context):
    return task_fill_context


@pytest.fixture(scope="session")
def plan_task_count(project_service, croppable_area_ids, created_plan_id):
    """Callable: how many tasks the plan currently has on the croppable area
    (to prove a request didn't create a duplicate)."""

    def _count():
        response = project_service.list_tasks_for_croppable_area(croppable_area_ids[0])
        assert response.status == 200, f"Task list failed: HTTP {response.status}: {response.text()}"
        return sum(1 for task in response.json() if task.get("planId") == created_plan_id)

    return _count


# --- claiming tasks per test ---------------------------------------------------


@pytest.fixture
def fresh_task(task_service, task_pool, task_fill_context):
    """A task of its own for a scenario that may well complete it."""
    return task_pool.claim_open(task_service, task_fill_context)


@pytest.fixture
def negative_target(task_service, task_pool, task_fill_context):
    """A shared task for scenarios whose request is expected to be rejected."""
    return task_pool.negative_target(task_service, task_fill_context)


@pytest.fixture
def attempt(task_service, task_fill_config):
    """Sends a fill body, then checks the status against the allowed list
    and the response time — returns the response for further checks."""

    def _attempt(payload, allowed, label, *, raw_body=None, headers=None):
        body = payload.to_dict() if isinstance(payload, TaskFillPayload) else payload
        response = task_service.fill(body, raw_body=raw_body, headers=headers)
        assert_status_in(response, allowed, label)
        assert_fill_fast(response, task_fill_config["max_response_ms"])
        return response

    return _attempt


@pytest.fixture
def assert_still_open(task_service):
    """Callable: GETs the task and asserts it was left open (a rejected
    request mustn't have changed it)."""

    def _check(task_id):
        response = task_service.get_task(task_id)
        assert response.status == 200, f"Task GET failed: HTTP {response.status}: {response.text()}"
        assert_open(response.json())

    return _check


# --- fills shared by many tests ----------------------------------------------


def _after(task_service, task_id, response):
    if response.status not in (200, 201):
        return {}
    get = task_service.get_task(task_id)
    return get.json() if get.status == 200 else {}


@pytest.fixture(scope="session")
@tracked_fixture
def filled_task(task_service, task_pool, task_fill_context):
    """The one happy-path fill (no draft) — TC_TF_001's request — whose result
    the assertion-only tests (002-007, 302-306, 401) all read."""
    handle = task_pool.claim_open(task_service, task_fill_context)
    payload = TaskFillPayload.base(handle.body, task_fill_context).to_dict()
    response = task_service.fill(payload)
    return FillResult(handle, payload, response, _after(task_service, handle.id, response))


@pytest.fixture(scope="session")
@tracked_fixture
def draft_then_completed(task_service, task_pool, task_fill_context):
    """Save a task as a draft, then complete that same task — the two
    happy-path sanity scenarios (TC_TF_008, TC_TF_009) share it."""
    handle = task_pool.claim_open(task_service, task_fill_context)
    draft_payload = TaskFillPayload.base(handle.body, task_fill_context).as_draft().to_dict()
    draft_response = task_service.fill(draft_payload)
    after_draft = _after(task_service, handle.id, draft_response)

    complete_payload = complete_response = after_complete = None
    if draft_response.status in (200, 201):
        complete_payload = TaskFillPayload.base(handle.body, task_fill_context).to_dict()
        complete_response = task_service.fill(complete_payload)
        after_complete = _after(task_service, handle.id, complete_response)

    return DraftFlow(handle, draft_payload, draft_response, after_draft,
                     complete_payload, complete_response, after_complete)
