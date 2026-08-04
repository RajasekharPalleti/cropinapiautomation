import pytest


@pytest.mark.project
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_add_asset_to_project_success(probable_assets_response):
    """probable_assets_response performs the actual probable-assets call
    (shared with other tests that need its result) — this test just asserts
    on what that one call returned."""
    assert probable_assets_response.get("recordsCompleted", 0) >= 1, (
        f"Expected at least one record completed, got: {probable_assets_response}"
    )
