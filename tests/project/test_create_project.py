import pytest

from src.core.response_validator import assert_status


@pytest.mark.project
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_create_project_success(created_project):
    """created_project performs the one project create() call for the whole
    run (shared with every other project-lifecycle test) — this test just
    asserts on what that call returned."""
    assert_status(created_project, 201)
