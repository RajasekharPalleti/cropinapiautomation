import pytest

from src.core.response_validator import assert_status


@pytest.mark.asset
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_create_asset_success(created_asset):
    """created_asset performs the one asset create() call for the whole run
    (shared with every other test needing an asset) — this test just
    asserts on what that call returned."""
    assert_status(created_asset, 201)
