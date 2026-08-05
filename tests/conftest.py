import functools
import inspect
import os
from pathlib import Path

import pytest
import requests
from pytest_html import extras

from src.config.settings import get_settings
from src.core.api_client import ApiClient
from src.core.auth_manager import AuthManager
from src.core.session_context import SessionContext
from src.services.asset_service import AssetService
from src.services.auth_service import AuthService
from src.services.crop_variety_service import CropVarietyService
from src.services.farmer_service import FarmerService
from src.services.plan_service import PlanService
from src.services.plantype_service import PlanTypeService
from src.services.project_service import ProjectService
from src.utils.hard_assert import hard_assert
from src.utils.logger import get_logger
from src.utils.test_data_loader import load_test_data

logger = get_logger(__name__)

# Set by the api_client fixture below (one ApiClient for the whole
# session) — read by the hooks below to attach each test's own API calls
# as a JSON extra in the HTML report.
_LAST_API_CLIENT: ApiClient | None = None
_api_call_log_offset = 0

# Many "create"/"call" fixtures (created_farmer, probable_assets_response,
# etc.) are session-scoped and only actually execute ONCE, the first time
# any test requests them — often during an EARLIER test's setup, because
# cleanup_created_records (autouse) forces the whole chain to resolve right
# away. A test that just asserts on the cached result (e.g.
# test_create_project_success(created_project)) would otherwise show no
# API calls at all, since none happened during ITS OWN phase. tracked_fixture
# (below) maps each such fixture name to the call(s) it caused, whenever it
# actually ran, so any test that directly asks for that fixture can still
# show them. (An earlier attempt used the pytest_fixture_setup hook for
# this — it never actually fired here, for reasons that didn't repay
# further digging, so fixtures needing this are wrapped directly instead.)
_CALLS_BY_FIXTURE: dict[str, list[dict]] = {}

# Raw creation responses, stashed as a side effect by the fixtures below
# (created_project, created_farmer, created_asset, created_crop_variety,
# probable_assets_response, self_validate_response) as soon as each one
# actually runs. cleanup_created_records reads this directly instead of
# taking these as fixture parameters — several created_X_id fixtures now
# call pytest.skip() when their creation failed, and skip exceptions are
# cached and re-raised for every dependent, cascading up through anything
# that requests them. cleanup_created_records is autouse, so if it listed
# any skip-raising fixture (or one that transitively depends on one, like
# created_asset needing created_farmer_id for its own payload) as a
# parameter, one failed creation would skip literally every test in the
# run, including the create test itself (which should show its own clear
# Failed, not Skipped). Reading from this plain dict sidesteps pytest's
# fixture graph entirely.
_CREATED_RECORDS: dict = {}


def tracked_fixture(fixture_func):
    """Decorator for a fixture whose body makes ApiClient calls — records
    the calls it causes into _CALLS_BY_FIXTURE, keyed by the fixture's own
    name, the one time its body actually executes. Apply directly above
    @pytest.fixture(...) (i.e. this decorator runs first, closest to the
    function)."""

    @functools.wraps(fixture_func)
    def wrapper(*args, **kwargs):
        if _LAST_API_CLIENT is None:
            return fixture_func(*args, **kwargs)
        before = len(_LAST_API_CLIENT.call_log)
        result = fixture_func(*args, **kwargs)
        after = len(_LAST_API_CLIENT.call_log)
        if after > before:
            _CALLS_BY_FIXTURE[fixture_func.__name__] = _LAST_API_CLIENT.call_log[before:after]
        return result

    return wrapper


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Attaches this test's relevant API calls (URL/payload/response,
    captured by ApiClient.call_log) as a clickable JSON extra in the HTML
    report — on the 'call' phase normally, or on 'setup' if setup itself
    failed (no 'call' phase runs in that case). Two sources, combined:
    1. Calls made directly during this test's own setup/call phases (a
       global read-offset, so each test only gets what's new since the
       last one reported).
    2. Calls already recorded against any fixture THIS TEST FUNCTION
       directly declares as a parameter (see _CALLS_BY_FIXTURE /
       tracked_fixture above) — this is what surfaces a call that
       actually happened earlier, cached, for a test that's purely
       "assert on the shared fixture's result." Uses the function's own
       declared params, not item.fixturenames, since the latter also
       includes autouse fixtures like cleanup_created_records — which
       pulls in EVERY business fixture for EVERY test, and would
       otherwise show the same huge combined list everywhere instead of
       just what each test actually cares about.
    """
    outcome = yield
    report = outcome.get_result()

    should_attach = report.when == "call" or (report.when == "setup" and report.outcome != "passed")
    if not should_attach or _LAST_API_CLIENT is None:
        return

    global _api_call_log_offset
    direct_calls = _LAST_API_CLIENT.call_log[_api_call_log_offset:]
    _api_call_log_offset = len(_LAST_API_CLIENT.call_log)

    fixture_calls = []
    for param_name in inspect.signature(item.function).parameters:
        fixture_calls.extend(_CALLS_BY_FIXTURE.get(param_name, []))

    all_calls = fixture_calls + direct_calls
    if all_calls:
        report_extras = getattr(report, "extras", [])
        report_extras.append(extras.json(all_calls, name=f"API Calls ({len(all_calls)})"))
        report.extras = report_extras


def pytest_addoption(parser):
    parser.addoption(
        "--env",
        action="store",
        default=None,
        choices=["qa", "uat", "prod", "dev", "stage"],
        help="Target environment for this run (qa/uat/prod/dev/stage). "
        "Overrides ENV from .env. Defaults to qa.",
    )


def pytest_configure(config):
    env_opt = config.getoption("--env")
    if env_opt:
        os.environ["ENV"] = env_opt
    active_env = os.getenv("ENV", "qa")

    # One report per environment so a UAT run never overwrites a QA/Prod report.
    config.option.htmlpath = f"reports/report_{active_env}.html"

    # Modern theme layered on top of pytest-html's default style.css —
    # appended after it, so same-specificity selectors here win the cascade.
    theme_path = str(Path(__file__).parent / "report_theme.css")
    if theme_path not in config.option.css:
        config.option.css.append(theme_path)

    if hasattr(config, "_metadata"):
        config._metadata["Environment"] = active_env.upper()


def pytest_html_report_title(report):
    report.title = f"Cropin API Automation Report ({os.getenv('ENV', 'qa').upper()})"


def pytest_unconfigure(config):
    """Emails the generated HTML report — prod only, and only when
    test_data/prod.json -> settings.email_report.enabled is true (so
    recipients/on-off live in test data, not code). Runs whether the suite
    was triggered manually or via CI (both are just `pytest --env=prod`
    underneath). Fires after pytest-html has finished writing the report
    file (pytest_unconfigure runs after pytest_sessionfinish, where
    pytest-html writes it), and never raises — a mail failure is logged,
    not allowed to affect the already-finalized test results."""
    active_env = os.getenv("ENV", "qa")
    if active_env != "prod":
        return

    try:
        email_settings = load_test_data("settings", "email_report", env="prod")
    except KeyError:
        return

    if not email_settings.get("enabled"):
        return

    recipients = email_settings.get("recipients") or []
    report_path = Path(f"reports/report_{active_env}.html")

    try:
        from src.utils.report_mailer import send_report_email

        send_report_email(get_settings(), report_path, recipients)
    except Exception as exc:
        logger.warning("Failed to email report to %s: %s", recipients, exc)


# Populated by cleanup_created_records' teardown (bottom of this file) and
# rendered as a distinct "Cleanup" section below the normal pass/fail rows —
# deleting test data isn't itself a test, so it doesn't get its own
# pass/fail row, but you still want to see what got cleaned up.
_CLEANUP_LOG: list[dict] = []


def _record_cleanup(
    entity_type: str,
    entity_id,
    response=None,
    *,
    status=None,
    success=None,
    note: str | None = None,
) -> None:
    """Pass either `response` (a single ApiResponse — status/success are
    read off it) or explicit `status`/`success` (for multi-step cleanup
    sequences like croppable area's close -> remove -> poll, where there's
    no single response to point at). Leaving all of status/success/response
    unset means this step hasn't been wired in yet (endpoint not provided)
    — rendered as "Not implemented yet" rather than looking like an
    attempted-and-failed delete."""
    if response is not None:
        status = response.status
        success = response.ok
        if not success and note is None:
            note = response.text()
    _CLEANUP_LOG.append(
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "status": status,
            "success": success,
            "note": note,
        }
    )


def _record_bulk_delete(entity_type: str, entity_id, response) -> None:
    """For the farmer/asset/variety bulk-delete endpoints
    (DELETE {resource_path}/bulk?ids=...) — a 200 alone doesn't mean the
    record was actually deleted, the body reports that as
    {"deletable": N, "nonDeletable": N}, so success is judged off the body,
    not just the HTTP status."""
    if response.status != 200:
        _record_cleanup(entity_type, entity_id, status=response.status, success=False, note=response.text())
        return
    body = response.json()
    success = body.get("nonDeletable", 0) == 0 and body.get("deletable", 0) >= 1
    _record_cleanup(
        entity_type, entity_id, status=response.status, success=success,
        note=None if success else f"response: {body}",
    )


_API_CALLS_MODAL_SCRIPT = """
<style>
.api-modal-overlay{display:none;position:fixed;inset:0;background:rgba(15,17,21,0.55);
  z-index:9999;align-items:center;justify-content:center;}
.api-modal-overlay.open{display:flex;}
.api-modal-box{background:#fff;border-radius:12px;max-width:900px;width:90%;max-height:80vh;
  display:flex;flex-direction:column;box-shadow:0 10px 40px rgba(0,0,0,0.35);}
.api-modal-header{padding:14px 20px;border-bottom:1px solid #e5e7eb;display:flex;
  justify-content:space-between;align-items:center;}
.api-modal-header strong{font-size:14px;color:#1f2430;}
.api-modal-close{cursor:pointer;border:none;background:none;font-size:22px;line-height:1;
  color:#6b7280;padding:0 4px;}
.api-modal-close:hover{color:#1f2430;}
.api-modal-body{padding:16px 20px;overflow-y:auto;flex:1;}
.api-modal-body pre{white-space:pre-wrap;word-break:break-word;
  font-family:"Courier New",Courier,monospace;font-size:12px;color:#1f2430;margin:0;}
</style>
<div class="api-modal-overlay" id="api-modal-overlay">
  <div class="api-modal-box">
    <div class="api-modal-header">
      <strong id="api-modal-title">API Calls</strong>
      <button class="api-modal-close" id="api-modal-close" aria-label="Close">&times;</button>
    </div>
    <div class="api-modal-body"><pre id="api-modal-content"></pre></div>
  </div>
</div>
<script>
window.addEventListener('DOMContentLoaded', function () {
  var overlay = document.getElementById('api-modal-overlay');
  var titleEl = document.getElementById('api-modal-title');
  var contentEl = document.getElementById('api-modal-content');

  function closeModal() { overlay.classList.remove('open'); }
  document.getElementById('api-modal-close').addEventListener('click', closeModal);
  overlay.addEventListener('click', function (e) { if (e.target === overlay) closeModal(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModal(); });

  function decodeDataUri(href) {
    var match = href.match(/^data:[^;]+;charset=([^;]+);base64,([\\s\\S]*)$/);
    if (!match) return null;
    try {
      var binary = atob(match[2]);
      var bytes = new Uint8Array(binary.length);
      for (var i = 0; i < binary.length; i++) { bytes[i] = binary.charCodeAt(i); }
      return new TextDecoder(match[1] || 'utf-8').decode(bytes);
    } catch (e) { return null; }
  }

  // Self-contained pytest-html reports render JSON extras as
  // <a class="col-links__extra json" href="data:...;base64,...">, which
  // browsers (Chrome in particular) silently block from opening via
  // target="_blank" — the click just does nothing. Intercept it here and
  // show the decoded content in this modal instead. Event delegation
  // (rather than binding to each link directly) since pytest-html renders
  // test rows client-side, after this script already ran.
  document.body.addEventListener('click', function (e) {
    var link = e.target.closest('a.col-links__extra.json');
    if (!link) return;
    e.preventDefault();
    var decoded = decodeDataUri(link.getAttribute('href'));
    if (decoded === null) {
      window.open(link.getAttribute('href'), '_blank');
      return;
    }
    try {
      decoded = JSON.stringify(JSON.parse(decoded), null, 2);
    } catch (e) { /* not JSON-parseable, show as-is */ }
    titleEl.textContent = link.textContent || 'API Calls';
    contentEl.textContent = decoded;
    overlay.classList.add('open');
  });
});
</script>
"""


def pytest_html_results_summary(prefix, summary, postfix):
    """Adds the API-calls modal (see _API_CALLS_MODAL_SCRIPT) to every
    report, then — if this run produced any — renders _CLEANUP_LOG as its
    own "Cleanup — Deleted Test Records" section, separate from the test
    result rows."""
    postfix.append(_API_CALLS_MODAL_SCRIPT)

    if not _CLEANUP_LOG:
        return
    rows = []
    for c in _CLEANUP_LOG:
        if c["success"] is None:
            result = c["note"] or "Not implemented yet"
        elif c["success"]:
            result = "Deleted / stopped"
        else:
            result = f"Failed: {c['note']}" if c["note"] else "Failed"
        rows.append(
            f"<tr><td>{c['entity_type']}</td><td>{c['entity_id']}</td>"
            f"<td>{c['status'] if c['status'] is not None else '-'}</td>"
            f"<td>{result}</td></tr>"
        )
    # pytest-html only exposes a hook for the summary area, which renders
    # ABOVE the results table — there's no hook for content after it. To
    # actually place this section at the bottom of the page (below the
    # results table), it's wrapped in a div and moved there via a script
    # that runs once the whole page (results table included) has loaded.
    postfix.extend(
        [
            "<div id='cleanup-section' style='margin-top:30px;padding-top:20px;border-top:2px solid #e6e6e6;'>",
            # Matches #results-table's own look (border/padding/font-size from
            # style.css) so this reads as part of the same report, not a
            # bare unstyled table bolted onto the end of the page.
            "<style>"
            "#cleanup-table{border:1px solid #e6e6e6;color:#999;font-size:12px;width:100%;"
            "border-collapse:collapse;}"
            "#cleanup-table th,#cleanup-table td{padding:5px;border:1px solid #e6e6e6;text-align:left;}"
            "#cleanup-table th{font-weight:bold;color:black;background-color:#f6f6f6;}"
            "#cleanup-table tr:nth-child(even){background-color:#f6f6f6;}"
            "</style>",
            "<h2>Cleanup &mdash; Deleted Test Records</h2>",
            "<table id='cleanup-table'>"
            "<thead><tr><th>Entity</th><th>ID</th><th>HTTP Status</th><th>Result</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>",
            "</div>",
            "<script>"
            "window.addEventListener('DOMContentLoaded', function () {"
            "var el = document.getElementById('cleanup-section');"
            "if (el) { document.body.appendChild(el); }"
            "});"
            "</script>",
        ]
    )


# The intended end-to-end business-flow order for the report to read
# top-to-bottom as one coherent story, instead of pytest's default
# alphabetical-by-file discovery order (which would run e.g. asset/ before
# farmer/ even though asset depends on farmer). "execute project" isn't
# part of the story as given — inserted after "validate asset" since the
# real API rejects validating/creating croppable areas on a project whose
# execution has already started (see test_execute_project.py's docstring).
_TEST_FILE_ORDER = [
    "tests/auth/test_generate_token.py",  # login
    "tests/farmer/test_create_farmer.py",  # farmer
    "tests/farmer/test_edit_farmer.py",  # update farmer
    "tests/asset/test_create_asset.py",  # asset
    "tests/asset/test_edit_asset.py",  # update asset
    "tests/plantype/test_create_plantype.py",  # plantype
    "tests/plantype/test_edit_plantype.py",  # update plantype
    "tests/crop_variety/test_create_crop_variety.py",  # crop variety
    "tests/crop_variety/test_edit_crop_variety.py",  # update crop variety
    "tests/plan/test_add_plan.py",  # plans to variety
    "tests/project/test_create_project.py",  # project
    "tests/project/test_add_asset_to_project.py",  # add asset to project
    "tests/project/test_validate_project_assets.py",  # validate asset
    "tests/project/test_execute_project.py",  # (not in the given list — see above)
    "tests/project/test_update_croppable_area.py",  # update crop variety + sowing date to CA
    "tests/project/test_verify_croppable_area.py",  # verify the variety and sowing date is added
]


def pytest_collection_modifyitems(config, items):
    """Reorders collected tests to follow _TEST_FILE_ORDER above. Anything
    not listed (e.g. tests/framework/'s intake-validator self-tests) keeps
    its natural collection order, appended after everything listed."""
    order_index = {path: i for i, path in enumerate(_TEST_FILE_ORDER)}
    original_order = {item: i for i, item in enumerate(items)}

    def sort_key(item):
        rel_path = item.path.relative_to(config.rootpath).as_posix()
        return (order_index.get(rel_path, len(_TEST_FILE_ORDER)), original_order[item])

    items.sort(key=sort_key)


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def request_context(settings):
    http_session = requests.Session()
    http_session.headers.update(settings.default_headers)
    yield http_session
    http_session.close()


@pytest.fixture(scope="session")
def session_context() -> SessionContext:
    return SessionContext()


@pytest.fixture(scope="session")
def auth_service(request_context, session_context) -> AuthService:
    return AuthService(AuthManager(request_context, session_context))


@pytest.fixture(scope="session")
def logged_in_session(auth_service, session_context) -> SessionContext:
    """Generates an access token once per test session; all services reuse it.
    Login is foundational — every module test depends on it — so a failure
    here aborts the entire run instead of leaving each dependent test to
    fail/error individually."""
    try:
        auth_service.generate_token(load_test_data("login", "valid"))
    except Exception as exc:
        hard_assert(False, f"Login happy-flow failed: {exc}")
    return session_context


@pytest.fixture(scope="session")
def api_client(request_context, logged_in_session) -> ApiClient:
    client = ApiClient(request_context, logged_in_session)
    # Stashed for pytest_runtest_makereport below — there's exactly one
    # ApiClient for the whole session, so a module-level reference is all
    # that's needed to read its call_log when building each test's JSON
    # extra.
    global _LAST_API_CLIENT
    _LAST_API_CLIENT = client
    return client


# One fixture per module, all built on the same authenticated api_client — add
# real endpoint/methods to the corresponding src/services/<module>_service.py
# once its API spec is provided, tests can start using these fixtures right away.
# Session-scoped since these are stateless wrappers around the shared
# api_client — no per-test freshness needed, and it lets dependency fixtures
# below (created_farmer_id etc.) use a broader "package" scope without a
# pytest fixture-scope mismatch.


@pytest.fixture(scope="session")
def farmer_service(api_client) -> FarmerService:
    return FarmerService(api_client)


@pytest.fixture(scope="session")
def asset_service(api_client) -> AssetService:
    return AssetService(api_client)


@pytest.fixture(scope="session")
def plantype_service(api_client) -> PlanTypeService:
    return PlanTypeService(api_client)


@pytest.fixture(scope="session")
def crop_variety_service(api_client) -> CropVarietyService:
    return CropVarietyService(api_client)


@pytest.fixture(scope="session")
def project_service(api_client) -> ProjectService:
    return ProjectService(api_client)


@pytest.fixture(scope="session")
def plan_service(api_client) -> PlanService:
    return PlanService(api_client)


# --- Session-scoped "created_X" (raw response) + "created_X_id" (asserted,
# extracted) pairs, one per entity type for the ENTIRE run. Every test that
# needs that entity — whether it's the dedicated create-test verifying the
# response, an edit test, or a downstream module using it as a dependency —
# shares the SAME single real record. This keeps each full run down to
# exactly one farmer, one asset, one plan type, one crop variety, and one
# project (plus the project's own execute/add-asset/validate/croppable-area
# chain, all against that same project), instead of a fresh record per test.


@pytest.fixture(scope="session")
@tracked_fixture
def created_farmer(farmer_service):
    """The one farmer create() response for the whole run — test_create_farmer
    asserts on this directly instead of making its own separate call."""
    response = farmer_service.create(
        farmer_service.build_create_payload(load_test_data("farmer", "create_valid"))
    )
    _CREATED_RECORDS["farmer"] = response
    return response


@pytest.fixture(scope="session")
def created_farmer_id(created_farmer):
    """The shared farmer's id — session-created only, no test-data
    placeholder fallback. test_create_farmer_success already asserts on
    created_farmer directly and reports its own failure there; if create
    failed, this fixture skips (via pytest.skip) instead of handing out a
    fake id — every test/fixture that depends on created_farmer_id (edit,
    asset creation, etc.) skips along with it rather than silently
    operating on a record that was never actually created this run."""
    if created_farmer.status == 201:
        farmer_id = created_farmer.json().get("id")
        if farmer_id:
            return farmer_id
    pytest.skip(
        f"Farmer creation failed this run (status {created_farmer.status}) — "
        "skipping tests that need created_farmer_id"
    )


@pytest.fixture(scope="session")
@tracked_fixture
def created_asset(asset_service, created_farmer_id):
    """The one asset create() response for the whole run (owned by the one
    shared farmer) — test_create_asset asserts on this directly."""
    response = asset_service.create(
        asset_service.build_create_payload(load_test_data("asset", "create_valid"), created_farmer_id)
    )
    _CREATED_RECORDS["asset"] = response
    return response


@pytest.fixture(scope="session")
def created_asset_id(created_asset):
    """The shared asset's id — session-created only, no test-data
    fallback. Skips dependent tests/fixtures if create failed — see
    created_farmer_id above for why."""
    if created_asset.status == 201:
        asset_id = created_asset.json().get("id")
        if asset_id:
            return asset_id
    pytest.skip(
        f"Asset creation failed this run (status {created_asset.status}) — "
        "skipping tests that need created_asset_id"
    )


@pytest.fixture(scope="session")
def created_plantype(plantype_service):
    """The one plan type create() response for the whole run —
    test_create_plantype asserts on this directly."""
    return plantype_service.create(
        plantype_service.build_create_payload(load_test_data("plantype", "create_valid"))
    )


@pytest.fixture(scope="session")
def created_plantype_id(created_plantype):
    """The shared plan type's id — session-created only, no test-data
    fallback. Skips dependent tests/fixtures if create failed — see
    created_farmer_id above for why."""
    if created_plantype.status == 201:
        plantype_id = created_plantype.json().get("id")
        if plantype_id:
            return plantype_id
    pytest.skip(
        f"Plan type creation failed this run (status {created_plantype.status}) — "
        "skipping tests that need created_plantype_id"
    )


@pytest.fixture(scope="session")
@tracked_fixture
def plantype_update_response(plantype_service, created_plantype_id) -> dict:
    """Fetches the shared plan type, appends a timestamp to its name, and
    PUTs it back EXACTLY ONCE for the whole run — shared by the test that
    verifies this action directly (test_edit_plantype_updates_name) and by
    the plan-type-tasks verify test, which needs the CURRENT (post-edit)
    name — the plan is created after this edit runs, so its tasks carry the
    updated name, not the one from created_plantype's original create().
    Never raises: a failure here shows up as that test's own assertion
    failing, not as a cascading fixture error."""
    get_response = plantype_service.get_by_id(created_plantype_id)
    if get_response.status != 200:
        return {"error": f"GET plan-type failed: HTTP {get_response.status}: {get_response.text()}"}

    updated_payload = plantype_service.build_update_payload(get_response.json())
    put_response = plantype_service.update(updated_payload)
    if put_response.status != 200:
        return {"error": f"PUT plan-type failed: HTTP {put_response.status}: {put_response.text()}"}
    return put_response.json()


@pytest.fixture(scope="session")
@tracked_fixture
def created_crop_variety(crop_variety_service):
    """The one crop variety create() response for the whole run —
    test_create_crop_variety asserts on this directly."""
    response = crop_variety_service.create(
        crop_variety_service.build_create_payload(load_test_data("crop_variety", "create_valid"))
    )
    _CREATED_RECORDS["crop_variety"] = response
    return response


@pytest.fixture(scope="session")
@tracked_fixture
def crop_variety_additional_attributes_response(crop_variety_service, created_crop_variety):
    """The mandatory additional-attribute follow-up call, run once against
    the one shared variety — test_create_crop_variety asserts on this
    directly too. No test-data fallback id — skips (and cascades to every
    test/fixture depending on it, including created_crop_variety_id below)
    if the variety itself was never actually created this run."""
    if created_crop_variety.status != 201 or not created_crop_variety.json().get("id"):
        pytest.skip(
            f"Crop variety creation failed this run (status {created_crop_variety.status}) — "
            "skipping the additional-attributes call"
        )
    variety_id = created_crop_variety.json()["id"]
    return crop_variety_service.add_additional_attributes(variety_id)


@pytest.fixture(scope="session")
def created_crop_variety_id(created_crop_variety, crop_variety_additional_attributes_response):
    """The shared crop variety's id — session-created only, no test-data
    fallback. Skips dependent tests/fixtures if create failed — see
    created_farmer_id above for why."""
    if created_crop_variety.status == 201:
        variety_id = created_crop_variety.json().get("id")
        if variety_id:
            return variety_id
    pytest.skip(
        f"Crop variety creation failed this run (status {created_crop_variety.status}) — "
        "skipping tests that need created_crop_variety_id"
    )


@pytest.fixture(scope="session")
@tracked_fixture
def created_plan(plan_service, created_plantype_id, created_crop_variety_id) -> dict:
    """The one add-plan-to-variety create() call for the whole run —
    test_add_plan_to_crop_variety_success asserts on this directly. Also
    exposes the exact payload used (its generated plan name), and
    created_plan_id below exposes the created plan's id — both consumed by
    the tasks-for-croppable-area verify test."""
    payload = plan_service.build_create_payload(
        load_test_data("plan", "create_valid"), created_plantype_id, created_crop_variety_id
    )
    response = plan_service.create(payload)
    return {"response": response, "payload": payload}


@pytest.fixture(scope="session")
def created_plan_id(created_plan):
    """The shared plan's id, extracted from the create() response — the
    real response body is a list (not a single object), so the id comes off
    its first item. No test-data fallback — skips dependent tests/fixtures
    if create failed or the response has no usable id — see
    created_farmer_id above for why."""
    response = created_plan["response"]
    if response.status == 200:
        body = response.json()
        plan_id = None
        if isinstance(body, list) and body:
            plan_id = body[0].get("id")
        elif isinstance(body, dict):
            plan_id = body.get("id")
        if plan_id:
            return plan_id
    pytest.skip(
        f"Plan creation failed this run (status {response.status}) — "
        "skipping tests that need created_plan_id"
    )


@pytest.fixture(scope="session")
@tracked_fixture
def created_project(project_service):
    """The one project create() response for the whole run —
    test_create_project asserts on this directly instead of making its own
    separate call, and every project-lifecycle test below (execute,
    add-asset, validate, verify, update-croppable-area) acts on this same
    project."""
    response = project_service.create(
        project_service.build_create_payload(load_test_data("project", "create_valid"))
    )
    _CREATED_RECORDS["project"] = response
    return response


@pytest.fixture(scope="session")
def created_project_id(created_project):
    """The shared project's id — session-created only, no test-data
    fallback. Skips dependent tests/fixtures if create failed — see
    created_farmer_id above for why."""
    if created_project.status == 201:
        project_id = created_project.json().get("id")
        if project_id:
            return project_id
    pytest.skip(
        f"Project creation failed this run (status {created_project.status}) — "
        "skipping tests that need created_project_id"
    )


@pytest.fixture(scope="session")
@tracked_fixture
def probable_assets_response(project_service, created_project_id, created_asset_id) -> dict:
    """Adds the shared asset to the shared project via probable-assets
    EXACTLY ONCE for the whole run, returning the raw response body (or a
    synthetic failure dict if the call itself errors) — shared by the test
    that verifies this action directly (test_add_asset_to_project) and by
    project_asset_ids below. Never raises: a failure here shows up as that
    one test failing on its own assertion, not as a cascading fixture error
    blocking every other project-lifecycle test."""
    response = project_service.add_probable_assets(created_project_id, [created_asset_id])
    if response.status != 200:
        result = {
            "recordsFailed": 1,
            "recordsCompleted": 0,
            "error": f"HTTP {response.status}: {response.text()}",
            "projectAssetIds": [],
        }
    else:
        result = response.json()
    _CREATED_RECORDS["probable_assets"] = result
    return result


@pytest.fixture(scope="session")
def project_asset_ids(probable_assets_response):
    """The projectAssetIds from the one probable-assets call above —
    session-created only, no test-data fallback. Skips dependent
    tests/fixtures if the call didn't return any — see created_farmer_id
    above for why."""
    ids = probable_assets_response.get("projectAssetIds")
    if not ids:
        pytest.skip(
            "probable-assets did not return any projectAssetIds this run — "
            f"skipping tests that need project_asset_ids: {probable_assets_response}"
        )
    return ids


@pytest.fixture(scope="session")
@tracked_fixture
def self_validate_response(project_service, created_project_id, project_asset_ids) -> dict:
    """Validates the project-asset associations via
    self-validate-project-assets EXACTLY ONCE for the whole run, returning
    the raw response body (or a synthetic failure dict) — same
    one-call-many-readers and never-raises reasoning as
    probable_assets_response above."""
    response = project_service.self_validate_project_assets(created_project_id, project_asset_ids)
    if response.status != 200:
        result = {
            "recordsFailed": 1,
            "recordsCompleted": 0,
            "croppableAreaIds": [],
            "error": f"HTTP {response.status}: {response.text()}",
        }
    else:
        result = response.json()
    _CREATED_RECORDS["self_validate"] = result
    return result


@pytest.fixture(scope="session")
def croppable_area_ids(self_validate_response):
    """The croppableAreaIds from the one self-validate-project-assets call
    above — session-created only, no test-data fallback. Skips downstream
    tests/fixtures (verify, update) if the response didn't return any —
    see created_farmer_id above for why."""
    ids = self_validate_response.get("croppableAreaIds")
    if not ids:
        pytest.skip(
            "self-validate-project-assets did not return any croppableAreaIds this run — "
            f"skipping tests that need croppable_area_ids: {self_validate_response}"
        )
    return ids


@pytest.fixture(scope="session")
@tracked_fixture
def croppable_area_update_response(project_service, croppable_area_ids, created_crop_variety_id) -> dict:
    """Fetches the shared croppable area, then updates it with the shared
    crop variety + a sowing date EXACTLY ONCE for the whole run — shared by
    the test that verifies this action directly
    (test_add_variety_and_sowing_date_to_croppable_area) and by the
    verify-step tests below that re-fetch and confirm the update actually
    persisted. Never raises: a failure here shows up as that test's own
    assertion failing, not as a cascading fixture error."""
    croppable_area_id = croppable_area_ids[0]
    get_response = project_service.get_croppable_area(croppable_area_id)
    if get_response.status != 200:
        return {"error": f"GET croppable-area failed: HTTP {get_response.status}: {get_response.text()}"}

    test_data = load_test_data("project", "croppable_area")
    updated_payload = project_service.build_croppable_area_update_payload(
        get_response.json(), test_data, created_crop_variety_id
    )
    put_response = project_service.update_croppable_area(updated_payload)
    if put_response.status != 200:
        return {"error": f"PUT croppable-area failed: HTTP {put_response.status}: {put_response.text()}"}
    return put_response.json()


@pytest.fixture(scope="session", autouse=True)
def cleanup_created_records(
    project_service,
    asset_service,
    farmer_service,
    crop_variety_service,
):
    """Session-scoped teardown: after all tests finish, cleans up this
    run's real records in the required order — close the croppable area(s),
    then delete them (POST remove/selected-ids), then variety, then asset,
    then farmer, and stop the project's execution last (per the user's
    specified order). Results go into _CLEANUP_LOG for the separate
    "Cleanup" report section (see pytest_html_results_summary above), not
    the normal pass/fail rows.

    Each step only runs if that entity's own create() call actually
    succeeded (status 201) THIS run — ids are extracted from the raw
    responses in _CREATED_RECORDS below, never from a test-data placeholder.

    Deliberately takes NO business-data fixtures as parameters — only the
    plain service fixtures (which never raise). The actual create responses
    are read from the module-level _CREATED_RECORDS dict instead (see its
    definition above), which each creation fixture stashes into as a side
    effect. Several created_X_id fixtures now call pytest.skip() when their
    creation failed, and skip exceptions are cached and re-raised for every
    dependent, cascading upward through anything that requests them
    (including transitively — e.g. created_asset needs created_farmer_id
    for its own payload). Since this is an autouse session fixture, every
    test's setup resolves it first; if it listed any such fixture as a
    parameter, one failed creation would skip literally every test in the
    run, including the create test itself (which should show its own clear
    Failed, not Skipped) — reading from the plain dict instead sidesteps
    pytest's fixture graph entirely.

    Note: as an autouse session fixture, this only sees whatever's in
    _CREATED_RECORDS by the time the session ends — acceptable for now
    since every run so far has been a full-suite run where all the create
    fixtures get triggered anyway; revisit if selective marker-based runs
    become common.

    Asset/farmer/crop variety deletes are the bulk-delete shape
    `DELETE {resource_path}/bulk?ids=...` (BaseService.delete_bulk) — a 200
    alone doesn't mean the record was deleted, so success is judged off the
    response body's `{"deletable": N, "nonDeletable": N}` (see
    _record_bulk_delete above), not just the HTTP status.

    The whole teardown can be turned off via test data —
    settings.cleanup.enabled in test_data/<env>.json — without touching
    code. Currently false for qa (no real records ever get created there
    anyway, since login fails immediately without real credentials), true
    for uat/prod. If the key is ever missing from some env file, this
    defaults to enabled rather than raising.
    """
    yield

    def _extract_id(response):
        if response is not None and response.status == 201:
            return response.json().get("id")
        return None

    def _created(response):
        return response is not None and response.status == 201

    created_project = _CREATED_RECORDS.get("project")
    created_asset = _CREATED_RECORDS.get("asset")
    created_farmer = _CREATED_RECORDS.get("farmer")
    created_crop_variety = _CREATED_RECORDS.get("crop_variety")
    probable_assets_response = _CREATED_RECORDS.get("probable_assets") or {}
    self_validate_response = _CREATED_RECORDS.get("self_validate") or {}

    created_project_id = _extract_id(created_project)
    created_asset_id = _extract_id(created_asset)
    created_farmer_id = _extract_id(created_farmer)
    created_crop_variety_id = _extract_id(created_crop_variety)
    project_asset_ids = probable_assets_response.get("projectAssetIds") or []
    croppable_area_ids = self_validate_response.get("croppableAreaIds") or []

    try:
        cleanup_enabled = load_test_data("settings", "cleanup").get("enabled", True)
    except KeyError:
        cleanup_enabled = True

    if not cleanup_enabled:
        _record_cleanup(
            "all", "-", note="Skipped — cleanup disabled via test data (settings.cleanup.enabled=false)"
        )
        return

    project_created = _created(created_project)

    # 1. Close, then delete croppable area(s) — two-step async process.
    # Skipped entirely if the project itself was never actually created
    # this run (croppable_area_ids/project_asset_ids would just be
    # test-data fallback placeholders, not real ids to act on).
    if not project_created:
        _record_cleanup(
            "croppable_area", croppable_area_ids,
            note="Skipped — project creation failed this run, no real croppable area to clean up",
        )
    else:
        close_response = project_service.close_croppable_areas(croppable_area_ids)
        if close_response.status != 200:
            _record_cleanup(
                "croppable_area", croppable_area_ids, status=close_response.status, success=False,
                note=f"close failed: {close_response.text()}",
            )
        else:
            remove_response = project_service.remove_project_assets(
                created_project_id, project_asset_ids, croppable_area_ids
            )
            if remove_response.status != 202:
                _record_cleanup(
                    "croppable_area", croppable_area_ids, status=remove_response.status, success=False,
                    note=f"remove failed: {remove_response.text()}",
                )
            else:
                process_id = remove_response.json().get("id")
                final = project_service.wait_for_execution_result(process_id)
                failed_count = (final.get("message") or {}).get("failedCount", 0)
                success = final.get("status") == "COMPLETED" and failed_count == 0
                _record_cleanup(
                    "croppable_area", croppable_area_ids, status=final.get("status"), success=success,
                    note=None if success else f"final: {final}",
                )

    # 2. Delete crop variety — DELETE {resource_path}/bulk?ids=... (bulk-delete shape).
    # Skipped if the variety was never actually created this run.
    if _created(created_crop_variety):
        _record_bulk_delete(
            "crop_variety", created_crop_variety_id, crop_variety_service.delete_bulk([created_crop_variety_id])
        )
    else:
        _record_cleanup(
            "crop_variety", created_crop_variety_id,
            note="Skipped — creation failed this run, no real record to delete",
        )

    # 3. Delete asset — DELETE {resource_path}/bulk?ids=... (bulk-delete shape).
    # Skipped if the asset was never actually created this run.
    if _created(created_asset):
        _record_bulk_delete("asset", created_asset_id, asset_service.delete_bulk([created_asset_id]))
    else:
        _record_cleanup(
            "asset", created_asset_id, note="Skipped — creation failed this run, no real record to delete"
        )

    # 4. Delete farmer — DELETE {resource_path}/bulk?ids=... (bulk-delete shape).
    # Skipped if the farmer was never actually created this run.
    if _created(created_farmer):
        _record_bulk_delete("farmer", created_farmer_id, farmer_service.delete_bulk([created_farmer_id]))
    else:
        _record_cleanup(
            "farmer", created_farmer_id, note="Skipped — creation failed this run, no real record to delete"
        )

    # 5. Stop the project's execution — last step. Skipped if the project
    # was never actually created this run.
    if not project_created:
        _record_cleanup(
            "project (stop-execution)", created_project_id,
            note="Skipped — project creation failed this run, nothing to stop",
        )
    else:
        # Async, like start-execution: the POST only returns an IN_PROGRESS
        # job id, so poll it to completion before recording success/failure.
        stop_response = project_service.stop_execution(created_project_id)
        if stop_response.status != 200:
            _record_cleanup(
                "project (stop-execution)", created_project_id, status=stop_response.status,
                success=False, note=stop_response.text(),
            )
        else:
            stop_process_id = stop_response.json().get("id")
            final = project_service.wait_for_execution_result(stop_process_id)
            success = final.get("status") == "COMPLETED"
            _record_cleanup(
                "project (stop-execution)", created_project_id, status=final.get("status"),
                success=success, note=None if success else f"final: {final}",
            )
