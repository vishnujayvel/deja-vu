"""Unit + contract tests for evals/run_evals.py (deja-vu-v2.21).

evals/run_evals.py's own --offline mode already exercises these functions
end-to-end against the real evals/ fixtures on every CI run and refinery
gate (scripts/refinery_gate.py). These tests add fast, isolated unit
coverage for the individual check functions -- in particular the two
coverage-honesty contract checks added for deja-vu-v2.21 -- with
constructed inputs, so a regression in one check is localized instead of
only showing up as an opaque failure against the full fixture set.

These are schema/keyword contract tests, not model-behavior tests: see
evals/observations.md for real script-level observations and why a
keyword check on key_reasons is deliberately weak evidence.
"""

import json
from pathlib import Path

import run_evals

CASE = Path("some-case")


# --------------------------------------------------------- offline, end-to-end ---

def test_run_offline_passes_against_the_real_repo_fixtures():
    """Regression guard: the shipped evals/ fixtures stay internally consistent."""
    assert run_evals.run_offline() == 0


# ---------------------------------------------------- coverage-honesty checks ---

def _packet(candidates=None, sweep_errors=None, reasons=None):
    input_obj = {
        "sweep": {
            "lanes_run": ["github"],
            "candidates": candidates or [],
            "errors": sweep_errors or [],
        }
    }
    expected_obj = {"key_reasons": reasons if reasons is not None else ["some reason"]}
    return input_obj, expected_obj


def test_sweep_errors_acknowledged_passes_silently():
    input_obj, expected_obj = _packet(
        sweep_errors=["github: unsupported -- rate limited"],
        reasons=["coverage is incomplete because the github lane is unsupported"],
    )
    errors = []
    run_evals.check_verdict_acknowledges_sweep_errors(
        CASE, input_obj, expected_obj, errors
    )
    assert errors == []


def test_sweep_errors_unacknowledged_is_flagged():
    input_obj, expected_obj = _packet(
        sweep_errors=["github: unsupported -- rate limited"],
        reasons=["adopt the top candidate, it looks great"],
    )
    errors = []
    run_evals.check_verdict_acknowledges_sweep_errors(
        CASE, input_obj, expected_obj, errors
    )
    assert len(errors) == 1
    assert "sweep.errors is non-empty" in errors[0]


def test_no_sweep_errors_never_flags():
    input_obj, expected_obj = _packet(sweep_errors=[], reasons=["nothing to see here"])
    errors = []
    run_evals.check_verdict_acknowledges_sweep_errors(
        CASE, input_obj, expected_obj, errors
    )
    assert errors == []


def test_null_license_candidate_acknowledged_passes_silently():
    input_obj, expected_obj = _packet(
        candidates=[{"name": "x", "license": None}],
        reasons=["no LICENSE file means all rights reserved"],
    )
    errors = []
    run_evals.check_null_license_candidates_are_acknowledged(
        CASE, input_obj, expected_obj, errors
    )
    assert errors == []


def test_null_license_candidate_unacknowledged_is_flagged():
    input_obj, expected_obj = _packet(
        candidates=[{"name": "x", "license": None}],
        reasons=["this is the best-fit candidate, adopt it"],
    )
    errors = []
    run_evals.check_null_license_candidates_are_acknowledged(
        CASE, input_obj, expected_obj, errors
    )
    assert len(errors) == 1
    assert "license: null" in errors[0]


def test_non_null_license_candidate_never_flags():
    input_obj, expected_obj = _packet(
        candidates=[{"name": "x", "license": "MIT"}],
        reasons=["adopt it, permissively licensed"],
    )
    errors = []
    run_evals.check_null_license_candidates_are_acknowledged(
        CASE, input_obj, expected_obj, errors
    )
    assert errors == []


def test_unsupported_required_lane_without_human_authority_is_flagged():
    input_obj, expected_obj = _packet(
        sweep_errors=["github: unsupported -- no fallback"],
        reasons=["build it"],
    )
    expected_obj["authority"] = "agent-authorized"
    errors = []
    run_evals.check_unsupported_required_lane_requires_human_authority(
        CASE, input_obj, expected_obj, errors
    )
    assert len(errors) == 1
    assert "human-required" in errors[0]


def test_unsupported_required_lane_with_human_authority_passes():
    input_obj, expected_obj = _packet(
        sweep_errors=["github: unsupported -- no fallback"],
        reasons=["coverage is incomplete, halt for a human decision"],
    )
    expected_obj["authority"] = "human-required"
    errors = []
    run_evals.check_unsupported_required_lane_requires_human_authority(
        CASE, input_obj, expected_obj, errors
    )
    assert errors == []


def test_degraded_but_not_unsupported_lane_never_requires_authority_field():
    input_obj, expected_obj = _packet(
        sweep_errors=["grep: 429 backoff retries exhausted"],
        reasons=["adopt the found candidate despite the grep gap"],
    )
    errors = []
    run_evals.check_unsupported_required_lane_requires_human_authority(
        CASE, input_obj, expected_obj, errors
    )
    assert errors == []


# ---------------------------------------------------------- validate_verdict_case ---

def test_validate_verdict_case_wires_coverage_checks_end_to_end(tmp_path):
    """A schema-valid fixture that hides a real coverage gap must still fail."""
    case_dir = tmp_path / "sneaky-case"
    case_dir.mkdir()
    (case_dir / "input.json").write_text(json.dumps({
        "problem": "need a widget",
        "sweep": {
            "lanes_run": ["github"],
            "candidates": [{"name": "x", "license": None}],
            "errors": ["github: unsupported"],
        },
        "provenance": {"profiles": [], "errors": []},
    }))
    (case_dir / "expected.json").write_text(json.dumps({
        "verdict": "BUILD",
        "key_reasons": ["just build it, seems fine"],
    }))

    errors = []
    run_evals.validate_verdict_case(case_dir, errors)

    assert any("sweep.errors is non-empty" in e for e in errors)
    assert any("license: null" in e for e in errors)
