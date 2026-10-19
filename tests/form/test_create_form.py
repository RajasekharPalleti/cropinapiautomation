import pytest

from src.core.response_validator import assert_status
from tests.form.form_asserts import assert_form_matches


@pytest.mark.form
@pytest.mark.sanity
@pytest.mark.regression
def test_create_form_success(created_form, stored_form, form_client_id):
    """created_form performs the one form create() call for the whole run
    (shared with the update and fill tests) and stored_form the one fresh GET
    of it — taken before the update, so this test sees the form as created.
    This test asserts on what the create returned, then on the GET: the create
    echo alone isn't proof the form was stored.

    The create status wasn't given with the spec (JHipster creates normally
    return 201), so 200 and 201 are both accepted — tighten to the code the
    first real run shows.

    clientId: the create body carries the run's form_client_id (one uuid4 per
    run, shared with the update and the fill — a deliberate, user-requested
    addition, the captured create body had none) and both the create response
    and the GET must show the same value.
    """
    response = created_form["response"]
    sent = created_form["payload"]
    assert response.status in (200, 201), (
        f"Expected status 200 or 201, got {response.status}. Body: {response.text()}"
    )

    created = response.json()
    assert isinstance(created.get("id"), int), (
        f"Expected a numeric form id in the response, got {created.get('id')!r}"
    )
    assert_form_matches(created, sent, "create response")
    assert sent.get("clientId") == form_client_id, (
        f"The create body should carry the run's clientId {form_client_id}, got {sent.get('clientId')!r}"
    )
    assert created.get("clientId") == form_client_id, (
        f"create response: expected clientId {form_client_id}, got {created.get('clientId')!r}"
    )

    assert stored_form is not None, "The form GET was not made — the create call returned no id"
    assert_status(stored_form, 200)
    stored = stored_form.json()
    assert stored.get("id") == created["id"], f"Expected GET id {created['id']}, got {stored.get('id')!r}"
    assert_form_matches(stored, sent, "GET")
    assert stored.get("clientId") == form_client_id, (
        f"GET: expected clientId {form_client_id}, got {stored.get('clientId')!r}"
    )
    assert stored.get("formTypeName") == sent["formTypeName"], (
        f"GET: expected formTypeName {sent['formTypeName']!r}, got {stored.get('formTypeName')!r}"
    )
