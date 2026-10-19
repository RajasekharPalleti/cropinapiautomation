"""Regenerates docs/Cropin_API_Test_Scenarios.xlsx from the ROWS list below —
the single source of truth for the test-case catalogue, kept as a script
(not hand-edited in Excel) so re-running it always produces the same
formatting. ROWS is meant to be extended, not the workbook.

Whenever a new test function is scaffolded (per the intake workflow in
CLAUDE.md / README.md section 6), append a matching tuple to ROWS — same
five columns, same order the test's own module section already uses — then
re-run this script:

    python scripts/build_test_scenarios_xlsx.py

Test Case ID convention: TC-<MODULE>-NNN, numbered sequentially within its
module section (e.g. the next farmer test after TC-FARMER-002 is
TC-FARMER-003). A brand-new module gets its own MODULE_SECTION_STARTS entry
and starts at NNN=001.

Exception: the TASK FILL section's IDs mirror the Task Fill spec's own
numbering (TC_TF_001 -> TC-TF-001, 101, 201, ... — non-contiguous on
purpose) so each row traces straight back to that document.

Test Case Name convention: a short human-readable title, e.g. "Farmer
Creation" or "Farmer Edit" — not the raw pytest function name. Put the
actual function (or cleanup step) name as a `backticked` prefix at the
start of the "What It Will Do" text instead, e.g.
"(`test_create_farmer_success`) Creates the one shared farmer record...",
so it's still easy to find the code from a row without it being the
column someone reads first.
"""
import os

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(REPO_ROOT, "docs", "Cropin_API_Test_Scenarios.xlsx")

HEADERS = ["Test Case ID", "Test Case Name", "Test Type", "What It Will Do", "APIs Used"]

# Test Type reflects the actual pytest markers on each test function (see
# tests/*/test_*.py) — most business-flow tests carry both sanity and
# regression, but the auth negative-path tests only carry regression
# (they're deliberately excluded from sanity runs), the framework
# self-tests carry no test-type marker at all, and the CLEANUP section's
# rows are teardown steps rather than pytest tests — tagged "Cleanup"
# since they don't carry a sanity/regression marker at all, but run every
# time the suite does (see tests/conftest.py's cleanup_created_records).
# "smoke" is registered in pyproject.toml but currently applied to no
# test — removed from every test for now (still easy to bring back).
_TASK_GET = "GET /services/farm/api/tasks/{id}"
_TASK_FILL = "PUT /services/farm/api/tasks"

# Test Case Name is a human-readable title (e.g. "Farmer Creation") — the
# underlying pytest function / cleanup step name is kept as a `backticked`
# prefix on the "What It Will Do" text instead, so nothing is lost for
# grepping the code, it's just not the headline column anymore.
ROWS = [
    # --- AUTH ---
    ("TC-AUTH-001", "Login - Valid Credentials", "Sanity, Regression",
     "(`test_generate_token_success`) Happy-path login: requests an access token using valid tenant/credentials and verifies the response is 200 with a valid token schema. Foundational test — if it fails, the entire run aborts instead of just this test failing.",
     "POST /auth/realms/{tenant_code}/protocol/openid-connect/token"),
    ("TC-AUTH-002", "Login - Token Persisted to Session", "Sanity, Regression",
     "(`test_generate_token_stores_tokens_on_session`) Verifies that after a successful login, the access_token and refresh_token are correctly stored on the shared session context so every other service call can reuse them.",
     "POST /auth/realms/{tenant_code}/protocol/openid-connect/token"),
    ("TC-AUTH-003", "Login - Invalid Credentials", "Regression",
     "(`test_generate_token_fails_with_invalid_credentials`) Negative: attempts login with an invalid username/password and verifies the API rejects it with 401.",
     "POST /auth/realms/{tenant_code}/protocol/openid-connect/token"),
    ("TC-AUTH-004", "Login - Invalid Tenant Code", "Regression",
     "(`test_generate_token_fails_with_invalid_tenant_code`) Negative: attempts login against an unknown/invalid tenant realm and verifies the API returns 400 or 404.",
     "POST /auth/realms/{invalid_tenant_code}/protocol/openid-connect/token"),
    ("TC-AUTH-005", "Login - Invalid Client Secret", "Regression",
     "(`test_generate_token_fails_with_invalid_client_secret`) Negative: attempts login with an invalid client_secret and verifies the API rejects it with 400.",
     "POST /auth/realms/{tenant_code}/protocol/openid-connect/token"),
    ("TC-AUTH-006", "Login - Missing Grant Type", "Regression",
     "(`test_generate_token_fails_when_grant_type_missing`) Negative: sends a token request with the grant_type field missing and verifies the API rejects it with 400.",
     "POST /auth/realms/{tenant_code}/protocol/openid-connect/token"),

    # --- FARMER ---
    ("TC-FARMER-001", "Farmer Creation", "Sanity, Regression",
     "(`test_create_farmer_success`) Creates the one shared farmer record used for the whole run and verifies the create call returns 201.",
     "POST /services/farm/api/farmers"),
    ("TC-FARMER-002", "Farmer Edit", "Sanity, Regression",
     "(`test_edit_farmer_updates_first_name`) Fetches the shared farmer, appends a timestamp to firstName, PUTs the updated record back, and verifies the update returns 200.",
     "GET /services/farm/api/farmers/{id}\nPUT /services/farm/api/farmers"),

    # --- ASSET ---
    ("TC-ASSET-001", "Asset Creation", "Sanity, Regression",
     "(`test_create_asset_success`) Creates the one shared asset (owned by the shared farmer) used for the whole run and verifies the create call returns 201.",
     "POST /services/farm/api/assets"),
    ("TC-ASSET-002", "Asset Edit", "Sanity, Regression",
     "(`test_edit_asset_updates_name`) Fetches the shared asset, appends a timestamp to name, PUTs the updated record back, and verifies the update returns 200.",
     "GET /services/farm/api/assets/{id}\nPUT /services/farm/api/assets"),

    # --- PLAN TYPE ---
    ("TC-PLANTYPE-001", "Plan Type Creation", "Sanity, Regression",
     "(`test_create_plantype_success`) Creates the one shared plan type used for the whole run and verifies the create call returns 201.",
     "POST /services/farm/api/plan-types"),
    ("TC-PLANTYPE-002", "Plan Type Edit", "Sanity, Regression",
     "(`test_edit_plantype_updates_name`) Fetches the shared plan type, appends a timestamp to name, PUTs the updated record back, and verifies the update returns 200.",
     "GET /services/farm/api/plan-types/{id}\nPUT /services/farm/api/plan-types"),

    # --- CROP VARIETY ---
    ("TC-VARIETY-001", "Crop Variety Creation", "Sanity, Regression",
     "(`test_create_crop_variety_success`) Resolves crop-stage and harvest-grade ids live by name, creates the one shared crop variety, then adds its mandatory additional-attribute record; verifies both calls return 201.",
     "GET /services/farm/api/crop-stages\nGET /services/master/api/harvest-grades\nPOST /services/farm/api/varieties\nPUT /services/farm/api/additional-attribute"),
    ("TC-VARIETY-002", "Crop Variety Edit", "Sanity, Regression",
     "(`test_edit_crop_variety_updates_name`) Fetches the shared crop variety, appends a timestamp to name, PUTs the updated record back, and verifies the update returns 200.",
     "GET /services/farm/api/varieties/{id}\nPUT /services/farm/api/varieties"),

    # --- PLAN ---
    ("TC-PLAN-001", "Plan Creation (Linked to Crop Variety)", "Sanity, Regression",
     "(`test_add_plan_to_crop_variety_success`) Links the shared plan type and crop variety by creating a plan — reads the plan type's current details live as part of building the payload — and verifies the create call returns 200.",
     "GET /services/farm/api/plan-types/{id}\nPOST /services/farm/api/plans"),

    # --- PROJECT ---
    ("TC-PROJECT-001", "Project Creation", "Sanity, Regression",
     "(`test_create_project_success`) Creates the one shared project used for the whole run and verifies the create call returns 201.",
     "POST /services/farm/api/projects"),
    ("TC-PROJECT-002", "Add Asset to Project", "Sanity, Regression",
     "(`test_add_asset_to_project_success`) Adds the shared asset to the shared project as a probable asset and verifies at least one record completed successfully.",
     "POST /services/farm/api/projects/{id}/probable-assets"),
    ("TC-PROJECT-003", "Validate Project Assets", "Sanity, Regression",
     "(`test_validate_project_assets_success`) Self-validates the project-asset association and verifies it returns non-empty croppableAreaIds with zero failed records.",
     "POST /services/farm/api/projects/{id}/self-validate-project-assets?cloneFlag=false"),
    ("TC-PROJECT-004", "Project Execution", "Sanity, Regression",
     "(`test_execute_project_completes`) Starts execution on the shared project and polls the async job until it finishes, verifying the final status is COMPLETED.",
     "POST /services/farm/api/projects/{id}/start-execution\nGET /services/farm/api/bulk-process/{execution_id} (polled)"),
    ("TC-PROJECT-005", "Croppable Area - Add Variety and Sowing Date", "Sanity, Regression",
     "(`test_add_variety_and_sowing_date_to_croppable_area`) Fetches the croppable area auto-created for the project, updates it with the shared crop variety and a sowing date, and verifies the PUT response echoes both back correctly.",
     "GET /services/farm/api/croppable-areas/{id}\nPUT /services/farm/api/croppable-areas"),
    ("TC-PROJECT-006", "Croppable Area - Verify Creation", "Sanity, Regression",
     "(`test_verify_croppable_area_created`) Re-fetches the croppable area by id and verifies the returned id matches the one produced during asset validation.",
     "GET /services/farm/api/croppable-areas/{id}"),
    ("TC-PROJECT-007", "Croppable Area - Verify Variety and Sowing Date", "Sanity, Regression",
     "(`test_verify_croppable_area_variety_and_sowing_date`) Re-fetches the croppable area with a fresh GET (not the PUT echo) to confirm the variety and sowing date update actually persisted on the server.",
     "GET /services/farm/api/croppable-areas/{id}"),
    ("TC-PROJECT-008", "Croppable Area - Verify Plan Type Tasks", "Sanity, Regression",
     "(`test_verify_plan_type_tasks_pulled_to_croppable_area`) Verifies that once the variety (linked to a plan and plan type) is assigned to the croppable area, the plan's tasks — with the correct planId, plan type name, and scheduled dates — pull through onto the croppable area.",
     "GET /services/farm/api/tasks/croppablearea/{id}?sort=lastModifiedDate,desc"),

    # --- TASK FILL (tests/task/). IDs mirror the Task Fill spec's own numbers
    # (TC_TF_001 -> TC-TF-001) so every row traces back to that document.
    # Only the two happy-path draft scenarios are sanity; the rest are regression.
    # Every scenario that fills a task also reads it back with GET (and claims the
    # task from the plan's tasks on the croppable area); shared-fill scenarios
    # (001-007, 302-306, 401) all assert on ONE fill performed once per run.
    ("TC-TF-001", "Task Fill - All Valid Data (Happy Path)", "Regression",
     "(`test_fill_task_with_all_valid_data`) Fills a task with all valid data (custom attributes, chemical, execution day = today + 1) and verifies the full set of post-fill checks A1-A12: status complete, execution dates, sowing/harvest dates, custom attributes, chemical, total, filledBy, identifiers, lastModifiedDate.",
     _TASK_GET + "\n" + _TASK_FILL),
    ("TC-TF-002", "Task Fill - Response Reflects Submitted Data", "Regression",
     "(`test_fill_response_body_reflects_submitted_data`) The fill response itself carries the task id, status complete, the execution date and the submitted custom attributes.",
     _TASK_FILL),
    ("TC-TF-003", "Task Fill - Execution Date In Every Date Field", "Regression",
     "(`test_execution_date_is_today_plus_offset_in_every_date_field`) After the fill, executedOn, expExecutedOn, startDate, endDate and the standard-attributes executedOn all carry the execution day.",
     _TASK_GET),
    ("TC-TF-005", "Task Fill - Total Chemical Quantity Equals Quantity x Audited Area", "Regression",
     "(`test_total_chemical_quantity_is_quantity_times_audited_area`) The stored total chemical quantity is the entered quantity multiplied by the croppable area's audited area (the server doesn't compute it, the request does) in the expected unit.",
     _TASK_GET),
    ("TC-TF-006", "Task Fill - Custom Attributes Persisted", "Regression",
     "(`test_custom_attributes_persisted`) The text, dropdown and smart-compute (land name) custom attributes are stored exactly as sent. Attribute names are read off the run's plan type, since they carry a unique suffix per run.",
     _TASK_GET + "\nGET /services/farm/api/plan-types/{id}"),
    ("TC-TF-007", "Task Fill - Chemical Details Persisted", "Regression",
     "(`test_chemical_details_persisted`) Chemical type, chemical id, per-quantity, quantity and concentration are stored exactly as sent.",
     _TASK_GET),
    ("TC-TF-008", "Task Fill - Save As Draft", "Sanity, Regression",
     "(`test_save_task_as_draft`) Happy path, step 1: saves the task as a draft (isSavedAsDraft = true, status kept open — the server completes any body whose status is COMPLETE). The task is not completed and what was entered is kept.",
     _TASK_GET + "\n" + _TASK_FILL),
    ("TC-TF-009", "Task Fill - Complete Task Saved As Draft", "Sanity, Regression",
     "(`test_complete_task_previously_saved_as_draft`) Happy path, step 2: completes the task TC-TF-008 saved as a draft (new clientId, isSavedAsDraft = false) and verifies A1-A12.",
     _TASK_GET + "\n" + _TASK_FILL),
    ("TC-TF-010", "Task Fill - Without Optional Chemical Section", "Regression",
     "(`test_fill_without_optional_chemical_section`) Fills with an empty chemical list. Accepted if chemical is optional, rejected if mandatory (frozen in test data after the first run); either way the task's state must agree with the response.",
     _TASK_GET + "\n" + _TASK_FILL),
    ("TC-TF-011", "Task Fill - Optional Standard Attributes", "Regression",
     "(`test_optional_standard_attributes_filled`) costPerArea = 10 and totalCost = 29.8 are accepted and persisted as sent.",
     _TASK_GET + "\n" + _TASK_FILL),

    ("TC-TF-101", "Task Fill - Task Id Does Not Exist", "Regression",
     "(`test_task_id_does_not_exist`) Negative: fills with id 999999999. Rejected (400/404) with an error message, and no task is changed.",
     _TASK_FILL),
    ("TC-TF-102", "Task Fill - Missing Task Id", "Regression",
     "(`test_missing_task_id`) Negative: fills with no id. Must be rejected, and must not silently create a new task (task count unchanged).",
     _TASK_FILL + "\nGET /services/farm/api/tasks/croppablearea/{id}"),
    ("TC-TF-103", "Task Fill - Invalid Status Value", "Regression",
     "(`test_invalid_status_value`) Negative: status \"DONE\" is rejected and the task stays open.",
     _TASK_FILL),
    ("TC-TF-104", "Task Fill - Missing Executed On", "Regression",
     "(`test_missing_executed_on_with_status_complete`) Negative: completing a task with no executedOn (top level and standard attributes) is rejected and the task stays open.",
     _TASK_FILL),
    ("TC-TF-105", "Task Fill - Invalid Date Format For Executed On", "Regression",
     "(`test_invalid_date_format_for_executed_on`) Negative: executedOn \"20-10-2026\" is rejected and the task stays open.",
     _TASK_FILL),
    ("TC-TF-106", "Task Fill - Mandatory Custom Attribute Missing", "Regression",
     "(`test_mandatory_custom_attribute_missing`) Drops the text custom attribute. If the plan type marks it mandatory the fill is rejected and the task stays open; if not (as in this suite's plan type) it is accepted and the attribute is simply absent.",
     _TASK_FILL),
    ("TC-TF-107", "Task Fill - Invalid Dropdown Option Value", "Regression",
     "(`test_invalid_dropdown_option_value`) Negative: a dropdown value that isn't one of the options (\"999\") is rejected and the task stays open.",
     _TASK_FILL),
    ("TC-TF-108", "Task Fill - Unknown Custom Attribute Key", "Regression",
     "(`test_unknown_custom_attribute_key`) An extra, unknown custom attribute key is rejected, or accepted with the key ignored (never persisted).",
     _TASK_FILL),
    ("TC-TF-109", "Task Fill - Invalid Chemical Id", "Regression",
     "(`test_invalid_chemical_id`) Negative: chemical id 999999999 is rejected and the task stays open.",
     _TASK_FILL),
    ("TC-TF-110", "Task Fill - Invalid Chemical Unit", "Regression",
     "(`test_invalid_chemical_unit`) Negative: chemical quantity unit \"INVALID_UNIT\" is rejected and the task stays open.",
     _TASK_FILL),
    ("TC-TF-111", "Task Fill - Negative Chemical Quantity", "Regression",
     "(`test_negative_chemical_quantity`) Negative: a quantity of -10 (total recalculated to match) is rejected and the task stays open.",
     _TASK_FILL),
    ("TC-TF-112", "Task Fill - Plan Type Does Not Match Task", "Regression",
     "(`test_plan_type_does_not_match_task`) Negative: planTypeId 1 is rejected and the task's own plan type is unchanged.",
     _TASK_FILL),
    ("TC-TF-113", "Task Fill - Croppable Area Does Not Match Task", "Regression",
     "(`test_croppable_area_does_not_match_task`) Negative: croppableAreaId 1 is rejected and the task's own croppable area is unchanged.",
     _TASK_FILL),
    ("TC-TF-114", "Task Fill - Empty Request Body", "Regression",
     "(`test_empty_request_body`) Negative: an empty JSON object body is rejected and the task stays open.",
     _TASK_FILL),
    ("TC-TF-115", "Task Fill - Malformed JSON", "Regression",
     "(`test_malformed_json`) Negative: a truncated JSON body is rejected and the task stays open.",
     _TASK_FILL),
    ("TC-TF-116", "Task Fill - Wrong Content Type", "Regression",
     "(`test_wrong_content_type`) Negative: a valid JSON body sent as Content-Type text/plain is rejected (400/415) and the task stays open.",
     _TASK_FILL),
    ("TC-TF-117", "Task Fill - Wrong Data Type For Id", "Regression",
     "(`test_wrong_data_type_for_id`) Negative: id \"abc\" is rejected and the task stays open.",
     _TASK_FILL),
    ("TC-TF-118", "Task Fill - Typo Key Instead Of Correct Key", "Regression",
     "(`test_get_typo_key_sent_instead_of_correct_key`) The GET response's misspelled key (chemicalQuanity) sent in place of chemicalQuantity is ignored or rejected.",
     _TASK_FILL),

    ("TC-TF-201", "Task Fill - Execution Date Is Today", "Regression",
     "(`test_execution_date_is_today`) Fills with an execution day of today (a boundary of the fixed dates and the sowing date) and verifies every date field.",
     _TASK_GET + "\n" + _TASK_FILL),
    ("TC-TF-202", "Task Fill - Execution Date Is Earliest Fixed Date", "Regression",
     "(`test_execution_date_is_earliest_fixed_date`) Fills with the earliest of the task's fixed execution dates.",
     _TASK_GET + "\n" + _TASK_FILL),
    ("TC-TF-203", "Task Fill - Execution Date Is Latest Fixed Date", "Regression",
     "(`test_execution_date_is_latest_fixed_date`) Fills with the latest of the task's fixed execution dates.",
     _TASK_GET + "\n" + _TASK_FILL),
    ("TC-TF-204", "Task Fill - Execution Date Not In Fixed Dates", "Regression",
     "(`test_execution_date_not_in_fixed_dates`) Negative: five days past the last fixed date is rejected and the task stays open.",
     _TASK_FILL),
    ("TC-TF-205", "Task Fill - Execution Date Before Sowing Date", "Regression",
     "(`test_execution_date_before_sowing_date`) Negative: the day before the croppable area's sowing date is rejected and the task stays open.",
     _TASK_FILL),
    ("TC-TF-206", "Task Fill - Execution Date After Harvest Date", "Regression",
     "(`test_execution_date_after_harvest_date`) The day after harvest: accepted or rejected (frozen in test data after the first run), with the task's state agreeing with the response.",
     _TASK_FILL),
    ("TC-TF-207", "Task Fill - Chemical Quantity Zero", "Regression",
     "(`test_chemical_quantity_zero`) Quantity 0 (total 0): accepted or rejected (frozen in test data after the first run), with the task's state agreeing with the response.",
     _TASK_FILL),
    ("TC-TF-208", "Task Fill - Decimal Chemical Quantity", "Regression",
     "(`test_decimal_chemical_quantity`) Quantity 12.5: accepted, and the total is stored as 12.5 x the audited area exactly.",
     _TASK_GET + "\n" + _TASK_FILL),
    ("TC-TF-209", "Task Fill - Text Attribute Max Length", "Regression",
     "(`test_text_attribute_max_length`) A 256-character text attribute is refused (leaving the task open), then a 255-character one is accepted and stored in full.",
     _TASK_GET + "\n" + _TASK_FILL),
    ("TC-TF-210", "Task Fill - Special Characters and Unicode", "Regression",
     "(`test_text_attribute_special_characters_and_unicode`) A text attribute with accents, symbols, Telugu script and an emoji is stored character for character.",
     _TASK_GET + "\n" + _TASK_FILL),

    ("TC-TF-301", "Task Fill - Total Chemical Mismatch", "Regression",
     "(`test_total_chemical_mismatch_is_not_stored_as_sent`) Sends a total that isn't quantity x audited area. Rejected or recalculated passes; if the server stores the wrong figure it is reported as an expected failure (it doesn't validate the total, which is why the request computes it).",
     _TASK_GET + "\n" + _TASK_FILL),
    ("TC-TF-302", "Task Fill - Identifiers Unchanged", "Regression",
     "(`test_identifiers_unchanged_after_fill`) id, planId, parentPlanId, planTypeId, croppableAreaId, landId and projectId equal their pre-fill values.",
     _TASK_GET),
    ("TC-TF-303", "Task Fill - Direct Adhoc Task Preserved", "Regression",
     "(`test_direct_adhoc_task_preserved`) The request sends directAdhocTask as null; the stored value must be unchanged by the fill.",
     _TASK_GET),
    ("TC-TF-304", "Task Fill - Created Date Not Overwritten", "Regression",
     "(`test_created_date_not_overwritten`) The fill body sends the current date as createdDate; the plan's own stored createdDate is unchanged after the fill, and so is the task's own createdDate when exposed.",
     _TASK_GET + "\nGET /services/farm/api/plans/{id}"),
    ("TC-TF-305", "Task Fill - Last Modified Date Updated", "Regression",
     "(`test_last_modified_date_updated`) The post-fill lastModifiedDate is later than the pre-fill one.",
     _TASK_GET),
    ("TC-TF-306", "Task Fill - Filled By and Filled Date Set", "Regression",
     "(`test_filled_by_and_filled_date_set`) filledBy equals what was sent and the server stamps filledDate on completion.",
     _TASK_GET),

    ("TC-TF-401", "Task Fill - Fill Completed Task Again", "Regression",
     "(`test_fill_already_completed_task_again`) A second fill (new clientId) of an already completed task is accepted as an edit or refused as locked (frozen in test data), but never leaves a duplicate task behind.",
     _TASK_FILL + "\nGET /services/farm/api/tasks/croppablearea/{id}"),
    ("TC-TF-402", "Task Fill - Same Client Id Sent Twice", "Regression",
     "(`test_same_client_id_sent_twice`) Replays an identical request (same clientId): handled idempotently or rejected, with one completion recorded and no extra task either way.",
     _TASK_GET + "\n" + _TASK_FILL + "\nGET /services/farm/api/tasks/croppablearea/{id}"),
    ("TC-TF-403", "Task Fill - Concurrent Fill Requests", "Regression",
     "(`test_concurrent_fill_requests`) Two fills of the same task in parallel (different clientIds): no server error, and the task ends in a consistent state.",
     _TASK_GET + "\n" + _TASK_FILL),

    ("TC-TF-501", "Task Fill - No Authorization Header", "Regression",
     "(`test_no_authorization_header`) Security: a fill with no Authorization header is rejected with 401 and the task stays open.",
     _TASK_FILL),
    ("TC-TF-502", "Task Fill - Invalid Token", "Regression",
     "(`test_invalid_token`) Security: a fill with a bogus bearer token is rejected with 401 and the task stays open.",
     _TASK_FILL),
    ("TC-TF-504", "Task Fill - Script Injection In Text Attribute", "Regression",
     "(`test_script_injection_in_text_attribute`) A script tag in a text attribute is rejected, or stored as plain text (verbatim or HTML-escaped) — never anything else.",
     _TASK_GET + "\n" + _TASK_FILL),

    # --- FORM (tests/form/). All run after the task-fill tests, in execution
    # order create -> update -> fill -> the two negative (regression-only)
    # scenarios, on the run's own crop variety and farmer. The form is deleted by
    # the CLEANUP section's TC-CLEANUP-003; there is no delete API for filled
    # forms, so each run leaves one filled form behind.
    ("TC-FORM-001", "Form Creation", "Sanity, Regression",
     "(`test_create_form_success`) Creates the one shared farmer form for the run (three custom attributes: text, drop down, date; linked to the shared crop variety; valid from today for 10 days; unique name; the body carries the run's clientId, one uuid4 generated per run and reused by the update and the fill) and verifies the create call returns 200 or 201 (the exact code is confirmed on the first real run) with the id, name, status, form type, variety, dates, attributes and the run's clientId echoed — then re-fetches it with a fresh GET to confirm the form was actually stored (name, status DISABLE, form type Farmer, attributes incl. dropdown options, variety, validity dates, clientId, not deleted).",
     "POST /services/form/api/forms\nGET /services/form/api/forms/{id}"),
    ("TC-FORM-002", "Form Update", "Sanity, Regression",
     "(`test_update_form_success`) Takes the create response of the shared form, changes only the name (appends \" updated\") and PUTs it back, then verifies the PUT returns 200 with the same id and the new name and that status, form type, variety, validity dates and attributes are unchanged — and re-fetches the form with a fresh GET to confirm the new name was actually stored, the other fields still match what was created, and formTypeName is still Farmer (not overwritten by the create response's null). The run's clientId must still be on the PUT body, the PUT response and the GET, and the GET's lastModifiedDate (the server's current timestamp) must be strictly later than the pre-update GET's — it is not asserted on the PUT response, which echoes the old value.",
     "PUT /services/form/api/forms\nGET /services/form/api/forms/{id}"),
    ("TC-FORM-003", "Form Fill", "Sanity, Regression",
     "(`test_fill_form_success`) Fills the shared form (under its current, updated name) for the shared farmer (text, drop-down option and a date value; the run's shared clientId; the farmer's current name read live) and verifies the call returns 201 with a filled-form id, the form id and form type, the submitted filled values, the farmer id, isDeleted false, isGDPRCompliant true and non-empty filled names. The request carries no id (this is a create). Then reads the filled form back with a GET by the id the POST returned and cross-checks it: form id, form name (name and formName both the form's current name), farmer name (data.firstName as sent, filledName containing it) and farmer id, plus the saved filled values, form version, isDeleted false and agreement with the POST response. The GET must also show the run's clientId (asserted on the GET only) and the dates: data.filledDate is the day that was sent, and createdDate and lastModifiedDate (server-stamped, compared as parsed instants, not strings) are today's UTC date.",
     "GET /services/farm/api/farmers/{id}\nPOST /services/form/api/filled-forms\nGET /services/form/api/filled-forms/{id}"),
    ("TC-FORM-004", "Form Creation - Blank Name", "Regression",
     "(`test_create_form_blank_name_rejected`) Negative: the normal create body (shared crop variety) with name \"\" is rejected with a 4xx (not a server error) and the response carries no new form id. The exact code is frozen in test data (form.expectations) after the first real run; a 2xx fails the test.",
     "POST /services/form/api/forms"),
    ("TC-FORM-005", "Form Fill - Form Does Not Exist", "Regression",
     "(`test_fill_form_unknown_form_id_rejected`) Negative: the normal fill body for the shared farmer with formId 999999999 is rejected — with a 4xx, or the 500 the real server returns for an unknown form id (both allowed in test data, form.expectations) — and the response carries no filled-form id. A 2xx fails the test.",
     "GET /services/farm/api/farmers/{id}\nPOST /services/form/api/filled-forms"),

    # --- CLEANUP (teardown steps in tests/conftest.py's cleanup_created_records
    # autouse fixture, not standalone pytest test functions — no pass/fail row of
    # their own, run once at the end of every run in this fixed order, each
    # skipped individually if its own entity was never created this run) ---
    ("TC-CLEANUP-001", "Cleanup - Close and Remove Croppable Area", "Cleanup",
     "(`cleanup_close_and_remove_croppable_area`) Closes the croppable area(s) created via project-asset validation, then removes them through the project's project-assets endpoint (an async job, polled to completion). First step of teardown; skipped if the project itself was never created this run.",
     "GET /services/farm/api/croppable-areas/closed?reasonId=4&ids=...\nPOST /services/farm/api/projects/{id}/project-assets/remove/selected-ids\nGET /services/farm/api/bulk-process/{job_id} (polled)"),
    ("TC-CLEANUP-002", "Cleanup - Delete Plan", "Cleanup",
     "(`cleanup_delete_plan`) Deletes the shared plan created this run. Runs before the crop variety delete below, since the plan references that variety.",
     "DELETE /services/farm/api/plans/bulk?ids=..."),
    ("TC-CLEANUP-003", "Cleanup - Delete Form", "Cleanup",
     "(`cleanup_delete_form`) Deletes the shared form created this run (the form-creation id). Runs before the crop variety delete below, since the form references that variety (its varietyId), and so before the farmer delete too. A 200 alone isn't enough: the response is {\"nonDeletedIds\": [], \"deletedIds\": [id]} and the step only counts as done when the form's id is in deletedIds and nonDeletedIds is empty — anything else is reported as a failed cleanup row with the response body. Skipped if the form was never created this run. The filled form has no delete API, so each run leaves one filled form behind.",
     "DELETE /services/form/api/forms/bulk?ids={id}"),
    ("TC-CLEANUP-004", "Cleanup - Delete Crop Variety", "Cleanup",
     "(`cleanup_delete_crop_variety`) Deletes the shared crop variety created this run. Runs after the plan and form deletes, since both reference it.",
     "DELETE /services/farm/api/varieties/bulk?ids=..."),
    ("TC-CLEANUP-005", "Cleanup - Delete Asset", "Cleanup",
     "(`cleanup_delete_asset`) Deletes the shared asset created this run.",
     "DELETE /services/farm/api/assets/bulk?ids=..."),
    ("TC-CLEANUP-006", "Cleanup - Delete Farmer", "Cleanup",
     "(`cleanup_delete_farmer`) Deletes the shared farmer created this run.",
     "DELETE /services/farm/api/farmers/bulk?ids=..."),
    ("TC-CLEANUP-007", "Cleanup - Stop Project Execution", "Cleanup",
     "(`cleanup_stop_project_execution`) Stops the shared project's execution — an async job, polled to completion — required before the project's other records can be considered fully torn down.",
     "POST /services/farm/api/projects/{id}/stop-execution\nGET /services/farm/api/bulk-process/{job_id} (polled)"),
    ("TC-CLEANUP-008", "Cleanup - Delete Plan Type", "Cleanup",
     "(`cleanup_delete_plan_type`) Deletes the shared plan type created this run. Last step of the whole teardown chain, run only once every other record above is already gone.",
     "DELETE /services/farm/api/plan-types/bulk?ids=..."),

    # --- FRAMEWORK (intake validation gate — internal unit tests, no live API calls) ---
    ("TC-FW-001", "Intake Spec - Valid Spec Accepted", "N/A (no marker)",
     "(`test_valid_spec_passes`) Verifies a fully valid single-scenario intake spec passes schema validation.",
     "N/A (unit test, no live API call)"),
    ("TC-FW-002", "Intake Spec - Unknown Module Rejected", "N/A (no marker)",
     "(`test_unknown_module_rejected`) Verifies an intake spec naming a module outside the allowed set (farmer/asset/plantype/crop_variety/project/login) is rejected.",
     "N/A (unit test, no live API call)"),
    ("TC-FW-003", "Intake Spec - Unsupported Method Rejected", "N/A (no marker)",
     "(`test_unsupported_method_rejected`) Verifies an intake spec using an HTTP method outside the allowed set is rejected.",
     "N/A (unit test, no live API call)"),
    ("TC-FW-004", "Intake Spec - Unknown Test Type Rejected", "N/A (no marker)",
     "(`test_unknown_test_type_rejected`) Verifies an intake spec with a test_type outside sanity/smoke/regression is rejected.",
     "N/A (unit test, no live API call)"),
    ("TC-FW-005", "Intake Spec - Endpoint Must Be Relative Path", "N/A (no marker)",
     "(`test_endpoint_must_be_relative_path`) Verifies an intake spec whose endpoint doesn't start with \"/\" is rejected.",
     "N/A (unit test, no live API call)"),
    ("TC-FW-006", "Intake Spec - Body Method Without Payload Rejected", "N/A (no marker)",
     "(`test_body_method_without_payload_rejected`) Verifies a POST/PUT/PATCH intake spec with an empty payload is rejected.",
     "N/A (unit test, no live API call)"),
    ("TC-FW-007", "Intake Spec - GET Without Payload Accepted", "N/A (no marker)",
     "(`test_get_without_payload_is_fine`) Verifies a GET intake spec with no payload is accepted, since payload is optional for GET.",
     "N/A (unit test, no live API call)"),
    ("TC-FW-008", "Intake Spec - Negative Scenario Requires Error Status", "N/A (no marker)",
     "(`test_negative_scenario_requires_error_status`) Verifies an intake spec marked negative:true but with a non-error expected_status is rejected.",
     "N/A (unit test, no live API call)"),
    ("TC-FW-009", "Intake Spec - Negative Scenario With Error Status Accepted", "N/A (no marker)",
     "(`test_negative_scenario_with_error_status_passes`) Verifies an intake spec marked negative:true with a proper >=400 expected_status is accepted.",
     "N/A (unit test, no live API call)"),
    ("TC-FW-010", "Intake Spec - Batch Validates All Items", "N/A (no marker)",
     "(`test_batch_validates_all_items`) Verifies a batch of several valid intake specs all validate together successfully.",
     "N/A (unit test, no live API call)"),
    ("TC-FW-011", "Intake Spec - Batch Rejects Invalid Item", "N/A (no marker)",
     "(`test_batch_rejects_if_any_item_invalid`) Verifies that if one scenario in an intake batch is invalid, validation of the whole batch fails.",
     "N/A (unit test, no live API call)"),
    # --- FRAMEWORK (report email body) ---
    ("TC-FW-012", "Report Email - Summary With No Failures", "N/A (no marker)",
     "(`test_summary_with_no_failures_says_so`) Verifies the email result block reports how many tests ran, passed, failed (0), errored and were skipped, and says there are no failed test cases.",
     "N/A (unit test, no live API call)"),
    ("TC-FW-013", "Report Email - Summary Lists Failed Tests", "N/A (no marker)",
     "(`test_summary_lists_each_failed_test_with_the_count`) Verifies the email result block gives the failed-test count and lists each failed test case by name with the first line of why it failed (passed tests are not listed).",
     "N/A (unit test, no live API call)"),
    ("TC-FW-014", "Report Email - Summary Errors, Expected Failures And Long Reasons", "N/A (no marker)",
     "(`test_summary_counts_errors_and_expected_failures_separately_and_shortens_long_reasons`) Verifies setup/teardown errors are counted and listed apart from failures, expected failures (xfail) are counted but not listed as failures, and very long failure reasons are shortened.",
     "N/A (unit test, no live API call)"),
]

MODULE_SECTION_STARTS = {
    0: "AUTH",
    6: "FARMER",
    8: "ASSET",
    10: "PLAN TYPE",
    12: "CROP VARIETY",
    14: "PLAN",
    15: "PROJECT",
    23: "TASK FILL",
    73: "FORM",
    78: "CLEANUP",
    86: "FRAMEWORK (Intake Validation, Report Email)",
}

NUM_COLS = len(HEADERS)

FONT_NAME = "Arial"
HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
SECTION_FILL = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
HEADER_FONT = Font(name=FONT_NAME, size=11, bold=True, color="FFFFFF")
SECTION_FONT = Font(name=FONT_NAME, size=10, bold=True, color="1F4E78")
BODY_FONT = Font(name=FONT_NAME, size=10)
ID_FONT = Font(name=FONT_NAME, size=10, bold=True)
thin = Side(style="thin", color="B7B7B7")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
WRAP_TOP_LEFT = Alignment(wrap_text=True, vertical="top", horizontal="left")
WRAP_TOP_CENTER = Alignment(wrap_text=True, vertical="top", horizontal="center")
CENTER_TOP = Alignment(wrap_text=True, vertical="top", horizontal="center")

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Test Scenarios"

# Title row
last_col_letter = chr(ord("A") + NUM_COLS - 1)
ws.merge_cells(f"A1:{last_col_letter}1")
ws["A1"] = "Cropin API Automation — Test Scenario Catalogue"
ws["A1"].font = Font(name=FONT_NAME, size=14, bold=True, color="1F4E78")
ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
ws.row_dimensions[1].height = 26

ws.merge_cells(f"A2:{last_col_letter}2")
ws["A2"] = f"{len(ROWS)} test scenarios across auth/farmer/asset/plantype/crop_variety/plan/project, task fill, form, the cleanup teardown chain, and the intake-validation framework self-tests"
ws["A2"].font = Font(name=FONT_NAME, size=9, italic=True, color="595959")
ws.row_dimensions[2].height = 16

HEADER_ROW = 4

for col_idx, header in enumerate(HEADERS, start=1):
    cell = ws.cell(row=HEADER_ROW, column=col_idx, value=header)
    cell.font = HEADER_FONT
    cell.fill = HEADER_FILL
    cell.alignment = CENTER_TOP
    cell.border = BORDER
ws.row_dimensions[HEADER_ROW].height = 20

current_row = HEADER_ROW + 1
for idx, row_data in enumerate(ROWS):
    if idx in MODULE_SECTION_STARTS:
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=NUM_COLS)
        sec_cell = ws.cell(row=current_row, column=1, value=MODULE_SECTION_STARTS[idx])
        sec_cell.font = SECTION_FONT
        sec_cell.fill = SECTION_FILL
        sec_cell.alignment = Alignment(horizontal="left", vertical="center")
        for c in range(1, NUM_COLS + 1):
            ws.cell(row=current_row, column=c).border = BORDER
        ws.row_dimensions[current_row].height = 18
        current_row += 1

    tc_id, tc_name, tc_type, tc_desc, tc_apis = row_data
    ws.cell(row=current_row, column=1, value=tc_id).font = ID_FONT
    ws.cell(row=current_row, column=2, value=tc_name).font = BODY_FONT
    ws.cell(row=current_row, column=3, value=tc_type).font = BODY_FONT
    ws.cell(row=current_row, column=4, value=tc_desc).font = BODY_FONT
    ws.cell(row=current_row, column=5, value=tc_apis).font = BODY_FONT

    for c in range(1, NUM_COLS + 1):
        cell = ws.cell(row=current_row, column=c)
        cell.alignment = WRAP_TOP_CENTER if c == 3 else WRAP_TOP_LEFT
        cell.border = BORDER

    current_row += 1

# Column widths
ws.column_dimensions["A"].width = 16
ws.column_dimensions["B"].width = 42
ws.column_dimensions["C"].width = 22
ws.column_dimensions["D"].width = 68
ws.column_dimensions["E"].width = 52

# Freeze header
ws.freeze_panes = f"A{HEADER_ROW + 1}"

wb.save(OUT_PATH)
print("Saved:", OUT_PATH)
print("Total data rows:", len(ROWS))
