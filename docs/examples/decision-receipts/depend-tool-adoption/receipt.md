# Exemplar: depend on a purpose-built CI tool instead of a custom link checker

**Label:** real — re-encodes this repository's own published `docs/adr/0001-link-checking-depend-lychee.md` into the decision-packet schema, with a fresh re-verification. No simulated data.

**Verdict:** DEPEND · **Confidence:** high · **Degraded lanes:** none · **Evidence gaps:** none

## Problem

CI needed to catch dead external links in this repo's Markdown docs before readers do — a
receipts-first repo that links to rotted evidence undermines its own premise. The reflex was
to write a small custom checker script; deja-vu ran its own hunt on that reflex first (ADR-1).

## Reasoning path

Full sweep, judge, and gate receipts already exist in `docs/adr/0001-link-checking-depend-lychee.md`
(dated 2026-07-19) — this exemplar does not repeat that work, it re-expresses the already-made
decision in the compositional packet schema (ADR-11) and re-confirms the winning candidate is
still healthy today.

Four real candidates plus the custom-build null-option were compared; `lycheeverse/lychee`
won on every declared dimension (CI-fit, activity, license, built-in retry/rate-limit
handling). The fence check named the actual hard parts of link-checking — retries, rate
limits, false-positive management — that a naive custom script would rediscover the hard way.

## Receipts

- `docs/adr/0001-link-checking-depend-lychee.md` — primary source, full sweep table and
  receipts (`gh api` calls against all four real candidates, dated 2026-07-19).
- `gh api repos/lycheeverse/lychee` re-verified 2026-09-11: license Apache-2.0,
  stargazers_count 3902, archived false, pushed_at 2026-09-08T16:32:45Z — still healthy
  and active seven weeks after the original decision.
- This repository's own `.github/workflows/ci.yml` runs the link-check step in every CI run —
  evidence_level `operational`, not merely documented, because it executes on every push/PR.
- Decision packet: `packet.json` in this directory, validated against
  `schemas/decision-packet.schema.json`.
