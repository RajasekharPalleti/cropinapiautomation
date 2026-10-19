"""Form negative scenarios (TC-FORM-004, TC-FORM-005): requests the server must
refuse, leaving no record behind. Each starts from the normal body and
changes the one thing its scenario is about, and makes its own call (so the
report shows it). (The unknown-form fill carries the form's created name, not
its updated one — irrelevant for a form that doesn't exist.)

The allowed statuses live in test data — form.expectations in
test_data/<env>.json. TC_FORM_004 allows any 4xx; TC_FORM_005 allows any 4xx
and also 500, because that is what the real server answers for a form id it
can't find ("Unable to find ...Form with id ...") — accepted as a refusal on
purpose. A 2xx fails the test: the server accepted something it should have
refused (the real server does exactly that for a blank form name). These run
after the happy-path form tests so a request that is wrongly accepted can't
disturb them.
"""
import pytest

from src.utils.test_data_loader import load_test_data
from tests.conftest import register_created_form
from tests.form.form_asserts import assert_rejected

pytestmark = [pytest.mark.form, pytest.mark.negative, pytest.mark.regression]

UNKNOWN_FORM_ID = 999999999


def test_create_form_blank_name_rejected(form_service, created_crop_variety_id):
    """TC_FORM_004 — the normal create body, but with name "": must be refused
    (4xx, not a server error) and must not return a new form id. If the server
    accepts it anyway the test fails — and the form it created is still deleted
    by the end-of-run cleanup."""
    payload = form_service.build_create_payload(load_test_data("form", "create_valid"), created_crop_variety_id)
    payload["name"] = ""

    response = form_service.create(payload)
    # The real server accepts a blank name (201) — that form exists whatever the
    # assertion below says, so register it for deletion BEFORE asserting.
    register_created_form(response, "TC-FORM-004 blank name")

    assert_rejected(
        response, load_test_data("form", "expectations")["TC_FORM_004"], "TC_FORM_004 (create with a blank name)"
    )


def test_fill_form_unknown_form_id_rejected(
    form_service, farmer_service, created_form, created_form_id, created_farmer, created_farmer_id
):
    """TC_FORM_005 — the normal fill body for the run's farmer, but formId is an
    id that doesn't exist: must be refused (a 4xx, or the 500 the real server
    gives for an unknown form — see form.expectations) and must not return a
    filled-form id. created_form_id is requested so the test skips
    when no form was created this run, like the fill test."""
    farmer_response = farmer_service.get_by_id(created_farmer_id)
    farmer_name = farmer_response.json().get("firstName") if farmer_response.status == 200 else None
    if not farmer_name:
        farmer_name = created_farmer.json().get("firstName")
    payload = form_service.build_fill_payload(
        load_test_data("form", "fill_valid"), created_form["payload"], UNKNOWN_FORM_ID,
        created_farmer_id, farmer_name,
    )

    response = form_service.fill(payload)

    assert_rejected(
        response, load_test_data("form", "expectations")["TC_FORM_005"],
        "TC_FORM_005 (fill of a form that does not exist)",
    )
