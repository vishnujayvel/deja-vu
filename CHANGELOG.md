# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `SKILL.md` frontmatter no longer fails Codex skill-creator structural
  validation: moved the bare top-level `version` key (unsupported per the
  Agent Skills spec's allowed-property set) under `metadata.version`, and
  trimmed the `description` field from 1474 to 1007 characters to clear the
  1024-character cap — both were blocking `Skill is valid!` on this skill.
  `scripts/sync_codex_plugin.py`'s manifest-version check now reads
  `metadata.version` from the frontmatter block instead of a top-level key.
- Slimmed activated context: cut the "Trust boundary" section's inline
  sandbox-protocol restatement (already fully covered in
  `references/snowball-probe.md`'s Stage 5) down to the core invariant plus
  a pointer, removing duplication between always-loaded and progressively-
  disclosed content. `SKILL.md` drops from 171 to 162 lines, 1881 to 1747
  words, 12,742 to 11,775 Unicode characters (12,820 to 11,849 UTF-8 bytes),
  ~3,185.5 to ~2,943.75 estimated tokens (chars/4), with no change to the
  six verdicts, the asymmetric BUILD gate, or the trust boundary's actual
  rules.

## [0.1.1] - 2026-07-19

### Fixed

- Offline evals now assert doc↔script lane-name consistency: every token inside a
  `--lanes` invocation in `SKILL.md` and `references/lanes.md` must be a member of
  `scripts/sweep.py`'s `ALL_LANES`. Drift fails CI with the drifted token named
  (closes an undetected doc/script mismatch gap).
- Live eval mode no longer relies on `--max-turns 1` + text-grep alone (1-turn
  budgets suppress skill invocation). Preferred path uses
  `--output-format stream-json --verbose --max-turns 3` and detects a Skill/skill
  tool invocation naming `deja-vu` in the JSON event stream; falls back to the
  old text-grep path when stream-json is unsupported. `--help` documents that
  live results measure headless trigger behavior, which may differ from
  interactive sessions.

### Added

- Quick-tier guidance in `references/lanes.md`: when github+registry hits look
  wrapper-heavy, run one LibHunt alternatives check before judging (cites the
  day-one lychee miss under two keyword sweeps).
- Concept-hunts subsection in `references/lanes.md`: for design-pattern /
  architecture questions with no code to sweep, lanes become standards bodies
  (ISO/INCOSE/RFCs), framework docs, and academic search — same loop, different
  sources.

## [0.1.0] - 2026-07-19

Initial release.

### Added

- The ten-stage deja-vu loop (`SKILL.md`, `docs/design.md`): re-problem, trigger,
  framing, sweep, snowball, probe, judge (artifact + provenance), gate, record, learn.
- `scripts/sweep.py` — stdlib-only, no-throw multi-lane sweep (GitHub, package
  registries, grep.app pattern search, OpenSSF Scorecard).
- `scripts/provenance.py` — stdlib-only maintainer-provenance judge
  (established-practitioner / active-builder / unknown-experimental signal).
- Reference guides for each stage under `references/` (framing, judge, lanes,
  learn, re-problem, record, snowball-probe).
- Unit test suite (`tests/`) — offline-tolerant, HTTP mocked via recorded fixtures.
- Eval harness (`evals/`) — `trigger_cases.jsonl` synthetic fire/silent fixtures,
  `run_evals.py` offline schema validator plus an experimental `--live` mode, and
  three seeded `verdict_cases/` fixtures for future verdict-quality scoring.
- CI (`.github/workflows/ci.yml`) — pytest, offline evals, and a repo
  sanitization sweep (`scripts/sanitize_check.sh`) on every push and PR.
- MIT license.
