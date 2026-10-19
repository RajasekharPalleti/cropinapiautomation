"""Builds the PUT /services/farm/api/tasks (task fill) request body.

The field-by-field mapping and derivation rules follow the Task Fill spec
(sections 4-6): most fields are copied from the task's own GET response,
the execution dates are generated (execution day = today UTC + an offset),
sowing/harvest dates come from the croppable area (re-written with a
trailing Z — the area GET uses a +0000 offset the server can't parse),
createdDate is the current date, and the chemical total is the entered quantity multiplied by the
croppable area's audited area (the server doesn't compute or check it).

TaskFillPayload wraps the body with small fluent helpers (with_, without,
execution_day, chemical_quantity, ...) so a test states its one deviation
from the happy path in a single readable line.
"""
import copy
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

_PATH_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


# --- dates (rules R1/R2/R7) -------------------------------------------------


def utc_today() -> date:
    return datetime.now(UTC).date()


def date_part(value: Any) -> str | None:
    """'2026-10-20T00:00:00.000Z' -> '2026-10-20' (None stays None) — the
    server returns the same instant with or without milliseconds, so dates
    are compared by calendar day."""
    return str(value)[:10] if value else None


def exec_date(day: date) -> str:
    return f"{day.isoformat()}T00:00:00Z"


def exec_date_ms(day: date) -> str:
    return f"{day.isoformat()}T00:00:00.000Z"


def current_created_date() -> str:
    """The current moment as the fill body's createdDate, in the spec's
    format (ISO-8601 UTC with microseconds, e.g. 2026-10-19T06:30:20.341789Z)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def now_ms() -> str:
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


# --- croppable area / chemical maths (rule R5) ------------------------------


def audited_area(ca: dict) -> Any:
    """The area the chemical total is multiplied by: the croppable area's
    auditedArea, or — when nobody has audited it yet — its declaredArea. A
    croppable area this suite has just created is never audited (prod returns
    auditedArea: null alongside declaredArea: {"count": 5.0}), so without the
    fallback there'd be no area to multiply by. Either field may be a plain
    number or an object carrying 'count'."""
    for field in ("auditedArea", "declaredArea"):
        value = ca.get(field)
        if isinstance(value, dict):
            value = value.get("count")
        if value is not None:
            return value
    return None


def ca_harvest_date(ca: dict) -> Any:
    """The croppable area's harvest date, copied from the GET
    croppable-areas/{id} response, which names the field expectedHarvestDate
    (sowing date + the variety's days to harvest). harvestDate is only a
    fallback for a response that carries it instead."""
    return ca.get("expectedHarvestDate") or ca.get("harvestDate")


def iso_z(value: Any) -> Any:
    """The same instant written the way the task fill request can parse it: UTC with a
    trailing 'Z'. The croppable area GET returns its dates with a +0000 offset
    (e.g. 2026-10-19T08:57:38.842+0000), which the server's ZonedDateTime
    parser rejects with a 400 when it's echoed back in the fill body. A value
    already ending in 'Z' (or anything that isn't a parseable timestamp) is
    returned untouched; fractional seconds are kept to millisecond precision."""
    if not isinstance(value, str) or value.endswith("Z"):
        return value
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        return value
    utc = parsed.astimezone(UTC)
    text = utc.strftime("%Y-%m-%dT%H:%M:%S")
    if "." in value:
        text += f".{utc.microsecond // 1000:03d}"
    return f"{text}Z"


def multiply(count: Any, area: Any) -> int | float:
    """count x area without float noise (1000.0 x 2.98 -> 2980, not
    2980.0000000000005); whole results come back as int like the spec's
    sample, anything else as float."""
    product = Decimal(str(count)) * Decimal(str(area))
    if product == product.to_integral_value():
        return int(product)
    return float(product)


# --- path helpers -----------------------------------------------------------


def _tokens(path: str) -> list:
    return [int(idx) if idx else key for key, idx in _PATH_TOKEN.findall(path)]


def set_path(body: dict, path: str, value: Any) -> None:
    tokens = _tokens(path)
    node = body
    for token in tokens[:-1]:
        node = node[token]
    node[tokens[-1]] = value


def remove_path(body: dict, path: str) -> None:
    tokens = _tokens(path)
    node = body
    for token in tokens[:-1]:
        node = node[token]
    if isinstance(node, list):
        node.pop(tokens[-1])
    else:
        node.pop(tokens[-1], None)


def get_path(body: Any, path: str, default: Any = None) -> Any:
    node = body
    for token in _tokens(path):
        try:
            node = node[token]
        except (KeyError, IndexError, TypeError):
            return default
    return node


# --- context + builder ------------------------------------------------------


@dataclass
class TaskFillContext:
    """Everything the body needs that isn't on the task itself."""

    ca: dict  # GET croppable-areas/{id}: sowingDate, expectedHarvestDate, auditedArea/declaredArea
    plan_created_date: str  # createdDate sent in the body: the current date (the plan itself reports null)
    attr_names: dict  # {"text": ..., "dropdown": ..., "smart": ...} custom attribute names
    cfg: dict  # test data: task.fill
    exec_day: date  # today (UTC) + task.fill.execution_day_offset
    attr_required: dict | None = None  # {"text": bool, ...} — validation.required on the plan type
    plan_stored_created_date: str | None = None  # the plan's own createdDate (GET plans/{id}) before any fill


def build_base_payload(
    task: dict, ctx: TaskFillContext, *, now: str | None = None, client_id: str | None = None
) -> dict:
    """The happy-path 'fill and complete' body (spec section 4)."""
    cfg = ctx.cfg
    chem = cfg["chemical"]
    area = audited_area(ctx.ca)
    exec_day_date = exec_date(ctx.exec_day)
    exec_day_ms = exec_date_ms(ctx.exec_day)

    custom_attributes = {
        ctx.attr_names["text"]: cfg["custom_attributes"]["text_value"],
        ctx.attr_names["dropdown"]: cfg["custom_attributes"]["dropdown_value"],
        ctx.attr_names["smart"]: task.get("landName"),
    }

    return {
        "id": task.get("id"),
        "name": task.get("name"),
        "description": task.get("description"),
        "message": task.get("message"),
        "data": {
            "standardAttributesEntered": {
                "executedOn": exec_day_ms,
                "cropStage": None,
                "farmResource": None,
                "costPerArea": None,
                "totalCost": 0,
            },
            "standardAttributesEnteredOverride": {},
            "customAttributesEntered": custom_attributes,
            "customAttributesEnteredOverride": {},
            "planHeaderAttributesEntered": [
                {
                    "typeId": chem["type_id"],
                    "chemicalName": chem["chemical_id"],
                    "perQuantity": chem["per_quantity"],
                    "chemicalQuantity": dict(chem["quantity"]),
                    "chemicalConcentration": dict(chem["concentration"]),
                    "totalChemicalQuantity": {
                        "count": multiply(chem["quantity"]["count"], area),
                        "unit": chem["total_unit"],
                    },
                }
            ],
            "planHeaderAttributesEnteredOverride": {},
            "planHeaderGroupEntered": {},
            "planHeaderGroupEnteredOverride": {},
        },
        # The GET response spells this key 'chemicalQuanity' — the fill request never
        # sends it; the correctly spelled key is always null.
        "chemicalQuantity": None,
        "planTypeId": task.get("planTypeId"),
        "planTypeName": task.get("planTypeName"),
        "images": task.get("images") or {},
        "croppableAreaId": task.get("croppableAreaId"),
        "croppableAreaName": task.get("croppableAreaName"),
        "cropUnitId": task.get("cropUnitId"),
        "cropUnitName": task.get("cropUnitName"),
        "landId": task.get("landId"),
        "status": "COMPLETE",
        "projectId": task.get("projectId"),
        "sowingDate": iso_z(ctx.ca.get("sowingDate")),
        "harvestDate": iso_z(ca_harvest_date(ctx.ca)),
        "expExecutedOn": exec_day_date,
        "executedOn": exec_day_ms,
        "planId": task.get("planId"),
        "parentTask": task.get("parentTask"),
        "adhocType": task.get("adhocType"),
        "planVersion": task.get("planVersion"),
        "startDate": exec_day_date,
        "endDate": exec_day_date,
        "taskType": task.get("taskType"),
        "filledBy": cfg["filled_by"],
        "alertPlanId": task.get("alertPlanId"),
        "clientId": client_id or str(uuid.uuid4()),
        "parentPlanId": task.get("parentPlanId"),
        "pinned": task.get("pinned"),
        "planned": task.get("planned"),
        "deleted": task.get("deleted"),
        "cadenceType": None,
        "isSavedAsDraft": False,
        "lastUpdateTime": None,
        "lastModifiedDate": now or now_ms(),
        "dependentTasks": None,
        "reScheduling": task.get("reScheduling"),
        "conditionalScheduling": task.get("conditionalScheduling"),
        # The UI sends null here even when the GET says true.
        "directAdhocTask": None,
        "createdDate": ctx.plan_created_date,
        "filledDate": task.get("filledDate"),
        "isGDPRCompliant": task.get("isGDPRCompliant"),
        "mobileLastModifiedDate": None,
    }


class TaskFillPayload:
    """A fill body plus the helpers tests use to deviate from it."""

    def __init__(self, body: dict, ctx: TaskFillContext, open_status: Any = None):
        self._body = body
        self._ctx = ctx
        self._open_status = open_status  # the task's own status before the fill (what a draft keeps)

    @classmethod
    def base(cls, task: dict, ctx: TaskFillContext) -> "TaskFillPayload":
        return cls(build_base_payload(task, ctx), ctx, open_status=task.get("status"))

    def with_(self, path: str, value: Any) -> "TaskFillPayload":
        set_path(self._body, path, value)
        return self

    def without(self, path: str) -> "TaskFillPayload":
        remove_path(self._body, path)
        return self

    def get(self, path: str, default: Any = None) -> Any:
        return get_path(self._body, path, default)

    def execution_day(self, day: date) -> "TaskFillPayload":
        """Moves all five execution-date fields together (rules R1/R2)."""
        set_path(self._body, "executedOn", exec_date_ms(day))
        set_path(self._body, "data.standardAttributesEntered.executedOn", exec_date_ms(day))
        for field in ("expExecutedOn", "startDate", "endDate"):
            set_path(self._body, field, exec_date(day))
        return self

    def chemical_quantity(self, count: Any) -> "TaskFillPayload":
        """Sets the entered quantity and recalculates the total from the
        croppable area's audited area (rule R5)."""
        set_path(self._body, "data.planHeaderAttributesEntered[0].chemicalQuantity.count", count)
        total = multiply(count, audited_area(self._ctx.ca))
        set_path(self._body, "data.planHeaderAttributesEntered[0].totalChemicalQuantity.count", total)
        return self

    def custom_attribute(self, role: str, value: Any) -> "TaskFillPayload":
        """role is 'text', 'dropdown' or 'smart' — resolved to this run's
        actual (unique) attribute name."""
        self._body["data"]["customAttributesEntered"][self._ctx.attr_names[role]] = value
        return self

    def without_custom_attribute(self, role: str) -> "TaskFillPayload":
        self._body["data"]["customAttributesEntered"].pop(self._ctx.attr_names[role], None)
        return self

    def as_draft(self) -> "TaskFillPayload":
        """Save without completing. The server decides completion from `status`
        alone — a body with isSavedAsDraft: true but status COMPLETE still
        completes the task (seen on prod) — so a draft keeps the task's own
        open status as well as setting the flag."""
        self.with_("isSavedAsDraft", True)
        if self._open_status is not None:
            self.with_("status", self._open_status)
        return self

    def with_new_client_id(self) -> "TaskFillPayload":
        return self.with_("clientId", str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return copy.deepcopy(self._body)
