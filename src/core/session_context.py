"""Holds per-run state (auth token, tenant id, correlation id) shared across services/tests."""
from dataclasses import dataclass, field


@dataclass
class SessionContext:
    access_token: str | None = None
    refresh_token: str | None = None
    tenant_id: str | None = None
    extra_headers: dict = field(default_factory=dict)

    def auth_headers(self) -> dict:
        headers = dict(self.extra_headers)
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if self.tenant_id:
            headers["X-Tenant-Id"] = self.tenant_id
        return headers

    def set_tokens(self, access_token: str, refresh_token: str | None = None) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
