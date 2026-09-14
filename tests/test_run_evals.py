"""Unit + contract tests for evals/run_evals.py's verdict-fixture checks.

evals/run_evals.py's own --offline mode already exercises these functions
end-to-end against the real evals/ fixtures on every CI run. These tests add
fast, isolated unit coverage for the individual check functions -- in
particular the coverage-honesty, rights, and authority contract checks --
with constructed inputs, so a regression in one check is localized instead of
only showing up as an opaque failure against the full fixture set.

These are schema/keyword/policy-lookup contract tests, not model-behavior
tests: see evals/observations.md for real script- and skill-level
observations, and why a keyword check on key_reasons is deliberately weak
evidence on its own.
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

def _packet(candidates=None, sweep_errors=None, reasons=None, tier=None):
    input_obj = {
        "sweep": {
            "lanes_run": ["github"],
            "candidates": candidates or [],
            "errors": sweep_errors or [],
        }
    }
    if tier is not None:
        input_obj["tier"] = tier
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
    # github is required at every tier (policy/tier-matrix.json), so an
    # "unsupported" github lane always triggers the requirement.
    input_obj, expected_obj = _packet(
        sweep_errors=["github: unsupported -- no fallback"],
        reasons=["build it"],
        tier="standard",
    )
    expected_obj["authority"] = "agent-authorized"
    expected_obj["stopping_rule"] = "required_human_decision"
    errors = []
    run_evals.check_unsupported_required_lane_requires_human_authority(
        CASE, input_obj, expected_obj, errors
    )
    assert len(errors) == 1
    assert "human-required" in errors[0]


def test_unsupported_required_lane_without_stopping_rule_is_flagged():
    input_obj, expected_obj = _packet(
        sweep_errors=["github: unsupported -- no fallback"],
        reasons=["coverage is incomplete, halt for a human decision"],
        tier="standard",
    )
    expected_obj["authority"] = "human-required"
    # stopping_rule deliberately omitted.
    errors = []
    run_evals.check_unsupported_required_lane_requires_human_authority(
        CASE, input_obj, expected_obj, errors
    )
    assert len(errors) == 1
    assert "required_human_decision" in errors[0]


def test_unsupported_required_lane_with_human_authority_and_stopping_rule_passes():
    input_obj, expected_obj = _packet(
        sweep_errors=["github: unsupported -- no fallback"],
        reasons=["coverage is incomplete, halt for a human decision"],
        tier="standard",
    )
    expected_obj["authority"] = "human-required"
    expected_obj["stopping_rule"] = "required_human_decision"
    errors = []
    run_evals.check_unsupported_required_lane_requires_human_authority(
        CASE, input_obj, expected_obj, errors
    )
    assert errors == []


def test_unsupported_required_lane_without_tier_is_flagged():
    """A fixture naming an unsupported lane must declare a tier so
    requiredness is checked against policy/tier-matrix.json, not assumed."""
    input_obj, expected_obj = _packet(
        sweep_errors=["github: unsupported -- no fallback"],
        reasons=["build it"],
    )
    errors = []
    run_evals.check_unsupported_required_lane_requires_human_authority(
        CASE, input_obj, expected_obj, errors
    )
    assert len(errors) == 1
    assert "no valid 'tier' field" in errors[0]


def test_unsupported_optional_lane_never_requires_authority():
    """An unsupported lane that is not in the tier's required_lanes list
    narrows coverage but does not, on its own, halt the hunt. 'curation' is
    optional at every tier per policy/tier-matrix.json."""
    input_obj, expected_obj = _packet(
        sweep_errors=["curation: unsupported -- no web_fetch capability"],
        reasons=["adopt the found candidate despite the missing curation lane"],
        tier="quick",
    )
    errors = []
    run_evals.check_unsupported_required_lane_requires_human_authority(
        CASE, input_obj, expected_obj, errors
    )
    assert errors == []


def test_degraded_status_never_triggers_required_human_decision():
    """policy/tier-matrix.json's required_human_decision stopping rule fires
    on an *unsupported* required lane specifically -- not on 'degraded'. grep
    is required at standard/full tier, but a 429-backoff degrade (grep's own
    documented on_unavailable.lane_status) still counts as partial coverage,
    not a halt. This is a status-vocabulary distinction, not a
    required-vs-optional one: even a required lane reporting 'degraded'
    (rather than 'unsupported') does not trigger the halt."""
    input_obj, expected_obj = _packet(
        sweep_errors=["grep: degraded -- 429 backoff retries exhausted"],
        reasons=["adopt the found candidate despite the grep gap"],
        tier="standard",
    )
    errors = []
    run_evals.check_unsupported_required_lane_requires_human_authority(
        CASE, input_obj, expected_obj, errors
    )
    assert errors == []


def test_freeform_error_without_lane_status_convention_is_ignored():
    """scripts/sweep.py's real errors[] strings (e.g. 'github(api): HTTP 403')
    don't follow the '<lane>: <status> --' convention fixtures use to name a
    tier-matrix status explicitly, so this check can't and doesn't classify
    them -- it only fires on fixtures that opt into the convention."""
    input_obj, expected_obj = _packet(
        sweep_errors=["github(api): HTTP 403 rate limited"],
        reasons=["adopt the found candidate"],
        tier="standard",
    )
    errors = []
    run_evals.check_unsupported_required_lane_requires_human_authority(
        CASE, input_obj, expected_obj, errors
    )
    assert errors == []


# ------------------------------------------------------- BUILD authority ---

def test_build_verdict_without_human_authority_is_flagged():
    expected_obj = {"verdict": "BUILD", "key_reasons": ["nothing fits"]}
    errors = []
    run_evals.check_build_verdict_requires_human_authority(CASE, expected_obj, errors)
    assert len(errors) == 1
    assert "human-required" in errors[0]


def test_build_verdict_with_human_authority_passes():
    expected_obj = {
        "verdict": "BUILD",
        "authority": "human-required",
        "key_reasons": ["nothing fits"],
    }
    errors = []
    run_evals.check_build_verdict_requires_human_authority(CASE, expected_obj, errors)
    assert errors == []


def test_non_build_verdict_never_requires_authority_field():
    expected_obj = {"verdict": "DEPEND", "key_reasons": ["adopt it"]}
    errors = []
    run_evals.check_build_verdict_requires_human_authority(CASE, expected_obj, errors)
    assert errors == []


# ------------------------------------------------ null-license rights ---

def test_github_null_license_requires_prohibited_rights():
    input_obj, expected_obj = _packet(
        candidates=[{"name": "x", "license": None, "source_lane": "github"}],
        reasons=["no LICENSE file means all rights reserved"],
    )
    expected_obj["rights_and_policy"] = "unknown"  # wrong: should be prohibited
    errors = []
    run_evals.check_null_license_rights_and_policy_matches_source(
        CASE, input_obj, expected_obj, errors
    )
    assert len(errors) == 1
    assert "prohibited" in errors[0]


def test_registry_null_license_requires_unknown_rights():
    input_obj, expected_obj = _packet(
        candidates=[{"name": "x", "license": None, "source_lane": "registry:pypi"}],
        reasons=["license metadata is missing from the registry adapter"],
    )
    expected_obj["rights_and_policy"] = "prohibited"  # wrong: should be unknown
    errors = []
    run_evals.check_null_license_rights_and_policy_matches_source(
        CASE, input_obj, expected_obj, errors
    )
    assert len(errors) == 1
    assert "unknown" in errors[0]


def test_matching_rights_and_policy_passes_silently():
    input_obj, expected_obj = _packet(
        candidates=[{"name": "x", "license": None, "source_lane": "github"}],
        reasons=["no LICENSE file means all rights reserved"],
    )
    expected_obj["rights_and_policy"] = "prohibited"
    errors = []
    run_evals.check_null_license_rights_and_policy_matches_source(
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
