#!/usr/bin/env python3
"""Fable pre-merge gate the Gas City refinery runs before fast-forwarding
polecat branches into p1-night.

Exit 0 = merge allowed. Any non-zero exit = merge refused. Always prints
one line: ``REFINERY_GATE: <allow|refuse> reason=...`` (or the fixed line
``REFINERY_GATE: skip`` when the context guard declines to run).

This script never merges, pushes, or closes Beads itself -- the refinery
formula (mol-refinery-patrol) does that. It only decides allow/refuse.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import fable_review_gate

DEFAULT_JOBCTL = Path.home() / "workplace" / "gc-router" / "bin" / "jobctl"
DEFAULT_BASE_BRANCH = "p1-night"
MAX_ROUND = 3
MAX_ATTEMPT = 3
QUALITY_GATE_TIMEOUT_SECONDS = 600
REVIEW_JOB_TIMEOUT_SECONDS = 900

# scripts/prepare_fable_review.py encodes round/attempt at the end of the
# job id it mints (job-fable-<slug>-<artifact12>-<governing12>-rR-aA).
JOB_ID_ROUND_ATTEMPT = re.compile(r"-r(?P<round>[1-3])-a(?P<attempt>[1-3])$")

# Order matches the bead contract: pytest, doctor, offline evals, sanitizer.
QUALITY_GATES: tuple[tuple[list[str], str], ...] = (
    (["python3", "-m", "pytest", "-q"], "pytest"),
    (["python3", "scripts/doctor.py"], "doctor"),
    (["python3", "evals/run_evals.py", "--offline"], "evals"),
    (["bash", "scripts/sanitize_check.sh"], "sanitize_check"),
)


def refinery_identity(agent: str | None) -> bool:
    """True when $GC_AGENT names this session's role as the refinery.

    Gastown session identities look like ``<rig>/<binding_prefix>refinery``
    (e.g. ``deja-vu/gastown.refinery``); there is no separate GC_ROLE env
    var in the gastown pack (grep confirms only $GC_AGENT is canonical --
    see mol-refinery-patrol's validate-identity step and
    agents/refinery/prompt.template.md).
    """
    if not agent:
        return False
    suffix = agent.rsplit("/", 1)[-1]
    role = suffix.rsplit(".", 1)[-1]
    return role == "refinery"


def resolve_bead_id(
    explicit: str | None, environ: dict[str, str], branch: str | None
) -> str | None:
    """Determine the work bead id: --bead flag, then env, then branch name.

    The refinery formula does not expose a documented env var carrying the
    work bead id to build_command (it is a bare shell variable local to the
    refinery agent's own conversation, not exported to subprocesses). The
    branch-naming contract (`polecat/<bead-id>`, required by CLAUDE.md) is
    the reliable fallback.
    """
    if explicit:
        return explicit
    for key in ("BEAD", "WORK", "GC_WORK_BEAD_ID"):
        value = environ.get(key)
        if value:
            return value
    if branch:
        match = re.fullmatch(r"polecat/(?P<bead>.+)", branch)
        if match:
            return match.group("bead")
    return None


def current_branch(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def changed_files(root: Path, base_ref: str) -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"git diff against {base_ref} failed: {completed.stderr.strip()}"
        )
    return [line for line in completed.stdout.splitlines() if line]


def run_quality_gates(root: Path) -> tuple[bool, str]:
    """Run pytest, doctor, offline evals, and the sanitizer in order."""
    for command, name in QUALITY_GATES:
        try:
            completed = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                timeout=QUALITY_GATE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return False, f"{name} timed out after {QUALITY_GATE_TIMEOUT_SECONDS}s"
        except OSError as error:
            return False, f"{name} could not run: {error}"
        if completed.returncode != 0:
            detail = (completed.stdout + completed.stderr).strip()
            return False, f"{name} failed (exit {completed.returncode}): {detail[-500:]}"
    return True, ""


def load_module_review_records(
    root: Path, module: str, bead_id: str
) -> list[dict[str, Any]]:
    completed = subprocess.run(
        [
            "bd",
            "list",
            "--all",
            "--label",
            "fable-review",
            "--metadata-field",
            f"review_module={module}",
            "--metadata-field",
            f"review_implementation_bead={bead_id}",
            "--limit",
            "0",
            "--json",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr.strip()
            or completed.stdout.strip()
            or "bd list failed while looking up prior review records"
        )
    loaded = json.loads(completed.stdout or "[]")
    if not isinstance(loaded, list):
        raise ValueError("bd list did not return a JSON array")
    return loaded


def select_round_attempt(
    records: list[dict[str, Any]],
    artifact_sha256: str,
    governing_sha256: str,
) -> tuple[int, int] | None:
    """Return the lowest unused (round, attempt) pair for this artifact and
    governing-contract hash, capped at 3/3. None means exhausted."""
    used: set[tuple[int, int]] = set()
    for record in records:
        metadata = record.get("metadata") or {}
        if metadata.get("review_artifact_sha256") != artifact_sha256:
            continue
        if metadata.get("review_governing_contract_sha256") != governing_sha256:
            continue
        job_id = metadata.get("review_delegate_job_id") or ""
        match = JOB_ID_ROUND_ATTEMPT.search(job_id)
        if not match:
            continue
        used.add((int(match.group("round")), int(match.group("attempt"))))
    for round_number in range(1, MAX_ROUND + 1):
        for attempt_number in range(1, MAX_ATTEMPT + 1):
            if (round_number, attempt_number) not in used:
                return round_number, attempt_number
    return None


def _run_json(
    command: list[str], root: Path, *, timeout: float | None = None
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{' '.join(command)} timed out: {error}") from error
    except OSError as error:
        raise RuntimeError(f"{' '.join(command)} could not run: {error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"{' '.join(command)} failed (exit {completed.returncode}): {detail[-800:]}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{' '.join(command)} did not return JSON: {error}") from error


def submit_fable_review(
    root: Path,
    module: str,
    round_number: int,
    attempt_number: int,
    jobctl: Path,
) -> dict[str, Any]:
    """Prepare, validate, submit, and wait for one Fable review job."""
    prep = _run_json(
        [
            "python3",
            "scripts/prepare_fable_review.py",
            module,
            "--root",
            str(root),
            "--round",
            str(round_number),
            "--attempt",
            str(attempt_number),
            "--json",
        ],
        root,
    )
    _run_json([str(jobctl), "validate", "--manifest", prep["manifest_path"], "--json"], root)
    submitted = _run_json(
        [str(jobctl), "submit", "--manifest", prep["manifest_path"], "--json"], root
    )
    job_id = submitted["job_id"]
    waited = _run_json(
        [str(jobctl), "wait", job_id, "--timeout", str(REVIEW_JOB_TIMEOUT_SECONDS), "--json"],
        root,
        timeout=REVIEW_JOB_TIMEOUT_SECONDS + 30,
    )
    if waited.get("state") != "succeeded":
        raise RuntimeError(
            f"review job {job_id} ended in state {waited.get('state')}: {waited.get('reason')}"
        )
    return {"prep": prep, "job_id": job_id}


def verify_fable_review(
    root: Path,
    job_id: str,
    module: str,
    bead_id: str,
    round_number: int,
    jobctl: Path,
) -> dict[str, Any]:
    return _run_json(
        [
            str(jobctl),
            "verify-review",
            job_id,
            "--module",
            module,
            "--implementation-bead",
            bead_id,
            "--round",
            str(round_number),
            "--json",
        ],
        root,
    )


def append_findings_note(
    root: Path, bead_id: str, module: str, review: dict[str, Any]
) -> None:
    findings = review.get("findings") or []
    lines = [f"Fable review refused for {module} (verdict={review.get('verdict')}):"]
    for finding in findings:
        lines.append(
            f"- [{finding.get('severity')}] {finding.get('summary')} "
            f"({finding.get('contract_clause')})"
        )
    completed = subprocess.run(
        ["bd", "update", bead_id, "--append-notes", "\n".join(lines)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr.strip() or completed.stdout.strip() or "bd update --append-notes failed"
        )


def write_review_record(root: Path, bead_id: str, review: dict[str, Any]) -> str:
    """Promote one verified pass review into a closed bd Bead the local
    coverage diagnostic (scripts/fable_review_gate.py) can see.

    review_permission is hardcoded "read-only" because this script only ever
    prepares reviews through scripts/prepare_fable_review.py, whose manifest
    permissions block (shell=none, network=none, write_roots=[]) is a fixed
    structural invariant, not caller-configurable -- there is no code path
    here that could produce a review under a different permission envelope.
    review_permission_attested is "true" because this function only runs
    after jobctl verify-review has reported evidence_verified=true.
    """
    metadata = {
        "review_schema": review["schema_version"],
        "review_module": review["module_path"],
        "review_artifact_sha256": review["artifact_sha256"],
        "review_contract_sha256": review["contract_sha256"],
        "review_governing_contract_sha256": review["governing_contract_sha256"],
        "review_contract_ref": review["contract_ref"],
        "review_implementation_bead": review["implementation_bead"],
        "review_delegate_job_id": review["delegate_job_id"],
        "review_launch_envelope_sha256": review["launch_envelope_sha256"],
        "review_model": review["reviewer"]["model"],
        "review_target": review["reviewer"]["target"],
        "review_permission": "read-only",
        "review_permission_attested": "true",
        "review_verdict": review["verdict"],
        "review_round": str(review["round"]),
        "review_findings_unresolved": str(len(review.get("findings") or [])),
    }
    completed = subprocess.run(
        [
            "bd",
            "create",
            "--title",
            f"Fable review: {review['module_path']} round {review['round']} ({bead_id})",
            "--type",
            "task",
            "--labels",
            "fable-review",
            "--status",
            "closed",
            "--metadata",
            json.dumps(metadata, sort_keys=True),
            "--notes",
            f"Recorded by scripts/refinery_gate.py for implementation bead {bead_id}.",
            "--json",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr.strip() or completed.stdout.strip() or "bd create failed while recording the review"
        )
    created = json.loads(completed.stdout)
    return created["id"]


def check_final_coverage(root: Path, governed_changed: list[str]) -> tuple[bool, str]:
    """Re-run scripts/fable_review_gate.py and require the changed governed
    modules to be covered with zero missing/stale problems.

    fable_review_gate.py's CLI always exits 1 by design (diagnostic-only,
    never self-authorizes release) except when it hits an internal error,
    where it exits 2 with no JSON on stdout -- so exit code alone cannot
    signal success here; only a parseable JSON report can.
    """
    completed = subprocess.run(
        ["python3", "scripts/fable_review_gate.py", "--root", str(root), "--json"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 2 or not completed.stdout.strip():
        raise RuntimeError(
            completed.stderr.strip() or "scripts/fable_review_gate.py errored"
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"scripts/fable_review_gate.py did not return JSON: {error}") from error
    covered = set(report.get("covered", []))
    uncovered = [module for module in governed_changed if module not in covered]
    if uncovered:
        return False, f"coverage-gate-uncovered:{','.join(uncovered)}"
    return True, ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--bead", help="Work bead id. Overrides env and branch-name inference.")
    parser.add_argument("--base-branch", default=DEFAULT_BASE_BRANCH)
    parser.add_argument("--jobctl", type=Path, default=DEFAULT_JOBCTL)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run the gate even when $GC_AGENT does not identify the refinery.",
    )
    parser.add_argument("--json", action="store_true", help="Also print the full diagnostic report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()

    if not args.force and not refinery_identity(os.environ.get("GC_AGENT")):
        print("REFINERY_GATE: skip")
        return 0

    def finish(status: str, reason: str, extra: dict[str, Any] | None = None) -> int:
        print(f"REFINERY_GATE: {status} reason={reason}")
        if args.json:
            report = {"status": status, "reason": reason}
            if extra:
                report.update(extra)
            print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if status == "allow" else 1

    passed, gate_reason = run_quality_gates(root)
    if not passed:
        return finish("refuse", gate_reason)

    try:
        changed = changed_files(root, f"origin/{args.base_branch}")
    except RuntimeError as error:
        return finish("refuse", str(error))

    contracts = fable_review_gate.load_canonical_module_contracts(root)
    modules = fable_review_gate.discover_modules(root)
    governed_changed = sorted(module for module in changed if module in modules)

    bead_id = None
    if governed_changed:
        bead_id = resolve_bead_id(args.bead, dict(os.environ), current_branch(root))
        if not bead_id:
            return finish("refuse", "missing-bead-id")

    for module in governed_changed:
        contract = contracts.get(module)
        if contract is None:
            return finish("refuse", f"no-contract:{module}")

        artifact_sha256 = hashlib.sha256(
            fable_review_gate.read_governed_bytes(root, module)
        ).hexdigest()
        governing_sha256 = fable_review_gate.governing_contract_sha256(root, module, contract)

        try:
            records = load_module_review_records(root, module, bead_id)
        except (RuntimeError, ValueError, json.JSONDecodeError) as error:
            return finish("refuse", f"review-lookup-failed:{module}:{error}")

        selection = select_round_attempt(records, artifact_sha256, governing_sha256)
        if selection is None:
            return finish("refuse", f"round-attempt-exhausted:{module}")
        round_number, attempt_number = selection

        try:
            submission = submit_fable_review(root, module, round_number, attempt_number, args.jobctl)
            verification = verify_fable_review(
                root, submission["job_id"], module, bead_id, round_number, args.jobctl
            )
        except RuntimeError as error:
            return finish("refuse", f"review-job-failed:{module}:{error}")

        review = verification.get("review") or {}
        if not verification.get("evidence_verified") or review.get("verdict") != "pass":
            try:
                append_findings_note(root, bead_id, module, review)
            except RuntimeError:
                pass  # best-effort note; the refusal below stands regardless
            return finish("refuse", f"review-verdict:{module}:{review.get('verdict')}")

        try:
            write_review_record(root, bead_id, review)
        except RuntimeError as error:
            return finish("refuse", f"review-record-write-failed:{module}:{error}")

    if governed_changed:
        try:
            coverage_ok, coverage_reason = check_final_coverage(root, governed_changed)
        except RuntimeError as error:
            return finish("refuse", f"coverage-recheck-failed:{error}")
        if not coverage_ok:
            return finish("refuse", coverage_reason)

    return finish("allow", "ok", {"governed_changed": governed_changed})


if __name__ == "__main__":
    raise SystemExit(main())
