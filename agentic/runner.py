"""Dynamic execution entry point: feed it a raw dict {method, url, headers, body, ...}
and it authenticates (once, cached), builds the request, executes it, and returns a
structured result. This is what an agent/CLI/script calls instead of hand-writing a
pytest test for one-off or exploratory API calls.

Usage:
    from agentic.runner import AgenticRunner

    runner = AgenticRunner()
    result = runner.run({
        "method": "GET",
        "url": "/some/api/path",
        "expect_status": 200,
    })
    print(result.status, result.body)
    runner.close()
"""
import time

import requests

from agentic.spec_schema import AgenticRequestSpec, AgenticResult
from src.config.settings import get_settings
from src.core.auth_manager import AuthManager
from src.core.response_wrapper import ApiResponse
from src.core.session_context import SessionContext
from src.utils.logger import get_logger
from src.utils.test_data_loader import load_test_data

logger = get_logger(__name__)


class AgenticRunner:
    def __init__(self, auto_login: bool = True, token_request: dict | None = None):
        self._settings = get_settings()
        self._http = requests.Session()
        self._http.headers.update(self._settings.default_headers)
        self._session = SessionContext()
        self._auth_manager = AuthManager(self._http, self._session)
        if auto_login:
            self._auth_manager.generate_token(token_request or load_test_data("login", "valid"))

    def run(self, raw_spec: dict) -> AgenticResult:
        spec = AgenticRequestSpec(**raw_spec)

        headers = {**self._settings.default_headers, **spec.headers}
        if spec.use_auth:
            headers.update(self._session.auth_headers())

        url = spec.url if spec.url.startswith("http") else f"{self._settings.base_url}{spec.url}"

        start = time.perf_counter()
        raw = self._http.request(
            spec.method,
            url,
            json=spec.body,
            params=spec.params,
            headers=headers,
            timeout=self._settings.timeout_ms / 1000,
        )
        response = ApiResponse(raw)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info("[agentic] %s %s -> %s (%sms)", spec.method, url, response.status, duration_ms)

        try:
            body = response.json()
        except Exception:
            body = response.text()

        if spec.expect_status is not None and response.status != spec.expect_status:
            raise AssertionError(
                f"Expected status {spec.expect_status}, got {response.status}. Body: {body}"
            )

        return AgenticResult(
            status=response.status,
            ok=response.ok,
            duration_ms=duration_ms,
            headers=dict(response.headers),
            body=body,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "AgenticRunner":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
