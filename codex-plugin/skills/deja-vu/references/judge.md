# Stage 6 — Judge: artifact and provenance

No single composite score — a weighted sum hides exactly the judgment the human needs to see
(the documented OpenBRR anti-pattern). Instead, QSOS-style **context weighting**: declare which
dimensions matter *for this decision*, before scoring, then score only those. Write the declared
weights down before you look at any candidate's numbers — same discipline as the pre-registered
exclusion criteria in Stage 2, for the same reason.

## Declare weights first

For this hunt, name the 2-4 dimensions below that actually matter and rank them. A CLI tool used
once a week does not need the same weighting as a library that will sit on every request path.
Example declarations:

- Auth library on the request hot path: health > license > fence-check > competency
- One-off data-migration script's dependency: license > competency (everything else is noise)

## The rubric — score only the declared dimensions

1. **Competency test** (Spolsky). Is this a core differentiator for what you're building, or
   commodity plumbing? Commodity defaults to adopt — spend your differentiation budget
   elsewhere.
2. **Innovation token** (McKinley). Your team has a scarce budget of "novel, unproven technology"
   choices before operational risk piles up. Is this candidate — or the decision to build instead
   — where you want to spend one?
3. **Health** (CHAOSS / OpenSSF):
   - Contributor-absence factor ≥ 2–3 (more than one or two people could disappear without the
     project stalling)
   - Activity in the last 90 days (commits, releases, issue responses)
   - Security-fix cadence (are CVEs patched, or do they sit open)
   - No single org/account > ~55% of commits, unless that concentration is the point (e.g. a
     vendor-maintained SDK for that vendor's own API)
   - Pull the OpenSSF Scorecard field straight from the `sweep.py` output (`scorecard` key) —
     don't re-derive it by hand.
4. **License** (SPDX buckets): permissive / weak-copyleft / strong-copyleft / unknown.
   - **AGPL/SSPL trap**: strong-copyleft-with-network-clause disqualifies anything that gets
     linked into a service you distribute or offer over a network, even if you don't modify it.
   - **No-LICENSE trap**: no LICENSE file means all rights reserved — you may read it and learn
     from it, you may not fork or vendor it. This is a hard disqualifier for FORK/VENDOR, not a
     yellow flag.
5. **Fence check** (Chesterton + Hyrum). Write one sentence: why is the existing solution shaped
   the way it is? Then name one piece of undocumented behavior you'd inherit (or break) by
   adopting it — every artifact with real users has load-bearing accidents; find at least one
   before you decide you understand the fence well enough to remove it.
6. **Reversibility**. Which failure is cheaper to undo: adopting something that later dies, or
   building something that rots in place? Write the answer down — it goes in the ADR
   (`references/record.md`) regardless of which way the verdict goes.

**Stars are the weakest signal and must never rank candidates.** In live testing of a
metadata-only scout, the top hit for "rate limiter python" was a Twitter scraper with 2.5k stars
— outranking every actual rate limiter in the result set. Popularity is a tiebreaker between two
candidates that are otherwise equal on every declared dimension, never a judge on its own.

## Stage 6b — Provenance

Who is behind the code, independent of what the code does.

```
python3 scripts/provenance.py --owner <github-login> [--owner <login2> ...]
```

stdout:

```json
{"profiles": [{"login": "...", "name": null, "company": null, "created_at": "...",
  "followers": 0, "public_repos": 0, "account_age_years": 0.0, "other_notable": [],
  "signal": "established-practitioner|active-builder|unknown-experimental"}]}
```

Run it against every shortlisted maintainer's login, then supplement with a plain web search for
talks, writing, and track record the script can't see. Watch for **name-collision traps**: a
company sharing a name with an older, acquired company can borrow unearned credibility from
business databases — verify the account behind the code is the account you think it is.

## The orthogonality rule

Provenance and design quality are independent axes — score them separately, and don't let one
contaminate the other. The best-designed candidate can come from an anonymous account with zero
external footprint; the most credentialed author can ship the thinnest implementation. Neither
correlation is guaranteed, so don't assume it.

**The probe (Stage 5) decides whether the ideas are good. Provenance decides how to adopt them:**

| Provenance signal | + Probe says the design is sound | Route |
|---|---|---|
| established-practitioner / active-builder, licensed, maintained | → | **DEPEND** or **FORK**: run their code |
| unknown-experimental, unlicensed, or abandoned | → | **VENDOR** the idea by reimplementing it yourself — borrow the design, not the artifact |

Carry both the rubric scores and the provenance signal into Stage 7 (Gate) — the gate reads the
receipts this stage produced, it does not re-derive them.
