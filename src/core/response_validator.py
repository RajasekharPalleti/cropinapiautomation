"""Reusable response assertions: status codes, JSON schema, and business rules."""
from typing import Any

from jsonschema import validate as jsonschema_validate

from src.core.response_wrapper import ApiResponse


def assert_status(response: ApiResponse, expected: int) -> None:
    assert response.status == expected, (
        f"Expected status {expected}, got {response.status}. Body: {response.text()}"
    )


def assert_json_schema(response: ApiResponse, schema: dict) -> None:
    body = response.json()
    jsonschema_validate(instance=body, schema=schema)


def assert_field_equals(response: ApiResponse, field_path: str, expected: Any) -> None:
    """field_path uses dot notation, e.g. 'data.farm.id'."""
    body = response.json()
    value = body
    for part in field_path.split("."):
        assert isinstance(value, dict) and part in value, (
            f"Field path '{field_path}' not found in response: {body}"
        )
        value = value[part]
    assert value == expected, f"Expected '{field_path}' == {expected}, got {value}"
