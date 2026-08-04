"""Builds a validated request spec from a raw dict — the entry point for the
'agentic' flow where a caller supplies url/method/headers/body dynamically.
"""
from pydantic import BaseModel, Field, field_validator


class RequestSpec(BaseModel):
    method: str = Field(..., description="HTTP method, e.g. GET/POST/PUT/PATCH/DELETE")
    url: str = Field(..., description="Absolute URL or path relative to base_url")
    headers: dict = Field(default_factory=dict)
    params: dict | None = None
    body: dict | None = None
    expect_status: int | None = None

    @field_validator("method")
    @classmethod
    def normalize_method(cls, v: str) -> str:
        allowed = {"GET", "POST", "PUT", "PATCH", "DELETE"}
        v = v.upper()
        if v not in allowed:
            raise ValueError(f"Unsupported method '{v}'. Must be one of {allowed}")
        return v


def build_request_spec(raw: dict) -> RequestSpec:
    """Validate and normalize a raw dict (e.g. from a user/agent) into a RequestSpec."""
    return RequestSpec(**raw)
