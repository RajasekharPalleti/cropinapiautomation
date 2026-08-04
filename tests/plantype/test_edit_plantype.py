import pytest


@pytest.mark.plantype
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_edit_plantype_updates_name(plantype_update_response):
    """Asserts directly on the shared plantype_update_response fixture (see
    tests/conftest.py) — the actual GET+PUT call happens exactly once for
    the whole run, shared with the plan-type-tasks verify test."""
    assert "error" not in plantype_update_response, plantype_update_response.get("error")
