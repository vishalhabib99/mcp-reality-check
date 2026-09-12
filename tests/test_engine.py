"""End-to-end tests: these actually launch the real fixture MCP server as a
subprocess and talk to it over real stdio — not mocked. Same discipline as
mcp-doctor/mcp-fuzz: verifies real runtime classification, not just the
input-generation/checks logic in isolation (see test_checks.py, test_
generator.py for that)."""

import sys
from pathlib import Path

import pytest

from mcp_reality_check.engine import run_reality_check
from mcp_reality_check.report import build_report

FIXTURE_SERVER = str(Path(__file__).parent / "fixtures" / "fixture_server.py")
TIMEOUT = 3.0


@pytest.fixture(scope="module")
def raw_report():
    import asyncio

    return asyncio.run(run_reality_check(sys.executable, [FIXTURE_SERVER], timeout=TIMEOUT))


def _result(raw_report, name):
    return next(r for r in raw_report.results if r.tool_name == name)


def test_connects_and_lists_all_six_tools(raw_report):
    assert raw_report.connect_error is None
    names = {r.tool_name for r in raw_report.results}
    assert names == {
        "well_behaved", "secretly_refuses", "returns_empty",
        "genuinely_fails", "no_string_args", "delete_everything",
    }


def test_non_read_only_tool_is_skipped_by_default(raw_report):
    r = _result(raw_report, "delete_everything")
    assert r.tested is False
    assert "readOnlyHint" in r.skip_reason


def test_well_behaved_tool_is_not_flagged(raw_report):
    r = _result(raw_report, "well_behaved")
    assert r.tested is True
    assert r.refusal_in_disguise is None
    assert r.empty_content is False
    assert r.schema_violation is None


def test_well_behaved_tool_echoes_its_input(raw_report):
    r = _result(raw_report, "well_behaved")
    # generate_realistic_arguments should have supplied a real-looking city
    # (e.g. "Paris"), and the fixture's response includes it verbatim.
    assert r.echo_mismatch_inputs == []


def test_disguised_refusal_is_caught(raw_report):
    r = _result(raw_report, "secretly_refuses")
    assert r.tested is True
    assert r.refusal_in_disguise is not None
    assert "don't have access" in r.refusal_in_disguise or "i'm sorry, but" in r.refusal_in_disguise.lower()


def test_empty_content_on_success_is_caught(raw_report):
    r = _result(raw_report, "returns_empty")
    assert r.tested is True
    assert r.empty_content is True


def test_honest_failure_is_not_flagged_as_a_disguised_refusal(raw_report):
    r = _result(raw_report, "genuinely_fails")
    assert r.tested is True
    # The SDK catches the raised ValueError and returns isError=true —
    # already honest about failing, so none of the content checks should
    # even run (skip_reason explains why, not a refusal-in-disguise flag).
    assert r.refusal_in_disguise is None
    assert r.empty_content is False
    assert r.skip_reason is not None and "isError=true" in r.skip_reason


def test_tool_with_no_string_args_has_no_echo_check(raw_report):
    r = _result(raw_report, "no_string_args")
    assert r.tested is True
    assert r.echo_mismatch_inputs is None


def test_report_scores_only_the_checkable_tools(raw_report):
    report = build_report(raw_report)
    # 6 tools total: 1 skipped (not read-only), 1 honest failure (not
    # checkable), leaving 4 checkable — well_behaved, secretly_refuses,
    # returns_empty, no_string_args.
    assert report.tested_count == 5
    assert report.skipped_count == 1
    assert report.checkable_count == 4
    assert report.flagged_count == 2  # secretly_refuses + returns_empty
    assert report.sanity_percent == 50.0
    assert report.grade == "D"


ENV_REQUIRED_SERVER = str(Path(__file__).parent / "fixtures" / "env_required_server.py")


def test_env_kwarg_is_passed_through_to_the_target_server():
    # Found via real dogfooding, not speculatively: sooperset/mcp-atlassian
    # (5.9k stars) registers zero tools without JIRA_*/CONFLUENCE_* config,
    # and this CLI had no way to supply it at all until now — mcp-fuzz
    # already solved the identical problem for brave-search-mcp-server.
    import asyncio

    report = asyncio.run(run_reality_check(
        sys.executable, [ENV_REQUIRED_SERVER],
        env={"REQUIRED_TEST_KEY": "expected-value"}, timeout=TIMEOUT,
    ))
    assert report.connect_error is None


def test_no_env_kwarg_does_not_leak_or_guess_the_required_value():
    # Without an explicit env, the server must NOT start — confirms this
    # isn't accidentally inheriting the operator's full shell environment
    # (a real secret-leaking regression), only the SDK's own minimal safe
    # default (PATH, HOME, ...).
    import asyncio

    report = asyncio.run(run_reality_check(sys.executable, [ENV_REQUIRED_SERVER], timeout=TIMEOUT))
    assert report.connect_error is not None


def test_env_kwarg_merges_onto_safe_defaults_rather_than_replacing_them():
    # A caller passing one custom var must not lose PATH/HOME in the
    # process — verified against a real failure mode: passing only an API
    # key with no PATH would break the interpreter/npx itself before the
    # target server ever runs.
    from mcp.client.stdio import get_default_environment

    from mcp_reality_check.engine import _merged_env

    merged = _merged_env({"SOME_API_KEY": "x"})
    assert merged["SOME_API_KEY"] == "x"
    for key in get_default_environment():
        assert key in merged


def test_no_env_is_passed_through_unchanged():
    from mcp_reality_check.engine import _merged_env

    assert _merged_env(None) is None
    assert _merged_env({}) == {}
