"""Per-call uniqueness helpers.

Every create scenario in this suite uses fixed example data (names, mobile
numbers, etc.) from test_data — fine once, but a real backend that enforces
uniqueness rejects any second identical value. That includes not just a
second pytest *run*, but a second entity created within the *same* run:
e.g. Asset's created_farmer_id fixture creates its own farmer, and Farmer's
own create test creates another — both need to end up distinct. So every
call gets a fresh value (a per-process base timestamp + an incrementing
counter), not a value cached and reused for the whole run.
"""
import time

_base = int(time.time())
_counter = 0


def _next_unique_int() -> int:
    global _counter
    _counter += 1
    return _base * 1000 + _counter


def unique_suffix() -> str:
    return str(_next_unique_int())


def make_unique(base_text: str) -> str:
    """Appends a fresh unique suffix to a human-readable text field (names,
    descriptions, etc.) — safe for any free-text value."""
    return f"{base_text} {unique_suffix()}"


def unique_mobile_number() -> str:
    """A syntactically valid 10-digit Indian mobile number, different on
    every call — starts with 9, remaining 9 digits derived from a fresh
    unique value (appending text like make_unique() would break the
    digits-only format a phone number needs)."""
    digits = str(_next_unique_int())[-9:].rjust(9, "0")
    return f"9{digits}"
