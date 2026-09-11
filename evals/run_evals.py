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
TIER_MATRIX_PATH = ROOT / "policy" / "tier-matrix.json"

VALID_EXPECTED = {"fire", "silent"}
VALID_VERDICTS = {
    "NOT-A-PROBLEM", "DIFFERENT-PROBLEM", "DEPEND", "FORK", "VENDOR", "BUILD",
}
# schemas/decision-packet.schema.json's own enums, reused (not migrated onto)
# as additive fields on the six-value verdict fixtures — see docs/adr/0011.
VALID_AUTHORITY = {"agent-authorized", "human-required", "approved", "rejected", "deferred"}
VALID_RIGHTS_AND_POLICY = {"permitted", "conditional", "prohibited", "unknown"}
# policy/tier-matrix.json's own stopping_rules keys (the four values under its
# top-level "stopping_rules" object). Only "required_human_decision" is used
# as a fixture-level halt marker today — a hunt that stops before Gate never
# issues one of the six verdicts.
VALID_STOPPING_RULES = {
    "sufficient_verified_fit", "exhausted_bounded_coverage",
    "budget_exhaustion_with_uncertainty", "required_human_decision",
}

# Matches a "<lane>: <status> -- <detail>" convention used by curated verdict
# fixtures to name a lane's tier-matrix status explicitly (scripts/sweep.py's
# own errors[] is free text and never emits this format itself — see
# _load_tier_matrix's docstring for why fixtures use it anyway).
LANE_STATUS_RE = re.compile(
    r"""^(?P<lane>[a-zA-Z0-9_]+):\s*(?P<status>unsupported|degraded|skipped|failed)\b"""
)


def _load_tier_matrix(path=TIER_MATRIX_PATH):
    """Load policy/tier-matrix.json, the canonical tier/lane policy source.

    Returns None (never raises) if the file is missing or malformed — callers
    treat that as "cannot validate tier-awareness" and skip rather than crash,
    matching this project's no-throw script discipline.
    """
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

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

    stopping_rule = expected_obj.get("stopping_rule")
    has_stopping_rule = "stopping_rule" in expected_obj
    if has_stopping_rule and stopping_rule not in VALID_STOPPING_RULES:
        errors.append(
            f"verdict_cases/{dir_path.name}/expected.json: 'stopping_rule' must be one "
            f"of {sorted(VALID_STOPPING_RULES)}, got {stopping_rule!r}"
        )
    if stopping_rule == "required_human_decision":
        # A hunt halted before Gate for a human decision has not reached any
        # of the six verdicts yet -- carrying both fields would let a naive
        # consumer read the verdict as resolved while the prose says it isn't
        # (exactly the defect this fixture shape replaces).
        if "verdict" in expected_obj:
            errors.append(
                f"verdict_cases/{dir_path.name}/expected.json: stopping_rule is "
                f"'required_human_decision' (halted before Gate) but 'verdict' is also "
                f"present ({expected_obj.get('verdict')!r}) -- a halted hunt must not "
                f"also carry a resolved verdict"
            )
        if expected_obj.get("authority") != "human-required":
            errors.append(
                f"verdict_cases/{dir_path.name}/expected.json: stopping_rule "
                f"'required_human_decision' requires authority == 'human-required'"
            )
    else:
        verdict = expected_obj.get("verdict")
        if verdict not in VALID_VERDICTS:
            errors.append(
                f"verdict_cases/{dir_path.name}/expected.json: 'verdict' must be one of "
                f"{sorted(VALID_VERDICTS)}, got {verdict!r}"
            )

    authority = expected_obj.get("authority")
    if "authority" in expected_obj and authority not in VALID_AUTHORITY:
        errors.append(
            f"verdict_cases/{dir_path.name}/expected.json: 'authority' must be one of "
            f"{sorted(VALID_AUTHORITY)}, got {authority!r}"
        )

    rights_and_policy = expected_obj.get("rights_and_policy")
    if "rights_and_policy" in expected_obj and rights_and_policy not in VALID_RIGHTS_AND_POLICY:
        errors.append(
            f"verdict_cases/{dir_path.name}/expected.json: 'rights_and_policy' must be "
            f"one of {sorted(VALID_RIGHTS_AND_POLICY)}, got {rights_and_policy!r}"
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
        return

    check_verdict_acknowledges_sweep_errors(dir_path, input_obj, expected_obj, errors)
    check_null_license_candidates_are_acknowledged(dir_path, input_obj, expected_obj, errors)
    check_null_license_rights_and_policy_matches_source(dir_path, input_obj, expected_obj, errors)
    check_unsupported_required_lane_requires_human_authority(dir_path, input_obj, expected_obj, errors)
    check_build_verdict_requires_human_authority(dir_path, expected_obj, errors)


# A verdict fixture is dishonest, not just schema-valid, if it stays silent
# about coverage loss. docs/design.md §2.3: "degraded", "failed", "skipped",
# and "unsupported" are distinct from a proven absence of results -- an empty
# candidates[] next to a non-empty sweep.errors[] must never read like a
# clean successful-empty search. This is a keyword check, not a semantic
# proof: it only guards against a fixture that never mentions the loss at
# all, the same way check_families_present guards SKILL.md drift.
COVERAGE_LOSS_TERMS = (
    "error", "degrad", "unsupported", "coverage", "uncertain", "fail",
    "incomplete", "residual", "inconclusive",
)


def check_verdict_acknowledges_sweep_errors(dir_path, input_obj, expected_obj, errors):
    sweep_errors = (input_obj.get("sweep") or {}).get("errors")
    if not isinstance(sweep_errors, list) or not sweep_errors:
        return
    reasons_blob = " ".join(expected_obj.get("key_reasons") or []).lower()
    if not any(term in reasons_blob for term in COVERAGE_LOSS_TERMS):
        errors.append(
            f"verdict_cases/{dir_path.name}: sweep.errors is non-empty "
            f"({sweep_errors!r}) but expected.key_reasons never acknowledges the "
            f"coverage loss (expected a term like {COVERAGE_LOSS_TERMS!r})"
        )


# A candidate with license: null is an unresolved rights question, not a
# silent non-issue (docs/design.md's rights-and-policy dimension: "unknown"
# is distinct from "permitted"). If the fixture's own candidates include one,
# the reasoning must say so somewhere -- otherwise the fixture models a
# verdict that quietly ignores a licensing gap.
def check_null_license_candidates_are_acknowledged(dir_path, input_obj, expected_obj, errors):
    candidates = (input_obj.get("sweep") or {}).get("candidates")
    if not isinstance(candidates, list):
        return
    has_null_license = any(
        isinstance(c, dict) and "license" in c and c.get("license") is None
        for c in candidates
    )
    if not has_null_license:
        return
    reasons_blob = " ".join(expected_obj.get("key_reasons") or []).lower()
    if "license" not in reasons_blob:
        errors.append(
            f"verdict_cases/{dir_path.name}: a candidate has license: null but "
            f"expected.key_reasons never mentions 'license'"
        )


# license: null means two different things depending on which lane produced
# the candidate, and collapsing them loses a real distinction (docs/design.md's
# rights-and-policy dimension): a github-sourced candidate's null license is a
# *confirmed* absence of a LICENSE file (github_lane reads the repo's own
# license metadata, so null there is a real signal: all rights reserved,
# rights_and_policy "prohibited"). A registry-sourced candidate's null license
# (see scripts/sweep.py's _pypi_search, which reads only info.license) is
# *adapter metadata loss* -- the field came back empty, not evidence the
# package itself has no license -- rights_and_policy "unknown", not
# "prohibited". A fixture that only ever writes "license: null" without this
# distinction lets a reader silently treat an unknown as a confirmed
# prohibition (over-claiming) or vice versa (under-claiming a real block).
def check_null_license_rights_and_policy_matches_source(dir_path, input_obj, expected_obj, errors):
    candidates = (input_obj.get("sweep") or {}).get("candidates")
    if not isinstance(candidates, list):
        return
    null_license_candidates = [
        c for c in candidates
        if isinstance(c, dict) and "license" in c and c.get("license") is None
    ]
    if not null_license_candidates:
        return
    expected_values = {
        "prohibited" if str(c.get("source_lane", "")).startswith("github") else "unknown"
        for c in null_license_candidates
    }
    rights_and_policy = expected_obj.get("rights_and_policy")
    if rights_and_policy not in expected_values:
        errors.append(
            f"verdict_cases/{dir_path.name}: candidate(s) with license: null imply "
            f"rights_and_policy in {sorted(expected_values)!r} (github source = "
            f"confirmed no-LICENSE-file = 'prohibited'; registry source = adapter "
            f"metadata loss = 'unknown'), but expected.rights_and_policy is "
            f"{rights_and_policy!r}"
        )


# policy/tier-matrix.json: an "unsupported" required lane (its exact status
# vocabulary -- see the github lane's on_unavailable.lane_status) triggers
# stopping_rules.required_human_decision, which halts the hunt before Gate --
# no verdict is issued at all (validate_verdict_case enforces that "verdict"
# and "stopping_rule": "required_human_decision" are mutually exclusive).
# This check cross-references the tier's actual required_lanes list in
# policy/tier-matrix.json rather than treating every "unsupported" mention as
# equally blocking: an unsupported *optional* lane narrows coverage but does
# not, on its own, halt the hunt. Fixtures name a lane's status explicitly
# via the "<lane>: <status> -- <detail>" convention (LANE_STATUS_RE) because
# scripts/sweep.py's own errors[] is free text and never emits this
# vocabulary itself -- see docs/design.md §2.3 for why status still matters
# even though the script doesn't structure it.
def check_unsupported_required_lane_requires_human_authority(dir_path, input_obj, expected_obj, errors):
    sweep_errors = (input_obj.get("sweep") or {}).get("errors")
    if not isinstance(sweep_errors, list):
        return

    unsupported_lanes = []
    for e in sweep_errors:
        m = LANE_STATUS_RE.match(str(e))
        if m and m.group("status") == "unsupported":
            unsupported_lanes.append(m.group("lane"))
    if not unsupported_lanes:
        return

    tier = input_obj.get("tier")
    tier_matrix = _load_tier_matrix()
    if tier_matrix is None or tier not in (tier_matrix.get("tiers") or {}):
        # Can't establish requiredness without a known tier + policy file --
        # fall back to the pre-tier-aware behavior rather than silently
        # skipping the check (a fixture naming an "unsupported" lane without a
        # recognized "tier" field is itself a fixture-authoring gap).
        errors.append(
            f"verdict_cases/{dir_path.name}: input.json reports unsupported lane(s) "
            f"{unsupported_lanes!r} but has no valid 'tier' field matching a tier in "
            f"{TIER_MATRIX_PATH} -- add one so lane requiredness can be checked "
            f"against policy instead of assumed"
        )
        return

    required_lanes = set(tier_matrix["tiers"][tier].get("required_lanes") or [])
    blocking_lanes = [lane for lane in unsupported_lanes if lane in required_lanes]
    if not blocking_lanes:
        return

    if expected_obj.get("authority") != "human-required":
        errors.append(
            f"verdict_cases/{dir_path.name}: {blocking_lanes!r} is unsupported and "
            f"required at tier {tier!r} (policy/tier-matrix.json), so "
            f"expected.authority must be 'human-required'"
        )
    if expected_obj.get("stopping_rule") != "required_human_decision":
        errors.append(
            f"verdict_cases/{dir_path.name}: {blocking_lanes!r} is unsupported and "
            f"required at tier {tier!r}, so expected.stopping_rule must be "
            f"'required_human_decision' (the hunt halts before Gate; no verdict is "
            f"issued from this state)"
        )


# SKILL.md's "THE ASYMMETRIC GATE": "A BUILD verdict is the one this skill
# exists to police, and it can never be self-approved." This holds
# unconditionally -- unlike DEPEND/FORK/VENDOR, which only need authority when
# Judge raises a flag, BUILD always needs it. Checking this directly off the
# verdict value (rather than inferring it from lane status) covers every
# BUILD fixture, including ones whose route to BUILD has nothing to do with
# an unsupported lane (e.g. build-no-license-nearmatch, where the trigger is
# a rights problem, not a coverage gap).
def check_build_verdict_requires_human_authority(dir_path, expected_obj, errors):
    if expected_obj.get("verdict") != "BUILD":
        return
    if expected_obj.get("authority") != "human-required":
        errors.append(
            f"verdict_cases/{dir_path.name}: verdict is 'BUILD', which SKILL.md's "
            f"asymmetric gate says can never be self-approved, so "
            f"expected.authority must be 'human-required'"
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
