"""Plan API service.

POST /services/farm/api/plans is multipart/form-data with the JSON body in
a 'dto' part (filename="blob"), same pattern as Farmer/Asset. Building the
payload requires a live GET on the plan type (embedded as-is into
data.information.planType) — the plan type id and crop variety id are both
resolved create-first/test-data-fallback by the caller (see
created_plantype_id / created_crop_variety_id fixtures in tests/conftest.py).
"""
import json as json_lib
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

        if "fixed_execution_dates" in test_data:
            payload["schedule"]["fixedExecutionDates"] = test_data["fixed_execution_dates"]

        return payload
