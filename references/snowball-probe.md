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

Cloning is fine — a `git clone` writes files, it doesn't execute the candidate. Installing,
building, and running it does: `npm ci`, `pip install -e .`, `cargo build`, a smoke test, all
execute code the candidate controls. `sandbox_exec` (`$SKILL_DIR/policy/tier-matrix.json`) gates that step,
not the clone.

Before running any install/build/test command, confirm a real, *enforceable* disposable
sandbox is available — a container, a VM, or an OS-level sandbox mechanism (whatever your
environment already provides; this doesn't mandate standing up Docker/Kubernetes or writing a
new sandbox runner). "Enforceable" means it actually prevents the candidate process from
reaching the host: no mount of your home directory, the working repository, credentials, or
agent sockets; a bounded writable scratch area; and no outbound network by default (loosen
only to the specific package-registry endpoints the install step needs, and only if your
sandbox mechanism can enforce that allowlist). A plain `.scratch/` directory, a tempfile, or a
changed `$HOME` env var does **not** isolate anything — the process can still read and write
everywhere your shell can — so none of those substitute for a real sandbox.

```bash
# only once an enforceable sandbox is confirmed:
<sandbox-run> sh -c '
  mkdir -p /work/probe-<candidate> && cd /work/probe-<candidate>
  git clone --depth 1 <url> .
  # install per its own instructions — npm ci / pip install -e . / cargo build, etc.
  # run its smoke test / a trivial invocation of its main entry point
'
```

If no enforceable sandbox is available, do not install, build, or run the candidate — read its
source statically instead (safe with ordinary trusted read tools; it never executes candidate
code) and stop there. Record `hands_on_probe` as `unsupported` and the evidence you do have as
weaker/source-only. At Full tier this is not a silent pass: `sandbox_exec` unsupported means the
hunt cannot reach a verified-fit stopping rule and must stop on `required_human_decision`
(`$SKILL_DIR/policy/tier-matrix.json`), not report success on source-reading alone.

**Receipt.** Every probe — performed or unsupported — writes one receipt conforming to
`$SKILL_DIR/schemas/probe-receipt.schema.json` before Judge (Stage 6) runs. A transcript is not
a receipt: the point is that a skeptical reader can check what actually happened without
re-running the hunt or trusting memory of it. Minimum required content:

- `candidate`, `source_revision` — the pinned commit SHA, tag, or package version actually
  probed, never a moving branch ref. (`source_revision` is `null` only when `hands_on_probe` is
  `unsupported` and nothing was even fetched.)
- `hands_on_probe: performed` — then also `commands` (the exact install/build/smoke-test
  commands run), `environment` (sandbox mechanism, network policy, mounts — which must stay
  empty — and the writable scratch area actually granted), `outputs` (what the commands
  returned), and `cleanup` (whether and how the sandbox/scratch was discarded).
- `hands_on_probe: unsupported` — then also `unsupported_reason` and, if gathered,
  `fallback_evidence` (e.g. a static source read or an `architecture_qa` answer).
- `failures` — an explicit empty array when nothing went wrong; omission is not the same claim.

```json
{
  "schema_version": "deja-vu.probe-receipt/v1",
  "candidate": "example-lib",
  "source_revision": "a1b2c3d4e5f6...",
  "hands_on_probe": "performed",
  "inspected_manifests": ["package.json", "scripts/install.sh"],
  "commands": ["npm ci", "node smoke.js"],
  "environment": {
    "sandbox_mechanism": "container (no host mounts)",
    "network": "allowlisted",
    "allowlisted_endpoints": ["registry.npmjs.org"],
    "mounts": [],
    "writable_scratch": "/work/probe-example-lib (500MB)"
  },
  "outputs": "npm ci: 42 packages, 0 vulnerabilities. smoke.js: exit 0, printed \"ok\".",
  "load_bearing_source_read": ["src/index.js", "src/plugin-loader.js"],
  "cleanup": { "performed": true, "method": "container destroyed after run" },
  "failures": []
}
```

When a sandbox *is* available, still read the source of the load-bearing part — the module that
would actually be on your call path, not the whole tree — after the sandboxed run. Ask,
concretely: does it do what the README claims, does it do things the README *doesn't* claim, and
does its configuration surface reveal anything (a native extension slot, an undocumented plugin
system, a hidden network call) that changes the verdict?

A documented real case: a spec framework's config file contained a native-extension slot no
documentation page mentioned — found only by running its `init` in a sandbox and reading what it
generated. A search-only evaluation had flatly missed it. Assume every candidate has one of
these until you've looked.

**Architecture Q&A shortcut:** before or alongside the hands-on clone, ask DeepWiki
(`github.com` → `deepwiki.com` URL-swap on the candidate repo) targeted questions — "what's the
extension mechanism," "how does it handle X" — it's faster than reading cold, but it is not a
substitute for running the code; treat its answers as a map, not a verdict.

Depth by tier: **Quick** and **Standard** skip the hands-on clone (DeepWiki Q&A only, if used at
all). **Full** — always attempt the hands-on clone when an enforceable sandbox is available; this
is the tier where being wrong is expensive enough that a README's word isn't good enough. When no
enforceable sandbox is available, the fallback above still applies: static read only,
`hands_on_probe: unsupported`, and `required_human_decision` — never clone-and-run without
isolation.

Clean up `.scratch/` when the hunt concludes — it's gitignored but no reason to leave it around.

Output of both stages: an updated, verified candidate list, ready for Stage 6 (`references/judge.md`).
