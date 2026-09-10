# Stage 0 — Re-problem

Before any search: is this the right problem? This stage is the cheapest thing the skill does
and the highest-leverage — it can end the hunt in two verdicts without a single HTTP request.

## The XY problem

You are being asked for help with an attempted solution (Y) instead of the actual problem (X).
"How do I parse the last line of `ps aux` output" is Y; the actual problem (X) might be "how do
I know if my process died," which has nothing to do with parsing at all. Every downstream stage
inherits whatever framing you lock in here — get it wrong and the entire hunt searches for
prior art to *the wrong problem*, expertly.

**Test:** write the problem statement with **zero solution vocabulary** in it. If you cannot
restate it without naming the thing you were about to build ("a rate limiter," "a job queue"),
you have not found the problem yet — you have found a solution and are working backward.

## Five whys

Ask "why do we need this" five times, or until you hit a need that doesn't dissolve further:

1. Why do we need a rate limiter? — To stop one client from starving the others.
2. Why would one client starve the others? — Because the backend has a fixed request budget.
3. Why is the budget fixed? — Because the downstream API bills per request.
4. Why does that matter here? — Because we're a thin proxy with no caching layer.
5. Why is there no caching layer? — **Nobody has asked this yet.**

The real fix might be a cache, not a rate limiter — a different search entirely, and possibly a
smaller one. Stop as soon as you reach a need a non-technical stakeholder would recognize; don't
manufacture whys past that point.

## Null solutions

Before searching for something to adopt, check whether nothing needs to be built at all:

- **Do nothing.** Is the problem actually costing anyone anything, or is it a hypothetical?
- **Delete the requirement.** Can the upstream constraint that created this need be removed
  instead of satisfied? (Example: the fixed request budget above — negotiate a bigger one?)
- **Change the process.** Is this a code problem, or a workflow/ownership problem wearing a
  code costume? ("We need a dedup engine" sometimes means "two teams should stop writing to
  the same table.")

## Jobs-to-be-Done framing

Customers don't want a quarter-inch drill, they want a quarter-inch hole — and sometimes they
don't even want the hole, they want the shelf mounted. Ask: who actually experiences this
problem, and what would they call success? Answer in their words, not in library names.

## When to hand off

If the ask is underspecified — no clear "for whom," no clear "why now," a one-line request that
could mean three different things — this stage is not the place to guess. Hand off to
`agent-skills:interview-me` (one question at a time until the actual intent is clear) rather than
inventing a problem statement and hunting for prior art to a fiction.

## Verdicts issuable here — no searching required

| Verdict | When |
|---|---|
| **NOT-A-PROBLEM** | A null solution above wins outright: doing nothing (or deleting the requirement) resolves it. |
| **DIFFERENT-PROBLEM** | Five whys surfaced a different X than the Y that was asked about. Restart the whole hunt from X — do not patch the original framing. |

Only a problem that survives this stage — real, correctly scoped, not solved by inaction —
earns a hunt. Proceed to `references/framing.md` (Stage 2) once it does.
