# Decision receipts corpus

A small, compact corpus of real decision receipts — pairs of a machine-checkable
`packet.json` (validated against `schemas/decision-packet.schema.json`) and a human-readable
`receipt.md` narrative — covering the reasoning shapes a Deja Vu hunt actually produces: good
reuse, justified custom work, a rights constraint, degraded evidence, and a decision that was
later revisited. See `docs/adr/0011-decision-taxonomy-compositional-packet.md` and
`docs/design.md` §5.4 for the packet schema this corpus targets, and `references/record.md`
for the ADR/receipt template it follows.

This corpus is deliberately separate from `evals/verdict_cases/`, which stays fully synthetic
per `docs/design.md`'s stated invariant — mixing real project data into that directory would
break it. Nothing here was added to or read from `data/decisions-registry.jsonl`, which stays
project-local and gitignored per `references/record.md`.

## What's here

| Entry | Category | Use this pattern when… |
|---|---|---|
| [`depend-skill-reuse/`](depend-skill-reuse/receipt.md) | Good reuse — existing skill, documented as a manual lane | you're about to build a discovery/index feature that an existing, differently-scoped tool already covers, even if wiring it in is a manual step rather than an automated call |
| [`depend-cli-runtime-capability/`](depend-cli-runtime-capability/receipt.md) | Good reuse — existing CLI/runtime capability (not a model capability — see that entry's correction note) | you're about to build a custom output-parsing or event-detection layer around an agent host that may already emit a structured signal for the event you care about |
| [`depend-tool-adoption/`](depend-tool-adoption/receipt.md) | Good reuse — external tool/service | the reflex is "write a small custom script" for a problem (link checking, retries, rate limits) that is actually commodity plumbing with an established leader |
| [`build-justified-no-fit/`](build-justified-no-fit/receipt.md) | Justified custom build | a real sweep found related candidates but none covers enough of the actual problem to adopt, and the gap itself is the argument for building |
| [`rights-constrained-clean-room/`](rights-constrained-clean-room/receipt.md) | Rights constraint | the best-fitting candidate has no clear reuse grant, so the route has to change (reimplement independently) even though the design fit is strong |
| [`degraded-evidence-source-rot/`](degraded-evidence-source-rot/receipt.md) | Degraded evidence, told honestly | a source you cited earlier has become harder to verify by the time you revisit it, and you need a pattern for saying exactly what degraded and what didn't |
| [`decision-changed-registry-to-packet/`](decision-changed-registry-to-packet/receipt.md) | A decision that later changed | an earlier "this format is good enough" decision turns out not to scale, and you need to record the revision honestly rather than pretend the new choice was there from the start |

Every entry is labeled **real** at the top of its `receipt.md`. None of the seven entries use
simulated or synthetic data; none contains a home-directory path, an email address, or any
other private-project data — this is enforced repo-wide by `scripts/sanitize_check.sh`, which
scans every tracked file including this corpus.

## Sourcing discipline

Facts in this corpus are drawn from two kinds of source, and each entry's `receipt.md` says
which for its specific claims (this list is illustrative, not an exhaustive taxonomy of every
possible source type):

- **Already published in this repository** — `docs/design.md`, `docs/adr/0001-...md`,
  `docs/adr/0011-...md`, `references/*.md`, or a script/module's own source and docstrings.
  These are cited, not re-derived.
- **Freshly re-verified for this corpus** — an external repository's current state (via
  `gh api`, a direct HTTP status check, or an official documentation page), dated at the time
  of verification, distinct from whatever was true when a fact was first cited elsewhere.

Evidence strength is recorded per route component using the schema's own five-level scale
(`metadata`, `documented`, `source-inspected`, `probed`, `operational`) — a claim is leveled at
what was actually done to support it, not at what would look most convincing. No claim in this
corpus asserts a hands-on run (executing a CLI command, cloning and running a repository) that
was not actually performed while authoring these entries; where a hands-on result is cited, it
is attributed to whoever originally recorded it (e.g. an existing note in `docs/design.md`),
not claimed as this corpus's own execution.

## Schema note

Every `packet.json` is `stage: "proposed"` and carries no `authority_receipts` or
cryptographic `signature` — no real signing infrastructure exists yet for this project
(`docs/adr/0011-...md`'s "Consequences" section). Each packet's `approval_material_sha256`
field is populated as the existing schema requires at this stage; this corpus does not define
or propose any new hashing, signing, or approval protocol beyond satisfying that requirement.

## Text alternative for visuals

This corpus is text-only by design: no images, screenshots, or diagrams are included, so no
alt text is required. The table above is Markdown source text, not an image.

## Running this corpus as regression input

```bash
python3 -m pytest tests/test_exemplar_corpus.py -q
```

validates every `packet.json` here against `schemas/decision-packet.schema.json`, confirms
the `stage: proposed` / no-fabricated-authority invariant, and checks that every entry carries
a companion `receipt.md` with a real/simulated label and that every required category is
represented. This runs as part of the repository's full `pytest tests/ -q`. It validates
structure and schema conformance, not the factual accuracy of any entry's claims.
