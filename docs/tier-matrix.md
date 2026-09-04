# Tier, lane, capability, and budget matrix

> This page is a readable view of [`policy/tier-matrix.json`](../policy/tier-matrix.json)
> (`schema_version: deja-vu.tier-matrix/v1`), which is the single canonical source of truth
> for tier and lane policy. If this page and the JSON ever disagree, the JSON wins — file an
> issue rather than trusting the prose. `SKILL.md`, `references/lanes.md`,
> `references/snowball-probe.md`, and `README.md` describe this same policy in narrative form;
> none of them is authoritative for the exact lane set or budget numbers.

Lane `phase` values (`discovery`, `shortlist_enrichment`, `probe`) match the lane envelope
defined in `docs/design.md` §5.2. `stage` is the hunt stage the lane belongs to (Stage 3 —
Sweep, Stage 5 — Probe, or Stage 6 — Judge).

## Lane count, resolved

Existing prose disagreed on the lane count: `README.md` said eight, `references/lanes.md`
enumerated 4 deterministic + 6 manual/subagent + 3 concept-hunt lanes (plus the Stage 5
hands-on probe, informally a 7th "manual" lane), and `scripts/sweep.py`'s `ALL_LANES` only
implements 4. **All of these are correct for what they describe, none of them is "the" lane
count** — lane count is tier-dependent, not fixed. The matrix below is the reconciliation:
15 lanes total (4 deterministic + 6 manual sweep-stage + 3 concept-hunt + 1 Judge-stage
provenance lane + 1 probe-stage lane), and each tier runs a bounded, explicit subset.

## Lanes

| Lane | Phase | Stage | Capability | Fallback | On unavailable |
|---|---|---|---|---|---|
| `github` | discovery | 3 | `github_search` | — | `unsupported`; required at every tier, no fallback — triggers `required_human_decision` |
| `registry` | discovery | 3 | `registry_lookup` | — | `skipped`; hunt may continue on remaining required lanes |
| `grep` | discovery | 3 | `code_pattern_search` | — | `degraded` on rate-limit backoff; partial results still count |
| `scorecard` | shortlist_enrichment | 3 | `scorecard_api` | `sweep.py --no-scorecard` | `skipped`; health falls back to `provenance.py` at Judge |
| `curation` | discovery | 3 | `web_fetch` | `general_web` | `unsupported`; optional at every tier |
| `github_code_reading` | shortlist_enrichment | 3 | `github_code_read` | `architecture_qa` | `unsupported`; optional at Standard/Full only, not part of Quick |
| `architecture_qa` | shortlist_enrichment | 3 | `web_fetch` | — | `unsupported`; map only, never a verdict substitute |
| `freshness` | discovery | 3 | `last30days_skill` | `web_search` | `degraded`; optional at Standard, **required at Full** |
| `skills_ecosystem` | discovery | 3 | `skills_index_search` | `general_web` | `unsupported`; optional at Standard/Full only, not part of Quick |
| `general_web` | discovery | 3 | `web_search` | — | `unsupported` |
| `standards_bodies` (concept) | discovery | 3 | `web_search` | — | `unsupported`; available at every tier via `concept_optional_lanes` |
| `framework_docs` (concept) | discovery | 3 | `web_fetch` | `general_web` | `unsupported`; available at every tier via `concept_optional_lanes` |
| `academic_survey` (concept) | discovery | 3 | `web_search` | — | `unsupported`; available at every tier via `concept_optional_lanes` |
| `provenance` | shortlist_enrichment | 6 (Judge) | `provenance_lookup` | — | `degraded` only — no-throw by design, never `unsupported`/`failed`; **required at Full** |
| `hands_on_probe` | probe | 5 | `sandbox_exec` | `architecture_qa` (weaker) | `unsupported`; Full tier must stop on `required_human_decision` |

Concept-hunt lanes (`standards_bodies`, `framework_docs`, `academic_survey`) are available at
every tier via that tier's `concept_optional_lanes`, and replace the code-discovery optional
lanes (`curation`, `skills_ecosystem`) only when the hunt has no code to sweep — see
`references/lanes.md` "Concept hunts" and the JSON's top-level `concept_hunt_policy`.
`scripts/sweep.py` still runs once even on a pure concept hunt; an empty result there is
expected, not a failed sweep.

The `provenance` lane runs at Stage 6 (Judge), not Stage 3 (Sweep): it evaluates the
maintainers of already-shortlisted candidates rather than discovering candidates itself. It is
required at Full tier for every shortlisted maintainer (see Evidence obligations below), and
`scripts/provenance.py` is written to never hard-fail — a missing or unreachable profile
degrades to an `unknown-experimental` signal instead of failing the lane.

## Tiers

| Tier | When | Required lanes | Optional lanes | Snowball | Probe | License check |
|---|---|---|---|---|---|---|
| **Quick** | Small script, easily reversed | `github`, `registry` | `curation` (+ concept lanes if no code to sweep) | 0 hops | none | not required |
| **Standard** | Module or notable dependency | `github`, `registry`, `grep`, `scorecard` | `curation`, `github_code_reading`, `architecture_qa`, `freshness`, `skills_ecosystem`, `general_web` (+ concept lanes) | 1 hop | DeepWiki Q&A allowed, no clone | required |
| **Full** | Subsystem, framework, or hard-to-reverse choice | `github`, `registry`, `grep`, `scorecard`, `hands_on_probe`, `provenance`, `freshness` | `curation`, `github_code_reading`, `architecture_qa`, `skills_ecosystem`, `general_web` (+ concept lanes) | 2-3 hops each direction | clone + smoke-test required, no exceptions | required |

`freshness` moves from optional at Standard to **required** at Full: the Full-tier evidence
obligations mandate a recorded freshness signal for the winning candidate, so the lane cannot
be merely optional there. `provenance` is required at Full only — it has no equivalent at
Quick or Standard, where no maintainer-provenance evidence is owed.

This resolves the Quick-tier pattern-search ambiguity directly: `grep` (pattern search) and
`scorecard` are **not** in Quick tier's required or optional lane set at all — Quick runs
`github` + `registry` only, exactly as `SKILL.md`'s tier table states, and any prose implying
Quick sweeps more than that is wrong.

## Budgets

| Tier | seconds | external_requests | tokens | probes | receipt_bytes |
|---|---|---|---|---|---|
| Quick | 90 | 15 | 15,000 | 0 | 50,000 |
| Standard | 420 | 45 | 90,000 | 0 | 250,000 |
| Full | 1,800 | 150 | 350,000 | 2 | 1,000,000 |

Per `docs/design.md` §7 rule 5, these are hard ceilings with durable units, not targets. A
lane or hunt that would exceed one stops instead of borrowing headroom from another budget
dimension.

## Stopping rules

Every tier shares the same four stopping-rule codes (`docs/design.md` §7 rule 6):

- **`sufficient_verified_fit`** — a candidate meets the tier's evidence obligations, the
  pre-registered exclusion criteria, and the rubric threshold. Stop sweeping further lanes.
- **`exhausted_bounded_coverage`** — every required lane has a terminal status and every
  optional lane has been attempted or explicitly declined. No further coverage exists within
  the tier's lane set.
- **`budget_exhaustion_with_uncertainty`** — a budget ceiling is reached before sufficient fit
  is established. Stop immediately; record the residual uncertainty, never extend the budget
  silently.
- **`required_human_decision`** — evidence trends toward BUILD, a required capability is
  unsupported at a tier where it is required, or authority for a non-trivial reuse route is
  needed. Hand off to the human gate (`SKILL.md` Stage 7).

## Degraded behavior

Per `docs/design.md` §7 rules 3-4, host adapters report capabilities before planning and never
invent silent fallbacks mid-execution. Each lane above lists its one documented fallback (or
`—` if none exists) and the lane status a missing capability produces
(`degraded`, `skipped`, or `unsupported`, per the lane-envelope status vocabulary in
`docs/design.md` §5.2). An `unsupported` status on a required lane never counts as an empty
success (`docs/design.md` §2.3); instead it triggers the `required_human_decision` stopping
rule, halting automated execution for human handoff. `blocked` is a separate, hunt-level state
reserved for an expired probe lease pending reconciliation (`docs/design.md` §7) — it is not
one of the lane-envelope statuses and must not be used as a lane status.
