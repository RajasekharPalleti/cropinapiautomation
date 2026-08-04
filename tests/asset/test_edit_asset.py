import pytest

from src.core.response_validator import assert_status


@pytest.mark.asset
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_edit_asset_updates_name(asset_service, created_asset_id):
    """Fetch the shared asset, append a timestamp to name, and PUT the
    edited record back."""
    get_response = asset_service.get_by_id(created_asset_id)
    assert_status(get_response, 200)

    updated_payload = asset_service.build_update_payload(get_response.json())
    put_response = asset_service.update(updated_payload)

    assert_status(put_response, 200)
