"""Self-tests for the result block of the report email
(src/utils/report_mailer.py::format_results_summary) — not API tests, so no
fixtures and no network."""
from src.utils.report_mailer import format_results_summary


def _result(test, outcome, reason=""):
    return {"test": test, "outcome": outcome, "reason": reason}


def test_summary_with_no_failures_says_so():
    summary = format_results_summary(
        [_result("tests/a.py::test_one", "passed"), _result("tests/a.py::test_two", "passed"),
         _result("tests/b.py::test_three", "skipped")]
    )
    assert "Result: 3 tests run - 2 passed, 0 failed, 0 errors, 1 skipped." in summary
    assert "Failed test cases: none." in summary


def test_summary_lists_each_failed_test_with_the_count():
    summary = format_results_summary(
        [_result("tests/a.py::test_ok", "passed"),
         _result("tests/a.py::test_bad", "failed", "AssertionError: Expected 2xx, got 400\nassert 400 == 201\n + where 400 = ..."),
         _result("tests/b.py::test_worse", "failed", "AssertionError: boom")]
    )
    assert "Result: 3 tests run - 1 passed, 2 failed, 0 errors, 0 skipped." in summary
    assert "Failed test cases (2):" in summary
    assert "1. tests/a.py::test_bad - AssertionError: Expected 2xx, got 400\n" in summary + "\n"
    assert "where 400" not in summary  # only the first line of the reason is used
    assert "2. tests/b.py::test_worse - AssertionError: boom" in summary
    assert "test_ok" not in summary


def test_summary_counts_errors_and_expected_failures_separately_and_shortens_long_reasons():
    summary = format_results_summary(
        [_result("tests/a.py::test_ok", "passed"),
         _result("tests/a.py::test_ok", "error", "teardown exploded"),
         _result("tests/c.py::test_known_gap", "xfailed"),
         _result("tests/d.py::test_long", "failed", "x" * 500)]
    )
    assert "3 tests run - 1 passed, 1 failed, 1 errors, 0 skipped (1 expected failures, 0 unexpected passes)." in summary
    assert "tests/a.py::test_ok [error] - teardown exploded" in summary
    assert "test_known_gap" not in summary.split("Failed test cases")[1]
    long_line = next(line for line in summary.splitlines() if "test_long" in line)
    assert long_line.endswith("...") and len(long_line) < 260
