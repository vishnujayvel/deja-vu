#!/usr/bin/env python3
"""deja-vu decision packet -- authority-chain verifier (docs/design.md Sec 5.4, ADR-11).

Pure, deterministic, stdlib-only. This module does NO network access, NO
subprocess execution, and NO cryptographic signature verification -- it never
authorizes anything itself. Signing and human sign-off stay outside this
repository's tooling (SKILL.md's THE ASYMMETRIC GATE); this module only makes
the paper trail mechanically checkable, closing the gap ADR-11's Consequences
section named as deferred: "approval_material_sha256 can be computed and
checked mechanically once a canonical serialization is implemented (not part
of this change)."

Canonicalization: `json.dumps(value, sort_keys=True, separators=(",", ":"),
ensure_ascii=True)`, encoded UTF-8. Deterministic regardless of input key
order or whitespace, so two structurally-equal packets always hash the same.

Two checks, mirroring the `stage` values in schemas/decision-packet.schema.json:

  compute_approval_material_sha256(proposed_packet) -> hex str
      Recomputes a `stage: proposed` packet's hash from exactly the fields
      ADR-11 names as approval material (problem_disposition,
      candidate_comparisons, uncertainty, reversibility, route_components).
      Compare the result against the packet's own `approval_material_sha256`,
      or against a later `authorized` record's `proposed_packet_ref`, to
      detect drift between what was proposed and what is later claimed to
      have been approved.

  compute_component_sha256(route_component) -> hex str
      Same canonicalization, scoped to one `route_components` entry, for
      comparing against an `authority_receipt.components[].component_sha256`.

  verify_authority_chain(proposed_packet, authorized_packet) -> dict
      Fail-closed authority-chain check. Never trusts the `authorized`
      packet's own claims: a component id counts as authorized only when (a)
      the authorized packet's `proposed_packet_ref` reproduces the supplied
      proposed packet's hash, and (b) at least one `authority_receipt` whose
      own `approval_material_sha256` also reproduces that hash covers the
      component id with a reproduced `component_sha256` match and
      `decision == "approved"`. Every other id in `executable_component_ids`
      is reported in `unauthorized_component_ids`. This is the concrete,
      machine-checkable form of "BUILD and any unapproved custom component
      stop at the gate": nothing may treat itself as authorized to execute
      merely because a record says so.

This module does not decide the human-facing verdict (that stays in
SKILL.md's asymmetric gate); it only tells the truth about whether the paper
trail is internally consistent, so a broken or forged chain cannot hide
behind a schema-valid shape.

Input (single JSON object on stdin, or via --input <path>):
  {
    "proposed": {...stage: "proposed" decision packet...},
    "authorized": {...stage: "authorized" decision packet...}
  }

Usage:
    python3 scripts/decision_packet.py verify --input packet_pair.json
    echo '{"proposed": {...}, "authorized": {...}}' | python3 scripts/decision_packet.py verify
    python3 scripts/decision_packet.py hash --input proposed_packet.json
"""

import argparse
import json
import hashlib
import sys

APPROVAL_MATERIAL_FIELDS = (
    "problem_disposition",
    "candidate_comparisons",
    "uncertainty",
    "reversibility",
    "route_components",
)


def canonical_json_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def sha256_hex(value):
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def approval_material(packet):
    if not isinstance(packet, dict):
        raise ValueError("packet must be a JSON object")
    missing = [f for f in APPROVAL_MATERIAL_FIELDS if f not in packet]
    if missing:
        raise ValueError(
            "packet missing approval-material field(s): " + ", ".join(missing)
        )
    return {field: packet[field] for field in APPROVAL_MATERIAL_FIELDS}


def compute_approval_material_sha256(packet):
    return sha256_hex(approval_material(packet))


def compute_component_sha256(route_component):
    if not isinstance(route_component, dict):
        raise ValueError("route_component must be a JSON object")
    return sha256_hex(route_component)


def verify_authority_chain(proposed_packet, authorized_packet):
    """Fail-closed: any error or unreproduced claim leaves components unauthorized."""
    errors = []

    try:
        recomputed_proposed_hash = compute_approval_material_sha256(proposed_packet)
    except ValueError as e:
        return {
            "ok": False,
            "errors": [f"proposed packet is malformed: {e}"],
            "authorized_component_ids": [],
            "unauthorized_component_ids": [],
        }

    ref = authorized_packet.get("proposed_packet_ref")
    if not isinstance(ref, dict):
        return {
            "ok": False,
            "errors": ["authorized packet is missing proposed_packet_ref"],
            "authorized_component_ids": [],
            "unauthorized_component_ids": [],
        }

    if ref.get("packet_id") != proposed_packet.get("packet_id"):
        errors.append(
            "proposed_packet_ref.packet_id does not match the supplied proposed packet"
        )
    if ref.get("approval_material_sha256") != recomputed_proposed_hash:
        errors.append(
            "proposed_packet_ref.approval_material_sha256 does not reproduce "
            "from the supplied proposed packet"
        )

    components_by_id = {}
    for component in proposed_packet.get("route_components", []) or []:
        if isinstance(component, dict) and component.get("component_id"):
            components_by_id[component["component_id"]] = component

    # component_id -> set of receipt_ids that reproducibly approve it
    approving_receipts = {}
    for receipt in authorized_packet.get("authority_receipts", []) or []:
        if not isinstance(receipt, dict):
            continue
        if receipt.get("approval_material_sha256") != recomputed_proposed_hash:
            # A receipt for a different (or since-tampered) proposed packet
            # never authorizes anything against THIS proposed packet.
            continue
        if receipt.get("decision") != "approved":
            continue
        for entry in receipt.get("components", []) or []:
            if not isinstance(entry, dict):
                continue
            cid = entry.get("component_id")
            component = components_by_id.get(cid)
            if component is None:
                continue
            if compute_component_sha256(component) != entry.get("component_sha256"):
                # The receipt describes a component that no longer matches
                # (or never matched) the proposed packet's version of it.
                continue
            approving_receipts.setdefault(cid, set()).add(receipt.get("receipt_id"))

    authorized_ids = []
    unauthorized_ids = []
    for cid in authorized_packet.get("executable_component_ids", []) or []:
        if cid in approving_receipts:
            authorized_ids.append(cid)
        else:
            unauthorized_ids.append(cid)

    if unauthorized_ids:
        errors.append(
            "executable_component_ids claims components with no reproducible "
            "approved receipt: " + ", ".join(unauthorized_ids)
        )

    return {
        "ok": not errors,
        "errors": errors,
        "authorized_component_ids": authorized_ids,
        "unauthorized_component_ids": unauthorized_ids,
    }


def _read_json(path):
    if path == "-":
        raw = sys.stdin.read()
    else:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    return json.loads(raw)


def build_arg_parser():
    p = argparse.ArgumentParser(
        description="deja-vu decision packet authority-chain verifier (design.md Sec 5.4)"
    )
    sub = p.add_subparsers(dest="command", required=True)

    verify_p = sub.add_parser(
        "verify", help="verify a proposed/authorized packet pair's authority chain"
    )
    verify_p.add_argument(
        "--input",
        default="-",
        help="path to a JSON object with 'proposed' and 'authorized' packets; "
        "'-' (default) reads stdin",
    )

    hash_p = sub.add_parser(
        "hash", help="compute a proposed packet's approval_material_sha256"
    )
    hash_p.add_argument(
        "--input",
        default="-",
        help="path to a stage: proposed decision packet JSON document; "
        "'-' (default) reads stdin",
    )

    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    try:
        doc = _read_json(args.input)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        print(
            json.dumps(
                {"ok": False, "errors": [f"decision_packet: cannot read input: {e}"]}
            )
        )
        return 1

    if args.command == "hash":
        try:
            digest = compute_approval_material_sha256(doc)
        except ValueError as e:
            print(json.dumps({"ok": False, "errors": [str(e)]}))
            return 1
        print(json.dumps({"ok": True, "approval_material_sha256": digest}))
        return 0

    # args.command == "verify"
    if not isinstance(doc, dict) or "proposed" not in doc or "authorized" not in doc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "errors": [
                        "input must be an object with 'proposed' and 'authorized' packets"
                    ],
                }
            )
        )
        return 1
    result = verify_authority_chain(doc["proposed"], doc["authorized"])
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
