import pytest

from src.core.response_validator import assert_status


@pytest.mark.plantype
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_create_plantype_success(created_plantype):
    """created_plantype performs the one plan type create() call for the
    whole run (shared with every other test needing a plan type) — this
    test just asserts on what that call returned."""
    assert_status(created_plantype, 201)
