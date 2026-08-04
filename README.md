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
│   │   └── project_service.py      # Skeleton — set resource_path once the Project API spec is provided
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
│   └── project/
│
├── test_data/
│   ├── qa.json                     # { "login": {...}, "farmer": {}, "asset": {}, "plantype": {}, "crop_variety": {}, "project": {} }
│   ├── uat.json                    # Same shape as qa.json, UAT values
│   ├── prod.json                   # Same shape as qa.json, Prod values
│   └── schemas/                    # JSON Schema files used by assert_json_schema
│       └── token_response.json
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

# Only sanity / smoke / regression tests
pytest -m sanity
pytest -m smoke
pytest -m regression

# Just the auth module, against UAT
pytest tests/auth -v --env=uat

# Only the farmer module once it has tests
pytest -m farmer

# Combine module + test type, e.g. farmer smoke tests only
pytest -m "farmer and smoke"

# Parallel run
pytest -n 4

# HTML report is written to reports/report_<env>.html automatically, e.g.
# reports/report_qa.html, reports/report_uat.html, reports/report_prod.html —
# one file per environment so a UAT run never clobbers a QA report. Each report's
# "Environment" metadata row and title reflect the env it was run against.
```

Markers available (defined in `pyproject.toml`): `sanity`, `smoke`, `regression`, `auth`, `negative`, `farmer`, `asset`, `plantype`, `crop_variety`, `project`. Every test carries exactly one module marker plus one test-type marker (`sanity`/`smoke`/`regression`), and `negative` on top of that where it applies — so `pytest -m "farmer and regression"` or `pytest -m "asset and negative"` always work.

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

Once it validates, the same four steps apply every time:

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

That's it — send the API + payload + test type; if anything required is missing or inconsistent, you'll get asked for it instead of the agent guessing, then these four pieces get filled in.

## 7. Conventions

- Tests never call `requests` directly — always go through a `Service`.
- All request/response payloads are typed with pydantic models in `src/models/`.
- Test data lives in `test_data/<env>.json` (one file per environment), organized by module section (`login`, `farmer`, `asset`, `plantype`, `crop_variety`, `project`, ...). Load it via `load_test_data("<module>", "<name>")` from `src/utils/test_data_loader.py` — the active `--env`/`ENV` is resolved automatically, never hardcode a filename or environment in a test.
- Secrets live only in `.env` (gitignored) — never hardcoded or committed.
- Format/lint with `black` and `ruff`; both are configured in `pyproject.toml`.
- Don't scaffold tests/services for APIs without a confirmed real spec — build only what's been verified against the actual endpoint.

## 8. CI (GitHub Actions)

`.github/workflows/api-tests.yml` runs the suite on demand — **manual trigger only** (`workflow_dispatch`), by design: every create/update test writes a real record to whichever environment it targets, so nothing runs automatically on push. The workflow file's own comments show exactly how to add a schedule or push trigger later if you want one.

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

GitHub → **Actions** tab → **"API Test Suite"** → **"Run workflow"** button → pick an environment (qa/uat/prod) and optionally a marker expression (e.g. `smoke`, `sanity`, `regression`, `farmer and smoke`) to run a subset → **Run workflow**. The HTML report (`reports/report_<env>.html`) is uploaded as a build artifact on every run, pass or fail — find it at the bottom of that run's summary page under "Artifacts".

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
