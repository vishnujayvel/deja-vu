# Behavioral observations

Purpose: distinguish deterministic script/fixture regressions (the checks in
`evals/run_evals.py --offline` and `tests/`) from actual model-behavior
evidence. A green `pytest` run and a green `run_evals.py --offline` prove the
fixtures and the fixture-schema/policy checks are internally consistent —
they do not by themselves prove a live model follows the skill, and they do
not prove the underlying lane scripts behave correctly against the real world
they claim to model. This file records real, reproducible runs against live
sources and a live model, with actual output and honest limitations.

These are observations, not proof. Each one is a single sample against one
query on one day; treat them as evidence of a *mechanism* (a real lane
limitation, a real happy path, a real stop-and-flag), not as a statistical
claim about hit rates or trigger accuracy.

## Compatibility baseline (deterministic, recorded for contrast)

Run fresh against this exact candidate, not carried forward from an earlier
session:

```
$ python3 -m pytest tests/ -q
179 passed in 9.22s
$ python3 evals/run_evals.py --offline
{"mode": "offline", "trigger_cases": 21, "fire_cases": 15, "silent_cases": 6,
 "verdict_cases": 6, "errors": [], "ok": true}
```

This is schema/policy-consistency and script-regression evidence only. It
says the lane scripts don't crash on the fixture shapes they were built
against, that every verdict fixture satisfies the coverage-honesty and
authority/rights contract checks below, and that fixture lane-status claims
(`unsupported`/`degraded`/etc.) cross-check against `policy/tier-matrix.json`'s
actual required-lane lists rather than being asserted freely. It says nothing
on its own about what a live model does when it runs the skill — see the two
skill-level observations below for that.

## Script-level observations (scripts/sweep.py in isolation)

These two are narrower than a full skill run: they call `scripts/sweep.py`
directly, not the skill's end-to-end loop. Kept because they demonstrate real,
reproducible lane-adapter behavior that the skill-level observations below
then build on.

### Script observation 1 (happy path): github lane finds a well-evidenced candidate

Command (real network, no mocks):

```
$ python3 scripts/sweep.py --query "pyrate-limiter" --lanes github --limit 3
```

Actual output (trimmed to the top hit):

```json
{
  "name": "vutran1710/PyrateLimiter",
  "url": "https://github.com/vutran1710/PyrateLimiter",
  "source_lane": "github",
  "description": "Python Rate-Limiter using Leaky-Bucket Algorithm Family",
  "stars": 522,
  "last_push": "2026-09-01T17:32:36Z",
  "license": "mit",
  "scorecard": null,
  "registry_downloads": null
}
```

Source: unauthenticated GitHub REST search API (`scripts/sweep.py`'s
`github_lane`, no `gh` CLI on this host at the time so it took the API
fallback path).

Reading: a real candidate is findable in one lane call for a plausible query,
carrying several adoption-favoring signals at once — a permissive license
(MIT), a recent push, and star count. None of these individually proves the
code is correct or well-maintained; `license: "mit"` here is the raw GitHub
API metadata field, not a verified confirmation that the repository's actual
license file matches (a repo can mislabel or omit one), and stars/recency are
popularity and activity signals, not a correctness or security audit.

Practical limitation: this is a *lane-script* observation, not a full skill
run — it shows the `github` lane's raw data quality, not whether a live model
correctly composes that data into a verdict, checks the license before
recommending reuse, or stops after a "good enough" match.

### Script observation 2 (degraded path): PyPI's exact-lookup lane produces a false negative on a natural-language query

Command 1 (the query as a person would actually phrase the need):

```
$ python3 scripts/sweep.py --query "token bucket rate limiter" --language python --lanes registry --limit 3
```

Actual output:

```json
{"query": "token bucket rate limiter", "lanes_run": ["registry"], "candidates": [], "errors": []}
```

Command 2 (the same lane, queried under the package's actual PyPI slug):

```
$ python3 scripts/sweep.py --query "pyrate-limiter" --language python --lanes registry --limit 3
```

Actual output:

```json
{
  "query": "pyrate-limiter", "lanes_run": ["registry"],
  "candidates": [{
    "name": "pyrate-limiter", "url": "https://pypi.org/project/pyrate-limiter/",
    "source_lane": "registry:pypi",
    "description": "Python rate limiter with pluggable algorithms and backends",
    "license": null, "stars": null, "last_push": null, "scorecard": null, "registry_downloads": null
  }]
}
```

Source: `scripts/sweep.py`'s `_pypi_search`, which does `GET
https://pypi.org/pypi/<slugified-query>/json` (an exact-name lookup) because
PyPI has no public full-text search API.

Reading: command 1 returns `errors: []` and `candidates: []` — schema-valid,
indistinguishable at the JSON level from a genuine successful-empty search.
But command 2 proves a real, well-known package for exactly this need
exists; the registry lane simply cannot find it under a multi-word natural
query, because it only checks one exact slug. A naive reading of command 1's
output as "no prior art" would be a false negative, not a proven absence.
This is why `evals/verdict_cases/build-successful-empty-full-coverage/`
carries an explicit caveat about this adapter limitation instead of claiming
proven absence, and why `evals/verdict_cases/halted-required-lane-unsupported/`
models an unsupported *required* lane as a hard stop rather than a route
label a reader could skip past.

**On the `license: null` in this output specifically:** this is *adapter
metadata loss*, not a confirmed rights signal — `_pypi_search` reads only
`info.license` from PyPI's JSON API, so a null here means the field came back
empty, not that the package has no license. That is a different fact from a
GitHub candidate's `license: null` (which reflects GitHub's own detection of
an absent LICENSE file — a real, confirmable signal). `evals/run_evals.py`'s
`check_null_license_rights_and_policy_matches_source` encodes exactly this
distinction: a github-sourced null license implies `rights_and_policy:
prohibited` (all rights reserved); a registry-sourced one implies
`rights_and_policy: unknown` (adapter couldn't tell either way) — see
`evals/verdict_cases/build-no-license-nearmatch/expected.json` for the
former case in a formal fixture.

Practical limitation: this observation is about the `registry` lane's PyPI
adapter specifically; `npm` and `crates.io` searches in the same function use
real search endpoints and do not share this exact-match constraint.

## Skill-level observations (the full deja-vu loop, live)

Unlike the two script observations above, these invoked the actual `deja-vu`
Skill tool end-to-end — the model chose a tier, ran the sweep, dispatched
additional lanes, judged the evidence, and reached (or explicitly declined to
reach) a verdict — not a direct call into one script. Each was run by a
freshly spawned agent with no memory of this development work and a plain,
solution-shaped task prompt that never named "deja-vu," "skill," or this
project's own tracking apparatus, so the skill firing at all was the model's
own trigger-matching, not a scripted invocation. Both explicitly declined to
create, edit, or execute any file in the repository, as instructed.

**Isolation caveats, stated plainly rather than smoothed over:** both agents
ran inside the same git worktree that this validation work is being done in,
sharing its filesystem with concurrent edits to this very fixture set (one
agent's own sanity check surfaced a `git status` diff it correctly attributed
to the shared environment rather than assuming it had caused it — reported
here as a known confound, not hidden). Both agents also resolved the skill
through this host's globally-installed skill copy (a separate, symlinked
checkout), not by importing this branch's in-progress `scripts/` directly —
so these observations exercise the *shipped* skill as an ordinary session
would load it, but are not a guarantee that they exercised the exact diff on
this branch. Neither confound changes what was actually observed below; both
are recorded so a future reader knows what "isolated" does and doesn't mean
here.

### Skill observation 1 (happy path): commodity rate-limiting, tier chosen correctly, verdict flagged for the right reason

Prompt given (verbatim, no mention of deja-vu or this project's tooling):
"Recommend an approach for rate limiting (token-bucket style) third-party API
calls from a worker pool that pulls jobs from a queue, to avoid blowing
through per-API request quotas. Scoping/recommendation only — no
implementation, no file writes."

The skill fired on its own (the prompt matches deja-vu's own trigger
vocabulary almost verbatim — "a rate limiter" is one of its named examples).
It chose **Standard** tier ("a rate limiter the whole worker pool depends on,
but a simple, easily-reversible utility, not a subsystem/framework") and
explained that choice rather than defaulting to it. It checked for a prior
recorded hunt first (none existed), ran `scripts/doctor.py` (8/8 capability
checks passed), then ran the real sweep:

```
$ python3 "$SKILL_DIR/scripts/sweep.py" --query "token bucket rate limiter API quota worker pool" --lanes github,registry,grep,scorecard --limit 10
```

Real results included both strong candidates (npm's `rate-limiter-flexible`,
`limiter`, several Go/Python equivalents by name) and one GPL-3.0-licensed
hit it flagged as a license mismatch rather than silently including. Two
lanes degraded in the same run: `grep` was rate-limited and skipped
("rate limited, skipped after retries"), and every candidate's `scorecard`
field came back `null` (the scorecard lane returned no health data at all,
despite being requested).

**Verdict reached: DEPEND, but explicitly flagged rather than auto-approved.**
The model's own stated reasoning: the scorecard lane returning null for every
candidate is an unresolved health-evidence gap, and per the skill's own gate
rule an unresolved gap at Judge reverts even a DEPEND to "wait for sign-off"
instead of proceeding automatically — so it presented the reuse recommendation
as solid while explicitly declining to pick and green-light one specific
package without that gap resolved or a human confirming the target stack.

Why this matters as evidence: this is the asymmetric gate (SKILL.md, "THE
ASYMMETRIC GATE") actually firing on a live run for the least dramatic
reason it's meant to catch — not a missing license, not an unsupported lane,
just a degraded health-signal lane that a less careful reading could shrug
off. It also declined to name a single winning package without knowing the
caller's language/runtime, consistent with this skill's stance that a
missing fact the user alone can supply is a reason to ask or flag, not to
guess.

### Skill observation 2 (degraded path): Full-tier hunt correctly refuses to fake the sandbox probe

Prompt given (verbatim): "We need to build a distributed job-queue subsystem
for our backend: durable enqueue, at-least-once delivery, retries with
backoff, and dead-letter handling across multiple worker processes. This
would become a core piece of infrastructure we'd be stuck maintaining for
years, so it's a big, hard-to-reverse decision. Recommendation only — no
implementation, no file writes." The prompt also explicitly told the agent
not to simulate an isolated sandbox step if none was genuinely available, and
to stop and say so instead.

The skill fired and chose **Full** tier ("subsystem, framework, or
hard-to-reverse choice," matching the prompt's own framing). The deterministic
sweep was low-signal by itself:

```
$ python3 "$SKILL_DIR/scripts/sweep.py" --query "distributed job queue durable at-least-once retry backoff dead letter" --lanes github,registry,grep,scorecard --limit 10
```

`errors` (verbatim): `"github: full query matched 0 repos; narrowed to
'distributed job queue' and found 10. Broaden or shorten --query."`,
`"registry(npm): HTTPError: HTTP Error 400: Bad Request"`,
`"grep: rate limited, skipped after retries"`. The narrowed github query
surfaced mostly abandoned toy repos (last pushes 2015-2017, 0-6 stars) because
none of the real industry-standard systems (Sidekiq, Celery, RabbitMQ, Kafka,
SQS, Temporal) describe themselves with the literal phrase "distributed job
queue." Recognizing the sweep as weak, the model dispatched one additional
blind research lane (a subagent briefed only on the solution-free problem
restatement, not shown the weak sweep output) which did surface the real
established systems, each with license and maintenance-risk notes (e.g.
flagging Sidekiq/Faktory as single-maintainer projects, and Redis's
AGPLv3/SSPL relicensing versus the BSD-licensed Valkey fork).

At Full tier the loop reaches a mandatory hands-on probe stage (clone +
install + smoke-test a shortlisted candidate inside an isolated,
secrets-free sandbox). **The model correctly determined no such sandbox was
actually available to it** — its only execution surface was a shell running
directly on the real host with real credentials and the real working
repository, which SKILL.md's own trust-boundary section explicitly disallows
as a probe environment — and stopped rather than either skipping the check
silently or pretending to have done it. It recorded this as an explicit
evidence gap and reached **DEPEND-at-the-meta-level, with no single specific
package endorsed**, again declining to guess the caller's stack.

Why this matters as evidence: this is the exact scenario
`policy/tier-matrix.json`'s `hands_on_probe.on_unavailable` entry and
SKILL.md's Probe-stage note describe in prose ("if no such sandbox is
available... mark `hands_on_probe` unsupported instead of executing"),
observed actually happening on a live run rather than only asserted in a
fixture.

## What this does not cover (explicitly out of scope for this observation set)

- **Statistical trigger/verdict accuracy.** Two skill-level runs and two
  script-level runs are mechanism evidence, not a sampled benchmark. They
  show specific real behaviors (a correct tier choice, a correctly-flagged
  gate, a correctly-refused fake probe, a real lane false-negative) — they do
  not establish hit rates, and `evals/trigger_cases.jsonl` /
  `evals/verdict_cases/` remain the fixed regression fixtures for that,
  necessary but not sufficient evidence on their own.
- **A resumable controller, evidence graph, decision-packet platform, or
  durability adapter.** Out of scope per this work's current governing scope;
  `tests/test_decision_packet_schema.py` already covers the schema contract
  where the additive `authority`/`rights_and_policy` vocabulary is reused
  from, without requiring the full platform.
- **A from-scratch, fully airgapped consumer install.** As noted above, both
  skill-level runs shared a filesystem with concurrent fixture edits and
  resolved the skill via its existing globally-installed copy. A genuinely
  from-scratch isolated install (fresh machine or container, no other
  process touching the working tree) would be a stronger version of the same
  evidence, not a different kind of evidence.
