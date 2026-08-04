"""Farmer API service.

POST /services/farm/api/farmers is sent as multipart/form-data with the JSON
body in a 'dto' part — filename="blob" mirrors the real captured request
(the browser appends the JSON as a Blob to FormData), not a plain
application/json body like the generic CRUD shape in BaseService.
"""
import json as json_lib
from datetime import datetime
from typing import Any

from src.core.response_wrapper import ApiResponse
from src.services.base_service import BaseService
from src.utils.run_uniqueness import make_unique, unique_mobile_number

# Same for every farmer this suite creates — not sourced from test data.
STATIC_ADDRESS = {
    "country": "India",
    "formattedAddress": "3rd Floor, 1021, 16th Main Rd, Tavarekere, Aicobo Nagar, "
    "1st Stage, BTM 1st Stage, Bengaluru, Karnataka 560029, India",
    "houseNo": "",
    "buildingName": "",
    "administrativeAreaLevel1": "Karnataka",
    "locality": "Bengaluru",
    "administrativeAreaLevel2": "Bangalore Division",
    "sublocalityLevel1": "BTM 1st Stage",
    "sublocalityLevel2": "1st Stage",
    "landmark": "",
    "postalCode": "560029",
    "placeId": "ChIJUeUT6hAVrjsRrywyoYVfGrc",
    "latitude": 12.918849,
    "longitude": 77.61041159999999,
}


class FarmerService(BaseService):
    resource_path = "/services/farm/api/farmers"

    def create(self, payload: dict, **kwargs: Any) -> ApiResponse:
        return self._client.post(
            self.resource_path,
            files={"dto": ("blob", json_lib.dumps(payload), "application/json")},
            **kwargs,
        )

    def update(self, payload: dict, **kwargs: Any) -> ApiResponse:
        """PUT to the plain collection URL — no id in the path, unlike
        BaseService.update()'s `{resource_path}/{resource_id}` shape. The
        farmer id must already be present inside `payload` (as returned by a
        prior get_by_id() call) since that's how the server identifies which
        record to update.
        """
        return self._client.put(
            self.resource_path,
            files={"dto": ("blob", json_lib.dumps(payload), "application/json")},
            **kwargs,
        )

    def build_create_payload(self, test_data: dict) -> dict:
        """Maps flat test_data fields onto the real nested API body. A field
        not present in test_data is left out of the payload entirely."""
        data_section = {}
        if "farmermobilenumber" in test_data:
            # A real, valid-looking number is generated fresh each run (not
            # test_data's literal value) since it must be unique against a
            # real backend that enforces farmer-detail uniqueness.
            data_section["mobileNumber"] = unique_mobile_number()
        if "farmerisdcode" in test_data:
            data_section["countryCode"] = test_data["farmerisdcode"]
        if "farmerisocode" in test_data:
            data_section["countryIsoCode"] = test_data["farmerisocode"]
        if "rajaadditionaltext" in test_data:
            data_section["rajaadditionaltext"] = test_data["rajaadditionaltext"]
        if "rajaadditionalDate" in test_data:
            data_section["rajaadditionalDate"] = test_data["rajaadditionalDate"]
        if "rajaadditionalMultiSelect" in test_data:
            data_section["rajaadditionalMultiSelect"] = [
                v.strip()
                for v in test_data["rajaadditionalMultiSelect"].split(",")
                if v.strip()
            ]

        declared_area = {"enableConversion": "true"}
        if "declaredAreaUnit" in test_data:
            declared_area["unit"] = test_data["declaredAreaUnit"]

        payload = {
            "status": "DISABLE",
            "data": data_section,
            "images": {},
            "declaredArea": declared_area,
            "address": STATIC_ADDRESS,
        }

        if "farmerfirstname" in test_data:
            unique_name = make_unique(test_data["farmerfirstname"])
            payload["firstName"] = unique_name
            payload["farmerCode"] = unique_name  # intentionally mirrors firstName

        if "assignedTo" in test_data:
            payload["assignedTo"] = test_data["assignedTo"]

        if "isGDPRCompliant" in test_data:
            payload["isGDPRCompliant"] = bool(test_data["isGDPRCompliant"])

        return payload

    def build_update_payload(self, farmer: dict) -> dict:
        """Takes the farmer object as returned by get_by_id() and returns a
        copy with firstName suffixed by the current timestamp, ready to PUT
        straight back — the id and every other field are carried through
        unchanged, exactly as fetched."""
        updated = dict(farmer)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        updated["firstName"] = f"{updated.get('firstName', '')}_{timestamp}"
        return updated
