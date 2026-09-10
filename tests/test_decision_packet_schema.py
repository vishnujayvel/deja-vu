"""Positive/negative fixtures for schemas/decision-packet.schema.json's five
packet-validation rules (docs/design.md §5.4, encoded per ADR-11):

1. a route component missing a stable ID, evidence, output boundary, or
   authority state fails `required`.
2. custom behavior cannot be hidden under `authority: agent-authorized`, and
   `route: clean-room-reimplement` or `route: custom-build` is forced to
   `custom_behavior: true`.
3. `rights: prohibited` cannot carry `authority: approved` or
   `agent-authorized`.
4. `rights: prohibited` or `rights: unknown` (the two values "unlicensed"
   source maps to per ADR-11) cannot carry `route: fork` or
   `route: vendor-source`.
5. a `stage: proposed` packet cannot carry post-resolution authority outcomes
   (`approved`, `rejected`, `deferred`) on any `route_components` entry —
   only the pre-resolution states (`agent-authorized`, `human-required`) are
   allowed before an authority receipt exists.
"""

import copy
import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "decision-packet.schema.json"
)
SCHEMA = json.loads(SCHEMA_PATH.read_text())


def base_component(**overrides):
    component = {
        "component_id": "c1",
        "route": "depend",
        "output_boundary": "adapter output",
        "evidence_refs": ["ev1"],
        "fit": "composable",
        "rights": "permitted",
        "evidence_level": "documented",
        "custom_behavior": False,
        "policy_clauses": [],
        "authority": "agent-authorized",
        "accepted_obligations": [],
        "residual_uncertainty": "none",
        "next_action": "proceed",
    }
    component.update(overrides)
    return component


def packet_with(component):
    return {
        "schema_version": "deja-vu.decision-packet/v1",
        "packet_id": "p1",
        "stage": "proposed",
        "problem_disposition": {"need_disposition": "proceed", "summary": "s"},
        "candidate_comparisons": [],
        "uncertainty": {"residual": "r"},
        "reversibility": "high",
        "route_components": [component],
        "approval_material_sha256": "a" * 64,
    }


def assert_valid(packet):
    jsonschema.validate(packet, SCHEMA)


def assert_invalid(packet):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(packet, SCHEMA)


def test_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_baseline_component_is_valid():
    assert_valid(packet_with(base_component()))


# Rule 1: required per-component fields.


@pytest.mark.parametrize(
    "field",
    ["component_id", "evidence_refs", "output_boundary", "authority"],
)
def test_rule1_missing_required_field_is_invalid(field):
    component = base_component()
    del component[field]
    assert_invalid(packet_with(component))


# Rule 2: custom behavior cannot be hidden under agent-authorized authority.


def test_rule2_custom_behavior_with_agent_authorized_is_invalid():
    component = base_component(
        custom_behavior=True,
        custom_delta={"ownership": "us", "maintenance_surface": "adapter"},
        authority="agent-authorized",
    )
    assert_invalid(packet_with(component))


def test_rule2_custom_behavior_with_human_required_is_valid():
    component = base_component(
        custom_behavior=True,
        custom_delta={"ownership": "us", "maintenance_surface": "adapter"},
        authority="human-required",
    )
    assert_valid(packet_with(component))


def test_rule2_clean_room_forces_custom_behavior_true():
    component = base_component(
        route="clean-room-reimplement",
        custom_behavior=False,
        rights="permitted",
        authority="human-required",
    )
    assert_invalid(packet_with(component))


def test_rule2_custom_build_forces_custom_behavior_true():
    component = base_component(
        route="custom-build",
        custom_behavior=False,
        rights="permitted",
        authority="agent-authorized",
    )
    assert_invalid(packet_with(component))


def test_rule2_custom_build_with_custom_behavior_true_is_valid():
    component = base_component(
        route="custom-build",
        custom_behavior=True,
        custom_delta={"ownership": "us", "maintenance_surface": "adapter"},
        rights="permitted",
        authority="human-required",
    )
    assert_valid(packet_with(component))


# Rule 3: prohibited rights cannot carry approved/agent-authorized authority.


def test_rule3_prohibited_rights_with_approved_authority_is_invalid():
    component = base_component(rights="prohibited", authority="approved")
    assert_invalid(packet_with(component))


def test_rule3_prohibited_rights_with_human_required_is_valid():
    component = base_component(rights="prohibited", authority="human-required")
    assert_valid(packet_with(component))


# Rule 4: prohibited/unknown rights cannot carry route fork or vendor-source.


@pytest.mark.parametrize("rights", ["prohibited", "unknown"])
@pytest.mark.parametrize("route", ["fork", "vendor-source"])
def test_rule4_unlicensed_rights_cannot_fork_or_vendor(rights, route):
    component = base_component(rights=rights, route=route, authority="human-required")
    assert_invalid(packet_with(component))


@pytest.mark.parametrize("route", ["fork", "vendor-source"])
def test_rule4_permitted_rights_can_fork_or_vendor(route):
    component = base_component(rights="permitted", route=route, authority="human-required")
    assert_valid(packet_with(component))


def test_rule4_conditional_rights_can_fork_or_vendor():
    # `conditional` still confers some reuse right (docs/design.md §5.4), so
    # unlike prohibited/unknown it is not blocked from fork/vendor-source.
    component = base_component(
        rights="conditional", route="fork", authority="human-required"
    )
    assert_valid(packet_with(component))


@pytest.mark.parametrize("rights", ["prohibited", "unknown"])
def test_rule4_unlicensed_rights_can_still_depend(rights):
    component = base_component(rights=rights, route="depend", authority="human-required")
    assert_valid(packet_with(component))


# Rule 5: `stage: proposed` cannot carry post-resolution authority outcomes
# on any route component.


@pytest.mark.parametrize("authority", ["approved", "rejected", "deferred"])
def test_rule5_proposed_stage_rejects_post_resolution_authority(authority):
    # base_component()'s rights default is "permitted", so rule 3 (prohibited
    # rights + approved/agent-authorized authority) never fires here — only
    # rule 5 is exercised.
    component = base_component(authority=authority)
    assert_invalid(packet_with(component))


@pytest.mark.parametrize("authority", ["agent-authorized", "human-required"])
def test_rule5_proposed_stage_allows_pre_resolution_authority(authority):
    component = base_component(authority=authority)
    assert_valid(packet_with(component))
