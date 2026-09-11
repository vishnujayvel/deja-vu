"""Regression checks for docs/examples/decision-receipts/ -- the sanitized
exemplar/counterexample corpus (deja-vu-p3.1). See that directory's README.md
for what this corpus is and the sourcing discipline behind it.

Scope: these checks validate schema conformance, required structure (a
packet.json + receipt.md pair per entry), the real/simulated label, and that
every requested category slug is present. They do not and cannot validate
the factual accuracy, citation reachability, or semantic honesty of any
entry's claims -- that is the job of an independent review of the committed
tree, not this test file.
"""

import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "docs" / "examples" / "decision-receipts"
SCHEMA_PATH = ROOT / "schemas" / "decision-packet.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())


def entry_dirs():
    if not CORPUS_DIR.is_dir():
        return []
    return sorted(p for p in CORPUS_DIR.iterdir() if p.is_dir())


ENTRY_DIRS = entry_dirs()
ENTRY_IDS = [p.name for p in ENTRY_DIRS]


def test_corpus_directory_exists_and_is_nonempty():
    assert CORPUS_DIR.is_dir(), f"missing corpus directory: {CORPUS_DIR}"
    assert ENTRY_DIRS, f"no exemplar entries found under {CORPUS_DIR}"


def test_corpus_has_a_readme():
    readme = CORPUS_DIR / "README.md"
    assert readme.is_file(), "docs/examples/decision-receipts/README.md is required"
    assert "real" in readme.read_text().lower(), (
        "README must document the real-vs-simulated labeling convention"
    )


@pytest.mark.parametrize("entry_dir", ENTRY_DIRS, ids=ENTRY_IDS)
def test_entry_has_packet_and_receipt(entry_dir):
    packet_path = entry_dir / "packet.json"
    receipt_path = entry_dir / "receipt.md"
    assert packet_path.is_file(), f"{entry_dir.name} is missing packet.json"
    assert receipt_path.is_file(), f"{entry_dir.name} is missing receipt.md"


@pytest.mark.parametrize("entry_dir", ENTRY_DIRS, ids=ENTRY_IDS)
def test_packet_validates_against_decision_packet_schema(entry_dir):
    packet = json.loads((entry_dir / "packet.json").read_text())
    jsonschema.validate(packet, SCHEMA)


@pytest.mark.parametrize("entry_dir", ENTRY_DIRS, ids=ENTRY_IDS)
def test_packet_is_proposed_stage_only(entry_dir):
    # This corpus never fabricates authority_receipts/signatures -- no real
    # signing infrastructure exists for this project yet (ADR-11
    # Consequences). Every exemplar must stay at the pre-authority stage.
    # approval_material_sha256 is still required by the existing schema at
    # this stage and is present on every packet; this suite does not define
    # or enforce any particular hashing scheme beyond the schema's own
    # sha256_hex pattern (checked by the schema-validation test above).
    packet = json.loads((entry_dir / "packet.json").read_text())
    assert packet["stage"] == "proposed", (
        f"{entry_dir.name}: exemplar corpus packets must be stage=proposed "
        "(no fabricated authority receipts/signatures)"
    )
    assert "authority_receipts" not in packet
    assert "executable_component_ids" not in packet
    assert "decision_record_sha256" not in packet


@pytest.mark.parametrize("entry_dir", ENTRY_DIRS, ids=ENTRY_IDS)
def test_receipt_declares_real_or_simulated(entry_dir):
    receipt_text = (entry_dir / "receipt.md").read_text()
    first_kb = receipt_text[:1024].lower()
    assert "label:" in first_kb, (
        f"{entry_dir.name}/receipt.md must declare a Label: real|simulated "
        "near the top, per docs/design.md's no-invented-prior-use discipline"
    )
    assert "real" in first_kb or "simulated" in first_kb


def test_all_required_category_slugs_present():
    # design field on deja-vu-p3.1: "good reuse, justified custom work,
    # degraded evidence, rights constraints, and decisions that later
    # changed" -- prefer a few high-signal examples, but every named
    # category must appear at least once. This checks presence of the
    # seven directory slugs below, not the truth of what's inside them.
    required_slugs = {
        "depend-skill-reuse",
        "depend-cli-runtime-capability",
        "depend-tool-adoption",
        "build-justified-no-fit",
        "rights-constrained-clean-room",
        "degraded-evidence-source-rot",
        "decision-changed-registry-to-packet",
    }
    present = {p.name for p in ENTRY_DIRS}
    missing = required_slugs - present
    assert not missing, f"corpus is missing required categories: {missing}"
