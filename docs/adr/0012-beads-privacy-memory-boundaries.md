# ADR-12: Beads, privacy, and memory database boundaries

**Date:** 2026-09-04
**Status:** accepted

## Context

Deja Vu product development, private host-project hunts, and any future shared
precedent index are three different data-ownership scopes with different
privacy requirements. Left unstated, they contaminate one another: this
repository's product Beads database can accumulate other projects' private
decision records, and a shared cross-project registry can leak project-specific
history before it has been reviewed for sharing. The current cross-project
registry and a sanitizer that fails on project-specific history are evidence of
that boundary defect (see `deja-vu-v2` audit baseline).

The underlying design was already settled in `docs/design.md` §2.5 and §8
(lines 578-629); this ADR records that decision as a discrete, citable
reference rather than re-deriving it.

## Decision

**Verdict:** Use this repository's existing Beads database for Deja Vu product
development only. Store runtime hunts in the consuming project's own Beads
database when available, or in a project-scoped filesystem fallback when it is
not. Defer a shared precedent database to P3, gated on explicit sanitize-and-opt-in
promotion.

### Ownership

This repository's existing Beads database is dedicated to Deja Vu product
development: epics, decisions, implementation work, review records, and
durable project memories. It does not store other projects' runtime hunt
evidence. (`docs/design.md` §8.1, lines 589-594)

### Host-project hunt storage

When a consuming (host) project uses Beads, one decision problem maps to one
primary Bead; detailed candidates and evidence live in a versioned artifact
referenced by that Bead. Additional Beads are created only for independent
lifecycles (a probe, human gate, implementation, revalidation, or doctrine
proposal) — candidates do not each become issues. Parent-child edges express
hierarchy, `blocks` expresses a true prerequisite, and `discovered-from`
records emergent work. (`docs/design.md` §8.2, lines 596-604)

### Visibility classes

Every hunt declares a `visibility`: `local-only`, `project-sync`, or
`promotion-eligible`. The default is `local-only`. `project-sync` requires an
explicit project policy and grants access only to that owning project's
authorized collaborators — it does not by itself make a hunt eligible for
cross-project promotion. (`docs/design.md` §8.2, lines 606-611)

### Retention

Receipts and observations are content-addressed and immutable; a reference
records its retention class alongside digest, media type, byte length, origin,
and retrieval time. Garbage collection cannot remove a receipt referenced by
any retained event, observation, decision, or supersession record. P1 does not
compact receipts — compaction requires a future tombstone event carrying the
complete normalized audit payload and its prior digest.
(`docs/design.md` §5.1, lines 280-287)

### Sanitized opt-in promotion (P3, not P1)

Cross-project promotion is a later, opt-in capability, not part of P1. A
separate cross-project precedent database may be proposed in P3, only after
promotion schemas, consent, sanitization, deletion, provenance, and tenant
boundaries are tested and validated. Nothing is promoted by default; promotion
always requires explicit sanitize-and-opt-in action on a `local-only` or
`project-sync` hunt. (`docs/design.md` §1, lines 56-58; §8.4, lines 624-628)

### Dolt sync exclusion for local-only

The Beads adapter uses an unversioned/local storage class for `local-only`
hunts and verifies that a Dolt push cannot include them. This is enforced at
the adapter layer, not left to operator discipline. (`docs/design.md` §8.2,
lines 607-609)

### Filesystem fallback (0700/0600)

Hosts without Beads store the same manifests, receipts, and decisions as
project-scoped, atomically written files — the fallback changes storage
mechanics only, never schemas or decision semantics, and it never imitates
issue tracking. `local-only` files live under a configured private state
directory with directory mode `0700` and file mode `0600`. Setup adds and
verifies a VCS ignore rule and fails closed if a target path is already
tracked or falls outside the owning project's approved state root. The
adapter never performs remote writes. (`docs/design.md` §8.3, lines 613-622)

### Beads remains optional

Beads is an optional durability adapter, not a runtime requirement. Durable
memory stays with its owner: this repository stores product development work,
a consuming project stores its own hunts, and portable skill code and public
examples do not absorb private project history. (`docs/design.md` §2.5, lines
90-95; §8.3, lines 613-617)

## Alternatives considered

- **Store all hunts centrally** (in this repository's Beads database, or a new
  always-on shared one): rejected — leaks one project's private decision
  context into every other project and into Deja Vu's own product backlog.
- **One Beads database per hunt**: rejected — fragments lifecycle state across
  many small stores with no coherent backlog view and no clear ownership home.
- **Avoid Beads entirely**: rejected — discards useful, optional durability;
  §2.5 already establishes Beads as optional, not mandatory, so avoiding it
  everywhere is unnecessary.

## Consequences

- No consumer project's private hunts or decisions are exposed to the Deja Vu
  product repository, and Deja Vu's product backlog is not diluted with other
  projects' runtime evidence.
- Beads remains fully optional for hosts: the filesystem fallback preserves
  identical manifests, receipts, and decision semantics under `0700`/`0600`
  permissions.
- Cross-project reuse of prior decisions is deferred until P3 defines a
  consented, sanitized promotion path — P1 and P2 hunts stay project-scoped by
  default.
- This ADR does not itself move or delete any existing registry or sanitizer
  data; remediation of the current cross-project registry and sanitizer
  failures is tracked separately (`deja-vu-v2.5`).

## Receipts

- `docs/design.md` §1 (P1 scope), lines 56-58
- `docs/design.md` §2.5 (Durable memory stays with its owner), lines 90-95
- `docs/design.md` §5.1 (receipts, retention class, no P1 compaction), lines 280-287
- `docs/design.md` §8 (Durability and database boundaries), lines 578-629
- `deja-vu-v2` epic notes: audit baseline documenting the cross-project
  registry and sanitizer boundary defect
