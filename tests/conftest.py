import base64
import functools
import inspect
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import requests
from pytest_html import extras
from pytest_metadata.plugin import metadata_key

from src.config.settings import get_settings
from src.core.api_client import ApiClient
from src.core.auth_manager import AuthManager
from src.core.session_context import SessionContext
from src.services.asset_service import AssetService
from src.services.auth_service import AuthService
from src.services.crop_variety_service import CropVarietyService
from src.services.farmer_service import FarmerService
from src.services.form_service import FormService
from src.services.plan_service import PlanService
from src.services.plantype_service import PlanTypeService
from src.services.project_service import ProjectService
from src.services.task_service import TaskService
from src.utils.hard_assert import hard_assert
from src.utils.logger import get_logger
from src.utils.test_data_loader import load_test_data

logger = get_logger(__name__)

# Set by the api_client fixture below (one ApiClient for the whole
# session) — read by the hooks below to attach each test's own API calls
# as a JSON extra in the HTML report.
_LAST_API_CLIENT: ApiClient | None = None
_api_call_log_offset = 0

# Set by pytest_configure below — read by pytest_html_report_title to show
# which -m marker expression this run used (SANITY/SMOKE/REGRESSION/ALL).
_execution_type = "ALL"

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
    function).

    Also advances the global _api_call_log_offset past these calls right
    here — without this, the test that happens to be the FIRST to trigger
    this fixture would double-count its calls: once via _CALLS_BY_FIXTURE
    (since the test names this fixture as a parameter) and again via
    pytest_runtest_makereport's own offset-based "direct calls" tracking
    (since they also happened during that same test's setup phase). This
    "consumes" the calls the moment they're attributed here, so they show
    up exactly once, on whichever test's fixture-list names this fixture —
    never also folded into anyone's direct-call count.
    """

    @functools.wraps(fixture_func)
    def wrapper(*args, **kwargs):
        if _LAST_API_CLIENT is None:
            return fixture_func(*args, **kwargs)
        before = len(_LAST_API_CLIENT.call_log)
        result = fixture_func(*args, **kwargs)
        after = len(_LAST_API_CLIENT.call_log)
        if after > before:
            _CALLS_BY_FIXTURE[fixture_func.__name__] = _LAST_API_CLIENT.call_log[before:after]
            global _api_call_log_offset
            _api_call_log_offset = after
        return result

    return wrapper


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Attaches this test's relevant API calls (URL/payload/response,
    captured by ApiClient.call_log) as a clickable JSON extra in the HTML
    report — on the 'call' phase normally, or on 'setup' if setup itself
    failed (no 'call' phase runs in that case). Two sources, but never
    combined — a test either made its own calls, or it didn't:
    1. Calls made directly during this test's own setup/call phases (a
       global read-offset, so each test only gets what's new since the
       last one reported). Whenever this test made at least one call of
       its own, that's the whole story — shown as-is.
    2. ONLY when this test made zero direct calls: calls already recorded
       against any fixture THIS TEST FUNCTION directly declares as a
       parameter (see _CALLS_BY_FIXTURE / tracked_fixture above) — this is
       what surfaces a call that actually happened earlier, cached, for a
       test that's purely "assert on the shared fixture's result." Uses
       the function's own declared params, not item.fixturenames, since
       the latter also includes autouse fixtures like
       cleanup_created_records — which pulls in EVERY business fixture for
       EVERY test, and would otherwise show the same huge combined list
       everywhere instead of just what each test actually cares about.

       Falling back to fixture_calls ONLY when direct_calls is empty
       matters for tests like test_verify_croppable_area_variety_and_sowing_date,
       which makes its own fresh GET AND names croppable_area_update_response
       as a parameter (just to read its sowingDate for comparison) —
       without this guard, that test would show its own GET plus the
       unrelated GET+PUT another test already triggered and reported,
       inflating "1 call" into "3 calls" for no reason tied to what this
       test itself actually did.
    """
    outcome = yield
    report = outcome.get_result()

    should_attach = report.when == "call" or (report.when == "setup" and report.outcome != "passed")
    if not should_attach or _LAST_API_CLIENT is None:
        return

    global _api_call_log_offset
    direct_calls = _LAST_API_CLIENT.call_log[_api_call_log_offset:]
    _api_call_log_offset = len(_LAST_API_CLIENT.call_log)

    if direct_calls:
        all_calls = direct_calls
    else:
        all_calls = []
        for param_name in inspect.signature(item.function).parameters:
            all_calls.extend(_CALLS_BY_FIXTURE.get(param_name, []))

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

    # Whatever -m marker expression this run used (sanity/smoke/regression/
    # a combination), or ALL if none was passed — shown in the report title
    # and metadata table so it's clear what kind of run this was without
    # needing to check how it was triggered. Stashed as a module global
    # (rather than read off `report.config` in pytest_html_report_title
    # below) since pytest-html's ReportData only exposes config as the
    # private `_config`.
    global _execution_type
    _execution_type = ((config.option.markexpr or "").strip() or "ALL").upper()

    # pytest-metadata (3.x) stores metadata in config.stash[metadata_key],
    # not the old config._metadata attribute — that attribute doesn't even
    # exist on this version, so a plain hasattr() check silently skips
    # every time. This is what actually renders as the "Environment" table
    # in the report.
    if metadata_key in config.stash:
        config.stash[metadata_key]["Environment"] = active_env.upper()
        config.stash[metadata_key]["Execution Type"] = _execution_type


def pytest_html_report_title(report):
    active_env = os.getenv("ENV", "qa").upper()
    report.title = f"Cropin API Automation Report ({active_env}) — {_execution_type}"


# One entry per recorded test outcome this run (see pytest_runtest_logreport);
# pytest_unconfigure turns it into the result block of the report email.
_run_results: list[dict] = []


def pytest_runtest_logreport(report):
    """Records each test's outcome for the report email: the 'call' phase's
    result, plus a setup/teardown phase only when it failed (an error) or,
    for setup, skipped the test. Expected failures are kept apart from real
    ones."""
    if report.when == "call":
        if hasattr(report, "wasxfail"):
            outcome = "xpassed" if report.passed else "xfailed"
        else:
            outcome = report.outcome
    elif report.failed:
        outcome = "error"
    elif report.when == "setup" and report.skipped:
        outcome = "skipped"
    else:
        return

    reason = ""
    if outcome in ("failed", "error"):
        crash = getattr(report.longrepr, "reprcrash", None)
        reason = crash.message if crash is not None else str(report.longrepr)
    _run_results.append({"test": report.nodeid, "outcome": outcome, "reason": reason})


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

    # EMAIL_RECIPIENTS_OVERRIDE (set by the GitHub Actions workflow's three
    # notify_* checkboxes, comma-separated) replaces the recipient LIST for
    # this run only — set (even to "", meaning every checkbox was
    # unchecked) it takes priority; unset (e.g. local runs) falls back to
    # test_data/prod.json's settings.email_report.recipients. Either way,
    # settings.email_report.enabled above still gates whether any email
    # sends at all.
    recipients_override = os.getenv("EMAIL_RECIPIENTS_OVERRIDE")
    if recipients_override is not None:
        recipients = [r.strip() for r in recipients_override.split(",") if r.strip()]
    else:
        recipients = email_settings.get("recipients") or []
    report_path = Path(f"reports/report_{active_env}.html")

    # _execution_type is set by pytest_configure above (SANITY/SMOKE/
    # REGRESSION/ALL, from the -m marker expression this run used).
    execution_label = _execution_type.title()
    today = datetime.now().strftime("%d %B %Y")

    try:
        from src.utils.report_mailer import format_results_summary, send_report_email

        body = (
            "Hi Team,\n\n"
            f"Please find attached the API {execution_label} test report for the "
            f"{active_env.upper()} environment, run on {today}.\n\n"
            f"{format_results_summary(_run_results)}\n\n"
            "Regards,\n"
            "QA Team"
        )
        send_report_email(get_settings(), report_path, recipients, summary_text=body)
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
    calls: list[dict] | None = None,
) -> None:
    """Pass either `response` (a single ApiResponse — status/success are
    read off it) or explicit `status`/`success` (for multi-step cleanup
    sequences like croppable area's close -> remove -> poll, where there's
    no single response to point at). Leaving all of status/success/response
    unset means this step hasn't been wired in yet (endpoint not provided)
    — rendered as "Not implemented yet" rather than looking like an
    attempted-and-failed delete.

    `calls` is this cleanup step's own slice of ApiClient.call_log (see
    cleanup_created_records below, which snapshots the log before/after
    each step) — rendered as its own "API Calls" link in the Cleanup
    section, same shape as a test's, but kept strictly separate: cleanup
    always runs in this fixture's teardown, after every test's own report
    has already been built and _api_call_log_offset already advanced past
    it (see cleanup_created_records' final offset bump), so these calls
    never get attributed to any test."""
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
            "calls": calls or [],
        }
    )


def _record_bulk_delete(entity_type: str, entity_id, response, calls: list[dict] | None = None) -> None:
    """For the farmer/asset/variety bulk-delete endpoints
    (DELETE {resource_path}/bulk?ids=...) — a 200 alone doesn't mean the
    record was actually deleted, the body reports that as
    {"deletable": N, "nonDeletable": N}, so success is judged off the body,
    not just the HTTP status."""
    if response.status != 200:
        _record_cleanup(
            entity_type, entity_id, status=response.status, success=False, note=response.text(), calls=calls
        )
        return
    body = response.json()
    success = body.get("nonDeletable", 0) == 0 and body.get("deletable", 0) >= 1
    _record_cleanup(
        entity_type, entity_id, status=response.status, success=success,
        note=None if success else f"response: {body}", calls=calls,
    )


def _record_delete_by_status(entity_type: str, entity_id, response, calls: list[dict] | None = None) -> None:
    """For bulk-delete endpoints whose real response shape isn't confirmed
    (plan/plan type — only their URLs were given, not a sample delete
    response), unlike farmer/asset/crop variety's confirmed
    {"deletable": N, "nonDeletable": N} body (see _record_bulk_delete
    above). Success is judged by status + absence of an error in the body,
    not a specific body shape: ok status, and if the body is a JSON object
    carrying an "error" field, that still counts as a failure even at a
    2xx status."""
    success = response.ok
    note = None
    if success:
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and body.get("error"):
            success = False
            note = f"response: {body}"
    if not success and note is None:
        note = response.text()
    _record_cleanup(entity_type, entity_id, status=response.status, success=success, note=note, calls=calls)


def _record_delete_by_ids(entity_type: str, entity_id, response, calls: list[dict] | None = None) -> None:
    """For the form bulk-delete (DELETE {resource_path}/bulk?ids=...), whose
    body has a different shape from farmer/asset/variety's
    {"deletable": N, "nonDeletable": N} (see _record_bulk_delete):
    {"nonDeletedIds": [...], "deletedIds": [...]}. A 200 alone isn't enough —
    success is the id being in deletedIds AND nonDeletedIds being empty;
    anything else is a failed cleanup row carrying the response body."""
    if response.status != 200:
        _record_cleanup(
            entity_type, entity_id, status=response.status, success=False, note=response.text(), calls=calls
        )
        return
    try:
        body = response.json()
    except ValueError:
        body = None
    deleted = {str(i) for i in (body.get("deletedIds") or [])} if isinstance(body, dict) else set()
    success = (
        isinstance(body, dict) and str(entity_id) in deleted and not (body.get("nonDeletedIds") or [])
    )
    _record_cleanup(
        entity_type, entity_id, status=response.status, success=success,
        note=None if success else f"response: {body if body is not None else response.text()}", calls=calls,
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


def _api_calls_link(calls: list[dict]) -> str:
    """Renders a cleanup step's own API calls as the exact same kind of
    link pytest-html emits for a test's JSON extra (same class, same
    data-URI shape — see selfcontained_report.py) — reuses the click
    handler already registered in _API_CALLS_MODAL_SCRIPT with no new JS."""
    if not calls:
        return "-"
    encoded = base64.b64encode(json.dumps(calls).encode("utf-8")).decode("utf-8")
    href = f"data:application/json;charset=utf-8;base64,{encoded}"
    return f'<a class="col-links__extra json" href="{href}">API Calls ({len(calls)})</a>'


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
            f"<td>{result}</td><td>{_api_calls_link(c.get('calls'))}</td></tr>"
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
            "<thead><tr><th>Entity</th><th>ID</th><th>HTTP Status</th><th>Result</th><th>API Calls</th></tr></thead>"
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
    # Task fill — runs on the plan's tasks once they've been pulled onto the
    # croppable area, and (like everything above) well before the teardown
    # in cleanup_created_records, which only fires at the very end of the run.
    "tests/task/test_task_fill_positive.py",
    "tests/task/test_task_fill_negative.py",
    "tests/task/test_task_fill_boundary.py",
    "tests/task/test_task_fill_integrity.py",
    "tests/task/test_task_fill_regression.py",
    "tests/task/test_task_fill_security.py",
    # Form — needs the run's crop variety and farmer (both created earlier),
    # and still comes before the teardown, which deletes the form (step 3 of
    # cleanup_created_records). There is no delete API for filled forms, so
    # the filled form stays behind.
    "tests/form/test_create_form.py",  # form creation
    "tests/form/test_update_form.py",  # form update (name only)
    "tests/form/test_fill_form.py",  # fill the (updated) form for the farmer
    "tests/form/test_form_negative.py",  # refused requests — after the happy path
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


@pytest.fixture(scope="session")
def task_service(api_client) -> TaskService:
    return TaskService(api_client)


@pytest.fixture(scope="session")
def form_service(api_client) -> FormService:
    return FormService(api_client)


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
    response = plantype_service.create(
        plantype_service.build_create_payload(load_test_data("plantype", "create_valid"))
    )
    _CREATED_RECORDS["plantype"] = response
    return response


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
    _CREATED_RECORDS["plan"] = response
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


def _form_id_or_none(created_form: dict):
    """The id off the form create() response, or None if creation didn't
    succeed (or the body isn't the expected JSON object). Never raises."""
    response = created_form["response"]
    if response.status not in (200, 201):
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("id") if isinstance(body, dict) else None


@pytest.fixture(scope="session")
def form_client_id() -> str:
    """The run's one clientId for the form: a fresh uuid4, generated once per
    run (never hardcoded, never from test data) and used as the clientId of
    the form create body, kept unchanged by the update (whose body is the
    create response) and sent as the clientId of the fill — create, update and
    fill all share this value."""
    return str(uuid.uuid4())


@pytest.fixture(scope="session")
@tracked_fixture
def created_form(form_service, created_crop_variety_id, form_client_id) -> dict:
    """The one form create() call for the whole run (linked to the shared
    crop variety, carrying the run's form_client_id) — test_create_form_success
    asserts on this directly.
    Also exposes the exact payload used (its generated unique name, the
    validity dates), which the stored-form check, the update and the fill
    read. Registers the raw create response in _CREATED_RECORDS so
    cleanup_created_records can delete the form at the end of the run (before
    the crop variety it is linked to)."""
    payload = form_service.build_create_payload(
        load_test_data("form", "create_valid"), created_crop_variety_id, form_client_id
    )
    response = form_service.create(payload)
    _CREATED_RECORDS["form"] = response
    return {"response": response, "payload": payload}


@pytest.fixture(scope="session")
def created_form_id(created_form):
    """The shared form's id — session-created only, no test-data fallback.
    Skips dependent tests/fixtures if create failed — see created_farmer_id
    above for why."""
    form_id = _form_id_or_none(created_form)
    if form_id:
        return form_id
    pytest.skip(
        f"Form creation failed this run (status {created_form['response'].status}) — "
        "skipping tests that need created_form_id"
    )


@pytest.fixture(scope="session")
@tracked_fixture
def stored_form(form_service, created_form):
    """A fresh GET of the shared form (not the create() echo), made once —
    test_create_form_success checks the form was really stored. None when
    creation failed: deliberately does not skip, so that test fails on its own
    create assertions instead of being skipped along with this fixture."""
    form_id = _form_id_or_none(created_form)
    if not form_id:
        return None
    return form_service.get_by_id(form_id)


@pytest.fixture(scope="session")
@tracked_fixture
def updated_form(form_service, created_form, created_form_id, stored_form) -> dict:
    """The one form update for the whole run — test_update_form_success
    asserts on this directly. PUTs the form's create() response back with
    only the name changed. Depends on stored_form (the create test's GET,
    taken once) purely so that GET always happens BEFORE this update and the
    create test sees the form as created. Never raises: a failed PUT shows up
    as that test's own assertion failing. Also exposes the exact body sent
    and the create payload (the form as created), which the test compares
    against."""
    payload = form_service.build_update_payload(
        created_form["response"].json(), load_test_data("form", "update_valid")
    )
    response = form_service.update(payload)
    return {"response": response, "payload": payload, "created_payload": created_form["payload"]}


@pytest.fixture(scope="session")
@tracked_fixture
def stored_updated_form(form_service, updated_form, created_form_id):
    """A fresh GET of the shared form after the update, made once —
    test_update_form_success checks the new name was really stored. None when
    the PUT didn't succeed, so that test fails on its own PUT assertion."""
    if updated_form["response"].status != 200:
        return None
    return form_service.get_by_id(created_form_id)


@pytest.fixture(scope="session")
@tracked_fixture
def filled_form(
    form_service, farmer_service, created_form, updated_form, created_form_id,
    created_farmer, created_farmer_id, form_client_id,
) -> dict:
    """Fills the shared form for the shared farmer EXACTLY ONCE for the whole
    run — test_fill_form_success asserts on this directly, and reads the
    filled form back through stored_filled_form below. Runs after the form
    update (depends on updated_form), carries the run's form_client_id as its
    clientId, and sends the form's CURRENT name: the
    updated one if the update returned 200, otherwise the name it was created
    with. The farmer's name is read with a fresh GET (test_edit_farmer appends
    a timestamp to it earlier in the run), falling back to the create()
    response's firstName. Never raises: a failed fill shows up as that test's
    own assertion failing, not as a cascading fixture error. Also exposes the
    exact payload sent. There is no delete API for filled forms, so this
    record is not cleaned up."""
    farmer_response = farmer_service.get_by_id(created_farmer_id)
    farmer_name = farmer_response.json().get("firstName") if farmer_response.status == 200 else None
    if not farmer_name:
        farmer_name = created_farmer.json().get("firstName")
    current_form = dict(created_form["payload"])
    if updated_form["response"].status == 200:
        current_form["name"] = updated_form["payload"]["name"]
    payload = form_service.build_fill_payload(
        load_test_data("form", "fill_valid"), current_form, created_form_id,
        created_farmer_id, farmer_name, form_client_id,
    )
    response = form_service.fill(payload)
    return {"response": response, "payload": payload}


@pytest.fixture(scope="session")
@tracked_fixture
def stored_filled_form(form_service, filled_form):
    """A fresh GET of the filled form (by the id the fill POST returned), made
    once — test_fill_form_success cross-checks it with the POST response, so
    the fill is verified by an independent read and not just its own echo.
    None when the POST didn't succeed or returned no id: deliberately neither
    raises nor skips, so that test fails on its own POST assertions instead."""
    response = filled_form["response"]
    if not 200 <= response.status < 300:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    filled_id = body.get("id") if isinstance(body, dict) else None
    if not filled_id:
        return None
    return form_service.get_filled(filled_id)


@pytest.fixture(scope="session", autouse=True)
def cleanup_created_records(
    project_service,
    asset_service,
    farmer_service,
    crop_variety_service,
    plantype_service,
    plan_service,
    form_service,
):
    """Session-scoped teardown: after all tests finish, cleans up this
    run's real records in the required order — close the croppable area(s),
    then delete them (POST remove/selected-ids), then the plan (it's linked
    to the crop variety, so it has to go before the variety itself can be
    deleted), then the form (its varietyId links it to the crop variety too,
    so it also goes before the variety), then variety, then asset, then
    farmer, then stop the project's execution, and finally delete the plan
    type last of all, once every other record is already gone (per the
    user's specified order). The filled form has no delete API, so it stays
    behind. Results go into _CLEANUP_LOG for the separate "Cleanup" report
    section (see pytest_html_results_summary above), not the normal
    pass/fail rows.

    Each step only runs if that entity's own create() call actually
    succeeded (status 201 — 200 for the plan, and 200 or 201 for the form,
    whose create status isn't confirmed) THIS run — ids are extracted from
    the raw responses in _CREATED_RECORDS below, never from a test-data
    placeholder.

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

    Asset/farmer/crop variety/plan/plan type deletes are all the same
    `DELETE {resource_path}/bulk?ids=...` shape (BaseService.delete_bulk),
    but judged for success two different ways depending on what's actually
    confirmed: asset/farmer/crop variety are confirmed (against real
    responses) to report `{"deletable": N, "nonDeletable": N}` in the body,
    so a 200 alone isn't enough — see _record_bulk_delete. Plan/plan type
    only ever had their URL given, not a sample delete response, so those
    two are judged by status + absence of an error in the body instead —
    see _record_delete_by_status. The form delete is the same URL shape but
    reports `{"nonDeletedIds": [...], "deletedIds": [...]}`, judged by the
    id being in deletedIds with nothing in nonDeletedIds — see
    _record_delete_by_ids.

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

    def _extract_form_id(response):
        # Form create() accepts 200 or 201 (the real status isn't confirmed),
        # so — unlike _extract_id — a 200 counts too, as long as it has an id.
        if response is None or response.status not in (200, 201):
            return None
        try:
            body = response.json()
        except ValueError:
            return None
        return body.get("id") if isinstance(body, dict) else None

    def _extract_plan_id(response):
        # Plan create() is the odd one out — 200, not 201, and the body is
        # a list (not a single object), same shape created_plan_id (above)
        # already handles for the test-facing fixture.
        if response is None or response.status != 200:
            return None
        body = response.json()
        if isinstance(body, list) and body:
            return body[0].get("id")
        if isinstance(body, dict):
            return body.get("id")
        return None

    def _log_len():
        return len(_LAST_API_CLIENT.call_log) if _LAST_API_CLIENT is not None else 0

    def _calls_since(start):
        return _LAST_API_CLIENT.call_log[start:] if _LAST_API_CLIENT is not None else []

    created_project = _CREATED_RECORDS.get("project")
    created_asset = _CREATED_RECORDS.get("asset")
    created_farmer = _CREATED_RECORDS.get("farmer")
    created_crop_variety = _CREATED_RECORDS.get("crop_variety")
    created_plantype = _CREATED_RECORDS.get("plantype")
    created_plan = _CREATED_RECORDS.get("plan")
    created_form = _CREATED_RECORDS.get("form")
    probable_assets_response = _CREATED_RECORDS.get("probable_assets") or {}
    self_validate_response = _CREATED_RECORDS.get("self_validate") or {}

    created_project_id = _extract_id(created_project)
    created_asset_id = _extract_id(created_asset)
    created_farmer_id = _extract_id(created_farmer)
    created_crop_variety_id = _extract_id(created_crop_variety)
    created_plantype_id = _extract_id(created_plantype)
    created_plan_id = _extract_plan_id(created_plan)
    created_form_id = _extract_form_id(created_form)
    project_asset_ids = probable_assets_response.get("projectAssetIds") or []
    croppable_area_ids = self_validate_response.get("croppableAreaIds") or []

    # CLEANUP_OVERRIDE (set by the GitHub Actions workflow's "cleanup"
    # yes/no input) takes priority for this run only; falls back to
    # test_data/<env>.json's settings.cleanup.enabled when not set (e.g.
    # local runs), which itself defaults to enabled if the key is missing.
    cleanup_override = os.getenv("CLEANUP_OVERRIDE")
    if cleanup_override is not None:
        cleanup_enabled = cleanup_override.strip().lower() == "yes"
        cleanup_source = "CLEANUP_OVERRIDE env var"
    else:
        try:
            cleanup_enabled = load_test_data("settings", "cleanup").get("enabled", True)
        except KeyError:
            cleanup_enabled = True
        cleanup_source = "test_data settings.cleanup.enabled"

    if not cleanup_enabled:
        _record_cleanup(
            "all", "-", note=f"Skipped — cleanup disabled via {cleanup_source}"
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
        step_start = _log_len()
        close_response = project_service.close_croppable_areas(croppable_area_ids)
        if close_response.status != 200:
            _record_cleanup(
                "croppable_area", croppable_area_ids, status=close_response.status, success=False,
                note=f"close failed: {close_response.text()}", calls=_calls_since(step_start),
            )
        else:
            remove_response = project_service.remove_project_assets(
                created_project_id, project_asset_ids, croppable_area_ids
            )
            if remove_response.status != 202:
                _record_cleanup(
                    "croppable_area", croppable_area_ids, status=remove_response.status, success=False,
                    note=f"remove failed: {remove_response.text()}", calls=_calls_since(step_start),
                )
            else:
                process_id = remove_response.json().get("id")
                final = project_service.wait_for_execution_result(process_id)
                failed_count = (final.get("message") or {}).get("failedCount", 0)
                success = final.get("status") == "COMPLETED" and failed_count == 0
                _record_cleanup(
                    "croppable_area", croppable_area_ids, status=final.get("status"), success=success,
                    note=None if success else f"final: {final}", calls=_calls_since(step_start),
                )

    # 2. Delete the plan — DELETE {resource_path}/bulk?ids=... . Linked to
    # the crop variety (and plan type), so it has to be removed before the
    # variety itself can be deleted. Success is judged by status + no error
    # in the body (see _record_delete_by_status) rather than the
    # deletable/nonDeletable shape, since only the URL was given for this
    # one. Skipped if the plan was never actually created this run.
    if created_plan_id is not None:
        step_start = _log_len()
        response = plan_service.delete_bulk([created_plan_id])
        _record_delete_by_status("plan", created_plan_id, response, calls=_calls_since(step_start))
    else:
        _record_cleanup(
            "plan", created_plan_id, note="Skipped — creation failed this run, no real record to delete"
        )

    # 3. Delete the form — DELETE /services/form/api/forms/bulk?ids=<id>.
    # Its varietyId links it to the crop variety, so it has to be removed
    # before the variety delete below (a variety still referenced by a form
    # can't be deleted). The body is {"nonDeletedIds": [...], "deletedIds":
    # [...]}, a different shape from the farmer/asset/variety deletes, so it
    # has its own check (see _record_delete_by_ids). Skipped if the form was
    # never actually created this run. The filled form has no delete API and
    # stays behind.
    if created_form_id is not None:
        step_start = _log_len()
        response = form_service.delete_bulk([created_form_id])
        _record_delete_by_ids("form", created_form_id, response, calls=_calls_since(step_start))
    else:
        _record_cleanup(
            "form", created_form_id, note="Skipped — creation failed this run, no real record to delete"
        )

    # 4. Delete crop variety — DELETE {resource_path}/bulk?ids=... (bulk-delete shape).
    # Skipped if the variety was never actually created this run.
    if _created(created_crop_variety):
        step_start = _log_len()
        response = crop_variety_service.delete_bulk([created_crop_variety_id])
        _record_bulk_delete("crop_variety", created_crop_variety_id, response, calls=_calls_since(step_start))
    else:
        _record_cleanup(
            "crop_variety", created_crop_variety_id,
            note="Skipped — creation failed this run, no real record to delete",
        )

    # 5. Delete asset — DELETE {resource_path}/bulk?ids=... (bulk-delete shape).
    # Skipped if the asset was never actually created this run.
    if _created(created_asset):
        step_start = _log_len()
        response = asset_service.delete_bulk([created_asset_id])
        _record_bulk_delete("asset", created_asset_id, response, calls=_calls_since(step_start))
    else:
        _record_cleanup(
            "asset", created_asset_id, note="Skipped — creation failed this run, no real record to delete"
        )

    # 6. Delete farmer — DELETE {resource_path}/bulk?ids=... (bulk-delete shape).
    # Skipped if the farmer was never actually created this run.
    if _created(created_farmer):
        step_start = _log_len()
        response = farmer_service.delete_bulk([created_farmer_id])
        _record_bulk_delete("farmer", created_farmer_id, response, calls=_calls_since(step_start))
    else:
        _record_cleanup(
            "farmer", created_farmer_id, note="Skipped — creation failed this run, no real record to delete"
        )

    # 7. Stop the project's execution. Skipped if the project was never
    # actually created this run.
    if not project_created:
        _record_cleanup(
            "project (stop-execution)", created_project_id,
            note="Skipped — project creation failed this run, nothing to stop",
        )
    else:
        # Async, like start-execution: the POST only returns an IN_PROGRESS
        # job id, so poll it to completion before recording success/failure.
        step_start = _log_len()
        stop_response = project_service.stop_execution(created_project_id)
        if stop_response.status != 200:
            _record_cleanup(
                "project (stop-execution)", created_project_id, status=stop_response.status,
                success=False, note=stop_response.text(), calls=_calls_since(step_start),
            )
        else:
            stop_process_id = stop_response.json().get("id")
            final = project_service.wait_for_execution_result(stop_process_id)
            success = final.get("status") == "COMPLETED"
            _record_cleanup(
                "project (stop-execution)", created_project_id, status=final.get("status"),
                success=success, note=None if success else f"final: {final}", calls=_calls_since(step_start),
            )

    # 8. Delete plan type — DELETE {resource_path}/bulk?ids=... . Last step
    # of all, run only once every other record above is already cleaned
    # up. Success is judged by status + no error in the body (see
    # _record_delete_by_status), same reasoning as the plan step above.
    # Skipped if the plan type was never actually created this run.
    if _created(created_plantype):
        step_start = _log_len()
        response = plantype_service.delete_bulk([created_plantype_id])
        _record_delete_by_status("plantype", created_plantype_id, response, calls=_calls_since(step_start))
    else:
        _record_cleanup(
            "plantype", created_plantype_id, note="Skipped — creation failed this run, no real record to delete"
        )

    # Marks every call made during this teardown as already "consumed," so
    # that even if some future test collection order ever put another test
    # after this one (this fixture's teardown always runs dead last today,
    # since it's the sole autouse session fixture every test depends on),
    # pytest_runtest_makereport's offset-based direct_calls would start
    # clean from here rather than sweeping up these cleanup calls as if
    # that later test had made them itself.
    global _api_call_log_offset
    _api_call_log_offset = _log_len()
