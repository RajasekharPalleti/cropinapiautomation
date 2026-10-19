import pytest

from src.core.response_validator import assert_status
from tests.form.form_asserts import assert_on_utc_day, utc_day, utc_today


def _assert_fill_fields(body: dict, sent: dict, form_id, farmer_id, source: str) -> None:
    """What the fill POST response and the GET read-back must both show
    (`source` names which, for the failure message): the form, the farmer, the
    saved answers and the flags."""
    assert body.get("formId") == form_id, f"{source}: expected formId {form_id}, got {body.get('formId')!r}"
    assert body.get("formTypeId") == sent["formTypeId"], (
        f"{source}: expected formTypeId {sent['formTypeId']!r}, got {body.get('formTypeId')!r}"
    )

    data = body.get("data") or {}
    assert data.get("filledValues") == sent["data"]["filledValues"], (
        f"{source}: expected filledValues {sent['data']['filledValues']}, got {data.get('filledValues')}"
    )
    assert data.get("farmerId") == farmer_id, (
        f"{source}: expected data.farmerId {farmer_id}, got {data.get('farmerId')!r}"
    )
    assert body.get("farmerId") == farmer_id, (
        f"{source}: expected farmerId {farmer_id}, got {body.get('farmerId')!r}"
    )

    assert body.get("isDeleted") is False, f"{source}: expected isDeleted false, got {body.get('isDeleted')!r}"
    assert body.get("isGDPRCompliant") is sent["isGDPRCompliant"], (
        f"{source}: expected isGDPRCompliant {sent['isGDPRCompliant']}, got {body.get('isGDPRCompliant')!r}"
    )
    for field in ("userFilledName", "filledName"):
        value = body.get(field)
        assert isinstance(value, str) and value.strip(), (
            f"{source}: expected a non-empty {field}, got {value!r}"
        )


@pytest.mark.form
@pytest.mark.sanity
@pytest.mark.regression
def test_fill_form_success(
    filled_form, stored_filled_form, created_form_id, created_farmer_id, form_client_id
):
    """filled_form performs the one fill for the whole run (the shared form,
    filled for the shared farmer) and stored_filled_form the one fresh GET of
    the filled form by the id the POST returned. This test asserts on what the
    POST returned, then reads the fill back through the GET and cross-checks
    the form id, the form name and the farmer name (plus the saved answers) —
    the POST echo alone isn't proof the fill was stored.

    clientId: the fill body carries the run's form_client_id (the same value as
    the form create and update), and the GET must show it. Checked on the GET
    only — the captured sample POST response's clientId came from a different
    call than the sample request, so it isn't proven to be an echo.

    Dates, all on the GET, compared as parsed instants / UTC days (the styles
    differ: createdDate comes back ending +0000, not Z): data.filledDate is
    the day that was sent (the current day), and createdDate and
    lastModifiedDate are the server's current timestamps, so they must fall on
    today's UTC day. A UTC-midnight rollover between the fill and this check is
    tolerated by also accepting the day the fill was sent.
    """
    response = filled_form["response"]
    sent = filled_form["payload"]
    assert_status(response, 201)

    body = response.json()
    assert isinstance(body.get("id"), int), (
        f"POST response: expected a numeric filled-form id, got {body.get('id')!r}"
    )
    _assert_fill_fields(body, sent, created_form_id, created_farmer_id, "POST response")

    # The independent read-back. If the POST succeeded but this GET isn't 200
    # the test fails here, it doesn't skip.
    assert stored_filled_form is not None, "The filled-form GET was not made — the fill POST returned no id"
    assert_status(stored_filled_form, 200)
    stored = stored_filled_form.json()
    stored_data = stored.get("data") or {}
    assert stored.get("id") == body["id"], f"GET: expected id {body['id']}, got {stored.get('id')!r}"
    _assert_fill_fields(stored, sent, created_form_id, created_farmer_id, "GET")

    # clientId: the run-wide id, GET only (see the docstring).
    assert sent["clientId"] == form_client_id, (
        f"The fill body should carry the run's clientId {form_client_id}, got {sent['clientId']!r}"
    )
    assert stored.get("clientId") == form_client_id, (
        f"GET: expected clientId {form_client_id}, got {stored.get('clientId')!r}"
    )

    # Dates: filledDate is what was sent (the current day); createdDate and
    # lastModifiedDate are server-stamped "now" — today's UTC day, or the day
    # the fill was sent if midnight UTC passed in between.
    sent_day = utc_day(sent["data"]["filledDate"])
    assert_on_utc_day(stored_data.get("filledDate"), {sent_day}, "data.filledDate", "GET")
    today_or_sent_day = {sent_day, utc_today()}
    assert_on_utc_day(stored.get("createdDate"), today_or_sent_day, "createdDate", "GET")
    assert_on_utc_day(stored.get("lastModifiedDate"), today_or_sent_day, "lastModifiedDate", "GET")

    # Form name: the GET reports the form's name in both name and formName
    # (the POST response leaves formName null, so this is where it is checked).
    form_name = sent["name"]
    assert stored.get("name") == form_name, f"GET: expected name {form_name!r}, got {stored.get('name')!r}"
    assert stored.get("formName") == form_name, (
        f"GET: expected formName {form_name!r}, got {stored.get('formName')!r}"
    )

    # Farmer name: data.firstName is the name that was sent. filledName is
    # checked with `in`, not ==, since the server may compose it from the name.
    farmer_name = sent["data"]["firstName"]
    assert stored_data.get("firstName") == farmer_name, (
        f"GET: expected data.firstName {farmer_name!r}, got {stored_data.get('firstName')!r}"
    )
    assert farmer_name in (stored.get("filledName") or ""), (
        f"GET: expected filledName to contain {farmer_name!r}, got {stored.get('filledName')!r}"
    )
    assert stored_data.get("filledFormVersion") == sent["data"]["filledFormVersion"], (
        f"GET: expected data.filledFormVersion {sent['data']['filledFormVersion']!r}, "
        f"got {stored_data.get('filledFormVersion')!r}"
    )

    # The GET and the POST response agree on the record.
    assert stored.get("formId") == body.get("formId"), (
        f"GET formId {stored.get('formId')!r} differs from the POST response's {body.get('formId')!r}"
    )
    assert stored_data.get("filledValues") == (body.get("data") or {}).get("filledValues"), (
        f"GET filledValues {stored_data.get('filledValues')} differ from the POST response's "
        f"{(body.get('data') or {}).get('filledValues')}"
    )
