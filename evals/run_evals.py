#!/usr/bin/env python3
"""deja-vu evals — trigger-fire fixtures + verdict-fixture schema validation.

Design rationale: docs/design.md §8 ("Testing & evals"). Stdlib only.

Two modes:

  --offline (default, CI-safe)
      Validates evals/trigger_cases.jsonl schema, cross-checks that every
      fire-case's `matched_family` phrase still appears in SKILL.md's
      frontmatter description (so a description edit that silently drops a
      trigger phrase fails CI instead of rotting quietly), validates the
      evals/verdict_cases/ fixture schemas, and asserts every lane name
      mentioned in `--lanes` invocation strings inside SKILL.md and
      references/lanes.md is a member of scripts/sweep.py's ALL_LANES.
      No network access, no tokens. Exits nonzero on any failure.

  --live (optional, EXPERIMENTAL, costs tokens, NOT run in CI)
      For each trigger case, shells out to a headless Claude Code session
      and detects whether the deja-vu skill was actually invoked.
      Preferred path: `claude -p <prompt> --output-format stream-json
      --verbose --max-turns 3`, then scan the JSON event stream for a
      Skill/skill tool_use whose payload names deja-vu. Falls back to
      grepping reply text for "deja-vu" when stream-json is unsupported.
      Live results measure trigger behavior in HEADLESS sessions, which
      may differ from interactive ones. Treat output as directional.

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
LANES_MD_PATH = ROOT / "references" / "lanes.md"
SWEEP_PY_PATH = ROOT / "scripts" / "sweep.py"

VALID_EXPECTED = {"fire", "silent"}
VALID_VERDICTS = {
    "NOT-A-PROBLEM", "DIFFERENT-PROBLEM", "DEPEND", "FORK", "VENDOR", "BUILD",
}

# Matches: --lanes github,registry  or  --lanes=github,registry,grep
LANES_FLAG_RE = re.compile(
    r"""--lanes(?:\s+|=)(?P<value>["']?)(?P<lanes>[a-zA-Z0-9_,]+)(?P=value)"""
)
ALL_LANES_ASSIGN_RE = re.compile(
    r"""^ALL_LANES\s*=\s*\[([^\]]*)\]""",
    re.MULTILINE,
)


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


# --------------------------------------------------------------- lane drift ---

def parse_all_lanes(path=SWEEP_PY_PATH):
    """Parse ALL_LANES = [...] from scripts/sweep.py via regex.

    Returns (list of lane name strings) or raises ValueError if the assignment
    cannot be found / parsed. Does not import sweep.py — keeps evals decoupled
    from script runtime side effects.
    """
    if not path.exists():
        raise ValueError(f"missing sweep script: {path}")
    text = path.read_text()
    m = ALL_LANES_ASSIGN_RE.search(text)
    if not m:
        raise ValueError(
            f"could not find ALL_LANES = [...] assignment in {path}"
        )
    inner = m.group(1)
    lanes = re.findall(r"""['"]([a-zA-Z0-9_-]+)['"]""", inner)
    if not lanes:
        raise ValueError(
            f"ALL_LANES assignment in {path} parsed to an empty list"
        )
    return lanes


def extract_lanes_from_docs(paths):
    """Yield (path, line_no, lane_token) for every name inside a --lanes value.

    Scans SKILL.md / references/lanes.md invocation strings for
    `--lanes github,registry,...` (space or `=` form). Each comma-separated
    token is reported individually so drift messages can name the bad token.
    """
    for path in paths:
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text().splitlines(), start=1):
            for m in LANES_FLAG_RE.finditer(line):
                raw = m.group("lanes")
                for token in raw.split(","):
                    token = token.strip()
                    if token:
                        yield path, i, token


def check_lane_consistency(errors, all_lanes=None, doc_paths=None):
    """Assert every --lanes token in docs is a member of ALL_LANES.

    Closes the gap where doc/script lane-name drift ships undetected.
    Appends one clear error per drifted token (names the token + source).
    """
    if all_lanes is None:
        try:
            all_lanes = parse_all_lanes()
        except ValueError as e:
            errors.append(str(e))
            return
    allowed = set(all_lanes)

    if doc_paths is None:
        doc_paths = [SKILL_MD_PATH, LANES_MD_PATH]

    missing_docs = [p for p in doc_paths if not p.exists()]
    for p in missing_docs:
        errors.append(f"missing doc for lane-consistency check: {p}")

    for path, line_no, token in extract_lanes_from_docs(doc_paths):
        if token not in allowed:
            rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
            errors.append(
                f"lane-name drift: {token!r} in {rel}:{line_no} is not a "
                f"member of ALL_LANES={all_lanes!r} (scripts/sweep.py)"
            )


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

    check_lane_consistency(errors)

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

def claude_supports_stream_json(claude_path):
    """Probe whether this claude binary advertises stream-json output format."""
    try:
        proc = subprocess.run(
            [claude_path, "--help"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:  # noqa: BLE001 - probe must never raise
        return False
    help_text = (proc.stdout or "") + (proc.stderr or "")
    return "stream-json" in help_text


def skill_invoked_in_stream(transcript):
    """True if stream-json events show a Skill/skill tool_use naming deja-vu.

    Claude Code stream-json emits one JSON object per line (plus occasional
    non-JSON noise). We walk each parseable line and look for tool_use /
    tool-call shapes whose name is Skill/skill and whose payload mentions
    deja-vu. Deliberately loose on nesting — the CLI's event schema has
    shifted before; a structural 'skill tool + deja-vu' signal is the goal.
    """
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if _event_has_deja_vu_skill(event):
            return True
    # Also accept a single JSON document (non-NDJSON) if the CLI ever
    # dumps an array/object of events instead of line-delimited ones.
    stripped = transcript.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            blob = json.loads(stripped)
        except json.JSONDecodeError:
            return False
        return _event_has_deja_vu_skill(blob)
    return False


def _event_has_deja_vu_skill(node):
    """Recursive walk: Skill/skill tool use whose args/content mention deja-vu."""
    if isinstance(node, dict):
        name = node.get("name") or node.get("tool") or node.get("tool_name")
        type_ = node.get("type")
        looks_like_tool = (
            type_ in ("tool_use", "tool_call", "tool-use", "tool-call")
            or (isinstance(name, str) and name.lower() in ("skill", "skills"))
        )
        if looks_like_tool and isinstance(name, str) and name.lower() in (
            "skill", "skills",
        ):
            payload = json.dumps(node, default=str)
            if re.search(r"deja-vu", payload, re.IGNORECASE):
                return True
        # Generic: any tool-shaped event whose serialized form pairs Skill + deja-vu
        if looks_like_tool:
            payload = json.dumps(node, default=str)
            if re.search(r"skill", payload, re.IGNORECASE) and re.search(
                r"deja-vu", payload, re.IGNORECASE
            ):
                return True
        for v in node.values():
            if _event_has_deja_vu_skill(v):
                return True
    elif isinstance(node, list):
        for item in node:
            if _event_has_deja_vu_skill(item):
                return True
    return False


def detect_fired(transcript, detection_mode):
    """Return True if the transcript indicates deja-vu fired.

    detection_mode:
      'stream-json' — require a Skill tool invocation containing deja-vu
      'text-grep'   — fall back: any case-insensitive 'deja-vu' in the text
    """
    if detection_mode == "stream-json":
        return skill_invoked_in_stream(transcript)
    return bool(re.search(r"deja-vu", transcript, re.IGNORECASE))


def run_live(max_cases=None):
    """EXPERIMENTAL. See module docstring — this is a best-effort heuristic,
    never run in CI, and it costs real tokens because it invokes Claude Code
    once per trigger case.

    Live results measure trigger behavior in HEADLESS sessions, which may
    differ from interactive ones.
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

    use_stream = claude_supports_stream_json(claude_path)
    detection_mode = "stream-json" if use_stream else "text-grep"

    results = []
    run_errors = []
    for i, obj in cases:
        prompt = obj.get("prompt", "")
        if use_stream:
            cmd = [
                claude_path, "-p", prompt,
                "--output-format", "stream-json",
                "--verbose",
                "--max-turns", "3",
            ]
        else:
            # Fallback when this claude build does not advertise stream-json.
            cmd = [claude_path, "-p", prompt, "--max-turns", "1"]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=180, cwd=str(ROOT),
            )
            transcript = (proc.stdout or "") + (proc.stderr or "")
        except Exception as e:  # noqa: BLE001 - no-throw discipline, matches scripts/
            run_errors.append(f"line {i}: {type(e).__name__}: {e}")
            continue

        fired = detect_fired(transcript, detection_mode)
        observed = "fire" if fired else "silent"
        results.append({
            "line": i,
            "prompt": prompt,
            "expected": obj.get("expected"),
            "observed": observed,
            "match": observed == obj.get("expected"),
            "detection": detection_mode,
        })

    matched = sum(1 for r in results if r["match"])
    result = {
        "mode": "live",
        "experimental": True,
        "detection_mode": detection_mode,
        "note": (
            "Live results measure trigger behavior in HEADLESS sessions, which may "
            "differ from interactive ones. "
            + (
                "Detects Skill/skill tool_use events naming deja-vu in the "
                "stream-json event stream (--output-format stream-json --verbose "
                "--max-turns 3)."
                if detection_mode == "stream-json"
                else "stream-json unsupported on this claude binary; fell back to "
                "grepping the response transcript for the skill's own name "
                "(--max-turns 1). Not a certified detection method."
            )
        ),
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
        epilog=(
            "Live mode note: --live measures trigger behavior in HEADLESS Claude Code "
            "sessions, which may differ from interactive ones. Preferred detection uses "
            "--output-format stream-json --verbose --max-turns 3 and looks for a Skill "
            "tool invocation naming deja-vu; falls back to text-grep if stream-json is "
            "unsupported. Never run --live in CI."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--offline", action="store_true",
        help="(default) CI-safe: validate fixture schemas, SKILL.md trigger-family coverage, "
             "and doc↔sweep.py lane-name consistency. No network access, no tokens.",
    )
    mode.add_argument(
        "--live", action="store_true",
        help="EXPERIMENTAL, costs tokens: headless `claude -p` per trigger case. Preferred: "
             "--output-format stream-json --verbose --max-turns 3, detecting a Skill tool "
             "invocation containing deja-vu; falls back to text-grep if stream-json is "
             "unsupported. Measures HEADLESS trigger behavior (may differ from interactive). "
             "Requires Claude Code on PATH. Never run this in CI.",
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
