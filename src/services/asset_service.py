"""Asset API service.

POST /services/farm/api/assets and its PUT update both use the same
multipart 'dto' blob pattern as FarmerService — see that module for the
Content-Disposition rationale.
"""
import json as json_lib
from datetime import datetime
from typing import Any

from src.core.response_wrapper import ApiResponse
from src.services.base_service import BaseService
from src.utils.run_uniqueness import make_unique

# Same for every asset this suite creates — not sourced from test data.
# Note: sublocalityLevel2 differs from FarmerService.STATIC_ADDRESS
# ("Aicobo Nagar" vs "1st Stage") — kept as a separate constant to match
# exactly what was captured for each resource.
STATIC_ADDRESS = {
    "country": "India",
    "formattedAddress": "3rd Floor, 1021, 16th Main Rd, Tavarekere, Aicobo Nagar, "
    "1st Stage, BTM 1st Stage, Bengaluru, Karnataka 560029, India",
    "administrativeAreaLevel1": "Karnataka",
    "locality": "Bengaluru",
    "administrativeAreaLevel2": "Bangalore Division",
    "sublocalityLevel1": "BTM 1st Stage",
    "sublocalityLevel2": "Aicobo Nagar",
    "landmark": "",
    "postalCode": "560029",
    "houseNo": "",
    "buildingName": "",
    "placeId": "ChIJUeUT6hAVrjsRrywyoYVfGrc",
    "latitude": 12.918849,
    "longitude": 77.61041159999999,
}


class AssetService(BaseService):
    resource_path = "/services/farm/api/assets"

    def create(self, payload: dict, **kwargs: Any) -> ApiResponse:
        return self._client.post(
            self.resource_path,
            files={"dto": ("blob", json_lib.dumps(payload), "application/json")},
            **kwargs,
        )

    def update(self, payload: dict, **kwargs: Any) -> ApiResponse:
        """PUT to the plain collection URL — no id in the path, same pattern
        as FarmerService.update(). The asset id must already be present
        inside `payload` (as returned by a prior get_by_id() call) since
        that's how the server identifies which record to update.
        """
        return self._client.put(
            self.resource_path,
            files={"dto": ("blob", json_lib.dumps(payload), "application/json")},
            **kwargs,
        )

    def build_create_payload(self, test_data: dict, owner_id: Any) -> dict:
        """Maps flat test_data fields onto the real nested API body. A field
        not present in test_data is left out of the payload entirely.
        owner_id is passed separately since it comes from a created farmer,
        not from the asset's own test data.
        """
        data_section = {}
        if "rajaadditionalcheckbox" in test_data:
            data_section["rajaadditionalcheckbox"] = test_data["rajaadditionalcheckbox"]
        if "rajaadditonalUrl" in test_data:
            data_section["rajaadditonalUrl"] = test_data["rajaadditonalUrl"]
        if "tags" in test_data:
            data_section["tags"] = test_data["tags"]

        declared_area = {"enableConversion": "true"}
        if "assetdeclaredareaunit" in test_data:
            declared_area["unit"] = test_data["assetdeclaredareaunit"]
        if "declaredareacount" in test_data:
            declared_area["count"] = test_data["declaredareacount"]

        # auditedArea.unit reuses the same test_data field as declaredArea.unit.
        audited_area = {"enableConversion": "true"}
        if "assetdeclaredareaunit" in test_data:
            audited_area["unit"] = test_data["assetdeclaredareaunit"]

        payload = {
            "data": data_section,
            "images": {},
            "companyStatus": "ACTIVE",
            "declaredArea": declared_area,
            "auditedArea": audited_area,
            "ownerId": owner_id,
            "address": STATIC_ADDRESS,
        }

        if "asset_name" in test_data:
            payload["name"] = make_unique(test_data["asset_name"])

        if "soiltypeid" in test_data:
            payload["soilType"] = {"id": test_data["soiltypeid"]}
        if "irrigationtypeid" in test_data:
            payload["irrigationType"] = {"id": test_data["irrigationtypeid"]}

        return payload

    def build_update_payload(self, asset: dict) -> dict:
        """Takes the asset object as returned by get_by_id() and returns a
        copy with `name` suffixed by the current timestamp, ready to PUT
        straight back — the id and every other field are carried through
        unchanged, exactly as fetched."""
        updated = dict(asset)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        updated["name"] = f"{updated.get('name', '')}_{timestamp}"
        return updated
