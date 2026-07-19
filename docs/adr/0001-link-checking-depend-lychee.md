# ADR-1: Check doc links in CI with lychee, not a custom script

**Date:** 2026-07-19
**Status:** accepted

## Context

External URLs in this repo's documentation (README, design doc, references) rot over time,
and a repo whose value proposition is *receipts* refutes itself when its receipt links die.
We want CI to notice dead links before readers do. The reflex was to write a small custom
checker script — the exact reflex this skill polices, so the decision went through the hunt.

## Options considered

| Candidate | Rubric summary | Provenance | Why it lost / won |
|---|---|---|---|
| lycheeverse/lychee (+ lychee-action) | CI-fit: purpose-built official action; activity: pushed this week; license: Apache-2.0; rate limits: built-in retries + `.lycheeignore` | org-backed (lycheeverse), 3,773★ / action 498★ | **Won** on every declared dimension |
| tcort/markdown-link-check | active (pushed this month), ISC, CI-usable | single-maintainer, 712★ | Markdown-only, node runtime; healthy runner-up |
| stevenvachon/broken-link-checker | 2,074★ but last push 2024-01 | single-maintainer | Excluded: dormancy criterion (>2y) pre-registered before the sweep |
| ruzickap/action-my-markdown-link-checker | wrapper action, 21★ | single-maintainer | Thin wrapper over the category it wraps; adopt the engine, not the wrapper |
| Custom script (BUILD) | — | — | Commodity plumbing fails the competency test; zero innovation-token justification |

## Decision

**Verdict:** DEPEND

Adopt lychee via `lycheeverse/lychee-action` as a CI step, unmodified, with a
`.lycheeignore` for known rate-limited hosts. Fence check: the existing tools look the way
they do because CI link-checking's hard parts are retries, rate limits, and false-positive
management — a naive custom script rediscovers all three the hard way. Reversibility: near
zero cost in either direction (delete one CI step), which is also why the quick tier was
the right depth.

## Receipts

- Sweep, vocabulary 1: `python3 scripts/sweep.py --query "markdown link checker" --lanes github,registry --limit 5 --no-scorecard` → wrapper actions only; category leader absent
- Sweep, vocabulary 2: `--query "broken link checker"` → surfaced stevenvachon/broken-link-checker (2,074★, dormant since 2024-01)
- Vocabulary lesson: lychee self-describes as an "async link checker" — neither markdown- nor broken- keyword sweep found it; confirmed via direct lookup
- `gh api repos/lycheeverse/lychee` → 3,773★, Apache-2.0, pushed 2026-07-14, not archived
- `gh api repos/lycheeverse/lychee-action` → 498★, Apache-2.0, pushed 2026-07-09
- `gh api repos/tcort/markdown-link-check` → 712★, ISC, pushed 2026-07-01
