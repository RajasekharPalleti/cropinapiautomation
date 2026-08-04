"""Validated schema for a dynamically supplied API call — the contract an agent
or external caller must follow when driving requests through runner.py."""
from pydantic import BaseModel, Field, field_validator


class AgenticRequestSpec(BaseModel):
    method: str = Field(..., description="HTTP method: GET/POST/PUT/PATCH/DELETE")
    url: str = Field(..., description="Absolute URL, or a path relative to the active base_url")
    headers: dict = Field(default_factory=dict)
    params: dict | None = None
    body: dict | None = None
    expect_status: int | None = Field(
        default=None, description="If set, runner raises AssertionError when status mismatches"
    )
    use_auth: bool = Field(
        default=True, description="Attach the cached session's Authorization/tenant headers"
    )

    @field_validator("method")
    @classmethod
    def normalize_method(cls, v: str) -> str:
        allowed = {"GET", "POST", "PUT", "PATCH", "DELETE"}
        v = v.upper()
        if v not in allowed:
            raise ValueError(f"Unsupported method '{v}'. Must be one of {allowed}")
        return v


class AgenticResult(BaseModel):
    status: int
    ok: bool
    duration_ms: float
    headers: dict
    body: dict | str | None
