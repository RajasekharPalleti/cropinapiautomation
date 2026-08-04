import pytest


@pytest.mark.project
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_validate_project_assets_success(self_validate_response):
    """self_validate_response performs the actual self-validate-project-assets
    call (shared with other tests that need its result) — this test just
    asserts on what that one call returned."""
    assert self_validate_response.get("recordsFailed", 1) == 0, (
        f"Expected recordsFailed == 0, got: {self_validate_response}"
    )
    assert self_validate_response.get("recordsCompleted", 0) >= 1, (
        f"Expected at least one record completed, got: {self_validate_response}"
    )
    assert self_validate_response.get("croppableAreaIds"), (
        f"Expected non-empty croppableAreaIds, got: {self_validate_response}"
    )
