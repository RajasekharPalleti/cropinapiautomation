"""Self-tests for the intake validation gate (intake/spec_schema.py) — not API
tests, so they don't touch auth_service/api_client fixtures or the network."""
import pytest
from pydantic import ValidationError

from intake.spec_schema import ApiIntakeBatch, ApiIntakeSpec

VALID_SPEC = {
    "module": "farmer",
    "scenario_name": "create_valid",
    "endpoint": "/farm/v1/farmers",
    "method": "POST",
    "test_type": "smoke",
    "payload": {"name": "Test Farmer"},
    "expected_status": 201,
}


def test_valid_spec_passes():
    spec = ApiIntakeSpec(**VALID_SPEC)
    assert spec.module == "farmer"
    assert spec.negative is False


def test_unknown_module_rejected():
    with pytest.raises(ValidationError):
        ApiIntakeSpec(**{**VALID_SPEC, "module": "weather"})


def test_unsupported_method_rejected():
    with pytest.raises(ValidationError):
        ApiIntakeSpec(**{**VALID_SPEC, "method": "TRACE"})


def test_unknown_test_type_rejected():
    with pytest.raises(ValidationError):
        ApiIntakeSpec(**{**VALID_SPEC, "test_type": "acceptance"})


def test_endpoint_must_be_relative_path():
    with pytest.raises(ValidationError):
        ApiIntakeSpec(**{**VALID_SPEC, "endpoint": "farm/v1/farmers"})


def test_body_method_without_payload_rejected():
    with pytest.raises(ValidationError):
        ApiIntakeSpec(**{**VALID_SPEC, "payload": {}})


def test_get_without_payload_is_fine():
    spec = ApiIntakeSpec(
        **{**VALID_SPEC, "method": "GET", "payload": {}, "expected_status": 200}
    )
    assert spec.payload == {}


def test_negative_scenario_requires_error_status():
    with pytest.raises(ValidationError):
        ApiIntakeSpec(**{**VALID_SPEC, "negative": True, "expected_status": 200})


def test_negative_scenario_with_error_status_passes():
    spec = ApiIntakeSpec(**{**VALID_SPEC, "negative": True, "expected_status": 400})
    assert spec.negative is True


def test_batch_validates_all_items():
    batch = ApiIntakeBatch(
        items=[
            VALID_SPEC,
            {**VALID_SPEC, "scenario_name": "create_missing_name", "negative": True, "expected_status": 400},
        ]
    )
    assert len(batch.items) == 2


def test_batch_rejects_if_any_item_invalid():
    with pytest.raises(ValidationError):
        ApiIntakeBatch(items=[VALID_SPEC, {**VALID_SPEC, "module": "unknown"}])
