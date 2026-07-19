#!/usr/bin/env python3
"""deja-vu setup doctor.

Checks every dependency the skill's source lanes use and prints one
machine-readable line per check:

    DOCTOR: PASS  <check> -- <detail>
    DOCTOR: WARN  <check> -- <detail>   (optional dep missing/degraded)
    DOCTOR: FAIL  <check> -- <detail>   (required dep broken)

Exit code is nonzero only if a REQUIRED check fails. Optional lanes
degrade to WARN so the skill stays usable without them.

Read-only: never installs anything, never prints secret values
(presence/absence only).
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.request

TIMEOUT = 10

results = []  # (level, name, detail)


def record(level, name, detail):
    results.append((level, name, detail))
    print(f"DOCTOR: {level:4s}  {name} -- {detail}")


def run(cmd, timeout=TIMEOUT):
    """Run a command, return (exit_code, stdout+stderr). Never raises."""
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def http_status(url):
    """Return an HTTP status code for a GET, or None on network failure."""
    req = urllib.request.Request(url, headers={"User-Agent": "deja-vu-doctor"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def check_python():
    v = sys.version_info
    if v >= (3, 9):
        record("PASS", "python3", f"{v.major}.{v.minor}.{v.micro}")
    else:
        record("FAIL", "python3", f"{v.major}.{v.minor} found; 3.9+ required")


def check_github_lane():
    """Required lane: gh CLI authenticated, or unauthenticated API fallback."""
    if shutil.which("gh"):
        code, out = run(["gh", "auth", "status"])
        if code == 0:
            record("PASS", "github", "gh CLI authenticated")
            return
        record("WARN", "github", "gh CLI present but not authenticated -- run: gh auth login")
    status = http_status("https://api.github.com/rate_limit")
    if status == 200:
        record(
            "WARN" if shutil.which("gh") is None else "PASS",
            "github-api",
            "unauthenticated GitHub API reachable (low rate limits; install+login gh for full lane)",
        )
    else:
        record("FAIL", "github-api", f"GitHub API unreachable (status={status})")


def check_scorecard():
    status = http_status(
        "https://api.securityscorecards.dev/projects/github.com/ossf/scorecard"
    )
    if status == 200:
        record("PASS", "scorecard", "OpenSSF Scorecard API reachable")
    else:
        record("WARN", "scorecard", f"Scorecard API unreachable (status={status}); health lane degraded")


def check_grep_app():
    status = http_status("https://grep.app/api/search?q=deja")
    if status in (200, 429):
        note = "reachable" if status == 200 else "reachable (rate-limited right now; sweep backs off automatically)"
        record("PASS", "grep.app", note)
    else:
        record("WARN", "grep.app", f"unreachable (status={status}); pattern lane degraded")


def check_octocode():
    """Optional: octocode MCP registered with Claude Code."""
    cfg = os.path.expanduser("~/.claude.json")
    try:
        with open(cfg) as f:
            data = json.load(f)
        servers = data.get("mcpServers", {})
        if "octocode" in servers:
            record("PASS", "octocode-mcp", "registered in Claude Code user config")
            return
    except Exception:
        pass
    record(
        "WARN",
        "octocode-mcp",
        "not registered -- optional; install: claude mcp add-json -s user octocode "
        "'{\"command\":\"npx\",\"type\":\"stdio\",\"args\":[\"-y\",\"@octocodeai/mcp@latest\"]}'",
    )


def check_skills_cli():
    if not shutil.which("npx"):
        record("WARN", "skills-cli", "npx not found -- skills-ecosystem lane unavailable")
        return
    code, out = run(["npx", "--yes", "skills", "--version"], timeout=60)
    if code == 0 and out.strip():
        record("PASS", "skills-cli", f"npx skills v{out.strip().splitlines()[-1]}")
    else:
        record("WARN", "skills-cli", "npx skills did not resolve -- skills-ecosystem lane degraded")


def check_last30days():
    path = os.path.expanduser("~/.claude/skills/last30days/SKILL.md")
    if os.path.exists(path):
        record("PASS", "last30days", "installed (freshness lane available)")
    else:
        record(
            "WARN",
            "last30days",
            "not installed -- optional freshness lane; see github.com/mvanhorn/last30days-skill",
        )


def main():
    check_python()
    check_github_lane()
    check_scorecard()
    check_grep_app()
    check_octocode()
    check_skills_cli()
    check_last30days()

    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    print(
        f"DOCTOR: SUMMARY -- {len(results) - len(fails) - len(warns)} pass, "
        f"{len(warns)} warn, {len(fails)} fail"
    )
    if fails:
        print("DOCTOR: VERDICT -- NOT READY (required checks failed)")
        return 1
    print("DOCTOR: VERDICT -- READY" + (" (some optional lanes degraded)" if warns else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
