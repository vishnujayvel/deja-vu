"""Pins schemas/probe-receipt.schema.json's shape (references/snowball-probe.md,
policy/tier-matrix.json hands_on_probe): the compact per-candidate receipt
gap identified for deja-vu-v2.16.

Each test below pins one of the four rules the schema encodes:

1. A receipt must always carry `candidate`, `source_revision`, and
   `hands_on_probe` -- there is no receipt without a claimed candidate and
   revision, even a null one.
2. `hands_on_probe: performed` forces `source_revision` to be a real,
   non-null string, plus `commands`, `environment`, `outputs`, and
   `cleanup` -- a performed probe cannot omit the fields that make it
   reproducible.
3. `hands_on_probe: unsupported` forces `unsupported_reason` -- silently
   marking a probe unsupported without saying why is rejected.
4. `environment.mounts` accepts only an array (empty by convention); this
   guards the field's presence and type so a future edit can't quietly
   drop it, since a non-empty list is meant to read as a sandbox
   violation, not a pass.
"""

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "probe-receipt.schema.json"
)
SCHEMA = json.loads(SCHEMA_PATH.read_text())

DOC_PATH = (
    Path(__file__).resolve().parent.parent
    / "references"
    / "snowball-probe.md"
)


def performed_receipt(**overrides):
    receipt = {
        "schema_version": "deja-vu.probe-receipt/v1",
        "candidate": "example-lib",
        "source_revision": "a1b2c3d4e5f6",
        "hands_on_probe": "performed",
        "inspected_manifests": ["package.json"],
        "commands": ["npm ci", "node smoke.js"],
        "environment": {
            "sandbox_mechanism": "container (no host mounts)",
            "network": "allowlisted",
            "allowlisted_endpoints": ["registry.npmjs.org"],
            "mounts": [],
            "writable_scratch": "/work/probe-example-lib",
        },
        "outputs": "smoke.js exited 0",
        "load_bearing_source_read": ["src/index.js"],
        "cleanup": {"performed": True, "method": "container destroyed"},
        "failures": [],
    }
    receipt.update(overrides)
    return receipt


def unsupported_receipt(**overrides):
    receipt = {
        "schema_version": "deja-vu.probe-receipt/v1",
        "candidate": "example-lib",
        "source_revision": None,
        "hands_on_probe": "unsupported",
        "unsupported_reason": "no enforceable sandbox mechanism available in this environment",
        "fallback_evidence": "static source read of src/index.js",
        "failures": [],
    }
    receipt.update(overrides)
    return receipt


def assert_valid(receipt):
    jsonschema.validate(receipt, SCHEMA)


def assert_invalid(receipt):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(receipt, SCHEMA)


def test_schema_is_valid_draft_2020_12():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_baseline_performed_receipt_is_valid():
    assert_valid(performed_receipt())


def test_baseline_unsupported_receipt_is_valid():
    assert_valid(unsupported_receipt())


# Rule 1: top-level required fields on every receipt.


@pytest.mark.parametrize("field", ["candidate", "source_revision", "hands_on_probe"])
def test_rule1_missing_top_level_required_field_is_invalid(field):
    receipt = performed_receipt()
    del receipt[field]
    assert_invalid(receipt)


def test_rule1_source_revision_may_be_explicitly_null_when_unsupported():
    assert_valid(unsupported_receipt(source_revision=None))


# Rule 2: a performed probe must carry the fields that make it reproducible.


@pytest.mark.parametrize(
    "field", ["source_revision", "commands", "environment", "outputs", "cleanup"]
)
def test_rule2_performed_probe_missing_field_is_invalid(field):
    receipt = performed_receipt()
    del receipt[field]
    assert_invalid(receipt)


def test_rule2_performed_probe_cannot_have_null_source_revision():
    assert_invalid(performed_receipt(source_revision=None))


def test_rule2_performed_probe_with_all_fields_is_valid():
    assert_valid(performed_receipt())


# Rule 3: an unsupported probe must say why.


def test_rule3_unsupported_probe_without_reason_is_invalid():
    receipt = unsupported_receipt()
    del receipt["unsupported_reason"]
    assert_invalid(receipt)


def test_rule3_unsupported_probe_with_reason_is_valid():
    assert_valid(unsupported_receipt())


# Rule 4: environment.mounts stays an array (empty by convention).


def test_rule4_mounts_must_be_array():
    receipt = performed_receipt()
    receipt["environment"]["mounts"] = "none"
    assert_invalid(receipt)


def test_rule4_empty_mounts_is_valid():
    receipt = performed_receipt()
    receipt["environment"]["mounts"] = []
    assert_valid(receipt)


# Drift guard: every schema property name that appears in the worked example
# inside references/snowball-probe.md must actually be a real schema
# property -- catches the doc's example drifting away from the schema it
# claims to conform to.


def test_doc_example_keys_are_all_real_schema_properties():
    text = DOC_PATH.read_text()
    start = text.index('"schema_version": "deja-vu.probe-receipt/v1"')
    fence_start = text.rindex("```json", 0, start)
    fence_end = text.index("```", start)
    example = json.loads(text[fence_start + len("```json") : fence_end])

    top_level_props = set(SCHEMA["properties"])
    assert set(example) <= top_level_props

    env_props = set(SCHEMA["properties"]["environment"]["properties"])
    assert set(example["environment"]) <= env_props

    cleanup_props = set(SCHEMA["properties"]["cleanup"]["properties"])
    assert set(example["cleanup"]) <= cleanup_props

    assert_valid(example)
