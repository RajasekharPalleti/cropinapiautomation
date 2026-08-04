"""CLI helper: python -m intake.validate_from_file <path_to_spec.json>

Validates a proposed API-onboarding spec (module/endpoint/method/test_type/
payload/expected_status — one object, or {"items": [...]} / a bare list for
several scenarios at once) against ApiIntakeSpec/ApiIntakeBatch *before* any
service, test data, or test code gets written. Exits non-zero with the exact
validation errors if the input is incomplete or malformed, so nothing gets
scaffolded from a bad spec.
"""
import json
import sys

from pydantic import ValidationError

from intake.spec_schema import ApiIntakeBatch, ApiIntakeSpec


def _print_errors(exc: ValidationError) -> None:
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        print(f"  - {loc}: {err['msg']}")


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m intake.validate_from_file <path_to_spec.json>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        raw = json.load(f)

    raw_items = raw["items"] if isinstance(raw, dict) and "items" in raw else raw
    is_batch = isinstance(raw_items, list)

    try:
        if is_batch:
            result = ApiIntakeBatch(items=raw_items)
            items = result.items
        else:
            items = [ApiIntakeSpec(**raw_items)]
    except ValidationError as exc:
        print("Intake spec is INVALID — fix these before it can be scaffolded:\n")
        _print_errors(exc)
        sys.exit(1)

    print(f"Intake spec is VALID ({len(items)} scenario(s)):\n")
    for item in items:
        print(json.dumps(item.model_dump(), indent=2))


if __name__ == "__main__":
    main()
