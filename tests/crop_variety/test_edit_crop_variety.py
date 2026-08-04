import pytest

from src.core.response_validator import assert_status


@pytest.mark.crop_variety
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_edit_crop_variety_updates_name(crop_variety_service, created_crop_variety_id):
    """Fetch a freshly created crop variety, append a timestamp to name, and
    PUT the edited record back."""
    get_response = crop_variety_service.get_by_id(created_crop_variety_id)
    assert_status(get_response, 200)

    updated_payload = crop_variety_service.build_update_payload(get_response.json())
    put_response = crop_variety_service.update(updated_payload)

    assert_status(put_response, 200)
