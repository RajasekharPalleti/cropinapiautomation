"""Form API service (form creation, form update, form fill).

POST /services/form/api/forms          — creates a form; plain JSON body, not
                                         multipart (inherited create()).
GET  /services/form/api/forms/{id}     — the stored form (inherited get_by_id()).
PUT  /services/form/api/forms          — updates a form (update()); the form
                                         object with its id in the body, not in
                                         the URL, same as farmer/plan type.
POST /services/form/api/filled-forms   — fills a form for a farmer (fill()); a
                                         create, so the body must NOT carry an
                                         id (the captured sample had one — it is
                                         left out here, the server assigns it).
GET  /services/form/api/filled-forms/{id} — the stored filled form (get_filled()),
                                         by the id the fill POST returned; used to
                                         read the fill back independently.

DELETE /services/form/api/forms/bulk?ids=<id> — the inherited delete_bulk(); the
                                         end-of-run cleanup deletes the run's form
                                         with it. Its body is {"nonDeletedIds": [...],
                                         "deletedIds": [...]}, not the {"deletable",
                                         "nonDeletable"} shape of farmer/asset/variety.

There is no delete API for filled forms, so each run leaves one filled form
behind (the cleanup has no step for it).
"""
import copy
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.response_wrapper import ApiResponse
from src.services.base_service import BaseService
from src.utils.run_uniqueness import make_unique

FILLED_FORMS_PATH = "/services/form/api/filled-forms"


def _utc_today():
    return datetime.now(timezone.utc).date()


def _day_z(day) -> str:
    """UTC midnight with a trailing Z — the server's ZonedDateTime parser
    rejects a +0000 offset, so every date this service writes ends in Z."""
    return f"{day.isoformat()}T00:00:00.000Z"


def _now_z() -> str:
    """The current moment, ISO-8601 UTC with milliseconds and a trailing Z."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class FormService(BaseService):
    resource_path = "/services/form/api/forms"

    def update(self, payload: dict, **kwargs: Any) -> ApiResponse:
        """PUT to the plain collection URL — no id in the path, unlike
        BaseService.update()'s `{resource_path}/{resource_id}` shape. The form
        id must already be inside `payload`."""
        return self._client.put(self.resource_path, json=payload, **kwargs)

    def fill(self, payload: dict, **kwargs: Any) -> ApiResponse:
        """POSTs a filled-form body (a create — no id in the body)."""
        return self._client.post(FILLED_FORMS_PATH, json=payload, **kwargs)

    def get_filled(self, filled_form_id: Any, **kwargs: Any) -> ApiResponse:
        """GETs a filled form by the id the fill POST returned — the
        independent read-back of what was stored."""
        return self._client.get(f"{FILLED_FORMS_PATH}/{filled_form_id}", **kwargs)

    def build_create_payload(self, test_data: dict, variety_id: Any, client_id: str | None = None) -> dict:
        """Maps test_data onto the real create body. The form name is made
        unique per run, the crop variety is the one this run created, and
        validFrom/validTo are days relative to today (UTC midnight) so the form
        is always valid on the day the suite runs. `client_id` is the run's
        one shared clientId (the same value goes into the update and the fill);
        a fresh uuid4 is generated when none is given (e.g. the negative
        tests). Sending a clientId on create is deliberate and user-requested —
        the captured create body had none, only the create response did."""
        attributes = []
        for definition in test_data.get("custom_attributes", []):
            attribute = {"name": definition["name"], "type": definition["type"], "label": definition["label"]}
            if "options" in definition:
                attribute["options"] = list(definition["options"])
            attribute.update(
                {
                    "condition": False,
                    "hasCalculation": False,
                    "validation": {"fixed": False, "required": False, "multiple": False},
                    "hidden": False,
                }
            )
            attributes.append(attribute)

        today = _utc_today()
        payload = {
            "status": test_data["status"],
            "data": {"customAttributes": attributes},
            "name": make_unique(test_data["form_name"]),
            "clientId": client_id or str(uuid.uuid4()),
            "formTypeId": test_data["form_type_id"],
            "formTypeName": test_data["form_type_name"],
            "varietyId": [variety_id],
            "validFrom": _day_z(today + timedelta(days=test_data["valid_from_day_offset"])),
            "validTo": _day_z(today + timedelta(days=test_data["valid_to_day_offset"])),
            "consentDetails": None,
            "fillOnlyOnce": None,
            "smartComputeScreenConfigData": {},
            "createdDate": None,
            "lastModifiedDate": None,
        }
        return payload

    def build_update_payload(self, created_body: dict, test_data: dict) -> dict:
        """The PUT body for a form update: the form create() response, exactly
        as returned (id included), with ONLY the name changed — test_data's
        name_suffix appended. No other field is re-added or normalised, so
        what goes out is what the server returned (that includes the
        create response's null formTypeName)."""
        updated = copy.deepcopy(created_body)
        updated["name"] = f"{created_body['name']}{test_data['name_suffix']}"
        return updated

    def build_fill_payload(
        self, test_data: dict, form_payload: dict, form_id: Any, farmer_id: Any, farmer_name: Any,
        client_id: str | None = None,
    ) -> dict:
        """The filled-form body for one farmer. The form is the one this run
        created (its id, unique name and form type come from the create
        payload/response, not test data); filledValues are the static values
        from test_data plus the date attributes, which are days relative to
        today. `client_id` is the run's one shared clientId (the same value as
        the form create body and update); a fresh uuid4 is generated when none
        is given (e.g. the negative tests). The current moment is generated as
        filledDate per call. No `id` — this is a create."""
        filled_values = dict(test_data.get("filled_values", {}))
        today = _utc_today()
        for attribute_name, day_offset in test_data.get("filled_date_values", {}).items():
            filled_values[attribute_name] = _day_z(today + timedelta(days=day_offset))

        return {
            "name": form_payload["name"],
            "clientId": client_id or str(uuid.uuid4()),
            "formName": form_payload["name"],
            "formId": form_id,
            "formTypeId": form_payload["formTypeId"],
            "data": {
                "filledValues": filled_values,
                "customAttributes": "",
                "filledValuesOverride": {},
                "firstName": farmer_name,
                "lastName": None,
                "filledFormVersion": test_data["filled_form_version"],
                "filledDate": _now_z(),
                "farmerId": farmer_id,
            },
            "images": {},
            "isDeleted": None,
            "isDraft": False,
            "archive": None,
            "isMobileFormrejection": None,
            "isGDPRCompliant": True,
            "consentSelected": False,
            "consentId": None,
            "farmerId": farmer_id,
            "lastModifiedDate": None,
        }
