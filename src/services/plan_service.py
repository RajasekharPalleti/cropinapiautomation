"""Plan API service.

POST /services/farm/api/plans is multipart/form-data with the JSON body in
a 'dto' part (filename="blob"), same pattern as Farmer/Asset. Building the
payload requires a live GET on the plan type (embedded as-is into
data.information.planType) — the plan type id and crop variety id are both
resolved create-first/test-data-fallback by the caller (see
created_plantype_id / created_crop_variety_id fixtures in tests/conftest.py).
"""
import json as json_lib
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.response_wrapper import ApiResponse
from src.services.base_service import BaseService
from src.utils.run_uniqueness import make_unique

PLAN_TYPE_PATH = "/services/farm/api/plan-types"


class PlanService(BaseService):
    resource_path = "/services/farm/api/plans"

    def create(self, payload: dict, **kwargs: Any) -> ApiResponse:
        return self._client.post(
            self.resource_path,
            files={"dto": ("blob", json_lib.dumps(payload), "application/json")},
            **kwargs,
        )

    def build_create_payload(self, test_data: dict, plantype_id: Any, variety_id: Any) -> dict:
        """Maps flat test_data fields plus the resolved plantype/variety ids
        onto the real nested API body. `data.information.planType` is filled
        with the full, unmodified GET /plan-types/{plantype_id} response —
        a live read, not sourced from test data.
        """
        plantype_response = self._client.get(f"{PLAN_TYPE_PATH}/{plantype_id}")

        payload = {
            "data": {
                "information": {
                    "planType": plantype_response.json(),
                    "geoLocation": False,
                    "signature": False,
                },
                "conditions": {},
                "customAttributes": {},
                "planHeaderAttributes": [],
                "planHeaderGroup": {},
                "conditionData": {
                    "data": {},
                    "conditionParams": variety_id,
                },
            },
            "images": {},
            "varieties": [variety_id],
            "planTypeId": plantype_id,
            "schedule": {
                "type": "Scheduled",
                "fixedDate": True,
            },
        }

        if "plan_name" in test_data:
            unique_name = make_unique(test_data["plan_name"])
            payload["data"]["information"]["planName"] = unique_name
            payload["name"] = unique_name

        if "fixed_execution_day_offsets" in test_data:
            # Days relative to today (UTC), midnight — so the plan's tasks
            # always sit in a window the task-fill tests can fill into
            # (execution day = today + N), no matter when the suite runs.
            offsets = test_data["fixed_execution_day_offsets"]
            # PLAN_TASK_COUNT_OVERRIDE=N makes the plan N tasks (days 0..N-1) for
            # one run, e.g. a full regression on an env whose test data keeps the
            # plan small to leave little data behind.
            task_count = os.getenv("PLAN_TASK_COUNT_OVERRIDE")
            if task_count:
                offsets = list(range(int(task_count)))
            today = datetime.now(timezone.utc).date()
            payload["schedule"]["fixedExecutionDates"] = [
                f"{today + timedelta(days=offset)}T00:00:00.000Z" for offset in offsets
            ]
        elif "fixed_execution_dates" in test_data:
            payload["schedule"]["fixedExecutionDates"] = test_data["fixed_execution_dates"]

        return payload
