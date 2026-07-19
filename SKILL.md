---
name: deja-vu
version: 0.1.0
description: >-
  Structured prior-art hunt that runs BEFORE anything custom gets built — the "has someone
  already solved this?" reflex, done as a disciplined loop instead of a vague feeling. Fires
  WHENEVER about to scaffold a commodity-ish capability from scratch, even if the user only
  said "build X": e.g. a rate limiter, auth/SSO flow, parser, job queue or scheduler, cache,
  retry/backoff logic, diff engine, template engine, config loader, migration runner, event
  bus, feature-flag system, notification/email pipeline, webhook delivery, search/index
  layer, state machine, file/CSV/PDF pipeline, dedupe engine, changelog generator, i18n
  layer (illustrative, not exhaustive). Also fires on: "let's build", "I'll write a
  script/tool/library that", "we need a", "implement a", "create a subsystem/service for",
  "is there something that already does X", "has anyone solved X", "don't reinvent the
  wheel", "should I roll my own or use a library", new-dependency or new-subsystem
  proposals. Runs proportional-depth (quick/standard/full) across parallel source lanes,
  snowballs from strong hits, probes shortlisted candidates hands-on, and returns one of six
  verdicts — NOT-A-PROBLEM, DIFFERENT-PROBLEM, DEPEND, FORK, VENDOR, BUILD — with receipts. A
  BUILD verdict cannot self-approve; it goes to the human. DO NOT USE FOR trivial edits — typo
  fixes, renames, one-line config tweaks, formatting, or continuing a build already approved
  by a prior deja-vu run (check the decisions registry first).
allowed-tools:
  - Bash
  - Read
  - WebFetch
  - WebSearch
---

# deja-vu

Most problems are already solved; the gap is *seeing* the solution. Finding it costs minutes —
rebuilding it costs hours now and maintenance forever, and every dependency you don't reinvent
hands you battle-tested edge cases for free. This skill is the pause between "here is the
problem" and "here is my design": a structured hunt for prior art before custom code gets written.

Full rationale and the failure mode each stage prevents: `docs/design.md`.

## Setup check

```
python3 scripts/doctor.py
```

One `DOCTOR: PASS|WARN|FAIL` line per dependency (gh, octocode MCP, grep.app, Scorecard API,
skills CLI, last30days), exit nonzero only when a **required** check fails. Run once after
install and any time a lane misbehaves. Optional lanes degrade to WARN — the skill stays
usable without them; each WARN line names its install command.

## 0. Before anything: check the registry

A hunt already run for this problem is never re-run — only re-validated if stale.

```
grep -l '"problem"' data/decisions-registry.jsonl 2>/dev/null && cat data/decisions-registry.jsonl
```

If a matching entry exists and its `review_by` date hasn't passed, cite it and stop — do not
re-hunt. If stale, re-validate the top candidate only (skip straight to stage 5). Details:
`references/record.md`.

## 1. Stakes classifier → pick a tier

Estimate build cost, maintenance surface (will this be depended on?), and reversibility (how
expensive is being wrong?) before choosing depth. A flat full-depth hunt on every trigger gets
this skill disabled within a week — the opposite failure of never searching at all.

| Tier | When | What runs | Invocation |
|---|---|---|---|
| **Quick** | Small script, easily reversed | GitHub + registry lanes only | `python3 scripts/sweep.py --query "<keywords>" --lanes github,registry --limit 5 --no-scorecard` |
| **Standard** | Module or notable dependency | + pattern + health/scorecard, snowball 1 hop, license check | `python3 scripts/sweep.py --query "<keywords>" --lanes github,registry,grep,scorecard --limit 10` |
| **Full** | Subsystem, framework, or hard-to-reverse choice | all 10 stages: full sweep, snowball, probe, provenance, freshness, full rubric | sweep as above, then `python3 scripts/provenance.py --owner <login1> --owner <login2>` on every shortlisted maintainer |

Deterministic-first: scripts sweep, fetch, and score — JSON out, never a composite number.
The LLM spends judgment only where judgment is needed: framing, probing, the rubric, the verdict.

## The loop

Each stage is derived from a specific failure mode (design.md §2) — do not skip one to save time.

| # | Stage | One-liner | Detail |
|---|-------|-----------|--------|
| 0 | **Re-problem** | Restate with zero solution vocabulary; five whys; check null solutions (do nothing / delete the requirement). Can end here: `NOT-A-PROBLEM` or `DIFFERENT-PROBLEM`. Underspecified ask → hand off to `agent-skills:interview-me`. | `references/re-problem.md` |
| 1 | **Trigger** | Already done if you're reading this — the description fired. Confirm tier (above) and registry (step 0). | inline, above |
| 2 | **Framing** | Restate the problem in 2–3 vocabularies a *different community* would use; write exclusion criteria **before** seeing any candidate. | `references/framing.md` |
| 3 | **Sweep** | Run `scripts/sweep.py` per the tier's invocation. Dispatch remaining lanes (curation, freshness, skills-ecosystem, general web) as blind parallel subagents — each briefed only on the framing output, never on another lane's results. | `references/lanes.md` |
| 4 | **Snowball** | From every strong hit, chase 2–3 hops backward (deps, stated inspirations, what it forked) and forward (who depends on it, who forked it). Standard tier: 1 hop. | `references/snowball-probe.md` |
| 5 | **Probe** | READMEs undersell. Clone the top 1–2 shortlisted candidates shallow into a scratch dir, install, run a smoke test, read the load-bearing source. Full tier only (or stale re-validation). | `references/snowball-probe.md` |
| 6 | **Judge** | Score only the dimensions declared up front (QSOS): competency test, innovation-token cost, health (`python3 scripts/provenance.py --owner <login>` for maintainer signal + Scorecard from the sweep output), license bucket (flag AGPL/SSPL/no-LICENSE explicitly), fence check, reversibility. Stars are the weakest signal — never rank on them. | `references/judge.md` |
| 7 | **Gate** | See below — imperative, not advisory. | inline, below |
| 8 | **Record** | Write an ADR + append one line to `data/decisions-registry.jsonl`. | `references/record.md` |
| 9 | **Learn** | Nothing to do at hunt time — debrief is a separate, later invocation. | `references/learn.md` |

## The six verdicts

| Verdict | Meaning | Issued by |
|---|---|---|
| **NOT-A-PROBLEM** | Null solution wins: do nothing / delete the requirement | Stage 0 |
| **DIFFERENT-PROBLEM** | Real problem is X, not Y; restart from X | Stage 0 |
| **DEPEND** | Adopt as a dependency, unmodified | Gate (proceeds) |
| **FORK** | Adopt and diverge; you own the delta | Gate (proceeds) |
| **VENDOR** | Copy in and amend; you own the copy (license permitting) | Gate (proceeds) |
| **BUILD** | Nothing fits; build custom | Gate (**human sign-off required**) |

## THE ASYMMETRIC GATE

**DEPEND, FORK, and VENDOR proceed on your own judgment — adopting proven work is the safe
default. Do not pause for permission on these three.**

**A BUILD verdict is the one this skill exists to police. It cannot be self-approved.** Stop.
Present the human with receipts — every candidate considered, the rubric scores, why each one
was disqualified — and wait for explicit sign-off before writing a line of custom code. If you
find yourself rationalizing past this gate ("we're basically out of time," "none of these are
*quite* right but BUILD feels obvious"), that is precisely the moment the gate exists for.

## Record + learn

After the gate resolves: write the ADR, append the registry line (`references/record.md`), then
stop — the hunt is done. Only run the debrief loop (`references/learn.md`) when explicitly asked
to review past verdicts; it never edits this file without a human confirming the change first.
