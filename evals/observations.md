# Behavioral observations (deja-vu-v2.21)

Purpose: distinguish deterministic script regressions (the fixtures in this
directory and `tests/`) from actual behavior evidence. A green `pytest` run and
a green `run_evals.py --offline` prove the fixtures and the fixture schema are
internally consistent — they do not prove a model follows the skill, and they
do not prove the underlying lane scripts behave correctly against the real
world they claim to model. This file records real, reproducible runs against
live sources, with their actual output and honest limitations, per
`deja-vu-v2.21`'s acceptance criteria.

These are observations, not proof. Each one is a single sample against one
query on one day; treat them as evidence of a *mechanism* (a real lane
limitation, a real happy path), not as a statistical claim about hit rates.

## Compatibility baseline (deterministic, recorded for contrast)

Run on 2026-09-11, this branch, no code changes beyond this bead:

```
$ python3 -m pytest tests/ -q
273 passed in 154.09s
$ python3 evals/run_evals.py --offline
{"mode": "offline", "trigger_cases": 21, "fire_cases": 15, "silent_cases": 6,
 "verdict_cases": 6, "errors": [], "ok": true}
```

This is schema and script-regression evidence only (docs/design.md's
"Assurance model" layer 1-2: unit tests, contract tests). It says the lane
scripts don't crash on the fixture shapes they were built against, and that
every verdict fixture satisfies the coverage-honesty contract checks added
below. It says nothing about what a live model does when it runs the skill.

## Observation 1 (happy path): github lane finds a well-evidenced candidate

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
`github_lane`, no `gh` CLI on this host so it took the API fallback path).

Reading: a real, permissively-licensed (MIT), actively-maintained (pushed
10 days before this run), popular candidate is findable in one lane call for
a plausible query. This is the shape a DEPEND verdict should look like
(compare `evals/verdict_cases/depend-established-library/`).

Practical limitation: this is a *lane-script* observation, not a full skill
run — it shows the `github` lane's raw data quality, not whether a live model
correctly composes that data into a verdict, checks the license before
recommending reuse, or stops after a "good enough" match. See "What this does
not cover" below.

## Observation 2 (degraded path): PyPI's exact-lookup lane produces a false
negative on a natural-language query

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
PyPI has no public full-text search API. Confirmed by reading
`scripts/sweep.py:254-276`.

Reading: command 1 returns `errors: []` and `candidates: []` — schema-valid,
indistinguishable at the JSON level from a genuine successful-empty search.
But command 2 proves a real, well-known package for exactly this need
exists; the registry lane simply cannot find it under a multi-word natural
query, because it only checks one exact slug. This is the concrete instance
of the exact-lookup limitation flagged in this bead's notes ("PyPI exact-lookup
limitations... producing visible uncertainty") — a naive reading of command
1's output as "no prior art" would be a false negative, not a proven absence.

This is also why `evals/verdict_cases/build-degraded-required-lane-unsupported/`
models a *registry-lane-succeeded-but-empty* result as **not** sufficient
grounds for an unqualified BUILD, and why the new
`check_verdict_acknowledges_sweep_errors` / license-null contract checks in
`evals/run_evals.py` exist: a fixture (or, eventually, a live model transcript)
that stays silent about a lane limitation is indistinguishable from one that
never noticed it.

Practical limitation: this observation is about the `registry` lane's PyPI
adapter specifically; `npm` and `crates.io` searches in the same function use
real search endpoints (`_npm_search`, `_crates_search`) and do not share this
exact-match constraint. It also does not test whether a live skill run
compensates for this (e.g. by also running the `github` or `grep` lane, which
the real hunt protocol requires alongside `registry`, not instead of it).

## What this does not cover (explicitly out of scope for this observation set)

- **Live model behavior.** `evals/run_evals.py --live` shells out to a fresh
  `claude -p` session to check whether the skill actually fires and how a
  model composes a verdict from lane output. It was **not** run in this
  session: this worktree's `CLAUDE.md` (this repo is a Gas City `deja-vu`
  polecat worktree) instructs any Claude Code session started here to behave
  as a Gas City polecat — claim beads, push branches, run the done sequence —
  which is exactly the kind of confound `--live`'s own docstring warns about
  ("never run in CI"; here, additionally, never run inside a polecat identity,
  since a nested session would try to act as a second polecat instead of
  answering the trigger prompt). Running `--live` safely requires a plain,
  non-Gas-City checkout with a normal interactive `CLAUDE.md`, exactly as
  `evals/run_evals.py`'s module docstring already scopes it to "EXPERIMENTAL,
  costs tokens, NOT run in CI." This is a real, load-bearing operational
  limitation, not an oversight — it is recorded here so a future session does
  not assume `--live` is safe to run from inside any Gas City worktree.
- **Composite scoring or a resumable controller.** Per the epic's 2026-09-11
  scope correction, this bead validates the shipped skill and scripts as they
  exist, not the superseded decision-packet/authority-gate platform design in
  `docs/design.md` §5-7. `tests/test_decision_packet_schema.py` already covers
  the schema contract for that structure where it is used.
- **Statistical trigger/verdict accuracy.** `evals/trigger_cases.jsonl` and
  `evals/verdict_cases/` are fixed regression fixtures, not a sampled
  benchmark; passing them is necessary, not sufficient, evidence of real-world
  accuracy.
