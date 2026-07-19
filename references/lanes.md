# Stage 3 — Sweep

Eight lanes, each answering a question no other lane can. Run them **blind to each other**: a
lane that knows what another lane already found starts confirming instead of searching. Brief
each lane subagent with only the Stage 2 output (vocabularies + exclusion criteria) — never with
another lane's candidates. Dedup and ranking happen once, after the barrier, in the main thread.

## Deterministic lane: `scripts/sweep.py`

Covers GitHub, registries, pattern-search, and health/Scorecard in one stdlib-only, no-throw
script. Run it once per tier (`SKILL.md` table has the exact flags per tier); it never crashes —
failures land in its `errors[]` field — and it never emits a composite score.

```
python3 scripts/sweep.py --query "<problem keywords>" [--pattern "<regex for grep.app>"] \
  [--language <lang>] [--limit N] [--lanes github,registry,grep,scorecard] [--no-scorecard]
```

stdout (single JSON object):

```json
{
  "query": "...",
  "lanes_run": ["github", "registry", "grep", "scorecard"],
  "candidates": [
    {"name": "...", "url": "...", "source_lane": "github", "description": "...",
     "stars": 0, "last_push": "...", "license": "...", "scorecard": {...},
     "registry_downloads": 0}
  ],
  "errors": []
}
```

Run it with the widest `--query` first (one of the Stage 2 vocabularies), then re-run with a
second vocabulary if the first returns thin results — don't assume one phrasing covers the space.

### Quick tier: when results look wrapper-heavy

On the quick tier (github + registry only), if hits are mostly thin wrappers or low-star
clones of the same idea, **add one LibHunt alternatives check before judging**:

```
https://www.libhunt.com/search?q=<term>
```

Keyword sweeps miss category leaders when self-description vocabulary diverges. Day-one
link-checking hunt: two sweeps (`markdown link checker`, `broken link checker`) returned
wrapper actions and a dormant runner-up — **lychee** (the actual category leader) only
surfaced after a curation/lookup pivot. One LibHunt pass is cheap insurance against that
failure mode; it is not a substitute for a second vocabulary, it sits beside it.

## Deterministic lane detail: what `sweep.py` is actually hitting

| Lane (`--lanes` value) | Question it answers | What it calls |
|---|---|---|
| `github` | What repos claim to solve this? | `gh search repos` equivalent — name, description, stars, URL |
| `registry` | Is it published? | npm / PyPI / crates.io metadata APIs |
| `scorecard` | Is it maintained safely? | OpenSSF Scorecard API (`api.securityscorecards.dev`) — skip with `--no-scorecard` on the Quick tier |
| `grep` | Does anyone actually *write* this pattern? | `grep.app` regex search over ~1M public repos; backs off gracefully on 429 |

## Manual/subagent lanes (no script yet — dispatch as blind parallel briefs)

| Lane | Question it answers | Concrete invocation |
|---|---|---|
| **GitHub code reading** | What does the code in a shortlisted repo actually do? | octocode-mcp tools for repo analysis and code search/reading, once `sweep.py`'s `github` lane has a shortlist |
| **Curation** | What do humans say the alternatives are? | LibHunt URL-swap: `github.com/<owner>/<repo>` → `libhunt.com/<owner>/<repo>`; fetch awesome-/best-of lists relevant to the vocabulary |
| **Probe (architecture Q&A)** | How is it built, at a level above raw source? | DeepWiki URL-swap: `github.com` → `deepwiki.com` on any shortlisted repo — ask it targeted architecture questions before the hands-on sandbox probe (`references/snowball-probe.md`) |
| **Freshness** | Did someone ship this in the last 30 days? | Invoke the `last30days` skill if installed (sweeps Reddit/X/HN/YouTube); if not installed, degrade to a plain `WebSearch` for `"<vocabulary>" 2026` — never hard-fail the lane for a missing optional dependency |
| **Skills ecosystem** | Did someone already build this as an agent skill? | `npx skills search "<vocabulary>"` (vercel-labs find-skills) or the skills.sh index |
| **General web** | What do essays/comparisons/discussions say? | `WebSearch` over `"<vocabulary>" vs`, `"<vocabulary>" alternatives`, `"<vocabulary>" review` |

## Concept hunts

Not every prior-art question has code to sweep. Design-pattern and architecture questions
("how should we structure multi-tenant isolation?", "is there a standard for X?") still run
the same loop — framing → blind parallel lanes → snowball → judge → gate — but the **lanes
become different sources**:

| Concept-hunt lane | What it answers | Where to look |
|---|---|---|
| **Standards bodies** | Is this codified? | ISO, INCOSE, IETF RFCs, W3C, NIST — search the body's catalog, not just web essays about it |
| **Framework docs** | Did a mature framework already decide this? | Official guides and ADRs for the stack in play (e.g. Django multi-tenancy patterns, k8s multi-tenancy docs) |
| **Academic / survey search** | What does the literature call the shape? | Scholar / Semantic Scholar / recent survey papers for the vocabulary from Stage 2 |

`scripts/sweep.py` may return empty or near-empty on pure concept hunts — that is expected,
not a failed sweep. Still run it once (a library sometimes *does* encode the pattern); then
weight the concept lanes above. Receipts still required: name the standard/RFC/doc page,
not a vibe.

## Dispatch pattern

One subagent per manual lane, each given: the solution-free problem (Stage 0), all 2–3
vocabularies and the pre-registered exclusion criteria (Stage 2), and nothing else. Each returns
candidates + receipts (the query it ran and what came back) — never a raw page dump. After every
lane (script + subagents) reports, merge into one candidate list, drop anything that fails an
exclusion criterion outright, and carry the rest into Stage 4 (Snowball).
