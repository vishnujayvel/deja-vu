"""Pins the Fable round-1 fixes to policy/tier-matrix.json (deja-vu-v2.3.1).

Each test below pins one of the five findings:

1. Full-tier's provenance evidence obligation has a matching `provenance` lane,
   with a capability, an on_unavailable policy, and a place in
   tiers.full.required_lanes.
2. Lane notes that claim a lane is "optional at every tier" (or phrase presence
   ambiguously) agree with which tiers actually list that lane as optional.
3. `freshness` is a mandatory Full-tier evidence obligation, so it is listed in
   tiers.full.required_lanes, not merely optional_lanes.
4. The three concept-hunt lanes appear in every tier's lane set via
   `concept_optional_lanes`, and a top-level `concept_hunt_policy` names them.
5. No lane or stopping-rule vocabulary in the matrix uses `blocked` — that is a
   hunt-level state (docs/design.md §7), not one of the lane-envelope statuses
   (docs/design.md §5.2: pending, running, succeeded, degraded, failed,
   skipped, unsupported).
"""

import json
from pathlib import Path

import pytest

MATRIX_PATH = Path(__file__).resolve().parent.parent / "policy" / "tier-matrix.json"

ALLOWED_LANE_STATUSES = {
    "pending",
    "running",
    "succeeded",
    "degraded",
    "failed",
    "skipped",
    "unsupported",
}


@pytest.fixture(scope="module")
def matrix():
    return json.loads(MATRIX_PATH.read_text())


def test_matrix_is_valid_json():
    json.loads(MATRIX_PATH.read_text())


# --- Finding 1: provenance lane -------------------------------------------------


def test_provenance_lane_exists_with_capability_and_policy(matrix):
    lane = matrix["lanes"]["provenance"]
    assert lane["capability"]
    assert "on_unavailable" in lane
    assert lane["on_unavailable"]["lane_status"] in ALLOWED_LANE_STATUSES


def test_provenance_is_required_at_full_tier(matrix):
    assert "provenance" in matrix["tiers"]["full"]["required_lanes"]


def test_provenance_never_hard_fails(matrix):
    # scripts/provenance.py is no-throw by design (degrades to
    # unknown-experimental instead of failing) — the matrix must not claim
    # this required lane can go unsupported/failed.
    assert matrix["lanes"]["provenance"]["on_unavailable"]["lane_status"] == "degraded"


# --- Finding 2: lane notes agree with tier optional-lane lists ------------------


def _optional_at(matrix, lane_name):
    return {
        tier_name
        for tier_name, tier in matrix["tiers"].items()
        if lane_name in tier.get("optional_lanes", [])
    }


def test_skills_ecosystem_note_matches_its_actual_tier_availability(matrix):
    available = _optional_at(matrix, "skills_ecosystem")
    assert available == {"standard", "full"}
    note = matrix["lanes"]["skills_ecosystem"]["on_unavailable"]["note"]
    assert "every tier" not in note
    assert "quick" not in matrix["tiers"]["quick"]["optional_lanes"]


def test_github_code_reading_note_matches_its_actual_tier_availability(matrix):
    available = _optional_at(matrix, "github_code_reading")
    assert available == {"standard", "full"}
    note = matrix["lanes"]["github_code_reading"]["on_unavailable"]["note"]
    assert "github_code_reading" not in matrix["tiers"]["quick"].get("optional_lanes", [])
    assert "Quick tier's lane set" in note or "not part of Quick" in note


def test_curation_is_genuinely_optional_at_every_tier(matrix):
    # Unlike skills_ecosystem/github_code_reading, curation's "every tier"
    # claim is actually true -- pin that it stays true.
    assert _optional_at(matrix, "curation") == {"quick", "standard", "full"}


# --- Finding 3: freshness is required, not optional, at Full -------------------


def test_freshness_is_required_at_full_tier(matrix):
    full = matrix["tiers"]["full"]
    assert "freshness" in full["required_lanes"]
    assert "freshness" not in full["optional_lanes"]


def test_freshness_stays_optional_at_standard_tier(matrix):
    standard = matrix["tiers"]["standard"]
    assert "freshness" in standard["optional_lanes"]
    assert "freshness" not in standard["required_lanes"]


def test_freshness_double_unavailability_is_documented(matrix):
    note = matrix["lanes"]["freshness"]["on_unavailable"]["note"]
    assert "web_search" in note
    assert "required_human_decision" in note


# --- Finding 4: concept-hunt lanes have defined tier coverage -------------------


CONCEPT_LANES = {"standards_bodies", "framework_docs", "academic_survey"}


def test_concept_hunt_policy_declares_the_concept_lanes(matrix):
    policy = matrix["concept_hunt_policy"]
    assert set(policy["lanes"]) == CONCEPT_LANES
    assert set(policy["substitutes_for"]) == {"curation", "skills_ecosystem"}


@pytest.mark.parametrize("tier_name", ["quick", "standard", "full"])
def test_every_tier_lists_concept_optional_lanes(matrix, tier_name):
    tier = matrix["tiers"][tier_name]
    assert set(tier["concept_optional_lanes"]) == CONCEPT_LANES


def test_concept_lanes_are_defined_in_the_lanes_map(matrix):
    for lane_name in CONCEPT_LANES:
        lane = matrix["lanes"][lane_name]
        assert lane.get("hunt_kind") == "concept"


# --- Finding 5: no "blocked" lane status; required_human_decision is the ------
# --- documented mechanism for an unsupported required lane --------------------


def test_no_lane_uses_a_blocked_status(matrix):
    for lane_name, lane in matrix["lanes"].items():
        status = lane["on_unavailable"]["lane_status"]
        assert status in ALLOWED_LANE_STATUSES, (
            f"lane {lane_name!r} uses non-envelope status {status!r}"
        )
        assert "blocked" not in status


def test_no_lane_note_prescribes_recording_a_blocked_hunt_state(matrix):
    for lane_name, lane in matrix["lanes"].items():
        note = lane["on_unavailable"]["note"]
        assert "record the hunt as blocked" not in note, lane_name


def test_github_lane_ties_unsupported_to_required_human_decision(matrix):
    note = matrix["lanes"]["github"]["on_unavailable"]["note"]
    assert "required_human_decision" in note


def test_stopping_rules_vocabulary_has_no_blocked_state(matrix):
    assert "blocked" not in matrix["stopping_rules"]
