# Decision receipts corpus

A small, compact corpus of real decision receipts — pairs of a machine-checkable
`packet.json` (validated against `schemas/decision-packet.schema.json`) and a human-readable
`receipt.md` narrative — covering the reasoning shapes a Deja Vu hunt actually produces: good
reuse, justified custom work, a rights constraint, degraded evidence, and a decision that was
later revisited. See `docs/adr/0011-decision-taxonomy-compositional-packet.md` and
`docs/design.md` §5.4 for the packet schema this corpus targets, and `references/record.md`
for the ADR/receipt template it follows.

This is a **portable exemplar corpus for learning and sharing**, per the P3 adoption epic
("Turn verified Deja Vu decisions into portable exemplars," Beads issue `deja-vu-p3`). It is
deliberately separate from
`evals/verdict_cases/`, which stays fully synthetic per `docs/design.md` line ~399 — mixing
real project data into that directory would break that documented invariant. Nothing here
was added to or read from `data/decisions-registry.jsonl`, which stays project-local and
gitignored per `references/record.md`.

## What's here

| Directory | Category | Real source |
|---|---|---|
| `depend-skill-reuse/` | Good reuse — existing skill | `vercel-labs/skills`, wired in as deja-vu's Sweep skills-ecosystem lane |
| `depend-model-capability/` | Good reuse — existing model/platform capability | Claude Code's `stream-json` headless output, used by `evals/run_evals.py --live` |
| `depend-tool-adoption/` | Good reuse — external tool/service | `lycheeverse/lychee`, adopted in CI per `docs/adr/0001-link-checking-depend-lychee.md` |
| `build-justified-no-fit/` | Justified custom build | deja-vu's own founding hunt (`docs/design.md` §6) — four real candidates compared, none covers the full nine-stage loop |
| `rights-constrained-clean-room/` | Rights constraint | The same hunt, isolating why a strong design fit (`trelmitt/claude-skills`) could not be forked — no LICENSE file |
| `degraded-evidence-source-rot/` | Degraded evidence, told honestly | A cited candidate (`TrevorS/dot-claude`) whose source path was removed from the live repo after citation |
| `decision-changed-registry-to-packet/` | A decision that later changed | `docs/adr/0011-decision-taxonomy-compositional-packet.md` — the registry's own verdict format was revisited after a 31-decision audit |

Every entry is labeled **real** at the top of its `receipt.md`. None of the seven entries use
simulated or synthetic data; none contains a home-directory path, an email address, or any
other private-project data — this is enforced repo-wide by `scripts/sanitize_check.sh`, which
scans every tracked file including this corpus.

## Sourcing discipline

Every real-world fact in this corpus is one of exactly two kinds, and each entry's `receipt.md`
says which:

1. **Already published in this repository** — `docs/design.md` §6, `docs/adr/0001-...md`,
   `docs/adr/0011-...md`, `references/judge.md`, or `evals/run_evals.py`'s own docstring.
   These are cited, not re-derived.
2. **Freshly re-verified for this corpus** — every external GitHub repository cited
   (`vercel-labs/skills`, `lycheeverse/lychee`, `trelmitt/claude-skills`, `TrevorS/dot-claude`,
   `runxhq/runx`) was re-checked via `gh api` (and, for the removed-upstream case, a direct
   `curl` HTTP-status check) on 2026-09-11, independent of the original citation dates. Where
   a fact changed since the original citation (e.g. `vercel-labs/skills`' star count), both
   the original and the re-verified figure are recorded.

No claim in this corpus asserts a hands-on run (`npx skills search`, cloning a repository,
executing a script) that was not actually performed while authoring these entries. Where the
underlying repository's own docs already record a hands-on verification (e.g. "the
[build-vs-borrow] script runs clean, no keys required," `docs/design.md` §6 footnote 1), that
is cited as an existing fact, not re-claimed as this corpus's own execution.

## Schema conformance and `approval_material_sha256`

Every `packet.json` is `stage: "proposed"` — the immutable pre-authority packet shape. None
carries `authority_receipts` or a cryptographic `signature`, because no real signing
infrastructure exists yet for this project (`docs/adr/0011-...md`'s "Consequences" section
notes canonical serialization/hashing is not implemented as of that ADR). Fabricating a
signature would be inventing evidence this corpus explicitly avoids.

`approval_material_sha256` on every packet *is* a real, reproducible SHA-256 digest — not a
placeholder — computed over exactly the fields ADR-11 names as covered
(`problem_disposition`, `candidate_comparisons`, `uncertainty`, `reversibility`,
`route_components`), canonically serialized as `json.dumps(fields, sort_keys=True,
separators=(",", ":"))` and UTF-8 encoded. `tests/test_exemplar_corpus.py` recomputes this
hash for every packet and fails if it doesn't match, so an edit to a packet's covered fields
without updating the hash is caught as a regression, not silently merged.

## Text alternative for visuals

This corpus is text-only by design: no images, screenshots, or diagrams are included, so no
alt text is required. The one table above is Markdown source text, not an image.

## Running this corpus as regression input

```bash
python3 -m pytest tests/test_exemplar_corpus.py -q
```

validates every `packet.json` here against `schemas/decision-packet.schema.json`, confirms
every `approval_material_sha256` matches a fresh recomputation, and checks that every entry
carries a companion `receipt.md`. This runs as part of the repository's full `pytest tests/ -q`
per `CLAUDE.md`/`AGENTS.md`.
