import pytest

from src.core.response_validator import assert_status
from src.utils.test_data_loader import load_test_data


@pytest.mark.project
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_verify_croppable_area_created(project_service, croppable_area_ids):
    assert croppable_area_ids, "No croppableAreaIds to verify"
    croppable_area_id = croppable_area_ids[0]

    response = project_service.get_croppable_area(croppable_area_id)

    assert_status(response, 200)
    actual_id = response.json().get("id")
    assert actual_id == croppable_area_id, (
        f"Expected croppable area id {croppable_area_id}, got {actual_id}"
    )


@pytest.mark.project
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_verify_croppable_area_variety_and_sowing_date(
    project_service, croppable_area_ids, created_crop_variety_id, croppable_area_update_response
):
    """Re-fetches the croppable area (a fresh GET, not the PUT echo from
    test_update_croppable_area.py) to confirm the variety + sowing date
    update actually persisted."""
    assert "error" not in croppable_area_update_response, croppable_area_update_response.get("error")
    croppable_area_id = croppable_area_ids[0]

    response = project_service.get_croppable_area(croppable_area_id)

    assert_status(response, 200)
    body = response.json()
    assert body.get("varietyId") == created_crop_variety_id, (
        f"Expected varietyId {created_crop_variety_id}, got {body.get('varietyId')}"
    )
    assert body.get("sowingDate") == croppable_area_update_response.get("sowingDate"), (
        f"Expected sowingDate {croppable_area_update_response.get('sowingDate')}, got {body.get('sowingDate')}"
    )


@pytest.mark.project
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_verify_plan_type_tasks_pulled_to_croppable_area(
    project_service, croppable_area_ids, croppable_area_update_response, created_plan_id, plantype_update_response
):
    """The variety assigned to this croppable area (test_update_croppable_area.py)
    already has a plan (test_add_plan.py) linking it to a plan type. Once
    the variety is on the croppable area, the plan's tasks (with their
    scheduled dates and plan type name) are expected to pull through onto
    the croppable area — verified via GET /tasks/croppablearea/{id}."""
    assert "error" not in croppable_area_update_response, croppable_area_update_response.get("error")
    assert created_plan_id is not None, "No plan id available from the create-plan step to verify against"
    croppable_area_id = croppable_area_ids[0]

    response = project_service.list_tasks_for_croppable_area(croppable_area_id)

    assert_status(response, 200)
    tasks = response.json()
    assert tasks, f"Expected at least one task for croppable area {croppable_area_id}, got none"

    matching_tasks = [task for task in tasks if task.get("planId") == created_plan_id]
    assert matching_tasks, (
        f"Expected tasks with planId {created_plan_id}, got planIds: {[task.get('planId') for task in tasks]}"
    )

    # Compared against plantype_update_response (the post-edit name from
    # test_edit_plantype.py), not created_plantype's original create() name —
    # the edit runs before the plan is created, so the plan (and its tasks)
    # carry the CURRENT, post-edit plan type name.
    expected_plantype_name = (
        plantype_update_response.get("name") if "error" not in plantype_update_response else None
    )
    if expected_plantype_name:
        for task in matching_tasks:
            assert task.get("planTypeName") == expected_plantype_name, (
                f"Expected planTypeName {expected_plantype_name!r}, got {task.get('planTypeName')!r}"
            )

    # Dates are compared by calendar day only — the plan's schedule stores
    # them with milliseconds ("...T00:00:00.000Z"), the task response
    # doesn't ("...T00:00:00Z"), same instant either way.
    expected_dates = {d[:10] for d in load_test_data("plan", "create_valid")["fixed_execution_dates"]}
    actual_dates = {task.get("startDate", "")[:10] for task in matching_tasks}
    assert actual_dates == expected_dates, f"Expected task dates {sorted(expected_dates)}, got {sorted(actual_dates)}"

    for task in matching_tasks:
        assert task.get("startDate") == task.get("endDate"), (
            f"Expected startDate == endDate for task {task.get('id')}, "
            f"got {task.get('startDate')} / {task.get('endDate')}"
        )
