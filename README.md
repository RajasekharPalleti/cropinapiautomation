# Cropin API Automation

API test automation framework for Cropin's agritech SaaS platform, built with **Python (`requests`)** and **pytest**. Runs against **qa / uat / prod** (plus `dev`/`stage`), selected with `--env` or the `ENV` var. Currently covers the SSO/Keycloak **auth token generation API** end-to-end; reusable scaffolding (service base class, fixtures, per-env test data sections) is already wired up for **farmer, asset, plantype, crop_variety, project** — real endpoint paths, request/response models, and tests get added to each as their API specs are provided. It also includes an **agentic runner** that lets you execute any API call dynamically by supplying a `{method, url, headers, body}` spec — without hand-writing a test for every one-off request.

---

## 1. Why this structure

The framework is layered so that each concern changes independently:

| Layer | Responsibility | Changes when... |
|---|---|---|
| `src/config` | Environment/base URL/credentials | Target env or secrets change |
| `src/core` | HTTP mechanics, auth, request building, response assertions | Transport/auth protocol changes |
| `src/models` | Pydantic request/response contracts per domain object | API contract changes |
| `src/services` | One class per API resource (currently: Auth) | New endpoint added/changed |
| `src/utils` | Logging, test data loading, schema loading, retries | Cross-cutting helper needs |
| `agentic/` | Dynamic, spec-driven request execution | You want ad-hoc/agent-driven calls |
| `tests/` | Actual pytest test cases, organized by module | New test scenarios |

A test never talks to `requests` directly — it goes through a `Service` (e.g. `AuthService.generate_token(...)`), which goes through `AuthManager`/`ApiClient`, which handles headers, logging, and status assertions in one place. This keeps tests short and readable, and means an endpoint or auth change only touches one file.

---

## 2. Project structure

```
cropin-api-automation/
├── src/
│   ├── config/
│   │   ├── settings.py            # Loads environments/<env>.yaml + .env, exposes a single Settings object
│   │   └── environments/
│   │       ├── dev.yaml
│   │       ├── qa.yaml
│   │       ├── uat.yaml
│   │       ├── prod.yaml
│   │       └── stage.yaml
│   │
│   ├── core/
│   │   ├── api_client.py          # Wraps requests.Session: logging, header injection, status checks
│   │   ├── auth_manager.py        # Owns the SSO/Keycloak token generation flow
│   │   ├── request_builder.py     # Validates a raw dict into a RequestSpec (pydantic)
│   │   ├── response_validator.py  # assert_status / assert_json_schema / assert_field_equals helpers
│   │   ├── response_wrapper.py    # ApiResponse — normalizes requests.Response (.status/.ok/.json()/.text())
│   │   └── session_context.py     # Holds access_token/tenant_id shared across services in a run
│   │
│   ├── models/                    # Pydantic domain models (request + response shapes) — add per module
│   │
│   ├── services/                  # One class per API resource — the layer tests call into
│   │   ├── base_service.py         # Generic create/get_by_id/list/update/delete over ApiClient
│   │   ├── auth_service.py         # Fully wired — login/token generation
│   │   ├── farmer_service.py       # Skeleton — set resource_path once the Farmer API spec is provided
│   │   ├── asset_service.py        # Skeleton — set resource_path once the Asset API spec is provided
│   │   ├── plantype_service.py     # Skeleton — set resource_path once the Plan Type API spec is provided
│   │   ├── crop_variety_service.py # Skeleton — set resource_path once the Crop Variety API spec is provided
│   │   ├── project_service.py      # Skeleton — set resource_path once the Project API spec is provided
│   │   ├── task_service.py         # Task GET + fill PUT (tests/task/); the task list lives on project_service
│   │   └── form_service.py         # Form create/GET/PUT + filled-forms POST (tests/form/)
│   │
│   └── utils/
│       ├── logger.py              # Consistent logging format across the framework
│       ├── test_data_loader.py    # Loads test_data/<env>.json by module + name
│       ├── schema_validator.py    # Loads JSON schema files from test_data/schemas
│       └── retry.py               # @retry decorator for flaky/eventually-consistent endpoints
│
├── agentic/                        # Dynamic, spec-driven request execution (see section 5)
│   ├── spec_schema.py              # Pydantic schema for an incoming {method,url,headers,body} spec
│   ├── runner.py                   # AgenticRunner: generates a token once, executes any spec, returns structured result
│   └── run_from_file.py            # CLI: python -m agentic.run_from_file <spec.json>
│
├── tests/
│   ├── conftest.py                 # Shared fixtures: request_context, session_context, services, --env option
│   ├── auth/
│   │   └── test_generate_token.py
│   ├── farmer/                     # Ready for tests once farmer_service has a real resource_path
│   ├── asset/
│   ├── plantype/
│   ├── crop_variety/
│   ├── task/                       # Task fill: 6 files (positive/negative/boundary/integrity/regression/security) + its own conftest.py
│   ├── form/                       # Form creation, update and fill + two negative cases (one test each; fixtures in tests/conftest.py)
│   └── project/
│
├── test_data/
│   ├── qa.json                     # { "login": {...}, "farmer": {}, "asset": {}, "plantype": {}, "crop_variety": {}, "project": {} }
│   ├── uat.json                    # Same shape as qa.json, UAT values
│   ├── prod.json                   # Same shape as qa.json, Prod values
│   └── schemas/                    # JSON Schema files used by assert_json_schema
│       └── token_response.json
│
├── docs/
│   └── Cropin_API_Test_Scenarios.xlsx  # Test-case catalogue — regenerated, not hand-edited (see section 6)
│
├── scripts/
│   └── build_test_scenarios_xlsx.py    # Regenerates docs/Cropin_API_Test_Scenarios.xlsx from its own ROWS list
│
├── reports/                        # pytest-html output per environment (gitignored)
├── .env.example                    # Template for local secrets — copy to .env
├── pytest.ini / pyproject.toml     # pytest config, markers, black/ruff/mypy config
└── requirements.txt
```

---

## 3. Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure credentials
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux
# then edit .env with real CROPIN_QA_USERNAME / CROPIN_UAT_USERNAME / CROPIN_PROD_USERNAME etc.

# 4. Point at the right environment: qa is the default if nothing is passed.
#    Either pass --env per run (see below) or set ENV=uat/prod/qa in .env.
```

---

## 4. Running tests

```bash
# Full suite (defaults to qa if --env / ENV isn't set)
pytest

# Target a specific environment
pytest --env=qa
pytest --env=uat
pytest --env=prod

# Only sanity / regression tests (smoke is registered in pyproject.toml
# but not currently applied to any test — removed for now, kept easy to
# bring back)
pytest -m sanity
pytest -m regression

# Just the auth module, against UAT
pytest tests/auth -v --env=uat

# Only the farmer module once it has tests
pytest -m farmer

# Combine module + test type, e.g. farmer regression tests only
pytest -m "farmer and regression"

# Parallel run
pytest -n 4

# HTML report is written to reports/report_<env>.html automatically, e.g.
# reports/report_qa.html, reports/report_uat.html, reports/report_prod.html —
# one file per environment so a UAT run never clobbers a QA report. Each report's
# "Environment" metadata row and title reflect the env it was run against.
```

Markers available (defined in `pyproject.toml`): `sanity`, `smoke`, `regression`, `auth`, `negative`, `boundary`, `integrity`, `security`, `farmer`, `asset`, `plantype`, `crop_variety`, `project`, `plan`, `task`, `task_fill`, `form`. Every test carries exactly one module marker plus its test-type marker(s) — currently `sanity` + `regression` together for happy-path tests (that includes the two task-fill draft tests and the three form tests), `regression` alone for negative-path tests (`smoke` is registered but not currently applied to any test — see the note above) — and `negative` on top where it applies, so `pytest -m "farmer and regression"` or `pytest -m "asset and negative"` always work.

### Task fill tests (`tests/task/`)

50 scenarios, all marked `task_fill` (run just these with `pytest -m task_fill`), against `PUT /services/farm/api/tasks` (positive, negative, boundary, data-integrity, regression, security), run after the croppable-area tests and before the teardown. Only the two happy-path draft scenarios — *save as draft* and *complete a task saved as draft* — are `sanity` (plus `regression`); every other one is `regression` only. Things worth knowing:

- **Fill is a `PUT` API only.** The original task-fill spec listed POST, but the fill is `PUT /services/farm/api/tasks` with the task's id in the JSON body (the URL carries no id). POST on that URL creates a *new* task and rejects a body that carries an id (`400 error.idexists`, found on the second prod run).
- **A draft keeps the task open by keeping its status.** The server decides completion from the body's `status` alone: a body with `isSavedAsDraft: true` but `status: "COMPLETE"` still completes the task (seen on prod), so the draft body sets the flag and keeps the task's own open status.
- **Tasks come from the run itself.** They're the open tasks the suite's own plan generated on its own croppable area (`GET .../tasks/croppablearea/{id}`) — session ids only, never an id from test data. A successful fill completes a task, so scenarios draw from that pool; scenarios that all assert on the same fill share one POST (`filled_task`, `draft_then_completed` in `tests/task/conftest.py`).
- **Pool size = number of plan dates.** The plan creates one task per fixed execution date, and `plan.create_valid.fixed_execution_day_offsets` in test data (days from today) sets how many (qa/uat: `0..23`; prod: `0..3` — four tasks, so a prod run leaves little behind; that's enough for the two sanity scenarios). A full task-fill regression uses ~18-19, so on prod run it with `PLAN_TASK_COUNT_OVERRIDE=24` (any run can set it; the GitHub workflow sets it to 24 automatically whenever the markers option is `regression`, and leaves sanity runs on the 4-task plan); with a smaller pool the later scenarios skip with a message saying so.
- **Execution day = today + `task.fill.execution_day_offset`** and must be one of the task's fixed dates, which the relative plan dates guarantee. Sowing/harvest dates and the audited area come from the croppable area; custom attribute names are read off the run's plan type (they carry a per-run unique suffix).
- **Fields the body builder takes from the croppable area and the clock** (confirmed on the first prod run): the area used for the chemical total is the croppable area's `auditedArea`, falling back to `declaredArea` when `auditedArea` is null; `sowingDate` and the harvest date come from the croppable area response (its harvest field is `expectedHarvestDate`) — the same instants, but re-written with a trailing `Z`, because that response writes them as `...+0000` and the fill POST rejects that format with a 400 (`Cannot deserialize ... ZonedDateTime`); and `createdDate` in the body is the current date (ISO-8601 UTC with microseconds), because the plan itself reports `createdDate: null`. TC-TF-304 checks the fill doesn't change what the plan stores.
- **Expected statuses live in test data.** `task.fill_expectations` in `test_data/<env>.json` lists the allowed statuses per scenario (exact codes and/or classes like `4xx`). Scenarios the spec marks *confirm on first run* start as classes — after the first real run, edit them to the codes actually seen, no code change needed.
- **Expected failure:** TC-TF-301 reports an expected failure while the server keeps storing a client-supplied chemical total unvalidated.

### Form tests (`tests/form/`)

Five scenarios (`pytest -m form`), run after the task-fill tests and before the teardown (which deletes the form, see below), on the run's own crop variety and farmer (session ids only). The three happy-path ones — create → update → fill, in that order — are `form` + `sanity` + `regression`; the two negative ones (`test_form_negative.py`, run last) are `form` + `negative` + `regression` only (`pytest -m "form and negative"`):

- **Form creation (TC-FORM-001)** — `POST /services/form/api/forms` (plain JSON). The body is a farmer form (`formTypeId` 2) with three custom attributes (text, drop down with four options, date), linked to the run's crop variety, valid from today for 10 days (`validFrom`/`validTo` are `T00:00:00.000Z` instants computed from `form.create_valid.valid_*_day_offset`), with a unique name per run and the run's **`clientId`** (one uuid4 generated per run in the `form_client_id` fixture — dynamic, never hardcoded — and reused unchanged by the update and the fill; sending it on create is a deliberate, user-requested addition: the captured create body had none, only the create response did, so the first real run shows whether the server keeps ours or replaces it). The test checks the create response (including that `clientId` is the run's), then re-fetches the form with `GET /services/form/api/forms/{id}` to confirm it was stored (the create response reports `formTypeName: null`, the GET says `Farmer`; the GET's `clientId` must be the run's too). The create status wasn't given with the spec, so 200 and 201 are both accepted — tighten it to the code the first real run shows.
- **Form update (TC-FORM-002)** — `PUT /services/form/api/forms` → 200, id in the body (not the URL). The PUT body is the **create response** exactly as returned (id included), with only `name` changed (`form.update_valid.name_suffix`, `" updated"`, appended) — no other field is re-added or normalised, so the create response's `formTypeName: null` goes back as is. The test checks the PUT response (same id, new name, status/form type/variety/validity dates/attributes unchanged, and the run's `clientId` still there — in the body it sent and in the response), then a fresh GET: new name stored, the rest still as created, `clientId` unchanged, `lastModifiedDate` **strictly later** than on the pre-update GET (parsed instants, not strings; it is the server's current timestamp — it is deliberately *not* asserted on the PUT response, which echoes the sent, old value; the create response's value is only a fallback if the pre-update GET had none), and `formTypeName` still `Farmer` (the server derives it from `formTypeId`; this guards against the null overwriting it). `companyId` isn't asserted — the PUT response reports it `null` while the GET shows the company. The create test's own GET is taken before the update (the `updated_form` fixture depends on `stored_form`), so the create test sees the form as created.
- **Form fill (TC-FORM-003)** — `POST /services/form/api/filled-forms` → 201. Fills that form, under its current name (the updated one if the PUT returned 200), for the run's farmer (name read live with a GET, since the farmer-edit test renames it) with a text value, a drop-down option and a date, all from `form.fill_valid`, and the run's shared **`clientId`** (the same uuid4 as the form create and update; the builders generate a fresh one only when none is passed, as the negative tests do). It's a create, so the request carries **no `id`** — the captured sample had one, which is left out here (the first real run confirms; on tasks a create body with an id is rejected). The created form is left `DISABLE`d, as in the captured flow. The test checks the POST response (id, `formId`, form type, filled values, farmer id, flags, non-empty filled names), then reads the filled form back with `GET /services/form/api/filled-forms/{id}` (by the id the POST returned; one fresh GET in the `stored_filled_form` fixture) and cross-checks it: **form id** (`formId` is the created form's id), **form name** (`name` and `formName` both equal the form's current name — the POST response leaves `formName` null, so the GET is where it is checked), **farmer name** (`data.firstName` equals the name that was sent; `filledName` must *contain* it, since the server may compose it) and **farmer id**, plus the saved `filledValues`, `filledFormVersion`, `isDeleted` false and the GET-vs-POST agreement on id/`formId`/`filledValues`. The GET must also show the run's **`clientId`** (asserted on the GET only: the captured sample POST response's `clientId` came from a different call than the sample request, so it isn't proven to be an echo), and the timestamps are compared as parsed instants / UTC days, never as strings (the styles differ — `createdDate` comes back ending `+0000`, not `Z`): `data.filledDate` is the current day that was sent, and the server-stamped `createdDate` and `lastModifiedDate` must be today's UTC date (the day the fill was sent is also accepted, so a UTC-midnight rollover during the run can't fail it). If the POST succeeded but the GET isn't 200 the test fails, it doesn't skip.
- **Blank name rejected (TC-FORM-004)** — `POST /services/form/api/forms` with the normal create body (the run's crop variety) but `"name": ""`. Must be refused with a 4xx (not a server error), and the response must not carry a form id. The real server accepts a blank name (201), which fails this test — and the form it created is still deleted by the teardown: the test registers it for cleanup *before* asserting (`register_created_form` in `tests/conftest.py`), and the cleanup deletes it right after the run's own form (a row `form (TC-FORM-004 blank name)` in the report's Cleanup section, TC-CLEANUP-004).
- **Fill of a form that doesn't exist rejected (TC-FORM-005)** — `POST /services/form/api/filled-forms` with the normal fill body for the run's farmer but `formId` 999999999 (the way task fill's "id does not exist" test does it). Must be refused with a 4xx — or a 500, which is what the real server answers for a form id it can't find, accepted as a refusal on purpose — and the response must not carry a filled-form id. If the server *accepts* either request (2xx) the test fails with a DEFECT message — it would also have created a record.
- **Expected statuses for the two negatives live in test data.** The real error codes weren't captured, so `form.expectations` in `test_data/<env>.json` lists the allowed statuses per scenario (`TC_FORM_004`, `TC_FORM_005`), `TC_FORM_004` allows any `4xx` and `TC_FORM_005` allows any `4xx` plus `500` (change them to exact codes whenever you like, no code change needed). The real server accepts a blank form name (201, so TC-FORM-004 fails until it is fixed) and answers 500 for an unknown form id (accepted by TC-FORM-005). The check is `tests/form/form_asserts.py::assert_rejected`, built on the task-fill status helper.
- **Cleanup: the form is deleted, the filled form is not.** The end-of-run teardown (`cleanup_created_records`) deletes the run's form with `DELETE /services/form/api/forms/bulk?ids=<form id>` (TC-CLEANUP-003, using the inherited `delete_bulk`). The order is: close/remove the croppable area, delete the plan, **delete the form**, delete the crop variety, the asset and the farmer, stop the project's execution, delete the plan type. The form goes before the crop variety because its `varietyId` links it to that variety (a variety still referenced by a form shouldn't be deletable). Unlike the farmer/asset/variety deletes (`{"deletable": N, "nonDeletable": N}`), this one answers `{"nonDeletedIds": [...], "deletedIds": [...]}`, so the step only counts as done when the form's id is in `deletedIds` and `nonDeletedIds` is empty; a non-200, or the id in `nonDeletedIds`, is a failed row in the report's Cleanup section carrying the response body (it doesn't fail the run). If the form was never created this run the step is a skipped row, and nothing is sent when cleanup is switched off (`CLEANUP_OVERRIDE=no` or `settings.cleanup.enabled`). **There is still no delete API for filled forms**, so each run leaves one filled form behind on the environment, and it may keep the farmer from being deleted (that row would report `nonDeletable`) until a delete API for filled forms exists.

---

## 5. The agentic flow

This is the piece built for dynamic/agent-driven use: instead of writing a pytest test for every one-off API call, you hand a plain dict (or JSON file) describing the request, and `AgenticRunner` handles token generation, base-URL resolution, header injection, and status assertions for you.

**Programmatic use:**

```python
from agentic.runner import AgenticRunner

with AgenticRunner() as runner:
    result = runner.run({
        "method": "GET",
        "url": "/some/api/path",
        "expect_status": 200
    })
    print(result.status, result.body)
```

**From a JSON file / CLI:**

```bash
python -m agentic.run_from_file path/to/spec.json
```

**Spec fields** (`agentic/spec_schema.py`):

| Field | Required | Notes |
|---|---|---|
| `method` | yes | GET / POST / PUT / PATCH / DELETE |
| `url` | yes | Absolute URL, or path relative to the active `base_url` |
| `headers` | no | Merged on top of default + auth headers |
| `params` | no | Query string params |
| `body` | no | JSON request body |
| `expect_status` | no | If set, raises `AssertionError` on mismatch |
| `use_auth` | no | Default `true` — attaches the cached session's Bearer token + tenant header |

Because `AgenticRunner` reuses `AuthManager`/`SessionContext` from `src/core`, every dynamically-fired request is authenticated exactly the same way as the pytest suite — there's no separate/duplicated auth path to drift out of sync.

---

## 6. Extending the framework

Modules already have their scaffolding in place — this is what "give me the API and I'll wire it in" looks like:

- **`farmer` / `asset` / `plantype` / `crop_variety` / `project`**: each has a skeleton service in `src/services/<module>_service.py` (subclassing `BaseService` for free `create`/`get_by_id`/`list`/`update`/`delete`), a fixture in `tests/conftest.py` (`farmer_service`, `asset_service`, ...), an empty section in every `test_data/<env>.json`, and an empty `tests/<module>/` folder.
- **New environment**: add `src/config/environments/<env>.yaml` (with `sso_base_url`), a matching `test_data/<env>.json`, add the env name to the `--env` choices in `tests/conftest.py`, and add its credentials to `.env.example`.
- **New reusable assertion**: add it to `src/core/response_validator.py`.

### Intake workflow — adding a real API

**Step 0 — validate first.** Every API you hand over (module, endpoint, method, payload, `expected_status`, and test type — `sanity`/`smoke`/`regression`) must pass `intake/spec_schema.py::ApiIntakeSpec` (or `ApiIntakeBatch` for several scenarios at once) before anything gets scaffolded. This catches missing fields, an unknown module, a POST with no payload, or a negative case paired with a 200 status — instead of guessing. See [CLAUDE.md](CLAUDE.md) for the exact rule the agent follows. To self-check a spec before sending it:

```bash
python -m intake.validate_from_file path/to/spec.json
```

```json
{
  "module": "farmer",
  "scenario_name": "create_valid",
  "endpoint": "/farm/v1/farmers",
  "method": "POST",
  "test_type": "smoke",
  "payload": {"name": "Test Farmer"},
  "expected_status": 201
}
```

Once it validates, the same five steps apply every time:

1. **Service**: set `resource_path` on `src/services/<module>_service.py` (add a non-CRUD method if the call doesn't fit `create`/`get_by_id`/`list`/`update`/`delete`).
2. **Test data**: add the payload as a named scenario under that module's section in `test_data/qa.json` (and `uat.json`/`prod.json` once real per-env values are known), e.g. `"farmer": {"create_valid": {...}, "create_missing_name": {...}}`.
3. **Model** (optional): add a Pydantic response model in `src/models/` if the response shape should be validated structurally, not just by status code.
4. **Test**: add the test function under `tests/<module>/`, loading data with `load_test_data("<module>", "<scenario_name>")`, and mark it with the module marker + the test type you gave me + `negative` if it's a failure-path case:

```python
@pytest.mark.farmer
@pytest.mark.smoke
def test_create_farmer_success(farmer_service):
    payload = load_test_data("farmer", "create_valid")
    response = farmer_service.create(payload)
    assert_status(response, 201)

@pytest.mark.farmer
@pytest.mark.regression
@pytest.mark.negative
def test_create_farmer_missing_name(farmer_service):
    payload = load_test_data("farmer", "create_missing_name")
    response = farmer_service.create(payload)
    assert_status(response, 400)
```

5. **Test-case catalogue**: append a row for the new test to `ROWS` in `scripts/build_test_scenarios_xlsx.py` (Test Case ID `TC-<MODULE>-NNN`, name, test type, what it does, APIs used), then run `python scripts/build_test_scenarios_xlsx.py` to regenerate `docs/Cropin_API_Test_Scenarios.xlsx`. Don't hand-edit the `.xlsx` — the script is the source of truth and a regeneration would overwrite direct edits.

That's it — send the API + payload + test type; if anything required is missing or inconsistent, you'll get asked for it instead of the agent guessing, then these five pieces get filled in.

## 7. Conventions

- Tests never call `requests` directly — always go through a `Service`.
- All request/response payloads are typed with pydantic models in `src/models/`.
- Test data lives in `test_data/<env>.json` (one file per environment), organized by module section (`login`, `farmer`, `asset`, `plantype`, `crop_variety`, `project`, `plan`, `task`, `form`, ...). Load it via `load_test_data("<module>", "<name>")` from `src/utils/test_data_loader.py` — the active `--env`/`ENV` is resolved automatically, never hardcode a filename or environment in a test.
- Secrets live only in `.env` (gitignored) — never hardcoded or committed.
- Format/lint with `black` and `ruff`; both are configured in `pyproject.toml`.
- Don't scaffold tests/services for APIs without a confirmed real spec — build only what's been verified against the actual endpoint.

## 8. CI (GitHub Actions)

`.github/workflows/api-tests.yml` runs the suite via `workflow_dispatch` only — by design, nothing runs automatically on `push`, since every create/update test writes a real record to whichever environment it targets. `workflow_dispatch` can be fired three ways: the Actions tab's "Run workflow" button, `gh workflow run api-tests.yml`, or an external cron pinger hitting the REST API dispatch endpoint on a schedule (see 8.4) — that last one is how the daily automated run works. GitHub's own native `schedule:` trigger was tried first and dropped: see 8.4 for why.

### 8.1 One-time setup — configuring this project in GitHub Actions

1. **Push this repo to GitHub** (if it isn't already) — `git remote add origin <your-repo-url>` then `git push -u origin main`. The workflow file at `.github/workflows/api-tests.yml` is picked up automatically once it's on GitHub; no separate "enable Actions" step is needed for a repo that already has it.
2. **Add the repository secrets** — go to your repo on GitHub → **Settings** tab → **Secrets and variables** (left sidebar) → **Actions** → **New repository secret**. Add each one below individually (name exactly as shown, then paste the value):
   - `CROPIN_QA_USERNAME`, `CROPIN_QA_PASSWORD`, `CROPIN_QA_TENANT_ID`
   - `CROPIN_UAT_USERNAME`, `CROPIN_UAT_PASSWORD`, `CROPIN_UAT_TENANT_ID`
   - `CROPIN_PROD_USERNAME`, `CROPIN_PROD_PASSWORD`, `CROPIN_PROD_TENANT_ID`
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` (see 8.3 below for how to get these — only needed if you want prod runs to email the report from CI)

   Only the block matching whichever environment you pick when triggering a run actually gets used (same `CROPIN_<ENV>_*` lookup as local `.env`, see `src/config/settings.py`) — you don't need all three filled in to use just one environment.
3. **Verify it's wired up** — go to the **Actions** tab on GitHub. You should see "API Test Suite" listed as a workflow on the left. If it's not there yet, confirm `.github/workflows/api-tests.yml` was actually pushed (check the Code tab).

That's the entire one-time setup — no other configuration (branch protection, environments, approvals, etc.) is required for this workflow to run.

### 8.2 Triggering a run

GitHub → **Actions** tab → **"API Test Suite"** → **"Run workflow"** button → pick an environment (qa/uat/prod) and a markers option (`sanity` or `regression` — `smoke` isn't currently offered here, since no test carries that marker right now) → **Run workflow**. The HTML report (`reports/report_<env>.html`) is uploaded as a build artifact on every run, pass or fail — find it at the bottom of that run's summary page under "Artifacts".

**What makes a run pass or fail.** Failed assertions do not fail the GitHub job: they are recorded in the HTML report (and listed in the emailed summary), the cleanup teardown runs regardless, and the job ends green with a notice pointing at the report. A cleanup step that fails — including one that raises, e.g. a network error — is recorded as a failed row in the report's **Cleanup** section and the remaining cleanup steps still run. Only a run that itself breaks fails the job: pytest exit code 2 (interrupted, e.g. a collection error), 3 (internal error), 4 (usage error) or 5 (no tests collected). The step is in `.github/workflows/api-tests.yml`.

### 8.3 Setting up the emailed report (prod only)

After any `--env=prod` run finishes (local or CI), the report is emailed via SMTP if `test_data/prod.json` → `settings.email_report.enabled` is `true`. Recipients are the `settings.email_report.recipients` list in that same file:

```json
"settings": {
  "email_report": {
    "enabled": true,
    "recipients": ["someone@cropin.com", "someone.else@cropin.com"]
  }
}
```

The email body states the result of the run — how many tests ran, passed, failed, errored and were skipped — and, when anything failed, lists each failed test case by name with the first line of why (`format_results_summary` in `src/utils/report_mailer.py`, fed by the outcomes `tests/conftest.py` records as the run goes). The HTML report stays attached for the full detail.

Add/remove addresses there directly, or flip `enabled` to `false` to turn it off — no code change needed either way.

**Getting the SMTP credentials** (using a Gmail/Google Workspace mailbox — swap in your own provider's SMTP host if different):

1. Decide which mailbox will send the report (ideally a shared/team mailbox rather than one person's personal account, but a personal `@cropin.com` account works too).
2. Log into that mailbox at [myaccount.google.com](https://myaccount.google.com).
3. Go to **Security** → under "How you sign in to Google", turn on **2-Step Verification** if it isn't already on (App Passwords only appear once this is enabled).
4. Still under **Security**, open **App Passwords** (or go directly to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)). Name it something identifiable (e.g. "Cropin API Automation") and click **Create**.
5. Copy the 16-character password shown — it's only displayed once.
6. Fill in these five values, either in your local `.env` (for running locally) or as GitHub Actions secrets from 8.1 above (for CI runs) — both use the exact same values:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=<the mailbox's email address>
   SMTP_PASSWORD=<the 16-character app password from step 5>
   SMTP_FROM_EMAIL=<same as SMTP_USERNAME>
   ```

**If "App Passwords" doesn't appear** even with 2-Step Verification on: your Google Workspace admin has likely disabled them organization-wide (common in managed/corporate Workspace accounts). In that case, either ask your admin to enable App Passwords for that specific account (Admin Console → Security → Authentication → App Passwords), ask if there's an internal SMTP relay instead, or fall back to a free-tier transactional email provider (e.g. SendGrid) — those support the same plain-SMTP relay shape, so it's just different values in the five fields above (`SMTP_HOST=smtp.sendgrid.net`, `SMTP_USERNAME=apikey`, `SMTP_PASSWORD=<your API key>`), no code changes needed either way.

A send failure (missing/wrong SMTP config, network issue, etc.) is logged as a warning and never fails the test run itself — see `pytest_unconfigure` in `tests/conftest.py` and `src/utils/report_mailer.py`.

### 8.4 Automating the daily run (external cron)

This workflow originally used GitHub's own `schedule:` trigger (`cron: "5 5 * * 1-6"`, i.e. 10:35 AM IST Monday–Saturday). It was removed: GitHub explicitly documents scheduled workflows as best-effort — they can be delayed during high load, and in some cases **skipped entirely** — and both failure modes showed up in practice (one run fired 47 minutes late, a later day didn't fire at all). There's no fix for this from inside the workflow file; the trigger has to live outside GitHub.

The replacement: an external cron service calls GitHub's REST API to fire `workflow_dispatch` directly, on its own schedule. Any "call this URL on a schedule" service works (cron-job.org is free and needs no account beyond an email); the request is the same regardless of provider:

1. **Create a fine-grained GitHub token** — [github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new) → **Repository access**: "Only select repositories" → this repo → **Permissions** → **Actions**: "Read and write" → **Generate token**. Copy it once; it isn't shown again. (Scoped to just this repo and just Actions — much narrower than a classic PAT.)
2. **Set up the scheduled HTTP call** on your chosen cron service, configured as:
   - **Method**: `POST`
   - **URL**: `https://api.github.com/repos/RajasekharPalleti/cropinapiautomation/actions/workflows/api-tests.yml/dispatches`
   - **Headers**:
     ```
     Accept: application/vnd.github+json
     Authorization: Bearer <the token from step 1>
     X-GitHub-Api-Version: 2022-11-28
     ```
   - **Body**: `{"ref": "main"}` — no `inputs` needed since the daily run just uses whatever the workflow file's current defaults are (currently prod, sanity, cleanup on, all three recipients — see the `markers` default in `.github/workflows/api-tests.yml` if that ever needs to change); pass an `"inputs"` object here too if you want this specific external trigger to always use different values regardless of the workflow's defaults.
   - **Schedule**: `5 5 * * 1-6` (10:35 AM IST / 05:05 UTC, Monday–Saturday) — or whatever cadence you want.
3. **Verify**: after the next scheduled fire time, check GitHub → **Actions** tab — a new run should appear with "Triggered via workflow_dispatch" (there's no "Triggered by" avatar for a token-authenticated dispatch, which is expected).

The token only ever lives inside the external cron service's own dashboard — it's never added as a GitHub Actions secret or checked into this repo.
