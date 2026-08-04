import pytest

from src.core.response_validator import assert_status


@pytest.mark.crop_variety
@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
def test_create_crop_variety_success(created_crop_variety, crop_variety_additional_attributes_response):
    """created_crop_variety and crop_variety_additional_attributes_response
    perform the one create + mandatory additional-attribute follow-up call
    for the whole run (shared with every other test needing a crop
    variety) — this test just asserts on what those calls returned."""
    assert_status(created_crop_variety, 201)
    assert_status(crop_variety_additional_attributes_response, 201)
