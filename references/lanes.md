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

## Dispatch pattern

One subagent per manual lane, each given: the solution-free problem (Stage 0), all 2–3
vocabularies and the pre-registered exclusion criteria (Stage 2), and nothing else. Each returns
candidates + receipts (the query it ran and what came back) — never a raw page dump. After every
lane (script + subagents) reports, merge into one candidate list, drop anything that fails an
exclusion criterion outright, and carry the rest into Stage 4 (Snowball).
