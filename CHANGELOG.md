# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
