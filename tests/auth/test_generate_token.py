import pytest

from src.core.response_validator import assert_json_schema, assert_status
from src.utils.hard_assert import hard_assert
from src.utils.schema_validator import load_schema
from src.utils.test_data_loader import load_test_data


@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
@pytest.mark.auth
def test_generate_token_success(auth_service):
    """Happy-flow login. Every other test depends on this working, so a
    failure here aborts the whole run instead of just failing this test."""
    payload = load_test_data("login", "valid")

    response = auth_service.request_token(payload)

    try:
        assert_status(response, 200)
        assert_json_schema(response, load_schema("token_response.json"))
    except AssertionError as exc:
        hard_assert(False, f"Login happy-flow failed: {exc}")


@pytest.mark.sanity
@pytest.mark.smoke
@pytest.mark.regression
@pytest.mark.auth
def test_generate_token_stores_tokens_on_session(auth_service, session_context):
    payload = load_test_data("login", "valid")

    try:
        auth_service.generate_token(payload)
    except Exception as exc:
        hard_assert(False, f"Login happy-flow failed: {exc}")

    hard_assert(bool(session_context.access_token), "Expected an access token to be stored")
    hard_assert(bool(session_context.refresh_token), "Expected a refresh token to be stored")


@pytest.mark.regression
@pytest.mark.negative
@pytest.mark.auth
def test_generate_token_fails_with_invalid_credentials(auth_service):
    payload = load_test_data("login", "invalid_credentials")

    response = auth_service.request_token(payload)

    assert_status(response, 401)


@pytest.mark.regression
@pytest.mark.negative
@pytest.mark.auth
def test_generate_token_fails_with_invalid_tenant_code(auth_service):
    payload = load_test_data("login", "invalid_tenant")

    response = auth_service.request_token(payload)

    assert response.status in (400, 404), (
        f"Expected 400/404 for an unknown tenant realm, got {response.status}"
    )


@pytest.mark.regression
@pytest.mark.negative
@pytest.mark.auth
def test_generate_token_fails_with_invalid_client_secret(auth_service):
    payload = load_test_data("login", "invalid_client_secret")

    response = auth_service.request_token(payload)

    assert_status(response, 400)


@pytest.mark.regression
@pytest.mark.negative
@pytest.mark.auth
def test_generate_token_fails_when_grant_type_missing(auth_service):
    payload = load_test_data("login", "missing_grant_type")

    response = auth_service.request_token(payload)

    assert_status(response, 400)
