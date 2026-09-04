# Deja Vu release-evidence implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans`.
> Beads is the authoritative task tracker; numbered steps here are execution
> instructions, not a second task list.

**Goal:** Produce one deterministic, immutable release-evidence packet that a
protected verifier can reproduce without trusting candidate-authored
eligibility claims or Beads status.

**Architecture:** Strict JSON Schemas define the wire contracts. A standard-
library Python module validates and canonicalizes records, and a diagnostic CLI
assembles evidence without authorizing release. Protected Switchboard receipts
and external Fable verification remain inputs owned outside the candidate.

**Tech stack:** Python 3, JSON Schema Draft 2020-12, `jsonschema` 4.x for schema
tests, `pytest`, SHA-256 canonical records.

**Spec:** `docs/superpowers/specs/2026-09-01-vishnu-city-release-control-design.md`

**Beads:** `deja-vu-p3.6.3`, blocked by `deja-vu-p3.6.2`

## Global constraints

- The candidate emits evidence and diagnostics only; it never emits
  `release_authorized: true`.
- Beads stores intent, dependencies, and evidence references, not correctness
  proof.
- Preserve each quality dimension and missingness. Do not collapse them into a
  single score.
- Bind every model-running step to the protected routing decision, capacity
  snapshot, provider family, and resolved model.
- Use RFC 8785-compatible canonical JSON conventions already declared in
  `docs/design.md`; reject duplicate keys, non-finite numbers, and non-NFC text.
- Every new schema, policy file, Python module, and shell module joins
  `contracts/module-contracts.json` and receives exact-hash Fable review.

---

### Task 1: Define strict release contracts

**Files:**

- Create: `requirements-dev.txt`
- Create: `schemas/model-routing-intent.schema.json`
- Create: `schemas/release-candidate.schema.json`
- Create: `schemas/release-evidence.schema.json`
- Create: `schemas/promotion-decision.schema.json`
- Create: `schemas/rollback-record.schema.json`
- Create: `tests/test_release_schemas.py`
- Create: `tests/fixtures/releases/valid-evidence.json`
- Create: `tests/fixtures/releases/invalid-codex-worker.json`
- Modify: `contracts/module-contracts.json`

**Interfaces:**

- Schema IDs use `deja-vu.<record-name>/v1`.
- Every object sets `additionalProperties: false`.
- Digest fields match lowercase `[0-9a-f]{64}`.
- Timestamps are RFC 3339 UTC with exactly three fractional digits.

1. Add `jsonschema>=4.25,<5` to `requirements-dev.txt`. Do not add a runtime
   dependency: the shipped validator remains standard-library Python.

2. Write a schema test that loads every file under `schemas/`, calls
   `Draft202012Validator.check_schema`, validates the good fixture, and proves
   these mutations fail:

   ```python
   @pytest.mark.parametrize("mutation", [
       lambda p: p["routing_receipts"][0].update(provider_family="codex"),
       lambda p: p["routing_receipts"][0].pop("resolved_model"),
       lambda p: p["evaluations"][0].pop("missingness"),
       lambda p: p.update(release_authorized=True),
   ])
   def test_release_evidence_rejects_unsafe_mutations(valid_packet, mutation):
       mutation(valid_packet)
       validator = jsonschema.Draft202012Validator(release_evidence_schema)
       with pytest.raises(jsonschema.ValidationError):
           validator.validate(valid_packet)
   ```

   The test module defines `release_evidence_schema` by loading
   `schemas/release-evidence.schema.json` and defines `valid_packet` by loading
   `tests/fixtures/releases/valid-evidence.json` through a deep copy per test.

3. Run and verify RED:

   ```bash
   python3 -m pytest tests/test_release_schemas.py -q
   ```

   Expected: schema files or required properties are absent.

4. Implement the schemas. `release-evidence` requires candidate/base hashes,
   architecture/schema/policy versions, changed modules, commands and outputs,
   dimensioned evaluations, routing receipts, Fable records, canary evidence,
   rollback reference, and provenance. It explicitly forbids a release-
   authorization field.

5. Add one non-empty module contract for every new governed file, run the
   schema tests, and verify GREEN.

### Task 2: Build the pure evidence validator and canonicalizer

**Files:**

- Create: `scripts/release_evidence.py`
- Create: `tests/test_release_evidence.py`
- Modify: `contracts/module-contracts.json`

**Interfaces:**

```python
@dataclass(frozen=True)
class EvidencePacket:
    canonical_bytes: bytes
    sha256: str
    data: Mapping[str, object]


def validate_release_evidence(raw: Mapping[str, object]) -> Mapping[str, object]: ...
def build_release_evidence(inputs: EvidenceInputs) -> EvidencePacket: ...
def load_json_strict(path: Path) -> Mapping[str, object]: ...
```

1. Write failing tests for duplicate JSON keys, non-finite numbers, non-NFC
   strings, unknown fields, unsorted duplicate module IDs, missing routing
   receipts, Codex provider family, stale capacity, inconsistent command/output
   digests, incomplete Fable coverage, and a changed verifier hash.

2. Write one determinism test that constructs logically identical inputs in a
   different mapping order and asserts identical `canonical_bytes` and SHA-256.

3. Run and verify RED:

   ```bash
   python3 -m pytest tests/test_release_evidence.py -q
   ```

4. Implement the minimum pure validator. Represent missing observations as
   typed states (`missing`, `unsupported`, `degraded`, `failed`); never replace
   them with zero. Require provider family `claude` for implementation,
   `claude-fable` for terminal module review, and a non-Codex allowed family for
   independent analysis.

5. Canonicalize only after validation. Write no files inside the pure builder.
   The CLI layer may atomically write a caller-selected output path.

6. Run the focused tests and verify GREEN.

### Task 3: Convert review preparation into protected intent

**Files:**

- Modify: `scripts/prepare_fable_review.py`
- Modify: `tests/test_prepare_fable_review.py`
- Modify: `schemas/fable-review-record.schema.json`
- Modify: `contracts/module-contracts.json`

**Interfaces:**

- `prepare_review(...)` continues to seal exact artifact, contract, governing
  contract, review round, and transport attempt identities.
- It emits `routing_intent_path` and a `jobctl validate` command.
- It never embeds grant authority or reports a submit as authorized.

1. Add failing tests proving the preparer emits a routing intent bound to the
   module hashes and does not copy `grant_id`, issuer, capacity, or eligibility
   claims into candidate-owned files.

2. Add a test proving transport attempts 1-3 preserve prompt bytes and semantic
   review identity while changing only the transport-attempt identity.

3. Run and verify RED:

   ```bash
   python3 -m pytest tests/test_prepare_fable_review.py -q
   ```

4. Implement the intent output and update the review record schema with the
   protected router decision ID, provider/model provenance, permission hash,
   stdout hash, and result-evidence hash. Preserve the external verifier as the
   only constructor of release-compatible review records.

5. Run the focused preparer and Fable gate suites.

### Task 4: Add the diagnostic release-check CLI

**Files:**

- Create: `scripts/release_check.py`
- Create: `tests/test_release_check.py`
- Modify: `scripts/doctor.py`
- Modify: `contracts/module-contracts.json`

**Interfaces:**

```text
python3 scripts/release_check.py build --inputs PATH --output PATH --json
python3 scripts/release_check.py inspect --packet PATH --json
```

Both commands return `release_authorized: false`. `build` writes one immutable
packet; `inspect` recomputes its digest and prints gaps by dimension.

1. Write a failing end-to-end test that builds the valid fixture, inspects it,
   and asserts deterministic digest, complete dimension report, and
   `release_authorized is False`.

2. Add negative CLI tests for a Codex receipt, missing Fable module, failed
   held-out evaluation, stale capacity, and altered command output.

3. Run and verify RED, implement the CLI with atomic output writes and no
   network access, then rerun and verify GREEN.

4. Add doctor checks for schema availability and fixture validation. A doctor
   check diagnoses the protected verifier's availability but cannot substitute
   for its result.

### Task 5: Integration verification and Fable coverage

1. Run the full deterministic evidence surface:

   ```bash
   python3 -m pytest -q
   python3 evals/run_evals.py
   python3 scripts/doctor.py
   bash scripts/sanitize_check.sh
   bd lint
   bd doctor --check=conventions
   ```

2. Run `scripts/fable_review_gate.py` to enumerate every changed governed
   module. Prepare and submit a fresh Fable review for each current artifact
   hash under the standing protected grant.

3. Reconcile all `FIX-FIRST` findings, rerun affected tests, and obtain a fresh
   terminal review record. Do not reuse a review whose artifact or governing
   contract hash changed.

4. Ask the protected external verifier to validate the packet and record its
   result-evidence digest on `deja-vu-p3.6.3`.

## Completion gate

Phase 2 is complete only when a valid packet reproduces byte-for-byte, every
declared unsafe mutation fails, all deterministic checks pass, every changed
governed module has current Fable evidence, and the protected verifier accepts
the packet independently of Beads.
