"""Owns the login flow. Every other service reads the token from SessionContext
instead of re-implementing login, so auth changes happen in exactly one place.
"""
import time

import requests

from src.config.settings import get_settings
from src.core.response_wrapper import ApiResponse
from src.core.session_context import SessionContext
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AuthManager:
    def __init__(self, http_session: requests.Session, session: SessionContext):
        self._http = http_session
        self._session = session
        self._settings = get_settings()

    def request_token(self, token_request: dict) -> ApiResponse:
        """Calls the Keycloak password-grant token endpoint for the given
        tenant_code and returns the raw response (no status assertions here,
        so negative-path tests can inspect status/body themselves).
        `token_request` supplies the form body — tenant_code, grant_type,
        client_id, client_secret, and optionally username/password for
        negative-path tests — see test_data/<env>.json -> "login" section.
        """
        data = dict(token_request)
        tenant_code = data.pop("tenant_code", None)
        if not tenant_code:
            raise ValueError("token_request must include 'tenant_code'")

        data.setdefault("username", self._settings.username)
        data.setdefault("password", self._settings.password)

        url = f"{self._settings.sso_base_url}/auth/realms/{tenant_code}/protocol/openid-connect/token"
        start = time.perf_counter()
        raw = self._http.post(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self._settings.timeout_ms / 1000,
        )
        response = ApiResponse(raw)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "POST %s (tenant=%s, grant_type=%s) -> %s (%sms)",
            url,
            tenant_code,
            data.get("grant_type"),
            response.status,
            duration_ms,
        )
        if not response.ok:
            logger.warning(
                "Non-200 response for %s -> %s: %s", url, response.status, response.text()
            )
        return response

    def generate_token(self, token_request: dict) -> SessionContext:
        """Requests a token and, on success, stores it on the SessionContext so
        every other service picks it up automatically for Authorization headers."""
        response = self.request_token(token_request)
        if not response.ok:
            raise RuntimeError(
                f"Token generation failed with status {response.status}: {response.text()}"
            )

        body = response.json()
        access_token = body.get("access_token")
        if not access_token:
            raise RuntimeError(f"Token response did not contain an access_token: {body}")

        self._session.set_tokens(
            access_token=access_token,
            refresh_token=body.get("refresh_token"),
        )
        self._session.tenant_id = token_request.get("tenant_code")
        logger.info("Generated token for tenant '%s'", self._session.tenant_id)
        return self._session
