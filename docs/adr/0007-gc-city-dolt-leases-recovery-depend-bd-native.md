# ADR 0007 — Gas City hq Dolt schema-skew (`leases` race): DEPEND on bd-native migration

- **Date:** 2026-07-22
- **Status:** accepted
- **Verdict:** DEPEND (bd-native `bd migrate schema` + upstream-documented ignored-table workaround; zero custom code)

## Context / problem (solution-vocabulary-free)

Gas City rig `vishnu-city` (`/Users/vishnu/vishnu-city`) hit disk exhaustion (97% full,
15 GiB free), traced to un-reaped polecat worktrees under `.gc/worktrees` (15 GB total,
13 GB in for-us, ~600 MB node_modules each). `auto_reap_closed_bead_worktrees` (enabled
2026-07-20 per ADR-0002, `city.toml:147`) only reaps via the daemon on bead-close — which
requires the city to be UP — so it cannot run at the exact moment disk pressure takes the
city down. ENOSPC starved Dolt, `gc restart`'s reconcile step timed out, and the city was
left in a repeating init-failure loop.

Freeing 12 GB (deleting node_modules inside the stale worktrees — safe, regenerable, no
git objects touched; disk 15→21+ GB) and killing a rogue standalone `bd dolt start` server
squatting port 52981 (empty data dir) did not fix the init loop. The persistent failure
is a *second, unrelated* problem surfaced by the same outage:

The city's own beads (prefix `vc`) live in the **`hq`** Dolt database (4056 issues), stuck
at schema **v41** against a bd CLI at **v56** (15 pending migrations). for-us's `fu` DB is
already v56, which is why for-us bd works while the city init does not. Replaying the
pending migrations hits upstream **beads#4176**: the main migration sequence references
the `dolt_ignore`'d `leases` table *before* the ignored-table sequence creates it, so
migration fails with `Error 1146: table not found: leases`. Reproduced directly —
`bd list` against `hq` fails identically; the supervisor loops "init failure #N ... table
not found: leases".

`hq` has no Dolt remote, so an in-place migration is fork-safe (upstream's remote-fork
guard, beads#4259, does not apply). `hq` was missing all 5 `dolt_ignore`'d tables
(`leases`, `wisps`, `ignored_schema_migrations`, `local_metadata`, `repo_mtimes`).

Also latent (not actioned by this ADR): `bw2`/`sj`/`contour`/`hw` bead DBs sit at v40
(same skew class); for-us retains a stale local `.beads/dolt/.dolt` that could become a
future split-brain if bd auto-starts a second server against it.

## Hunt summary

- Registry checked: ADR-0002 (2026-07-20, same rig) covered the worktree-disk side of
  this outage only; no prior hunt on Dolt schema migration or the `leases` table.
- `leases` was introduced upstream in **beads PR #4863** (merged 2026-07-17, 5 days
  before this incident) as a `dolt_ignore`'d node-local table — architecturally identical
  precedent to `wisps`.
- **beads#4176** (OPEN) — "Fresh Dolt-server clone crashes in migration 0047 (table not
  found: wisps)": the exact race class (ignored sequence runs after the main sequence,
  which unconditionally references the ignored table before it exists).
  https://github.com/gastownhall/beads/issues/4176
- **beads#4891** (MERGED 2026-07-18) — self-healing ignored-migration pattern for
  `wisps`: recreate the local ignored table's shape "at store open," idempotently. Not
  yet applied to `leases`. https://github.com/gastownhall/beads/pull/4891
- **beads#4468** (OPEN) — related but distinct: `table "p" does not have column
  is_blocked`, shared-server mode, unresolved.
  https://github.com/gastownhall/beads/issues/4468
- **beads#4259** — the guard that blocks in-place migration on remote-backed DBs
  (fork risk). Confirmed not applicable: `hq` has no remote.
  https://github.com/gastownhall/beads/pull/4259
- beads PR: https://github.com/gastownhall/beads/pull/4863
- Repo is `gastownhall/beads` (the `steveyegge/beads` URL redirects there). Maintainer is
  actively patching this exact `dolt_ignore` race class (#4891 landed for `wisps` one day
  after the underlying `leases`-introducing PR merged).

## Decision

DEPEND on bd-native recovery — do not build a custom pre-init wrapper or fork bd's
migration runner:

1. Clone fu's (v56) ignored-table structures into `hq` — `CREATE TABLE hq.X LIKE fu.X`
   for the 5 missing `dolt_ignore`'d tables — to satisfy #4176's forward reference before
   migration runs.
2. Back up `hq` (`bd export`).
3. Run `bd migrate schema` on `hq` → v56. Fork-safe: no remote configured.
4. `gc start`.

Status as of writing: step 1 (the DB mutation) is **PENDING USER AUTHORIZATION** — a
safety classifier blocked the agent from mutating `hq` directly.

Recommend also filing an upstream issue: "`leases` hits the same `wisps`-class race as
#4176/#4891" — the maintainer's existing self-healing pattern (#4891) is the natural fix
but has not yet been generalized past `wisps`.

## Disqualified alternatives

- **Custom pre-init wrapper** (e.g. a script that pre-creates ignored tables on every
  `gc start`): duplicates the maintainer's active, in-progress fix (#4891's pattern);
  BUILD not justified when the upstream owner is actively patching this exact class.
- **Forking bd's migration runner**: unnecessary risk to a Dolt store for a race the
  maintainer already has a merged precedent for (`wisps`); would also need to be
  re-forked every time bd ships a new migration.
- **Hand-editing Dolt schema state ad hoc** (skip `bd migrate schema` entirely): riskier
  than the tool's own migration path and forfeits `bd export`'s pre-migration safety net.

## Consequences

- Once migrated, `hq` reaches v56 and the city-init loop should clear — but this ADR
  only covers `hq`; `bw2`/`sj`/`contour`/`hw` remain at v40 and will hit the same class of
  failure on their own next migration unless separately upgraded (tracked as prevention
  work in the incident postmortem, not scoped here).
- The disk-exhaustion trigger (reaper can't run while the city is down) is ADR-0002's
  concern, not re-litigated here; this ADR is scoped to the schema-skew failure the same
  outage exposed once disk was recovered.

## Review trigger

Re-validate if: `bd migrate schema` fails against `hq` even after the ignored-table
clone (would indicate #4176's fix assumption is incomplete); the `bw2`/`sj`/`contour`/`hw`
v40 DBs hit the same race on their own migration; or beads ships a generalized fix for
`dolt_ignore`d-table forward references (would obsolete the manual clone-DDL step).

## Sources

- https://github.com/gastownhall/beads/pull/4863
- https://github.com/gastownhall/beads/pull/4891
- https://github.com/gastownhall/beads/issues/4176
- https://github.com/gastownhall/beads/issues/4468
- https://github.com/gastownhall/beads/pull/4259
- ADR-0002: `docs/adr/0002-worktree-gc-depend-gascity-native.md` (same rig, disk-side of
  this outage)
