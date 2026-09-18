"""Tests for scripts/decision_packet.py -- the authority-chain verifier that
closes ADR-11's deferred gap ("approval_material_sha256 can be computed and
checked mechanically once a canonical serialization is implemented").

Every schema-valid fixture is also validated against
schemas/decision-packet.schema.json so these tests exercise realistic
packets, not shapes the schema itself would reject.
"""

import copy
import json
from pathlib import Path

import jsonschema
import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from decision_packet import (  # noqa: E402
    compute_approval_material_sha256,
    compute_component_sha256,
    verify_authority_chain,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "decision-packet.schema.json"
)
SCHEMA = json.loads(SCHEMA_PATH.read_text())


def base_component(**overrides):
    component = {
        "component_id": "c1",
        "route": "custom-build",
        "output_boundary": "adapter output",
        "evidence_refs": ["ev1"],
        "fit": "mismatch",
        "rights": "permitted",
        "evidence_level": "documented",
        "custom_behavior": True,
        "custom_delta": {"ownership": "us", "maintenance_surface": "adapter"},
        "policy_clauses": [],
        "authority": "human-required",
        "accepted_obligations": [],
        "residual_uncertainty": "none",
        "next_action": "await human sign-off",
    }
    component.update(overrides)
    return component


def proposed_packet(component=None, **overrides):
    packet = {
        "schema_version": "deja-vu.decision-packet/v1",
        "packet_id": "p1",
        "stage": "proposed",
        "problem_disposition": {"need_disposition": "proceed", "summary": "s"},
        "candidate_comparisons": [],
        "uncertainty": {"residual": "r"},
        "reversibility": "high",
        "route_components": [component or base_component()],
        "approval_material_sha256": "a" * 64,
    }
    packet.update(overrides)
    return packet


def receipt_for(proposed, component_id, decision="approved", receipt_id="r1"):
    component = next(
        c for c in proposed["route_components"] if c["component_id"] == component_id
    )
    return {
        "receipt_id": receipt_id,
        "principal": "vishnu",
        "issuer": "human-gate",
        "auth_method": "manual",
        "project_id": "deja-vu",
        "hunt_id": "hunt-1",
        "policy_version": "v1",
        "approval_material_sha256": compute_approval_material_sha256(proposed),
        "components": [
            {
                "component_id": component_id,
                "component_sha256": compute_component_sha256(component),
            }
        ],
        "decision": decision,
        "nonce": "n1",
        "issued_at": "2026-09-17T00:00:00Z",
        "expires_at": "2026-12-31T00:00:00Z",
        "issuer_key_id": "key-1",
        "signature": {"algorithm": "manual", "value": "bm9uZQ=="},
    }


def authorized_packet(proposed, receipts, executable_component_ids, **overrides):
    packet = {
        "schema_version": "deja-vu.decision-packet/v1",
        "packet_id": "p1-authorized",
        "stage": "authorized",
        "problem_disposition": proposed["problem_disposition"],
        "candidate_comparisons": proposed["candidate_comparisons"],
        "uncertainty": proposed["uncertainty"],
        "reversibility": proposed["reversibility"],
        "route_components": [
            dict(c, authority="approved") for c in proposed["route_components"]
        ],
        "proposed_packet_ref": {
            "packet_id": proposed["packet_id"],
            "approval_material_sha256": compute_approval_material_sha256(proposed),
        },
        "authority_receipts": receipts,
        "executable_component_ids": executable_component_ids,
        "decision_record_sha256": "b" * 64,
    }
    packet.update(overrides)
    return packet


def assert_schema_valid(packet):
    jsonschema.validate(packet, SCHEMA)


# --- canonical hash properties ---


def test_hash_is_deterministic_regardless_of_key_order():
    proposed = proposed_packet()
    # Build a genuinely different key-ordered dict to prove order independence.
    reordered = {k: proposed[k] for k in reversed(list(proposed.keys()))}
    assert compute_approval_material_sha256(proposed) == compute_approval_material_sha256(
        reordered
    )


def test_hash_changes_when_material_field_changes():
    proposed = proposed_packet()
    tampered = copy.deepcopy(proposed)
    tampered["reversibility"] = "low"
    assert compute_approval_material_sha256(proposed) != compute_approval_material_sha256(
        tampered
    )


def test_hash_ignores_non_material_fields():
    proposed = proposed_packet()
    only_material_fields_changed = copy.deepcopy(proposed)
    only_material_fields_changed["approval_material_sha256"] = "f" * 64
    only_material_fields_changed["packet_id"] = "different-id"
    assert compute_approval_material_sha256(proposed) == compute_approval_material_sha256(
        only_material_fields_changed
    )


def test_hash_rejects_packet_missing_material_field():
    proposed = proposed_packet()
    del proposed["reversibility"]
    with pytest.raises(ValueError, match="reversibility"):
        compute_approval_material_sha256(proposed)


# --- authority-chain verification ---


def test_chain_authorizes_component_with_matching_approved_receipt():
    proposed = proposed_packet()
    assert_schema_valid(proposed)
    receipt = receipt_for(proposed, "c1")
    authorized = authorized_packet(proposed, [receipt], ["c1"])
    assert_schema_valid(authorized)

    result = verify_authority_chain(proposed, authorized)

    assert result["ok"] is True
    assert result["authorized_component_ids"] == ["c1"]
    assert result["unauthorized_component_ids"] == []


def test_chain_rejects_component_with_no_receipt_at_all():
    proposed = proposed_packet()
    authorized = authorized_packet(proposed, receipts=[], executable_component_ids=["c1"])

    result = verify_authority_chain(proposed, authorized)

    assert result["ok"] is False
    assert result["unauthorized_component_ids"] == ["c1"]
    assert result["authorized_component_ids"] == []


def test_chain_rejects_component_whose_receipt_was_rejected_not_approved():
    proposed = proposed_packet()
    receipt = receipt_for(proposed, "c1", decision="rejected")
    authorized = authorized_packet(proposed, [receipt], ["c1"])

    result = verify_authority_chain(proposed, authorized)

    assert result["ok"] is False
    assert "c1" in result["unauthorized_component_ids"]


def test_chain_fails_closed_when_proposed_packet_is_tampered_after_approval():
    proposed = proposed_packet()
    receipt = receipt_for(proposed, "c1")
    authorized = authorized_packet(proposed, [receipt], ["c1"])

    tampered_proposed = copy.deepcopy(proposed)
    tampered_proposed["reversibility"] = "low"  # e.g. someone edits the hunt after sign-off

    result = verify_authority_chain(tampered_proposed, authorized)

    assert result["ok"] is False
    assert result["unauthorized_component_ids"] == ["c1"]
    assert any("proposed_packet_ref" in e for e in result["errors"])


def test_chain_fails_closed_when_component_is_tampered_after_receipt_issued():
    proposed = proposed_packet()
    receipt = receipt_for(proposed, "c1")
    authorized = authorized_packet(proposed, [receipt], ["c1"])

    tampered_proposed = copy.deepcopy(proposed)
    tampered_proposed["route_components"][0]["custom_delta"]["maintenance_surface"] = (
        "a different, wider surface than what was actually approved"
    )
    # Re-point proposed_packet_ref/receipt hash at the tampered packet's own
    # material hash so only the *component* mismatch is being exercised.
    authorized["proposed_packet_ref"]["approval_material_sha256"] = (
        compute_approval_material_sha256(tampered_proposed)
    )
    authorized["authority_receipts"][0]["approval_material_sha256"] = (
        compute_approval_material_sha256(tampered_proposed)
    )

    result = verify_authority_chain(tampered_proposed, authorized)

    assert result["ok"] is False
    assert result["unauthorized_component_ids"] == ["c1"]


def test_chain_ignores_receipt_issued_for_a_different_proposed_packet():
    proposed = proposed_packet()
    # `packet_id` is not part of the approval-material fields (ADR-11), so
    # vary `reversibility` too to guarantee a genuinely different hash.
    other_proposed = proposed_packet(packet_id="p-other", reversibility="low")
    stale_receipt = receipt_for(other_proposed, "c1")  # hash won't match `proposed`
    authorized = authorized_packet(proposed, [stale_receipt], ["c1"])

    result = verify_authority_chain(proposed, authorized)

    assert result["ok"] is False
    assert result["unauthorized_component_ids"] == ["c1"]


def test_chain_reports_missing_proposed_packet_ref():
    proposed = proposed_packet()
    authorized = authorized_packet(proposed, [], ["c1"])
    del authorized["proposed_packet_ref"]

    result = verify_authority_chain(proposed, authorized)

    assert result["ok"] is False
    assert result["authorized_component_ids"] == []
    assert result["unauthorized_component_ids"] == []
    assert any("proposed_packet_ref" in e for e in result["errors"])


def test_chain_authorizes_only_the_specific_component_a_receipt_covers():
    c1 = base_component(component_id="c1")
    c2 = base_component(component_id="c2", route="depend", custom_behavior=False,
                         custom_delta=None, authority="agent-authorized")
    proposed = proposed_packet()
    proposed["route_components"] = [c1, c2]
    assert_schema_valid(proposed)

    receipt = receipt_for(proposed, "c1")  # only approves c1
    authorized = authorized_packet(proposed, [receipt], ["c1", "c2"])

    result = verify_authority_chain(proposed, authorized)

    assert result["ok"] is False
    assert result["authorized_component_ids"] == ["c1"]
    assert result["unauthorized_component_ids"] == ["c2"]
