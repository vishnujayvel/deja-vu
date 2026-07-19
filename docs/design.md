# deja-vu — Design

> The skill that gives your agent the feeling it has seen this problem before.

**Status:** approved for implementation · **Version:** 1.0 · **Date:** 2026-07-19 · **Author:** Vishnu Jayavel

---

## 1. Philosophy

Most problems are already solved; the gap is *seeing* the solution. The economics are
brutally asymmetric: finding an existing solution costs minutes, while rebuilding it costs
hours now and maintenance forever — and every dependency you *don't* reinvent hands you
battle-tested edge cases for free. Yet coding agents (and humans) systematically slide from
"here is the problem" straight into "here is my design" without pausing at "who has already
solved this?" deja-vu exists to close exactly that gap: it is a structured, tool-rich,
self-improving prior-art hunt that runs *before* anything custom gets built. This document
was itself produced under the discipline it describes: before designing deja-vu, we hunted
for existing prior-art skills, found four, probed the best one hands-on, and reimplemented
its strongest ideas (§6).

## 2. The loop: ten stages, each earned by a failure mode

Every stage exists because a specific, observed failure mode demands it. Remove a stage and
its failure mode returns. That is the design invariant: **stages are derived, not brainstormed.**

| # | Stage | Failure mode it prevents | Mechanism |
|---|-------|--------------------------|-----------|
| 0 | **Re-problem** | Solving the wrong problem perfectly (XY problem) | Solution-free problem statement; five whys; null-solution check |
| 1 | **Trigger** | The search never happens | Auto-fire on build/design moments; commodity detection; stakes classifier |
| 2 | **Framing** | Searching your solution's vocabulary, not the problem's | Multi-vocabulary restatement; pre-registered exclusion criteria |
| 3 | **Sweep** | Single-angle search misses whole categories | Parallel blind lanes (§5) |
| 4 | **Snowball** | Stopping at page one of results | 2–3 hops backward/forward from any strong hit |
| 5 | **Probe** | Trusting READMEs — docs chronically undersell | Sandbox install/run; interrogate the code itself |
| 6a | **Judge: artifact** | Star-ranking; one-number scores | Context-weighted rubric (§2.6) |
| 6b | **Judge: provenance** | Adopting a weekend experiment dressed as a product | Maintainer profile; orthogonality rule |
| 7 | **Gate** | Advisory verdicts get rubber-stamped under pressure | Asymmetric gate: BUILD needs human sign-off |
| 8 | **Record** | Re-litigating in 18 months; re-hunting the same question | ADR + decisions registry, checked at trigger time |
| 9 | **Learn** | The rubric never improves; wrong verdicts repeat | Debrief loop scoring past verdicts |

### 2.0 Re-problem

Before any search: is this the right problem? The XY problem — asking for help with your
attempted solution (Y) instead of your actual problem (X) — poisons every downstream stage.
Mechanisms: restate the problem with **zero solution vocabulary** in it; ask who actually
experiences it and what they would call success; run five whys down to the underlying need;
check the **null solutions** — do nothing, delete the requirement, change the process.
Jobs-to-be-Done framing applies: customers don't want a quarter-inch drill, they want a
quarter-inch hole. Only a problem that survives this stage earns a hunt. Two of the six
verdicts (§3) can be issued here without any searching at all — they are the cheapest wins
the skill produces.

### 2.1 Trigger

The characteristic failure is not a bad search — it is *no* search. The skill's description
auto-fires on build/design moments ("let's build", "we need a", "I'll write a script that",
new-subsystem proposals) and on commodity-subsystem nouns (rate limiter, auth flow, parser,
job queue, scheduler, cache, retry logic, diff engine, template engine…). At trigger time,
two cheap checks run first: the **decisions registry** (§2.8 — has this hunt already been
done?) and the **stakes classifier** (§4 — how deep should this hunt go?).

### 2.2 Framing

Prior art hides behind vocabulary. A "spec drift detector" is also a "doc-code sync
checker," a "living documentation tool," and a "docs-as-tests framework" — four search
strings, four different result sets. The stage produces: (a) the problem restated in 2–3
distinct vocabularies, including the terms a *different community* would use; (b)
**exclusion criteria written before searching** (Kitchenham's rule from systematic-review
methodology): decide what disqualifies a candidate *before* you meet one, so you cannot
rationalize a tempting hit in after the fact.

### 2.3 Sweep

Parallel lanes, each blind to the others (§5). Blindness is deliberate: a lane that knows
what another lane found starts confirming instead of searching. Lanes return raw candidates
with receipts; deduplication and ranking happen after the barrier, not inside any lane.

### 2.4 Snowball

Wohlin's snowballing, ported from academic systematic reviews: from any strong hit, chase
2–3 hops **backward** (its dependencies, its stated inspirations, what it forked) and
**forward** (who depends on it, who forked it, who discusses it). Snowballing is empirically
competitive with exhaustive database search at a fraction of the cost — and it is how the
non-obvious finds happen: the best candidate is often one hop away from a mediocre search
hit, in a repo whose name shares no vocabulary with your query.

### 2.5 Probe

READMEs undersell, oversell, and omit. The only ground truth is the artifact itself.
For shortlisted candidates (top 1–2): install into a scratch sandbox and run it; read the
actual source of the load-bearing parts; interrogate architecture via DeepWiki. A real
observed case: a spec framework's configuration file contained a native extension slot that
no documentation page mentioned — it was discovered only by running the framework's `init`
in a sandbox and reading what it generated. A search-only evaluation had flatly missed it.

### 2.6 Judge: artifact

No single composite score — a weighted sum hides exactly the judgment the human needs to
see (the documented anti-pattern from OpenBRR, §6). Instead, QSOS-style **context
weighting**: declare which dimensions matter *for this decision* before scoring, then score
only those. The rubric:

1. **Competency test** (Spolsky): is this a core differentiator or commodity plumbing?
   Commodity defaults to adopt.
2. **Innovation token** (McKinley): novelty budget is scarce — is this where to spend it?
3. **Health** (CHAOSS/OpenSSF): contributor-absence factor ≥ 2–3; activity in the last 90
   days; security-fix cadence; no single org > ~55% of commits.
4. **License** (SPDX buckets): permissive / weak-copyleft / strong-copyleft / unknown —
   with the AGPL/SSPL/no-LICENSE traps flagged explicitly. *No LICENSE file means all
   rights reserved: you may read and learn, you may not fork.*
5. **Fence check** (Chesterton + Hyrum): state in one sentence why the existing solution is
   shaped the way it is; name the undocumented behavior you would inherit or break.
6. **Reversibility**: which failure is cheaper to undo — adopting something that dies, or
   building something that rots? Write the answer down (§2.8).

Stars are the **weakest signal** and must never rank candidates: in live testing of a
metadata-only scout, the top result for "rate limiter python" was a Twitter scraper with
2.5k stars, outranking every actual rate limiter. Popularity is a tiebreaker, never a judge.

### 2.6b Judge: provenance

Who is behind the code? `gh api users/<login>` yields bio, employer, account age, followers
in one call; a web search covers talks, writing, and track record. Verdict: **established
practitioner** / **active builder** / **unknown-experimental**. Provenance also catches
name-collision traps — a company sharing a name with an older, acquired company can borrow
unearned credibility from business databases.

**The orthogonality rule** — provenance and design quality are independent axes. In this
skill's own prior-art hunt, the best-designed candidate came from an anonymous account with
zero external footprint, while the most credentialed author had shipped the thinnest one.
Therefore: **the probe decides *whether* the ideas are good; provenance decides *how* to
adopt them** — run their code (credible, licensed, maintained) versus borrow their ideas
and reimplement (anonymous, unlicensed, or abandoned).

### 2.7 Gate

Purely advisory verdicts get rubber-stamped the first week a deadline appears. The gate is
therefore **asymmetric**: DEPEND, FORK, and VENDOR verdicts proceed on the agent's judgment
— adopting proven work is the safe default. A **BUILD verdict is the failure mode this
skill polices, so it cannot be self-approved**: it goes to the human with receipts — here
is what exists, here is why none of it fits — before a line of custom code is written.

### 2.8 Record

Two artifacts. An **ADR** per decision (context, options considered, verdict, receipts) —
the "alternatives considered" section is the highest-value part 18 months later. A
**decisions registry** (append-only JSONL) that stage 1 checks at trigger time: a hunt
already performed is never re-run, only re-validated if stale (registry entries carry a
review-by date).

### 2.9 Learn

The rubric must improve from outcomes. A **debrief** command scores past verdicts: did the
adopted dependency survive? did the approved BUILD prove necessary, or did prior art surface
later? Results append to a calibration file that future judges load as worked examples —
the same case-law pattern used by taste-calibration systems. The learn stage **never edits
the skill's own instructions without human confirmation**; it accumulates evidence, a human
ratifies doctrine.

## 3. The verdict space

Six verdicts, not four — the two cheapest end the work before any search runs:

| Verdict | Meaning | Issued by |
|---|---|---|
| **NOT-A-PROBLEM** | The null solution wins: do nothing / delete the requirement | Stage 0 |
| **DIFFERENT-PROBLEM** | The real problem is X, not Y; restart from X | Stage 0 |
| **DEPEND** | Adopt as a dependency, unmodified | Gate (proceeds) |
| **FORK** | Adopt and diverge; you own the delta | Gate (proceeds) |
| **VENDOR** | Copy in and amend; you own the copy (license permitting) | Gate (proceeds) |
| **BUILD** | Nothing fits; build custom | Gate (**human sign-off required**) |

## 4. Proportional depth

A flat full-depth hunt on every trigger gets the skill disabled within a week — the same
death, in the opposite direction, as "never blocks." Depth must be proportional to stakes.

At trigger time a **stakes classifier** estimates: build cost (lines/hours), maintenance
surface (will this be depended on?), and reversibility (how expensive is being wrong?).
Three tiers:

| Tier | When | What runs | Budget |
|---|---|---|---|
| **Quick** | Small script, easily reversed | Core lanes only: registry + GitHub + pattern check | ~2 min |
| **Standard** | Module or notable dependency | + curation, snowball 1 hop, license/health checks | ~10 min |
| **Full** | Subsystem, framework, or hard-to-reverse choice | All 10 stages: probe, provenance, freshness, full rubric | as needed |

**Deterministic-first** governs every tier: scripts sweep, fetch, and score (machine-
readable JSON out); the LLM spends judgment only where judgment is needed — framing,
probing, the rubric, the verdict. This is the same filter architecture as a two-layer
staleness detector: cheap deterministic filter selects, expensive intelligence decides.

## 5. Source lanes

Each lane answers a question no other lane can. Lanes run as parallel subagents, blind to
each other, each returning candidates + receipts.

| Lane | Question it answers | Concrete invocation |
|---|---|---|
| **GitHub** | What repos claim to solve this? | `gh search repos --topic <t> --sort stars --json fullName,description,stargazersCount,url` + octocode-mcp for repo analysis and code reading |
| **Curation** | What do humans say the alternatives are? | LibHunt URL-swap (`github.com/x/y` → `libhunt.com/x/y`); awesome-/best-of lists via web fetch |
| **Pattern** | Does anyone actually *write* this? | `curl 'https://grep.app/api/search?q=<pattern>'` — regex over ~1M public repos |
| **Probe** | What does the artifact actually do? | DeepWiki URL-swap (`github.com` → `deepwiki.com`) for architecture Q&A; sandbox install/run in a scratch dir |
| **Registries + health** | Is it published, maintained, safe? | npm / PyPI / crates.io APIs; OpenSSF Scorecard API (`api.securityscorecards.dev`) |
| **Freshness** | Did someone ship this in the last 30 days? | `last30days` skill if installed (Reddit/X/HN/YouTube sweep); degrade gracefully to web search if absent |
| **Skills ecosystem** | Did someone build this as an agent skill? | skills.sh / vercel-labs find-skills |
| **General web** | What do the essays and discussions say? | Web search over discussions, blog posts, comparisons |

Lane results are scored per-dimension (never summed): the QSOS rule — the dimensions that
matter are declared per-decision *before* scoring, and the output shows the human every
dimension, not a ranking.

## 6. Prior art of this skill itself

deja-vu was designed under its own discipline. The hunt found four existing candidates and
an essay; all receipts reproduce.

| Stage | build-vs-borrow¹ | github-prior-art² | find-skills³ | runx prior-art⁴ |
|---|---|---|---|---|
| 0 Re-problem | ❌ | ❌ | ❌ | ⚠️ partial |
| 1 Trigger | ✅ strong | ⚠️ vague | ❌ manual | ⚠️ system-internal |
| 2 Framing | ⚠️ intake only | ❌ | ❌ | ⚠️ partial |
| 3 Sweep | ⚠️ GitHub+npm+crates+Scorecard only | ⚠️ web only | ⚠️ skills only | ⚠️ unclear |
| 4 Snowball | ❌ | ❌ | ❌ | ❌ |
| 5 Probe | ❌ | ❌ | ❌ | ❌ |
| 6 Judge | ⚠️ signal scoring; good license classifier | ❌ | ⚠️ install-count trust | ✅ confidence-tagged |
| 7 Gate | ❌ explicitly advisory | ❌ | ❌ | ❓ |
| 8 Record | ✅ ADR + registry | ❌ | ❌ | ⚠️ |
| 9 Learn | ❌ | ❌ | ❌ | ❌ |

¹ https://github.com/trelmitt/claude-skills/tree/main/build-vs-borrow — the near-match.
An 8-stage pipeline (DETECT→…→VERDICT→RECORD), a working stdlib-only scout script hitting
GitHub + npm + crates + OpenSSF Scorecard, a 4-verdict model (DEPEND/FORK/VENDOR/BUILD),
SPDX license buckets, an ADR template. Verified hands-on: the script runs clean, no keys
required. **No LICENSE file** — all rights reserved — and an anonymous author, so its code
was *not* forked; its designs were treated as a reference and reimplemented (ADR-1, §9).
What it lacked is exactly what deja-vu adds: probing, snowballing, freshness, re-problem,
the gate, and learning.
² https://github.com/TrevorS/dot-claude/tree/master/skills/github-prior-art — "search
GitHub before answering"; no verdict, no scoring.
³ https://github.com/vercel-labs/skills — mature (26k+ stars), solves a different problem
(finding installable agent *skills*); wired in as deja-vu's skills-ecosystem lane rather
than competed with.
⁴ https://github.com/runxhq/runx/tree/main/skills/prior-art — broader than code (tools,
protocols, governance) with confidence-tagged findings, but welded into its host system;
not extractable.
⁵ Essay lineage: "Stop Your AI Agent From Building Tools That Already Exist"
(https://dev.to/turacthethinker/stop-your-ai-agent-from-building-tools-that-already-exist-6o9)
— scan→score→recommend with a reuse/adapt/build verdict; concept only, no implementation.

**Formal-methods lineage** (the algorithms are borrowed, with pride):
Kitchenham & Charters' systematic-review protocol (pre-registered inclusion/exclusion
criteria); Wohlin's snowballing guidelines (https://www.wohlin.eu/ease14.pdf); QSOS
context-weighted scoring (https://en.wikipedia.org/wiki/QSOS); SEI PECA's non-technical
criteria — maintainer viability and ecosystem trajectory
(https://resources.sei.cmu.edu/asset_files/TechnicalReport/2004_005_001_14252.pdf);
OpenSSF Scorecard automated health checks (https://openssf.org/projects/scorecard/);
CHAOSS contributor-absence factor (https://chaoss.community/); Endor Labs' reachability
principle — evaluate only the dimensions your call path touches
(https://www.endorlabs.com/learn/evaluating-and-scoring-oss-packages); Choose Boring
Technology (https://mcfunley.com/choose-boring-technology); In Defense of Not-Invented-Here
(https://www.joelonsoftware.com/2001/10/14/in-defense-of-not-invented-here-syndrome/);
Chesterton's Fence, Gall's Law, Hyrum's Law (https://github.com/dwmkerr/hacker-laws);
ThoughtWorks Tech Radar's "no adopt without production experience"
(https://www.thoughtworks.com/radar); ADR practice (https://adr.github.io/).

No prior work unifies these into one loop; every ingredient above pre-existed. That gap —
plus five unsolved stages (0, 4, 5, 7, 9) — is the justification for this BUILD verdict,
which was itself gated: the human approved building deja-vu after seeing these receipts.

## 7. Architecture

**Token-lean router.** `SKILL.md` is a thin router — trigger description, stage index, and
per-tier checklists — following the context-engineering hierarchy: the router is always
loaded; per-stage reference files (`references/framing.md`, `references/judge-rubric.md`,
`references/provenance.md`, …) load on demand at the stage that needs them; nothing else
enters context. Scripts do the heavy lifting and emit **machine-readable JSON** (one
verdict line per candidate), so the transcript carries conclusions, not dumps.

**Parallel blind lanes.** The sweep dispatches one subagent per lane with a terse,
self-contained brief; each returns candidates + receipts, never raw page dumps. Dedup and
ranking happen in the main thread after the barrier.

**Receipts everywhere.** Every claim ships with its reproduction: the command to run and
what it returns ("run this, see this"). A verdict whose receipts don't reproduce is void.

**Layout:**

```
deja-vu/
├── SKILL.md                  # thin router: trigger, tiers, stage index
├── docs/design.md            # this document
├── references/               # per-stage guidance, loaded on demand
├── scripts/                  # deterministic lanes: sweep, health, provenance, registry
├── data/                     # decisions registry + calibration file (gitignored samples)
├── evals/                    # trigger + verdict evals, synthetic fixtures
└── tests/                    # unit tests, offline-tolerant (mocked HTTP)
```

## 8. Testing & evals

**Unit tests** for every script: offline-tolerant (HTTP mocked with recorded fixtures; live
calls behind an opt-in flag), no-throw contract (errors collect into an `errors[]` field,
never crash the hunt), JSON-schema-validated output.

**Trigger evals**: a fixture corpus of synthetic prompts — build-ish asks that must fire
("let's write a rate limiter", "I'll build a queue for this"), trivial asks that must not
("fix this typo", "rename this variable"), and ambiguous middle cases with expected tier.
Measures both false negatives (missed hunts) and false positives (skill fatigue).

**Verdict evals**: seeded hunts with known ground truth — e.g., a fixture problem whose
correct verdict is DEPEND on a well-known library; a fixture with a no-LICENSE near-match
whose correct verdict is reimplement-not-fork. The eval passes when the verdict and its
cited receipts match expectations.

**Learning loop**: `debrief` scores past verdicts against outcomes and appends to the
calibration file. Calibration is data, not doctrine: the skill's instructions change only
by human-confirmed edits, with the calibration file as evidence.

All fixtures are fully synthetic — no real names, employers, or private-project data.

## 9. ADRs

**ADR-1: Reimplement build-vs-borrow rather than fork it.**
Context: closest prior art, verified working. Decision: treat as design reference;
reimplement. Rationale: no LICENSE file (all rights reserved — forking is not legally
clean) and unknown-experimental provenance (anonymous account, zero external footprint,
all commits in a two-week window). Per the orthogonality rule: the probe said the ideas
are good, provenance said don't run the code. Borrowed as ideas: the 4-verdict core,
SPDX license buckets, ADR/registry recording, the no-throw stdlib scout pattern.

**ADR-2: Adopt octocode-mcp for the GitHub lane.**
Context: `gh search` is deterministic but shallow; the lane needs code-level analysis.
Decision: DEPEND. Rationale via the rubric: commodity capability (not our differentiator);
OSS, actively released; reuses the existing `gh` auth token (no new credentials); healthy
activity. Reversible: the lane degrades to `gh` + web fetch if the server is absent.

**ADR-3: Keep both grep.app and octocode in the pattern/GitHub lanes.**
Context: apparent overlap. Decision: keep both. Rationale: different indexes and different
strengths — grep.app is a fast regex engine over a curated ~1M-repo corpus (precision;
"does anyone write this exact pattern"); GitHub code search via octocode has broader
coverage but weaker regex and rate limits (breadth). Both are free single HTTP calls;
redundancy here is cheap and the failure mode (a missed existence proof) is expensive.

**ADR-4: last30days is an optional dependency.**
Context: the freshness lane wants social/discussion recency (agent training data is always
months stale). Decision: integrate if installed, degrade gracefully to web search if not.
Rationale: it is a third-party skill with its own API-key requirements; a hard dependency
would break portability of a public repo. The lane contract is "freshness signal," not
"this tool."

---

*deja-vu practices what it preaches: every algorithm in this document is borrowed from
published prior art; the only novel part is the loop that composes them — and we searched
for that too before building it.*
