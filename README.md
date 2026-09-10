# deja-vu

> The skill that gives your agent the feeling it has seen this problem before.

A skill for Claude Code and Codex that runs a structured prior-art hunt **before** anything
custom gets built.

## The problem

You're mid-task, someone says "we need a rate limiter" (or an auth flow, a retry helper, a
link checker for the docs), and the reflex is to open a new file and start writing it. Later
you find out a maintained library already handled the edge cases you just hit — this skill is
the pause that checks for that library first.

deja-vu asks "has someone already solved this?" through a ten-stage loop, then backs whatever
it finds with the actual repos, license, and health data it checked, not a star count. Full
design rationale and the failure mode each stage addresses: [`docs/design.md`](docs/design.md).

## Install

**Option A — git clone + symlink** (full control over the checkout location):

```bash
git clone https://github.com/vishnujayvel/deja-vu "$HOME/workplace/deja-vu"
mkdir -p "$HOME/.claude/skills"
ln -s "$HOME/workplace/deja-vu" "$HOME/.claude/skills/deja-vu"
```

Verify the symlink resolves:

```bash
ls -la "$HOME/.claude/skills/deja-vu"
```

**Option B — [`npx skills`](https://github.com/vercel-labs/skills)** (fetches directly from
GitHub, no manual clone):

```bash
npx skills add vishnujayvel/deja-vu
```

Either way, that's the whole install — `SKILL.md`'s frontmatter is what Claude Code reads to
decide when to bring the skill in.

**Option C — native plugin (Claude Code or Codex)**: this repo also ships a repo-local
marketplace (`.claude-plugin/marketplace.json`) that both clients' native plugin installers can
read directly — no manual symlink, and the client manages updates/removal for you.

As of this writing, this plugin packaging has not yet merged to `origin/main` — a fresh `git
clone` of `main` will not have `.claude-plugin/marketplace.json` yet. Until it merges, point the
marketplace-add commands below at a local checkout that already has this packaging on disk (for
example, the checkout you're reading this from):

```bash
cd <path-to-your-local-checkout>

# Claude Code
claude plugin marketplace add ./
claude plugin install deja-vu@deja-vu-marketplace

# Codex
codex plugin marketplace add ./
codex plugin add deja-vu@deja-vu-marketplace
```

Once this packaging reaches `origin/main`, both CLIs also accept the GitHub shorthand directly,
no local checkout required:

```bash
claude plugin marketplace add vishnujayvel/deja-vu
codex plugin marketplace add vishnujayvel/deja-vu
```

**Use it**: once installed, deja-vu is designed to activate on its own for build-shaped requests
in either client (see "Try it" below) — neither client needs a special slash command. The
reliable way to invoke it, especially right after installing, is to ask directly: "run a deja-vu
hunt on this" / "check for prior art before I build this."

Verify with `claude plugin list` / `codex plugin list`. Remove with `claude plugin uninstall
deja-vu@deja-vu-marketplace` then `claude plugin marketplace remove deja-vu-marketplace` (Codex:
`codex plugin remove deja-vu@deja-vu-marketplace` then `codex plugin marketplace remove
deja-vu-marketplace`).

### Optional dependencies (the skill degrades gracefully without them)

- **octocode-mcp** — gives the GitHub lane real code search/reading instead of just repo
  metadata:
  ```bash
  claude mcp add-json octocode --scope user '{"command":"npx","type":"stdio","args":["-y","@octocodeai/mcp@latest"]}'
  ```
- **last30days** — feeds the freshness lane recent Reddit/X/HN/YouTube signal instead of a plain
  web search. If you already have it installed as a skill, deja-vu picks it up automatically.

Neither is required. `scripts/sweep.py` and `scripts/provenance.py` are stdlib-only Python and
run with nothing beyond a Python 3 interpreter and network access.

## Setup check

For Option A/B, `cd` into the installed skill directory (e.g. `$HOME/.claude/skills/deja-vu`
for Option A, or wherever `npx skills add` placed it for Option B) and run:

```bash
python3 scripts/doctor.py
```

For Option C (native plugin), the skill resolves its own bundled scripts by absolute path (see
`SKILL.md`), so no `cd` is needed — just ask the agent to run the doctor check, or invoke the
same script directly at its installed cache path.

It prints one `DOCTOR: PASS|WARN|FAIL` line per dependency (gh CLI, octocode MCP, grep.app,
OpenSSF Scorecard API, skills CLI, last30days). It exits nonzero only when a REQUIRED check
fails; optional lanes degrade to WARN with actionable guidance (an install/auth command where
one applies, or a pointer to the relevant project otherwise).

Illustrative sample output:

```
DOCTOR: PASS python3
DOCTOR: PASS github
DOCTOR: WARN last30days -- not installed -- optional freshness lane; see github.com/mvanhorn/last30days-skill
```

## Try it

deja-vu is designed to fire on its own when a prompt looks like it's about to scaffold
something commodity-ish — you don't have to name it. For example:

> "I'll write a token-bucket rate limiter for our API gateway."

If it doesn't trigger, or you want to force a hunt, ask for it directly: "run a deja-vu hunt
on this" works too. Either way, it reframes the problem, sweeps the sources below at a depth
matched to how hard the choice is to reverse, and returns one of six verdicts backed by
whatever it actually found. The result is a recommendation with sources, saved as a decision
record in your project. Full hunts may also clone, install, and try shortlisted tools; the skill
instructs the agent to run those probes in a disposable sandbox.

## Where it looks

Stage 3 (Sweep) runs `scripts/sweep.py` for the sources below it can query directly, and
dispatches the rest as agent research. Which lanes run depends on the tier the hunt picked —
a quick, easily-reversed choice only checks the first two; a full, hard-to-reverse one runs
all of them:

| Lane | Kind | What it checks | Runs at |
|---|---|---|---|
| GitHub repos | `sweep.py` | Repos claiming to solve the problem — via `gh search repos` if the `gh` CLI is available, else the unauthenticated GitHub REST search API | every tier |
| Package registries | `sweep.py` | npm and crates.io by keyword; PyPI by exact package name (no public keyword-search API) | every tier |
| Code pattern search (grep.app) | `sweep.py` | Does anyone actually write this pattern, over ~1M public repos? | standard tier and up |
| Maintainer health ([OpenSSF Scorecard](https://openssf.org/projects/scorecard/)) | `sweep.py` | Is it maintained safely? | standard tier and up |
| Curation ([LibHunt](https://www.libhunt.com/), awesome-lists) | Agent research | What do humans say the alternatives are? | as needed |
| Freshness (`last30days`, if installed) | Agent research (optional) | Did something ship in the last 30 days? | full tier |
| Skills ecosystem (`npx skills search`) | Agent research | Is this already an agent skill? | as needed |
| General web | Agent research | What do comparisons/reviews say? | as needed |

## A real example

deja-vu ran on itself. When this repo needed CI to catch dead documentation links, the reflex
was to write a small link-checker script — exactly the reflex this skill exists to interrupt.
The hunt is recorded in
[`docs/adr/0001-link-checking-depend-lychee.md`](docs/adr/0001-link-checking-depend-lychee.md):
it compared several link-checking tools against a declared rubric (CI fit, license, activity,
rate-limit handling) — one candidate was excluded outright for having gone dormant — and landed
on **DEPEND**: adopt [`lycheeverse/lychee`](https://github.com/lycheeverse/lychee) unmodified,
via [`lycheeverse/lychee-action`](https://github.com/lycheeverse/lychee-action) in CI.

The first CI run using it caught real dead links in this repo's own docs; the fix is
[`db1f4aa`](https://github.com/vishnujayvel/deja-vu/commit/db1f4aad77c90f389981f2e05a98f3d2fbe9e1f7).

## Limitations

- **Six verdicts, no synthesis step** — NOT-A-PROBLEM, DIFFERENT-PROBLEM, DEPEND, FORK, VENDOR,
  BUILD. If the real answer is "combine two libraries," that judgment call is still yours.
- Not every lane runs on every hunt — the tier picked in Stage 1 decides which of the sources
  above get checked (see the table).
- The scripted lanes need network access; `python3 scripts/doctor.py` tells you exactly what's
  missing or degraded before you rely on results.
- Agent-research lanes (curation, freshness, skills ecosystem, general web) depend on what's
  installed and how the hunt is invoked — a WARN from `doctor.py` means a lane degraded, not
  that the hunt failed.
- deja-vu hands you a verdict and the evidence behind it, not a merged change. DEPEND/FORK/VENDOR
  proceed on the agent's own judgment; only BUILD is gated on an explicit human sign-off.
- A hunt can still miss prior art that uses different vocabulary than the ones it tried
  (`references/framing.md` covers how it tries to mitigate this).

## Credits

deja-vu's loop composes ideas from published prior art (deja-vu ran on itself before being
built; see [`docs/design.md`](docs/design.md) §6). Closest prior art:
[build-vs-borrow](https://github.com/trelmitt/claude-skills/tree/main/build-vs-borrow), an
8-stage DEPEND/FORK/VENDOR/BUILD pipeline reimplemented here rather than forked (no LICENSE
file, unknown-experimental provenance). Full citation list — Kitchenham & Charters' systematic
review protocol, Wohlin's snowballing guidelines, QSOS, CHAOSS, OpenSSF Scorecard, and more —
is in `docs/design.md` §6.

## License

MIT — see [`LICENSE`](LICENSE).
