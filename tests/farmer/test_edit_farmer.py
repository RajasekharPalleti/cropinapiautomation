import pytest

from src.core.response_validator import assert_status


@pytest.mark.farmer
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_edit_farmer_updates_first_name(farmer_service, created_farmer_id):
    """Fetch a freshly created farmer, append a timestamp to firstName, and
    PUT the edited record back."""
    get_response = farmer_service.get_by_id(created_farmer_id)
    assert_status(get_response, 200)

    updated_payload = farmer_service.build_update_payload(get_response.json())
    put_response = farmer_service.update(updated_payload)

    assert_status(put_response, 200)
