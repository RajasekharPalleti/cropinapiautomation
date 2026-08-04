# Cropin API Automation — agent instructions

This is an API test automation framework (Python + pytest + `requests`) for Cropin's platform, covering qa/uat/prod. See [README.md](README.md) for full architecture.

## Intake gate — validate before scaffolding

When the user hands over a new API to wire into the framework (endpoint, method, payload, test type), **do not write any service/test-data/model/test code until the input validates against `intake/spec_schema.py::ApiIntakeSpec`** (or `ApiIntakeBatch` for several scenarios at once).

Required per scenario: `module` (one of `login`/`farmer`/`asset`/`plantype`/`crop_variety`/`project`), `scenario_name`, `endpoint` (relative path starting with `/`), `method`, `test_type` (`sanity`/`smoke`/`regression`), `expected_status`, and `payload` (non-empty for POST/PUT/PATCH). `negative: true` requires `expected_status >= 400`.

Steps:
1. Build the `ApiIntakeSpec`/`ApiIntakeBatch` mentally (or actually run `python -m intake.validate_from_file <file>` if the user gave you a JSON file) from what was provided.
2. If anything required is missing or inconsistent (e.g. a negative case with a 200 expected status, a POST with no payload, an unknown module name), **stop and ask the user for exactly what's missing** — don't guess a payload, don't invent an endpoint, don't assume a status code.
3. Only once every scenario validates, proceed with the four scaffolding steps in README section 6: service `resource_path` → `test_data/<env>.json` entry → optional Pydantic model → test function tagged with the module marker + the given test type (+ `negative` if applicable).

This mirrors the existing `agentic/spec_schema.py` pattern already used for the dynamic runner — same idea, applied to onboarding real API modules instead of one-off dynamic calls.

## Hard rule (pre-existing, keep honoring it)

Don't scaffold services/tests for APIs without a confirmed real spec from the user — a prior farm-management module was scaffolded speculatively and had to be deleted for exactly this reason. The empty `resource_path = ""` skeletons in `src/services/` and empty `test_data/<env>.json` module sections are the "ready" state; they only get filled in once real, validated input arrives.
