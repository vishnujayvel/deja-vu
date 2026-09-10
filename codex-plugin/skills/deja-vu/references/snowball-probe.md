# Stage 4 — Snowball, Stage 5 — Probe

Two stages, one file: snowball finds candidates that lane-search structurally cannot; probe
verifies the ones snowball and sweep surfaced. Both stop mattering the moment you stop doing them
by hand — neither is a script, both require reading.

## Stage 4 — Snowball

Wohlin's snowballing, ported from academic systematic reviews: from any strong hit, chase 2–3
hops in each direction. Snowballing is empirically competitive with exhaustive search at a
fraction of the cost, and it is how the non-obvious finds happen — the best candidate is often
one hop from a mediocre search hit, in a repo whose name shares no vocabulary with your query.

**Backward** (what the candidate depends on or was inspired by):
- Its dependency manifest — what does it lean on that might itself be closer to what you need?
- Its README's "inspired by" / "prior art" / "credits" section
- What it explicitly forked from (check for a fork relationship on GitHub)

**Forward** (what depends on or discusses the candidate):
- `gh api repos/<owner>/<repo>/forks` — who forked it, and why (check their fork's diff/README)
- Reverse-dependency search on the registry lane's package (npm/PyPI "used by", crates.io
  "reverse deps")
- Web search for `"<repo name>" alternative` or `"<repo name>" vs` — who compares against it?

Depth by tier: **Quick** — skip snowballing entirely. **Standard** — 1 hop, backward or forward,
whichever the strongest hit's README suggests. **Full** — 2–3 hops each direction, until hits
stop turning up anything not already in the candidate list.

## Stage 5 — Probe

READMEs undersell, oversell, and omit. The only ground truth is the artifact itself. Probe the
top 1–2 shortlisted candidates — never the whole list, this stage doesn't scale and shouldn't.

**Sandbox protocol:**

```
mkdir -p .scratch/probe-<candidate> && cd .scratch/probe-<candidate>
git clone --depth 1 <url> .
# install per its own instructions — npm ci / pip install -e . / cargo build, etc.
# run its smoke test / a trivial invocation of its main entry point
```

Then read the source of the load-bearing part — the module that would actually be on your call
path, not the whole tree. Ask, concretely: does it do what the README claims, does it do things
the README *doesn't* claim, and does its configuration surface reveal anything (a native
extension slot, an undocumented plugin system, a hidden network call) that changes the verdict?

A documented real case: a spec framework's config file contained a native-extension slot no
documentation page mentioned — found only by running its `init` in a sandbox and reading what it
generated. A search-only evaluation had flatly missed it. Assume every candidate has one of
these until you've looked.

**Architecture Q&A shortcut:** before or alongside the hands-on clone, ask DeepWiki
(`github.com` → `deepwiki.com` URL-swap on the candidate repo) targeted questions — "what's the
extension mechanism," "how does it handle X" — it's faster than reading cold, but it is not a
substitute for running the code; treat its answers as a map, not a verdict.

Depth by tier: **Quick** and **Standard** skip the hands-on clone (DeepWiki Q&A only, if used at
all). **Full** — always clone and run, no exceptions; this is the tier where being wrong is
expensive enough that a README's word isn't good enough.

Clean up `.scratch/` when the hunt concludes — it's gitignored but no reason to leave it around.

Output of both stages: an updated, verified candidate list, ready for Stage 6 (`references/judge.md`).
