import pytest

from src.core.response_validator import assert_status


@pytest.mark.farmer
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_create_farmer_success(created_farmer):
    """created_farmer performs the one farmer create() call for the whole
    run (shared with every other test needing a farmer) — this test just
    asserts on what that call returned."""
    assert_status(created_farmer, 201)
