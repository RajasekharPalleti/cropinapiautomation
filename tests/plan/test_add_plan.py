import pytest

from src.core.response_validator import assert_status


@pytest.mark.plan
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_add_plan_to_crop_variety_success(created_plan):
    """Asserts directly on the shared created_plan fixture (see
    tests/conftest.py) — the actual create() call happens exactly once for
    the whole run, shared with test_verify_plan_active_for_variety."""
    assert_status(created_plan["response"], 200)
