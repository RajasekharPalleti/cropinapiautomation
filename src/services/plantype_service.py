"""Plan Type API service.

POST/PUT /services/farm/api/plan-types use a plain JSON body (NOT multipart —
confirmed explicitly, unlike Farmer/Asset). The create payload is a large,
mostly-static structure (src/services/templates/plantype_create_template.json)
where only specific fields are test-data-driven — everything else in the
template is sent through unchanged, per instruction.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.response_wrapper import ApiResponse
from src.services.base_service import BaseService
from src.utils.run_uniqueness import make_unique

TEMPLATE_PATH = Path(__file__).parent / "templates" / "plantype_create_template.json"

# The one entry smartComputeScreenConfigData always holds — only its key
# (the custom attribute 3 name) is test-data-driven.
SMART_COMPUTE_ENTRY = [
    {
        "value": "assetname",
        "path": "Source:  Standard Fields  >  Asset  >  Asset Name",
        "type": "ATR",
    }
]


class PlanTypeService(BaseService):
    resource_path = "/services/farm/api/plan-types"

    def update(self, payload: dict, **kwargs: Any) -> ApiResponse:
        """PUT to the plain collection URL — no id in the path, same pattern
        as Farmer/Asset's update(). The plan type id must already be present
        inside `payload` (as returned by a prior get_by_id() call). Not
        explicitly confirmed for Plan Type (no PUT URL was given) — assumed
        consistent with the other 'farm' module resources.
        """
        return self._client.put(self.resource_path, json=payload, **kwargs)

    def build_create_payload(self, test_data: dict) -> dict:
        """Loads the static plan-type template and overlays only the
        test-data-driven fields (custom attribute 1/2/3 name+label, the
        attribute-3 -> attribute-2 dependentOn cross-reference, the
        smartComputeScreenConfigData key, and the top-level name) —
        everything else in the template is left exactly as captured.
        """
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)

        # Names are made unique per run (not test_data's literal value) since
        # the backend rejects a second run's identical plan type/attribute
        # names as duplicates. The dependentOn/smartComputeScreenConfigData
        # cross-references below point at these same unique values, not the
        # raw test_data ones, so they stay correct.
        attr1_name = make_unique(test_data["custom_attribute_1_name"])
        attr2_name = make_unique(test_data["custom_attribute_2_name"])
        attr3_name = make_unique(test_data["custom_attribute_3_name"])

        custom_attrs = payload["data"]["customAttributes"]
        custom_attrs[0]["name"] = attr1_name
        custom_attrs[0]["label"] = test_data["custom_attribute_1_label"]
        custom_attrs[1]["name"] = attr2_name
        custom_attrs[1]["label"] = test_data["custom_attribute_2_label"]
        custom_attrs[2]["name"] = attr3_name
        custom_attrs[2]["label"] = test_data["custom_attribute_3_label"]
        # dependentOn references attribute 2's name, not an independent field.
        custom_attrs[2]["dependentOn"] = attr2_name

        payload["name"] = make_unique(test_data["plantype_name"])
        # smartComputeScreenConfigData is keyed by attribute 3's name.
        payload["smartComputeScreenConfigData"] = {attr3_name: SMART_COMPUTE_ENTRY}

        return payload

    def build_update_payload(self, plantype: dict) -> dict:
        """Takes the plan type object as returned by get_by_id() and returns
        a copy with `name` suffixed by the current timestamp, ready to PUT
        straight back — the id and every other field are carried through
        unchanged, exactly as fetched."""
        updated = dict(plantype)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        updated["name"] = f"{updated.get('name', '')}_{timestamp}"
        return updated
