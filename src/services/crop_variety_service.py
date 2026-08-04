"""Crop Variety API service.

POST/PUT /services/farm/api/varieties use a plain JSON body. `cropStages` and
`harvestGrades` are resolved by name via two separate lookup GET APIs —
test data supplies names, the real matching objects (id/description/etc.)
come from those APIs, and the field is an empty list if nothing matches
(same as the always-empty `seedGrades`).
"""
from datetime import datetime
from typing import Any

from src.core.response_wrapper import ApiResponse
from src.services.base_service import BaseService
from src.utils.run_uniqueness import make_unique

CROP_STAGES_PATH = "/services/farm/api/crop-stages"
HARVEST_GRADES_PATH = "/services/master/api/harvest-grades"
ADDITIONAL_ATTRIBUTE_PATH = "/services/farm/api/additional-attribute"

# Static for every variety this suite creates — not sourced from test data.
STATIC_LOCATION = {
    "bounds": {
        "northeast": {"lat": 14.42780722260265, "lng": 79.75546729378563},
        "southwest": {"lat": 14.33598011099241, "lng": 79.67786110356819},
    },
    "country": "India",
    "administrativeAreaLevel3": "Sri Potti Sriramulu Nellore",
    "administrativeAreaLevel1": "Andhra Pradesh",
    "placeId": "ChIJTayUG8bBTDoR8WYAMdBkmsY",
    "latitude": 14.3848012,
    "longitude": 79.73268279999999,
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
                            [79.67786110356819, 14.33598011099241],
                            [79.75546729378563, 14.33598011099241],
                            [79.75546729378563, 14.42780722260265],
                            [79.67786110356819, 14.42780722260265],
                            [79.67786110356819, 14.33598011099241],
                        ]
                    ],
                },
            }
        ],
    },
    "name": "Podalakur",
}

STATIC_VARIETY_ADDITIONAL_ATTRIBUTES = [
    {
        "name": "Automation Text",
        "datatype": "Text",
        "attributeValue": "",
        "data": {"value": "Automation Text"},
        "visible": True,
        "sequence": 1,
        "validation": {"fixed": False, "multiple": True, "required": False},
        "_isNew": True,
    },
    {
        "name": "Automation ",
        "datatype": "Image",
        "attributeValue": "",
        "data": {
            "value": [
                {
                    "contentType": "image/jpeg",
                    "identifier": "59403b06-4fe7-48c1-9413-a8642edb0eab",
                    "feature": "Variety_Additional_Attribute",
                    "originalFileName": "compress17800443213061785390475342.jpeg",
                    "size": 274551,
                    "imageType": "configured",
                    "channel": "web",
                    "imageSource": None,
                    "capturedDateTime": None,
                    "imageLat": None,
                    "imageLong": None,
                    "active": True,
                }
            ],
            "images": {
                "compress17800443213061785390475342.jpeg": "data.values.[1].cropAdditionalAtrImaghldr"
            },
            "data": {"cropAdditionalAtrImag": []},
            "cropAdditionalAtrImaghldr": [
                {
                    "contentType": "image/jpeg",
                    "identifier": "59403b06-4fe7-48c1-9413-a8642edb0eab",
                    "feature": "Variety_Additional_Attribute",
                    "originalFileName": "compress17800443213061785390475342.jpeg",
                    "size": 274551,
                    "imageType": "configured",
                    "channel": "web",
                    "imageSource": None,
                    "capturedDateTime": None,
                    "imageLat": None,
                    "imageLong": None,
                    "active": True,
                }
            ],
        },
        "visible": True,
        "sequence": 2,
        "validation": {"fixed": False, "multiple": True, "required": False},
        "_isNew": True,
        "type": "Image",
    },
]


class CropVarietyService(BaseService):
    resource_path = "/services/farm/api/varieties"

    def update(self, payload: dict, **kwargs: Any) -> ApiResponse:
        """PUT to the plain collection URL — no id in the path. Not
        explicitly confirmed for Crop Variety (no PUT details were given) —
        assumed consistent with Farmer/Asset/Plantype per instruction.
        """
        return self._client.put(self.resource_path, json=payload, **kwargs)

    def add_additional_attributes(self, variety_id: Any, **kwargs: Any) -> ApiResponse:
        """PUT /services/farm/api/additional-attribute — a mandatory
        follow-up call after create(), since it needs the variety's id
        (which only exists once create() has returned). Re-sends the same
        varietyAdditionalAttributeList used in the create payload, combined
        with the new variety_id.

        Live-verified the field is `varietyId`, not `id` — the latter (what
        the original spec described, matching the create payload's own
        "id": null field) got rejected by the real API with
        errorKey=varietyIdNull, since this is a different backing service
        (varietyAdditionalAttributeService) with its own field naming.
        """
        payload = {
            "varietyId": variety_id,
            "varietyAdditionalAttributeList": STATIC_VARIETY_ADDITIONAL_ATTRIBUTES,
        }
        return self._client.put(ADDITIONAL_ATTRIBUTE_PATH, json=payload, **kwargs)

    def resolve_crop_stages_by_names(self, names: list) -> list:
        """Calls GET /services/farm/api/crop-stages and returns the full
        objects whose 'name' is in `names` — empty list if none match or
        `names` is empty (same fallback as the always-empty seedGrades)."""
        if not names:
            return []
        response = self._client.get(CROP_STAGES_PATH)
        return [stage for stage in response.json() if stage.get("name") in names]

    def resolve_harvest_grades_by_names(self, names: list) -> list:
        """Calls GET /services/master/api/harvest-grades and returns the
        full objects whose 'name' is in `names` — empty list if none match
        or `names` is empty."""
        if not names:
            return []
        response = self._client.get(HARVEST_GRADES_PATH)
        return [grade for grade in response.json() if grade.get("name") in names]

    def build_create_payload(self, test_data: dict) -> dict:
        """Maps flat test_data fields onto the real nested API body.
        cropStages/harvestGrades are resolved live from their lookup APIs by
        name — everything else matches the captured payload exactly.
        """
        yield_entry = {
            "data": {},
            "locations": STATIC_LOCATION,
            "expectedYieldQuantity": "",
            "_uid": 1,
            "_isNew": True,
        }
        if "expected_yield" in test_data:
            yield_entry["expectedYield"] = test_data["expected_yield"]
        if "expected_yield_unit" in test_data:
            yield_entry["expectedYieldUnits"] = test_data["expected_yield_unit"]
        if "reference_area_unit" in test_data:
            yield_entry["refrenceAreaUnits"] = test_data["reference_area_unit"]

        payload = {
            "data": {"yieldPerLocation": [yield_entry]},
            "processStandardDeduction": None,
            "cropPrice": None,
            "seedGrades": [],
            "id": None,
            "varietyAdditionalAttributeList": STATIC_VARIETY_ADDITIONAL_ATTRIBUTES,
        }

        if "crop_id" in test_data:
            payload["cropId"] = test_data["crop_id"]
        if "variety_name" in test_data:
            unique_name = make_unique(test_data["variety_name"])
            payload["name"] = unique_name
            payload["nickName"] = unique_name  # intentionally mirrors name
        if "expected_harvest_days" in test_data:
            payload["expectedHarvestDays"] = test_data["expected_harvest_days"]

        payload["cropStages"] = self.resolve_crop_stages_by_names(
            test_data.get("crop_stage_names", [])
        )
        payload["harvestGrades"] = self.resolve_harvest_grades_by_names(
            test_data.get("harvest_grade_names", [])
        )

        return payload

    def build_update_payload(self, variety: dict) -> dict:
        """Takes the variety object as returned by get_by_id() and returns a
        copy with `name` suffixed by the current timestamp, ready to PUT
        straight back — the id and every other field are carried through
        unchanged, exactly as fetched."""
        updated = dict(variety)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        updated["name"] = f"{updated.get('name', '')}_{timestamp}"
        return updated
