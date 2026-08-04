import pytest


@pytest.mark.project
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_add_variety_and_sowing_date_to_croppable_area(created_crop_variety_id, croppable_area_update_response):
    """Asserts directly on the shared croppable_area_update_response fixture
    (see tests/conftest.py) — the actual GET+PUT call happens exactly once
    for the whole run, shared with the verify-step tests in
    test_verify_croppable_area.py."""
    assert "error" not in croppable_area_update_response, croppable_area_update_response.get("error")
    assert croppable_area_update_response.get("varietyId") == created_crop_variety_id, (
        f"Expected varietyId {created_crop_variety_id}, got {croppable_area_update_response.get('varietyId')}"
    )
    assert croppable_area_update_response.get("sowingDate"), "Expected a sowingDate on the updated croppable area"
