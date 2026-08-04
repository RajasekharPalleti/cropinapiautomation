"""Normalizes a requests.Response to the stable interface the rest of the
framework already depends on (.status, .ok, .headers, .json(), .text()) — so
the underlying HTTP library can change without touching response_validator.py,
services, or tests.
"""
from typing import Any

import requests


class ApiResponse:
    def __init__(self, raw: requests.Response):
        self._raw = raw

    @property
    def status(self) -> int:
        return self._raw.status_code

    @property
    def ok(self) -> bool:
        return self._raw.ok

    @property
    def headers(self) -> dict:
        return dict(self._raw.headers)

    def json(self) -> Any:
        return self._raw.json()

    def text(self) -> str:
        return self._raw.text
