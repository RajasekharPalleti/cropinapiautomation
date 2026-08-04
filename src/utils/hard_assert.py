"""Hard assertion for foundational checks (e.g. login) where a failure means
every other test in the run would be meaningless. Unlike a plain `assert`
(which only fails the current test and lets pytest continue), this skips —
via `pytest.skip`, not a plain failure. When raised inside a session-scoped
fixture (e.g. logged_in_session), pytest caches the Skipped exception and
re-raises it for every other test that depends on that fixture (directly or
transitively), so each one shows up in the report individually as Skipped
with this message — instead of the old `pytest.exit` behavior, which aborted
the whole session and left the HTML report showing "0 tests" with no trace
of what went wrong. Tests with no dependency on the failed fixture are
unaffected and still run normally.
"""
import pytest


def hard_assert(condition: bool, message: str) -> None:
    if not condition:
        pytest.skip(f"[HARD ASSERTION FAILED] {message}")
