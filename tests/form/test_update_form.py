import pytest

from src.core.response_validator import assert_status
from tests.form.form_asserts import assert_form_matches, parse_instant


@pytest.mark.form
@pytest.mark.sanity
@pytest.mark.regression
def test_update_form_success(stored_form, updated_form, stored_updated_form, created_form_id, form_client_id):
    """updated_form performs the one PUT for the whole run: the form's create
    response with only the name changed. stored_updated_form is the one fresh
    GET taken after it. This test asserts on the PUT response (new name, same
    id, everything else unchanged), then on the GET — the PUT echo alone isn't
    proof the new name was stored.

    The GET's formTypeName guards against the create response's null
    formTypeName (sent back unchanged in the PUT body) overwriting the stored
    "Farmer". companyId is deliberately not asserted: the PUT response reports
    it null while the GET shows the real value.

    clientId: the PUT body is the create response, so it must still carry the
    run's form_client_id, and the PUT response and the GET after must show it
    unchanged.

    lastModifiedDate is the server's current timestamp: on the GET after the
    update it must be strictly later (parsed instants, not strings) than on the
    GET taken before the update (stored_form; the create response's value is
    the fallback only if that GET had none). It is NOT asserted on the PUT
    response — the captured PUT response echoed the sent (old) value, only the
    GET shows the new stamp.
    """
    response = updated_form["response"]
    sent = updated_form["payload"]
    created = updated_form["created_payload"]
    assert_status(response, 200)

    # The form as it should now be: what was created, under the new name.
    expected = {**created, "name": sent["name"]}
    assert sent["name"] != created["name"], f"The update did not change the name: {sent['name']!r}"

    body = response.json()
    assert body.get("id") == created_form_id, f"Expected id {created_form_id}, got {body.get('id')!r}"
    assert_form_matches(body, expected, "update response")
    assert sent.get("clientId") == form_client_id, (
        f"The update body (the create response) should still carry the run's clientId {form_client_id}, "
        f"got {sent.get('clientId')!r}"
    )
    assert body.get("clientId") == form_client_id, (
        f"update response: expected clientId {form_client_id} unchanged, got {body.get('clientId')!r}"
    )

    assert stored_updated_form is not None, "The form GET after the update was not made"
    assert_status(stored_updated_form, 200)
    stored = stored_updated_form.json()
    assert stored.get("id") == created_form_id, f"GET: expected id {created_form_id}, got {stored.get('id')!r}"
    assert_form_matches(stored, expected, "GET after update")
    assert stored.get("clientId") == form_client_id, (
        f"GET after update: expected clientId {form_client_id} unchanged, got {stored.get('clientId')!r}"
    )

    # lastModifiedDate advanced: the pre-update GET is the "before"; the create
    # response's value (carried in the PUT body) only if that GET had none.
    before_value = None
    if stored_form is not None and stored_form.status == 200:
        before_value = stored_form.json().get("lastModifiedDate")
    before_source = "GET before the update"
    if parse_instant(before_value) is None:
        before_value = sent.get("lastModifiedDate")
        before_source = "create response (the pre-update GET had no usable lastModifiedDate)"
    before, after = parse_instant(before_value), parse_instant(stored.get("lastModifiedDate"))
    assert before is not None, f"No usable lastModifiedDate before the update, got {before_value!r}"
    assert after is not None, (
        f"GET after update: expected a lastModifiedDate, got {stored.get('lastModifiedDate')!r}"
    )
    assert after > before, (
        f"GET after update: expected lastModifiedDate later than {before_value!r} ({before_source}), "
        f"got {stored.get('lastModifiedDate')!r}"
    )
    assert stored.get("formTypeName") == created["formTypeName"], (
        f"GET after update: expected formTypeName {created['formTypeName']!r}, "
        f"got {stored.get('formTypeName')!r}"
    )
