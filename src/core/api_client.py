"""Thin wrapper over requests.Session.

Every request funnels through here so logging, header injection, and timing
are handled in exactly one place instead of being duplicated per test/service.
"""
import time
from typing import Any

import requests

from src.config.settings import get_settings
from src.core.response_wrapper import ApiResponse
from src.core.session_context import SessionContext
from src.utils.logger import get_logger
from src.utils.test_data_loader import load_test_data

logger = get_logger(__name__)


class ApiClient:
    def __init__(self, http_session: requests.Session, session: SessionContext):
        self._http = http_session
        self._session = session
        self._settings = get_settings()
        # Pacing between API calls — per-environment, from test data (not
        # hardcoded), so qa/uat/prod can each throttle at a different rate.
        self._call_interval_seconds = load_test_data("settings", "api_call_interval")["seconds"]
        # Every call's full detail (url/payload/response), read by
        # tests/conftest.py's pytest_runtest_makereport to attach a JSON
        # extra per test in the HTML report. Never includes headers (avoids
        # leaking the bearer token into a report that gets emailed).
        self.call_log: list[dict] = []

    def _merged_headers(self, extra_headers: dict | None) -> dict:
        headers = {**self._settings.default_headers, **self._session.auth_headers()}
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        json: dict | None = None,
        data: Any = None,
        files: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
        expect_status: int | None = None,
    ) -> ApiResponse:
        url = endpoint if endpoint.startswith("http") else f"{self._settings.base_url}{endpoint}"
        merged_headers = self._merged_headers(headers)
        if files is not None:
            # Let requests compute multipart/form-data's Content-Type (with the
            # boundary) itself. Must be set to None, not just popped/absent:
            # the shared http_session carries its own persistent default
            # Content-Type header (set once in the request_context fixture),
            # and requests' header-merging re-applies that session-level
            # value whenever the per-request dict doesn't override it. Only
            # an explicit None is treated as "unset this", removing it from
            # both the per-request headers and the inherited session default.
            merged_headers["Content-Type"] = None

        start = time.perf_counter()
        raw = self._http.request(
            method.upper(),
            url,
            json=json,
            data=data,
            files=files,
            params=params,
            headers=merged_headers,
            timeout=self._settings.timeout_ms / 1000,
        )
        response = ApiResponse(raw)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "%s %s -> %s (%sms)", method.upper(), url, response.status, duration_ms
        )

        self.call_log.append(
            {
                "method": method.upper(),
                "url": url,
                "request_payload": self._safe_request_payload(json, data, files),
                "request_params": params,
                "response_status": response.status,
                "response_body": self._safe_response_body(response),
                "duration_ms": duration_ms,
            }
        )

        if self._call_interval_seconds:
            time.sleep(self._call_interval_seconds)

        if expect_status is not None and response.status != expect_status:
            raise AssertionError(
                f"Expected status {expect_status} but got {response.status} for "
                f"{method.upper()} {url}. Body: {self._safe_body(response)}"
            )
        return response

    def get(self, endpoint: str, **kwargs: Any) -> ApiResponse:
        return self.request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs: Any) -> ApiResponse:
        return self.request("POST", endpoint, **kwargs)

    def put(self, endpoint: str, **kwargs: Any) -> ApiResponse:
        return self.request("PUT", endpoint, **kwargs)

    def patch(self, endpoint: str, **kwargs: Any) -> ApiResponse:
        return self.request("PATCH", endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs: Any) -> ApiResponse:
        return self.request("DELETE", endpoint, **kwargs)

    @staticmethod
    def _safe_body(response: ApiResponse) -> str:
        try:
            return response.text()
        except Exception:
            return "<unreadable body>"

    @staticmethod
    def _safe_request_payload(json: dict | None, data: Any, files: dict | None) -> Any:
        """For the report's per-test JSON extra. `files` (multipart) holds
        the actual JSON body inside a ("blob", <json-string>, ...) tuple —
        decoded back to a dict so the report shows real content instead of
        an opaque tuple; falls back to a plain marker if that shape isn't
        met."""
        if files is not None:
            dto = files.get("dto")
            if isinstance(dto, tuple) and len(dto) >= 2:
                try:
                    import json as json_lib

                    return json_lib.loads(dto[1])
                except Exception:
                    pass
            return "<multipart/form-data>"
        if json is not None:
            return json
        if data is not None:
            return data
        return None

    @staticmethod
    def _safe_response_body(response: ApiResponse) -> Any:
        try:
            return response.json()
        except Exception:
            return ApiClient._safe_body(response)
