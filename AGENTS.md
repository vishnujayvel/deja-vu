# Agent Instructions

Guidance for AI coding agents (and humans) contributing to deja-vu — a Claude Agent Skill that
runs a structured prior-art hunt before custom code gets built.

## Project layout

- `SKILL.md` — the skill itself; Claude Code's frontmatter-triggered entry point. This is the
  shipped behavior users depend on — changes to it should go through normal review.
- `docs/design.md` — full design rationale, one section per stage, citations.
- `docs/adr/` — architecture decision records, including deja-vu's own prior-art hunts (see
  ADR-1 for the CI link-checker choice).
- `references/` — one reference doc per stage (framing, judge, lanes, learn, re-problem, record,
  snowball-probe) — the detail `SKILL.md` points to rather than inlines.
- `scripts/` — stdlib-only Python: `sweep.py` (multi-lane candidate search), `provenance.py`
  (maintainer signal), `doctor.py` (setup check), plus `sanitize_check.sh` (public-repo hygiene
  gate).
- `tests/` — pytest suite; HTTP calls are mocked via recorded fixtures in `tests/fixtures/`.
- `evals/` — offline schema-validated trigger/verdict fixtures plus an experimental `--live`
  mode.
- `.github/workflows/ci.yml` — what actually runs on every push/PR (see Checks below).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install --upgrade pip pytest jsonschema
python3 scripts/doctor.py   # reports optional dependencies: gh CLI, octocode MCP, etc.
```

The scripts themselves are stdlib-only Python 3 with network access; `jsonschema` is only a
test dependency, needed by `tests/test_decision_packet_schema.py`.

## Checks

Run these before opening a PR — they cover CI's command-based checks:

```bash
python3 -m pytest tests/ -q
python3 evals/run_evals.py --offline
bash scripts/sanitize_check.sh
```

CI additionally runs a link check ([lychee](https://github.com/lycheeverse/lychee)) over every
Markdown file — see `docs/adr/0001-link-checking-depend-lychee.md` for why.

## Conventions

- `scripts/sweep.py` is stdlib-only and no-throw by design: failures land in its `errors[]`
  output field instead of raising, so a partial/degraded sweep still returns useful data.
- Significant dependency, adoption, or reimplementation decisions in this repo are recorded as
  ADRs under `docs/adr/` — check there for precedent before reinventing something new.
- `scripts/sanitize_check.sh` fails the build on machine-specific `/Users/<name>/` paths or
  email addresses in tracked files — use `$HOME` or repo-relative paths in docs and scripts.
- Keep `SKILL.md`, `references/*.md`, and `scripts/sweep.py`'s lane list in sync —
  `evals/run_evals.py --offline` checks this and fails naming the drifted token.

## Contributing

Open a PR against `main`. Small, focused changes are easier to review — if you're touching
`SKILL.md` or the loop's stage behavior, explain the reasoning with the same receipts-first
discipline the skill itself asks for: what you compared, and why the change wins. No specific
issue tracker or workflow tool is required to contribute here.
