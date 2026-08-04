"""Validated schema for onboarding a real API into the test framework.

Whenever a new endpoint/payload/test-type is handed over for login/farmer/asset/
plantype/crop_variety/project/plan, it must first pass this schema — module,
endpoint, method, test_type, scenario_name, payload, and expected_status all
present and mutually consistent — before any service, test data, or test code
gets written. See README section 6 ("Intake workflow") and CLAUDE.md for the
enforcement rule.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

# Kept in sync by hand with: pyproject.toml markers, src/services/*_service.py,
# tests/*/ folders, and the module sections in test_data/<env>.json.
KNOWN_MODULES = ("login", "farmer", "asset", "plantype", "crop_variety", "project", "plan")
KNOWN_TEST_TYPES = ("sanity", "smoke", "regression")
KNOWN_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")

BODY_METHODS = {"POST", "PUT", "PATCH"}


class ApiIntakeSpec(BaseModel):
    module: Literal["login", "farmer", "asset", "plantype", "crop_variety", "project", "plan"] = Field(
        ..., description="Which service/test_data section this scenario belongs to"
    )
    scenario_name: str = Field(
        ..., min_length=1, description="Key it's stored under in test_data/<env>.json, e.g. 'create_valid'"
    )
    endpoint: str = Field(..., min_length=1, description="Path relative to base_url, e.g. '/farm/v1/farmers'")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    test_type: Literal["sanity", "smoke", "regression"]
    payload: dict = Field(default_factory=dict, description="Request body/params to store in test_data")
    expected_status: int = Field(..., description="Status code the test should assert")
    negative: bool = Field(default=False, description="True for failure-path scenarios")
    description: Optional[str] = Field(default=None, description="Human-readable note on what this scenario covers")

    @model_validator(mode="after")
    def endpoint_is_relative_path(self) -> "ApiIntakeSpec":
        if not self.endpoint.startswith("/"):
            raise ValueError(
                f"endpoint should be a path relative to base_url, starting with '/', got '{self.endpoint}'"
            )
        return self

    @model_validator(mode="after")
    def body_methods_need_a_payload(self) -> "ApiIntakeSpec":
        if self.method in BODY_METHODS and not self.payload:
            raise ValueError(
                f"method '{self.method}' normally sends a body — payload is empty. "
                "Provide the request payload, or confirm this endpoint truly takes none."
            )
        return self

    @model_validator(mode="after")
    def negative_scenarios_expect_error_status(self) -> "ApiIntakeSpec":
        if self.negative and self.expected_status < 400:
            raise ValueError(
                f"negative=True but expected_status={self.expected_status} — "
                "negative scenarios should expect a 4xx/5xx status"
            )
        return self


class ApiIntakeBatch(BaseModel):
    """A single API is usually handed over as several scenarios at once
    (one valid case + a few negative cases) — validate them together."""

    items: list[ApiIntakeSpec] = Field(..., min_length=1)
