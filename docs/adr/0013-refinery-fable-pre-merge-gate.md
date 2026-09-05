# ADR-13: Refinery Fable pre-merge gate

**Date:** 2026-09-04
**Status:** accepted

## Context

Gas City's refinery is the merge authority for rig `deja-vu` (target
`p1-night`), but it was disabled (`min_active_sessions = 0`,
`max_active_sessions = 0` in `city.toml`) because, unmodified, it would fast
forward any branch-ready polecat work into `p1-night` with only local quality
checks and no adversarial review. The conductor (Fable 5.1) has been merging
by hand instead — a manual bottleneck that does not scale and depends on one
human-attended session staying available.

`scripts/fable_review_gate.py` already exists to diagnose Fable review
coverage from local Beads metadata, but it is explicitly diagnostic-only: it
never authorizes a merge, and `check_coverage`'s local review records are
untrusted (`authority_note`: "Local Beads metadata is untrusted coverage
input. Only the pinned external verifier may authorize release."). Something
has to sit between "diff arrives at the refinery" and "diff lands on
`p1-night`" that actually drives a fresh Claude Fable 5 review through
`gc-router`'s protected launcher and refuses the merge on anything short of a
verified pass.

## Decision

**Verdict:** Add `scripts/refinery_gate.py`, a pure-stdlib script the
refinery runs (via `[rigs.formula_vars] build_command`, wired in a follow-up
bead scoped to `city.toml`) on its rebased temp branch before fast-forwarding
into the target branch. Exit 0 allows the merge; any non-zero exit refuses
it. It always prints one line: `REFINERY_GATE: <allow|refuse> reason=...`
(or the fixed line `REFINERY_GATE: skip` when the context guard declines to
run).

### Context guard

The gate only runs its full logic when `$GC_AGENT` identifies the refinery
role for this rig, or `--force` is passed. There is no `GC_ROLE` env var
anywhere in the gastown pack (confirmed by search) — `mol-refinery-patrol`'s
`validate-identity` step and `agents/refinery/prompt.template.md` both use
`$GC_AGENT` as the refinery's canonical identity, since `$GC_ALIAS` can be
empty or stale (the cause of a prior refinery self-poll incident, upstream
gastownhall/gascity#1833). Gastown session identities take the shape
`<rig>/<binding_prefix><agent-name>` (e.g. `deja-vu/gastown.refinery`), so
the guard checks that the identity's final `.`-separated segment is
`refinery`. Round-2 review (deja-vu-5x6.3) tightened this to a closed
allowlist: `REFINERY_GATE: skip` (exit 0) is returned ONLY for a polecat
session on this rig (`deja-vu/gastown.<alias>`, confirmed against
`city.toml`'s rig-scoped `[[patches.agent]]` entries and this session's own
`$GC_AGENT`); any other identity — including the reserved role literals
`witness`/`mayor`/`deacon`, another rig, an unset/blank value, or an
unparseable one — refuses with `reason=identity-unknown`. An earlier version
classified any non-empty trailing token as a generic "other" role and let it
skip, which silently passed garbled or unrecognized identities.

### Ordering: quality gates before review

Step order is pytest, `scripts/doctor.py`, `evals/run_evals.py --offline`,
`scripts/sanitize_check.sh`, then (only if all pass) the Fable review step.
Any local failure refuses immediately without spending a review round —
review capacity is scarce and expensive; a branch that fails its own test
suite should never consume one.

### Bead id resolution

The refinery formula does not export a documented env var carrying the work
bead id into `build_command` (it stays a bash variable local to the refinery
agent's own conversation across separately-invoked Bash calls, not something
subprocesses inherit). The gate resolves the bead id in order: `--bead` flag,
then `$BEAD`/`$WORK`/`$GC_WORK_BEAD_ID` env, then parsing the current branch
name against the required `polecat/<bead-id>` convention (CLAUDE.md). This
keeps the gate correct however the refinery agent chooses to invoke
`build_command`, without guessing an undocumented contract.

### Round/attempt selection

For each governed module changed versus the target branch, the gate looks up
prior review Beads for that module and implementation bead, filters to
records whose recorded artifact and governing-contract hashes match the
*current* ones (a stale hash means a superseded review, not a used slot), and
parses round/attempt off `review_delegate_job_id` — `prepare_fable_review.py`
already encodes both at the end of the job id it mints
(`...-r<round>-a<attempt>`), so no separate metadata field is needed. It
picks the lowest unused `(round, attempt)` pair in order 1/1 through 3/3 and
refuses with a `round-attempt-exhausted` reason if all nine are taken for
this artifact and governing hash.

### Fable review pipeline

One review per changed governed module: `scripts/prepare_fable_review.py`
(prepares the sealed prompt/manifest, never submits), then
`gc-router`'s `jobctl validate` / `submit` / `wait --timeout 900` /
`verify-review --module --implementation-bead --round`. The gate refuses
unless `verify-review` reports `evidence_verified: true` and
`review.verdict == "pass"`. On any other outcome (including `fix-first`) the
gate appends the review's findings to the work bead's notes
(`bd update BEAD --append-notes`) as a best-effort diagnostic aid, then
refuses regardless of whether the note append itself succeeds.

### Recording the review

A passing review is promoted into a closed Beads issue carrying exactly the
metadata fields `scripts/fable_review_gate.py`'s `_review_problems` checks
(`review_schema`, `review_module`, `review_artifact_sha256`,
`review_contract_sha256`, `review_governing_contract_sha256`,
`review_contract_ref`, `review_implementation_bead`,
`review_delegate_job_id`, `review_launch_envelope_sha256`, `review_model`,
`review_target`, `review_permission`, `review_permission_attested`,
`review_verdict`, `review_round`, `review_findings_unresolved`), labeled
`fable-review`. This logic lives inside `scripts/refinery_gate.py` itself
rather than a separate `scripts/record_fable_review.py` module so that only
one new contract entry is needed in `contracts/module-contracts.json` — the
conductor's `.scratch/record_fable_review.py` is gitignored and was not
available to reimplement from directly; this was rebuilt from
`schemas/fable-review-record.schema.json` and the exact fields
`fable_review_gate.py` reads.

`review_permission` is hardcoded `"read-only"`: this gate only ever prepares
reviews through `scripts/prepare_fable_review.py`, whose manifest permissions
block (`shell: none`, `network: none`, `write_roots: []`) is a fixed
structural invariant of that script, not something this gate's call sites
can vary. `review_permission_attested` is `"true"` only because this code
path runs strictly after `jobctl verify-review` has reported
`evidence_verified: true`.

### Final coverage re-check

After processing all changed governed modules, the gate re-runs
`scripts/fable_review_gate.py --json` and refuses unless every changed
governed module appears in its `covered` list. `fable_review_gate.py`'s CLI
always exits 1 by design (it is deliberately diagnostic-only and never
self-authorizes release) except on an internal error, where it exits 2 with
no JSON on stdout — so the gate treats a parseable JSON report as success
regardless of exit code, and only exit 2 / unparseable stdout as a hard
error.

### Scope boundaries

This script never merges, pushes to the target branch, or closes Beads —
`mol-refinery-patrol`'s `merge-push` step does that only after this gate
allows. It never edits `docs/design.md`, `policy/`, or existing
`contracts/module-contracts.json` entries — only its own new entry was added
(`deja-vu-design-md-governs-all-review-hashes`: any such edit stales every
existing Fable review record). Wiring `build_command` in `city.toml` to
invoke this script, and re-enabling the refinery agent's session limits, are
scoped to a separate bead under the `deja-vu-5x6` epic.

## Alternatives considered

- **Extend `scripts/fable_review_gate.py` itself to also submit reviews and
  gate the merge**: rejected — that script's own contract is explicitly
  "diagnose... while refusing to authorize release," and its coverage
  function treats local Beads records as untrusted input. Conflating
  diagnosis with the actual merge decision would blur that boundary and
  force every future coverage-only caller to carry review-submission
  side effects.
- **A separate `scripts/record_fable_review.py` module for the
  review-recording logic**: considered, since the bead allowed either
  location. Rejected in favor of keeping it inside `scripts/refinery_gate.py`
  — a second governed module would need its own new contract entry, and the
  bead scope only calls for one.
- **Trust `jobctl verify-review`'s exit code to distinguish pass from
  fix-first**: rejected after reading `gc_router/external_release_verifier.py`
  and `jobctl`'s `TERMINAL` set — `verify-review` exits 0 whenever the
  evidence itself is verifiable, regardless of the review's verdict content;
  only evidence problems raise non-zero. The gate must inspect
  `review.verdict` explicitly.

## Consequences

- The refinery can be re-enabled (in a follow-up bead) without merging
  unreviewed polecat work: every governed-module change gets a fresh,
  artifact-and-contract-bound Fable 5 review before landing.
- Review capacity is spent only after local quality gates already pass, and
  never spent twice for the same artifact/governing-contract hash beyond the
  documented 3-round/3-attempt cap.
- This gate is itself a governed module (`contracts/module-contracts.json`
  entry added) and therefore requires its own Fable review pass record
  before its first production use, same as any other executable module.
- This ADR does not itself re-enable the refinery agent or touch
  `city.toml` — that remains a separate `deja-vu-5x6` child bead.

## Receipts

- `contracts/module-contracts.json`: new `scripts/refinery_gate.py` entry.
- `scripts/fable_review_gate.py`: `check_coverage`, `_review_problems`,
  `discover_modules`, `governing_contract_sha256` (reused, not duplicated).
- `scripts/prepare_fable_review.py`: sealed prompt/manifest preparation and
  job id format (`...-r<round>-a<attempt>`).
- The `gc-router` repository's `bin/jobctl` and
  `gc_router/external_release_verifier.py`: `validate` / `submit` / `wait` /
  `verify-review` behavior and exit-code semantics.
- `schemas/fable-review-record.schema.json`: the review record shape used to
  reconstruct `write_review_record`'s metadata fields.
- `city.toml` rig `deja-vu` block: current refinery-disabled state and the
  `test_command` / `lint_command` / `build_command` `formula_vars`
  convention this gate is meant to be wired into.
- `deja-vu-5x6` (epic) and `deja-vu-5x6.1` (this bead).

## Status

Refinery re-enabled 2026-09-04. `build_command` runs
`scripts/refinery_gate.py`. First merge landed through the refinery.
