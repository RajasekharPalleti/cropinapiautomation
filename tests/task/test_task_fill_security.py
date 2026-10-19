"""Task fill — security scenarios (TC_TF_501, 502, 504)."""
import html

import pytest

from src.utils.task_fill_assertions import is_2xx
from src.utils.task_fill_payload import TaskFillPayload, get_path

pytestmark = [pytest.mark.task, pytest.mark.task_fill, pytest.mark.regression, pytest.mark.security]


def test_no_authorization_header(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_501 — no Authorization header at all."""
    payload = TaskFillPayload.base(negative_target.body, fill_ctx)
    attempt(payload, fill_expectations["TC_TF_501"], "TC_TF_501", headers={"Authorization": None})
    assert_still_open(negative_target.id)


def test_invalid_token(negative_target, fill_ctx, attempt, assert_still_open, fill_expectations):
    """TC_TF_502 — 'Bearer invalid'."""
    payload = TaskFillPayload.base(negative_target.body, fill_ctx)
    attempt(payload, fill_expectations["TC_TF_502"], "TC_TF_502", headers={"Authorization": "Bearer invalid"})
    assert_still_open(negative_target.id)


def test_script_injection_in_text_attribute(task_service, fresh_task, fill_ctx, attempt, fill_expectations):
    """TC_TF_504 — a script tag in a text attribute is rejected, or stored as
    plain text (verbatim, or HTML-escaped on read) — never anything else."""
    script = "<script>alert(1)</script>"
    payload = TaskFillPayload.base(fresh_task.body, fill_ctx).custom_attribute("text", script)
    response = attempt(payload, fill_expectations["TC_TF_504"], "TC_TF_504")
    if is_2xx(response):
        after = task_service.get_task(fresh_task.id).json()
        stored = (get_path(after, "data.customAttributesEntered") or {}).get(fill_ctx.attr_names["text"])
        assert stored in (script, html.escape(script)), f"Script value was stored as something unexpected: {stored!r}"
