"""Project API service.

POST/GET /services/farm/api/projects use a plain JSON body (not multipart).
Execution is a two-step async flow: POST .../start-execution kicks off a
background job and returns immediately with an execution id and an
IN_PROGRESS status; completion has to be polled via
GET /services/farm/api/bulk-process/{execution_id} until percentage reaches
100 — the caller then decides pass/fail from the final 'status' field
(COMPLETED vs FAILED).
"""
import time
from datetime import datetime, timezone
from typing import Any

from src.core.response_wrapper import ApiResponse
from src.services.base_service import BaseService
from src.utils.run_uniqueness import make_unique

BULK_PROCESS_PATH = "/services/farm/api/bulk-process"
CROPPABLE_AREAS_PATH = "/services/farm/api/croppable-areas"
TASKS_CROPPABLE_AREA_PATH = "/services/farm/api/tasks/croppablearea"


def _current_sowing_date() -> str:
    """Current UTC time in the API's expected format, e.g.
    '2026-07-01T00:00:00.000+0000' (milliseconds + literal +0000 offset,
    not a 'Z' suffix or colon-separated offset)."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}+0000"

# Static for every project this suite creates — not sourced from test data.
STATIC_LOCATION = {
    "bounds": {
        "northeast": {"lat": 12.91732207107709, "lng": 77.6253500731938},
        "southwest": {"lat": 12.89918992609962, "lng": 77.59983003730844},
    },
    "political": "BTM Layout",
    "country": "India",
    "administrativeAreaLevel3": "Bengaluru Urban",
    "administrativeAreaLevel2": "Bangalore Division",
    "administrativeAreaLevel1": "Karnataka",
    "placeId": "ChIJ4b8AQvwUrjsRtShU44e_fpg",
    "latitude": 12.9136984,
    "longitude": 77.606262,
    "geoInfo": {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [77.59983003730844, 12.89918992609962],
                            [77.6253500731938, 12.89918992609962],
                            [77.6253500731938, 12.91732207107709],
                            [77.59983003730844, 12.91732207107709],
                            [77.59983003730844, 12.89918992609962],
                        ]
                    ],
                },
            }
        ],
    },
    "name": "BTM Layout 2nd Stage",
}


class ProjectService(BaseService):
    resource_path = "/services/farm/api/projects"

    def start_execution(self, project_id: Any, **kwargs: Any) -> ApiResponse:
        """POST /services/farm/api/projects/{project_id}/start-execution —
        kicks off the (async) execution job; the response is only the
        initial IN_PROGRESS state, not the final result."""
        return self._client.post(
            f"{self.resource_path}/{project_id}/start-execution", json={}, **kwargs
        )

    def stop_execution(self, project_id: Any, **kwargs: Any) -> ApiResponse:
        """POST /services/farm/api/projects/{project_id}/stop-execution —
        part of teardown: stop a project's execution before it (and its
        croppable areas/assets/etc.) can be deleted."""
        return self._client.post(
            f"{self.resource_path}/{project_id}/stop-execution", json={}, **kwargs
        )

    def wait_for_execution_result(
        self, execution_id: Any, *, max_attempts: int = 10, delay_seconds: float = 3.0
    ) -> dict:
        """Polls GET /services/farm/api/bulk-process/{execution_id} until
        percentage reaches 100, then returns the final response body. Does
        NOT decide pass/fail itself — the caller checks 'status'
        (e.g. COMPLETED vs FAILED) on the returned body.
        """
        last_body = None
        for attempt in range(1, max_attempts + 1):
            response = self._client.get(f"{BULK_PROCESS_PATH}/{execution_id}")
            assert response.status == 200, (
                f"Polling bulk-process/{execution_id} failed with status "
                f"{response.status}: {response.text()}"
            )
            last_body = response.json()
            if last_body.get("percentage") == 100:
                return last_body
            if attempt < max_attempts:
                time.sleep(delay_seconds)
        return last_body

    def add_probable_assets(self, project_id: Any, asset_ids: list, **kwargs: Any) -> ApiResponse:
        """POST /services/farm/api/projects/{project_id}/probable-assets —
        submits candidate asset ids to be added to the project."""
        return self._client.post(
            f"{self.resource_path}/{project_id}/probable-assets", json=asset_ids, **kwargs
        )

    def self_validate_project_assets(
        self, project_id: Any, project_asset_ids: list, **kwargs: Any
    ) -> ApiResponse:
        """POST /services/farm/api/projects/{project_id}/self-validate-project-assets
        ?cloneFlag=false — validates the project-asset associations and
        returns the resulting croppableAreaIds."""
        return self._client.post(
            f"{self.resource_path}/{project_id}/self-validate-project-assets",
            json=project_asset_ids,
            params={"cloneFlag": "false"},
            **kwargs,
        )

    def get_croppable_area(self, croppable_area_id: Any, **kwargs: Any) -> ApiResponse:
        """GET /services/farm/api/croppable-areas/{croppable_area_id}."""
        return self._client.get(f"{CROPPABLE_AREAS_PATH}/{croppable_area_id}", **kwargs)

    def list_tasks_for_croppable_area(self, croppable_area_id: Any, **kwargs: Any) -> ApiResponse:
        """GET /services/farm/api/tasks/croppablearea/{croppable_area_id}
        ?sort=lastModifiedDate,desc — the tasks generated on this croppable
        area from its variety's plan, each carrying its own planId and
        planTypeName. Used to verify the plan type actually pulled through
        to the croppable area once the variety was assigned to it."""
        return self._client.get(
            f"{TASKS_CROPPABLE_AREA_PATH}/{croppable_area_id}",
            params={"sort": "lastModifiedDate,desc"},
            **kwargs,
        )

    def update_croppable_area(self, payload: dict, **kwargs: Any) -> ApiResponse:
        """PUT to the plain collection URL — no id in the path, same
        pattern as Farmer/Asset/Plantype/CropVariety's update(). The
        croppable area id must already be present inside `payload` (as
        returned by a prior get_croppable_area() call)."""
        return self._client.put(CROPPABLE_AREAS_PATH, json=payload, **kwargs)

    def close_croppable_areas(
        self, croppable_area_ids: list, reason_id: int = 4, **kwargs: Any
    ) -> ApiResponse:
        """GET /services/farm/api/croppable-areas/closed?reasonId=...&ids=...
        — closes the given croppable area(s) (comma-separated ids), the
        mandatory first teardown step before they can be deleted.
        """
        ids_param = ",".join(str(i) for i in croppable_area_ids)
        return self._client.get(
            f"{CROPPABLE_AREAS_PATH}/closed",
            params={"reasonId": reason_id, "ids": ids_param},
            **kwargs,
        )

    def remove_project_assets(
        self, project_id: Any, project_asset_ids: list, croppable_area_ids: list, **kwargs: Any
    ) -> ApiResponse:
        """POST /services/farm/api/projects/{project_id}/project-assets/remove/selected-ids
        — deletes the given croppable area(s) by removing their underlying
        project-asset associations. Async (202) — returns a bulk-process id;
        poll it via wait_for_execution_result()."""
        payload = {"projectAssetIds": project_asset_ids, "croppableAreaIds": croppable_area_ids}
        return self._client.post(
            f"{self.resource_path}/{project_id}/project-assets/remove/selected-ids",
            json=payload,
            **kwargs,
        )

    def build_croppable_area_update_payload(
        self, croppable_area: dict, test_data: dict, variety_id: Any
    ) -> dict:
        """Takes the croppable area object as returned by
        get_croppable_area() and returns a copy with `varietyId` and
        `sowingDate` set — every other field is carried through unchanged,
        exactly as fetched. sowingDate prefers test_data's 'ca_sowing_date';
        falls back to the current UTC time in the API's format if not set.
        """
        updated = dict(croppable_area)
        updated["varietyId"] = variety_id
        updated["sowingDate"] = test_data.get("ca_sowing_date") or _current_sowing_date()
        return updated

    def build_create_payload(self, test_data: dict) -> dict:
        """Maps flat test_data fields onto the real nested API body. `name`
        and `data.description` both mirror the same test-data field (their
        given example values already matched, unlike crop variety's
        name/nickName). Everything else — locations, statuses, null dates —
        is static, matching the captured payload exactly.
        """
        payload = {
            "companyStatus": "ACTIVE",
            "data": {"projectTypes": ["MAIN_FIELD"]},
            "expectedEndDate": None,
            "expectedStartDate": None,
            "officialEndDate": None,
            "officialStartDate": None,
            "linkProject": False,
            "projectStatus": "LIVE",
            "locations": [STATIC_LOCATION],
            "createdDate": None,
            "lastModifiedDate": None,
        }

        if "project_name" in test_data:
            unique_name = make_unique(test_data["project_name"])
            payload["name"] = unique_name
            payload["data"]["description"] = unique_name  # mirrors name

        return payload
