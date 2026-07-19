# deja-vu

> The skill that gives your agent the feeling it has seen this problem before.

A Claude Code / Claude Agent Skill that runs a structured prior-art hunt **before** anything
custom gets built. It's the pause between "here is the problem" and "here is my design" — the
question coding agents (and humans) systematically skip: *who has already solved this?*

## Philosophy

Most problems are already solved; the gap is *seeing* the solution. The economics are brutally
asymmetric — finding an existing solution costs minutes, rebuilding it costs hours now and
maintenance forever, and every dependency you don't reinvent hands you battle-tested edge cases
for free. deja-vu closes that gap with a ten-stage loop, each stage earned by a specific,
observed failure mode: it re-frames the problem before searching (so it doesn't search for the
wrong thing well), sweeps eight blind parallel source lanes (so it doesn't miss a whole category
of prior art), snowballs and hands-on probes the strongest hits (so it doesn't trust a README
that undersells its own project), judges on a declared, unweighted rubric instead of star count,
and — the part most "check for prior art" prompts skip — refuses to let a BUILD verdict
self-approve. Adopting, forking, or vendoring proceeds on the agent's own judgment; building
custom goes to a human with receipts.

Full design rationale, the failure-mode-per-stage derivation, and every ADR: [`docs/design.md`](docs/design.md).

## Install

**Option A — git clone + symlink** (full control over the checkout location):

```bash
git clone <this-repo-url> "$HOME/workplace/deja-vu"
ln -s "$HOME/workplace/deja-vu" "$HOME/.claude/skills/deja-vu"
```

Verify the symlink resolves:

```bash
ls -la "$HOME/.claude/skills/deja-vu"
```

**Option B — [`npx skills`](https://github.com/vercel-labs/skills)** (fetches directly from
GitHub, no manual clone):

```bash
npx skills add <owner>/deja-vu
# or, with the full URL:
npx skills add https://github.com/<owner>/deja-vu
```

Either way, that's the whole install — `SKILL.md`'s frontmatter is what makes Claude Code
pick it up automatically on build-ish prompts.

### Optional dependencies (the skill degrades gracefully without them)

- **octocode-mcp** — gives the GitHub lane real code search/reading instead of just repo
  metadata:
  ```bash
  claude mcp add-json octocode --scope user '{"command":"npx","type":"stdio","args":["@octocodeai/mcp@latest"]}'
  ```
- **last30days** — feeds the freshness lane recent Reddit/X/HN/YouTube signal instead of a plain
  web search. If you already have it installed as a skill, deja-vu picks it up automatically.

Neither is required. `scripts/sweep.py` and `scripts/provenance.py` are stdlib-only Python and
run with nothing beyond a Python 3 interpreter and network access.

## Setup check

After installing, run:

```bash
python3 scripts/doctor.py
```

It prints one `DOCTOR: PASS|WARN|FAIL` line per dependency (gh CLI, octocode MCP, grep.app,
OpenSSF Scorecard API, skills CLI, last30days). It exits nonzero only when a REQUIRED check
fails; optional lanes degrade to WARN, and each WARN line names its install command.

Illustrative sample output:

```
DOCTOR: PASS python3
DOCTOR: PASS github
DOCTOR: WARN last30days — install: npx skills add last30days (or install as a Claude Code skill)
```

## A worked example (fully synthetic)

> Everything below — repo names, star counts, maintainer handles, dates — is **illustrative,
> fabricated for this README**, not a real hunt. It shows the shape of the output, not a real
> verdict.

**Prompt:** "I'll write a token-bucket rate limiter for our API gateway."

**Stage 0 (Re-problem):** Solution-free restatement — "prevent one client from starving the
gateway's fixed downstream budget." Five whys don't surface a different problem; a null solution
(raising the downstream budget) was already ruled out by the team as too costly. Survives —
proceed.

**Stage 1 (Trigger/tier):** Registry check: no prior entry for this problem. Stakes classifier:
this sits on every request path and will be depended on indefinitely → **Full** tier.

**Stage 2 (Framing):** Vocabularies — "rate limiter," "token bucket / leaky bucket algorithm,"
"API throttling middleware." Exclusion criteria pre-registered: no LICENSE file disqualifies
FORK/VENDOR; unmaintained (no commits in 12 months) disqualifies DEPEND.

**Stage 3 (Sweep), illustrative excerpt from `sweep.py`:**

```json
{"query": "token bucket rate limiter", "lanes_run": ["github", "registries", "scorecard"],
 "candidates": [
   {"name": "acme-org/ratelimit-go", "url": "https://github.com/acme-org/ratelimit-go",
    "source_lane": "github", "stars": 4200, "last_push": "2026-06-30",
    "license": "Apache-2.0", "scorecard": {"score": 8.1}},
   {"name": "someone/twitter-scrape-tool", "url": "https://github.com/someone/twitter-scrape-tool",
    "source_lane": "github", "stars": 9800, "last_push": "2024-01-02",
    "license": "MIT", "scorecard": {"score": 3.2}}
 ], "errors": []}
```

The second hit has more than double the stars and gets discarded immediately — it's an
unrelated scraper that happened to match the search term (the real failure mode this stage
guards against; see `references/judge.md`).

**Stage 4–5 (Snowball/Probe):** `acme-org/ratelimit-go` forks and depends on a smaller primitive,
`acme-org/bucket-core`, which turns out to be the more composable piece for this use case. Cloned
both into a scratch sandbox; ran their test suites; read the token-refill implementation —
matches the README, no surprises.

**Stage 6 (Judge):** Declared weights — health > license > competency (commodity plumbing on a
hot path). Health: 6 contributors active in the last 90 days, no single-org concentration,
Scorecard 8.1. License: Apache-2.0, permissive, no trap. Competency: rate limiting is not this
team's differentiator. Fence check: the library assumes a single-process in-memory bucket by
default and needs a Redis-backed variant for the actual multi-instance gateway — a real,
inheritable gap, not disqualifying, but worth knowing going in.

**Stage 6b (Provenance):**

```json
{"profiles": [{"login": "acme-maintainer", "company": "Acme Infra Co.", "account_age_years": 6.5,
  "followers": 340, "public_repos": 41, "signal": "established-practitioner"}]}
```

**Stage 7 (Gate):** DEPEND proceeds without human sign-off — that's the point of the asymmetric
gate.

**Verdict: DEPEND** on `acme-org/ratelimit-go` (Redis-backed configuration), with a follow-up
note in the ADR about the in-memory-default fence.

**Stage 8 (Record):** ADR written; registry line appended with `review_by` six months out
(single-org-adjacent health signal warrants a shorter recheck than a fully diffuse-maintainer
project would).

## Credits

deja-vu borrows every algorithm in its loop from published prior art — the only new part is the
loop that composes them, and even that was searched for before being built (see `docs/design.md`
§6 for the full prior-art hunt this skill ran on itself). Named with gratitude:

- [build-vs-borrow](https://github.com/trelmitt/claude-skills/tree/main/build-vs-borrow) — the
  closest prior art: an 8-stage DEPEND/FORK/VENDOR/BUILD pipeline with a working stdlib scout
  script. Reimplemented rather than forked (no LICENSE file, unknown-experimental provenance) —
  see ADR-1 in `docs/design.md`.
- [find-skills](https://github.com/vercel-labs/skills) — solves a different, adjacent problem
  (finding installable agent skills); wired in as the skills-ecosystem lane.
- Kitchenham & Charters' systematic-review protocol — pre-registered inclusion/exclusion
  criteria, the backbone of `references/framing.md`.
- [Wohlin's snowballing guidelines](https://www.wohlin.eu/ease14.pdf) — the backward/forward hop
  method in `references/snowball-probe.md`.
- [QSOS](https://en.wikipedia.org/wiki/QSOS) — context-weighted, declare-first scoring instead
  of a single composite number.
- [CHAOSS](https://chaoss.community/) — the contributor-absence-factor health signal.
- [OpenSSF Scorecard](https://openssf.org/projects/scorecard/) — automated repo health checks.
- [Choose Boring Technology](https://mcfunley.com/choose-boring-technology) — the reversibility
  framing in the rubric.
- [In Defense of Not-Invented-Here Syndrome](https://www.joelonsoftware.com/2001/10/14/in-defense-of-not-invented-here-syndrome/)
  (Spolsky) — the competency-test dimension: commodity plumbing defaults to adopt.

Full citation list, including SEI PECA, Endor Labs' reachability principle, and the
Chesterton's-Fence/Hyrum's-Law fence check, is in `docs/design.md` §6.

## License

MIT — see [`LICENSE`](LICENSE).
