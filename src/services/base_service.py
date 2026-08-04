"""Generic reusable service for CRUD-shaped API resources, built on top of ApiClient.

Subclass this for any module (Farmer, Asset, PlanType, CropVariety, Project, ...) and
set `resource_path` once the real endpoint is known — create/get_by_id/list/update/
delete come for free. Add module-specific methods on the subclass for anything that
doesn't fit the plain CRUD shape (bulk actions, nested resources, custom filters, etc).
"""
from typing import Any

from src.core.api_client import ApiClient
from src.core.response_wrapper import ApiResponse


class BaseService:
    resource_path: str = ""  # e.g. "/farm/v1/farmers" — set this on the subclass

    def __init__(self, api_client: ApiClient):
        self._client = api_client

    def _require_resource_path(self) -> str:
        if not self.resource_path:
            raise NotImplementedError(
                f"{type(self).__name__}.resource_path is not set yet — "
                "add the real endpoint once the API spec is available."
            )
        return self.resource_path

    def create(self, payload: dict, **kwargs: Any) -> ApiResponse:
        return self._client.post(self._require_resource_path(), json=payload, **kwargs)

    def get_by_id(self, resource_id: str, **kwargs: Any) -> ApiResponse:
        return self._client.get(f"{self._require_resource_path()}/{resource_id}", **kwargs)

    def list(self, params: dict | None = None, **kwargs: Any) -> ApiResponse:
        return self._client.get(self._require_resource_path(), params=params, **kwargs)

    def update(self, resource_id: str, payload: dict, **kwargs: Any) -> ApiResponse:
        return self._client.put(
            f"{self._require_resource_path()}/{resource_id}", json=payload, **kwargs
        )

    def delete(self, resource_id: str, **kwargs: Any) -> ApiResponse:
        return self._client.delete(f"{self._require_resource_path()}/{resource_id}", **kwargs)

    def delete_bulk(self, ids: list, **kwargs: Any) -> ApiResponse:
        """DELETE {resource_path}/bulk?ids=1,2,3 — the real bulk-delete shape
        used by farmer/asset/variety cleanup. Response body is
        {"deletable": N, "nonDeletable": N}, not just a bare status."""
        ids_param = ",".join(str(i) for i in ids)
        return self._client.delete(
            f"{self._require_resource_path()}/bulk", params={"ids": ids_param}, **kwargs
        )
