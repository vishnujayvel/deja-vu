#!/usr/bin/env python3
"""deja-vu evals — trigger-fire fixtures + verdict-fixture schema validation.

Design rationale: docs/design.md §8 ("Testing & evals"). Stdlib only.

Two modes:

  --offline (default, CI-safe)
      Validates evals/trigger_cases.jsonl schema, cross-checks that every
      fire-case's `matched_family` phrase still appears in SKILL.md's
      frontmatter description (so a description edit that silently drops a
      trigger phrase fails CI instead of rotting quietly), and validates the
      evals/verdict_cases/ fixture schemas. No network access, no tokens.
      Exits nonzero on any failure.

  --live (optional, EXPERIMENTAL, costs tokens, NOT run in CI)
      For each trigger case, shells out to a headless `claude -p "<prompt>"
      --max-turns 1` invocation and greps the transcript for whether the
      deja-vu skill appears to have fired. Requires Claude Code installed
      on PATH. The exact flags for deterministically detecting *which*
      skill fired are not pinned down by any stable, documented interface
      at the time this was written, so this mode is a best-effort text
      heuristic, not a certified check — treat its output as directional.

Usage:
  python3 evals/run_evals.py                 # offline (default)
  python3 evals/run_evals.py --offline
  python3 evals/run_evals.py --live [--max-cases N]
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRIGGER_CASES_PATH = ROOT / "evals" / "trigger_cases.jsonl"
VERDICT_CASES_DIR = ROOT / "evals" / "verdict_cases"
SKILL_MD_PATH = ROOT / "SKILL.md"

VALID_EXPECTED = {"fire", "silent"}
VALID_VERDICTS = {
    "NOT-A-PROBLEM", "DIFFERENT-PROBLEM", "DEPEND", "FORK", "VENDOR", "BUILD",
}


# ------------------------------------------------------------- trigger cases ---

def load_trigger_cases(path=TRIGGER_CASES_PATH):
    """Returns (list of (line_no, obj)), errors)."""
    cases = []
    errors = []
    if not path.exists():
        return cases, [f"missing trigger cases file: {path}"]
    for i, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"trigger_cases.jsonl line {i}: invalid JSON ({e})")
            continue
        if not isinstance(obj, dict):
            errors.append(f"trigger_cases.jsonl line {i}: must be a JSON object")
            continue
        cases.append((i, obj))
    return cases, errors


def validate_trigger_case_schema(i, obj, errors):
    for key in ("prompt", "expected", "why"):
        if key not in obj:
            errors.append(f"trigger_cases.jsonl line {i}: missing required key '{key}'")

    prompt = obj.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        errors.append(f"trigger_cases.jsonl line {i}: 'prompt' must be a non-empty string")

    expected = obj.get("expected")
    if expected not in VALID_EXPECTED:
        errors.append(
            f"trigger_cases.jsonl line {i}: 'expected' must be one of "
            f"{sorted(VALID_EXPECTED)}, got {expected!r}"
        )

    why = obj.get("why")
    if not isinstance(why, str) or not why.strip():
        errors.append(f"trigger_cases.jsonl line {i}: 'why' must be a non-empty string")

    if expected == "fire":
        family = obj.get("matched_family")
        if not isinstance(family, str) or not family.strip():
            errors.append(
                f"trigger_cases.jsonl line {i}: fire cases require a non-empty "
                f"'matched_family' naming the SKILL.md trigger phrase it relies on"
            )


def extract_skill_description_blob(path=SKILL_MD_PATH):
    """Best-effort YAML-frontmatter text extractor.

    Returns the whitespace-collapsed text of the frontmatter block (between
    the two '---' fences). Whitespace-collapsing (rather than a real YAML
    parse) is deliberate: this project is stdlib-only, and collapsing runs
    of whitespace to a single space is robust to the folded-scalar (">-")
    line-wrapping SKILL.md's description uses, without adding a PyYAML
    dependency just for this check.
    """
    if not path.exists():
        return ""
    text = path.read_text()
    parts = text.split("---")
    # A well-formed file is '---\n<frontmatter>\n---\n<body...>', which
    # split("---") turns into ['', <frontmatter>, <body...>].
    if len(parts) < 3:
        return ""
    frontmatter_raw = parts[1]
    return re.sub(r"\s+", " ", frontmatter_raw).strip()


def check_families_present(cases, description_blob, errors):
    families = sorted({
        obj.get("matched_family")
        for _, obj in cases
        if obj.get("expected") == "fire" and obj.get("matched_family")
    })
    for family in families:
        if family not in description_blob:
            errors.append(
                f"SKILL.md frontmatter description no longer contains the trigger-phrase "
                f"family {family!r} that a fire-case in trigger_cases.jsonl relies on"
            )
    return families


# ------------------------------------------------------------- verdict cases ---

def validate_verdict_case(dir_path, errors):
    input_path = dir_path / "input.json"
    expected_path = dir_path / "expected.json"

    if not input_path.exists():
        errors.append(f"verdict_cases/{dir_path.name}: missing input.json")
        return
    if not expected_path.exists():
        errors.append(f"verdict_cases/{dir_path.name}: missing expected.json")
        return

    try:
        input_obj = json.loads(input_path.read_text())
    except json.JSONDecodeError as e:
        errors.append(f"verdict_cases/{dir_path.name}/input.json: invalid JSON ({e})")
        return
    try:
        expected_obj = json.loads(expected_path.read_text())
    except json.JSONDecodeError as e:
        errors.append(f"verdict_cases/{dir_path.name}/expected.json: invalid JSON ({e})")
        return

    if not isinstance(input_obj.get("problem"), str) or not input_obj.get("problem", "").strip():
        errors.append(f"verdict_cases/{dir_path.name}/input.json: 'problem' must be a non-empty string")

    sweep = input_obj.get("sweep")
    if not isinstance(sweep, dict):
        errors.append(f"verdict_cases/{dir_path.name}/input.json: 'sweep' must be an object (sweep.py-shaped)")
    else:
        for key in ("lanes_run", "candidates", "errors"):
            if key not in sweep or not isinstance(sweep[key], list):
                errors.append(f"verdict_cases/{dir_path.name}/input.json: sweep.{key} must be present and a list")

    provenance = input_obj.get("provenance")
    if not isinstance(provenance, dict):
        errors.append(f"verdict_cases/{dir_path.name}/input.json: 'provenance' must be an object (provenance.py-shaped)")
    else:
        for key in ("profiles", "errors"):
            if key not in provenance or not isinstance(provenance[key], list):
                errors.append(f"verdict_cases/{dir_path.name}/input.json: provenance.{key} must be present and a list")

    verdict = expected_obj.get("verdict")
    if verdict not in VALID_VERDICTS:
        errors.append(
            f"verdict_cases/{dir_path.name}/expected.json: 'verdict' must be one of "
            f"{sorted(VALID_VERDICTS)}, got {verdict!r}"
        )

    reasons = expected_obj.get("key_reasons")
    if (
        not isinstance(reasons, list)
        or not reasons
        or not all(isinstance(r, str) and r.strip() for r in reasons)
    ):
        errors.append(
            f"verdict_cases/{dir_path.name}/expected.json: 'key_reasons' must be a "
            f"non-empty list of non-empty strings"
        )


# ------------------------------------------------------------------ offline ---

def run_offline():
    errors = []

    cases, load_errors = load_trigger_cases()
    errors += load_errors
    for i, obj in cases:
        validate_trigger_case_schema(i, obj, errors)

    description_blob = extract_skill_description_blob()
    if not description_blob:
        errors.append(f"could not extract YAML frontmatter from {SKILL_MD_PATH}")
    else:
        check_families_present(cases, description_blob, errors)

    fire_count = sum(1 for _, o in cases if o.get("expected") == "fire")
    silent_count = sum(1 for _, o in cases if o.get("expected") == "silent")
    if fire_count == 0:
        errors.append("trigger_cases.jsonl has zero 'fire' cases")
    if silent_count == 0:
        errors.append("trigger_cases.jsonl has zero 'silent' cases")

    verdict_case_dirs = []
    if not VERDICT_CASES_DIR.exists():
        errors.append(f"missing verdict cases directory: {VERDICT_CASES_DIR}")
    else:
        verdict_case_dirs = sorted(p for p in VERDICT_CASES_DIR.iterdir() if p.is_dir())
        if not verdict_case_dirs:
            errors.append(f"{VERDICT_CASES_DIR} has no verdict case directories")
        for d in verdict_case_dirs:
            validate_verdict_case(d, errors)

    result = {
        "mode": "offline",
        "trigger_cases": len(cases),
        "fire_cases": fire_count,
        "silent_cases": silent_count,
        "verdict_cases": len(verdict_case_dirs),
        "errors": errors,
        "ok": not errors,
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


# --------------------------------------------------------------------- live ---

def run_live(max_cases=None):
    """EXPERIMENTAL. See module docstring — this is a best-effort heuristic,
    never run in CI, and it costs real tokens because it invokes Claude Code
    once per trigger case.
    """
    claude_path = shutil.which("claude")
    if not claude_path:
        print(json.dumps({
            "mode": "live",
            "experimental": True,
            "ok": False,
            "errors": ["claude CLI not found on PATH -- install Claude Code to use --live"],
        }, indent=2))
        return 1

    cases, errors = load_trigger_cases()
    if errors:
        print(json.dumps({"mode": "live", "experimental": True, "ok": False, "errors": errors}, indent=2))
        return 1

    if max_cases:
        cases = cases[:max_cases]

    results = []
    run_errors = []
    for i, obj in cases:
        prompt = obj.get("prompt", "")
        try:
            proc = subprocess.run(
                [claude_path, "-p", prompt, "--max-turns", "1"],
                capture_output=True, text=True, timeout=120, cwd=str(ROOT),
            )
            transcript = (proc.stdout or "") + (proc.stderr or "")
        except Exception as e:  # noqa: BLE001 - no-throw discipline, matches scripts/
            run_errors.append(f"line {i}: {type(e).__name__}: {e}")
            continue

        fired = bool(re.search(r"deja-vu", transcript, re.IGNORECASE))
        observed = "fire" if fired else "silent"
        results.append({
            "line": i,
            "prompt": prompt,
            "expected": obj.get("expected"),
            "observed": observed,
            "match": observed == obj.get("expected"),
        })

    matched = sum(1 for r in results if r["match"])
    result = {
        "mode": "live",
        "experimental": True,
        "note": "best-effort heuristic: greps the response transcript for the skill's own "
                "name. Not a certified detection method -- treat as directional.",
        "total": len(results),
        "matched": matched,
        "results": results,
        "errors": run_errors,
        "ok": not run_errors,
    }
    print(json.dumps(result, indent=2))
    return 0 if not run_errors else 1


# --------------------------------------------------------------------- main ---

def build_arg_parser():
    p = argparse.ArgumentParser(
        description="deja-vu evals: trigger-fire fixtures + verdict-fixture schema validation "
                     "(docs/design.md §8)",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--offline", action="store_true",
        help="(default) CI-safe: validate fixture schemas and SKILL.md trigger-family coverage. "
             "No network access, no tokens.",
    )
    mode.add_argument(
        "--live", action="store_true",
        help="EXPERIMENTAL, costs tokens: shells out to `claude -p \"<prompt>\" --max-turns 1` "
             "per trigger case and checks whether deja-vu appears to have fired. Requires "
             "Claude Code installed on PATH. Never run this in CI.",
    )
    p.add_argument(
        "--max-cases", type=int, default=None,
        help="--live only: cap the number of cases invoked (each one costs tokens).",
    )
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    if args.live:
        return run_live(max_cases=args.max_cases)
    return run_offline()


if __name__ == "__main__":
    sys.exit(main())
