import pytest

from src.core.response_validator import assert_status


@pytest.mark.project
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_execute_project_completes(project_service, created_project_id, self_validate_response):
    """Triggers execution on the shared project and polls until the async
    job reaches 100% — passes only if the final status is COMPLETED.

    Depends on self_validate_response (not used directly) purely to force
    asset-validation to happen BEFORE execution starts: the real API
    rejects validating assets / creating croppable areas on a project whose
    execution has already begun ("...unavailability" error), so this
    ordering must hold regardless of which test file pytest happens to
    collect first.
    """
    execute_response = project_service.start_execution(created_project_id)
    assert_status(execute_response, 200)

    execution_id = execute_response.json()["id"]
    result = project_service.wait_for_execution_result(execution_id)

    assert result.get("status") == "COMPLETED", (
        f"Execution did not complete: status={result.get('status')!r} "
        f"at {result.get('percentage')}%. Full response: {result}"
    )
