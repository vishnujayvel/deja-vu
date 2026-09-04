"""Behavioral tests for scripts/sanitize_check.sh.

The script resolves its own REPO_ROOT from its own path
(dirname(BASH_SOURCE)/..), not from the caller's cwd, so each test builds a
throwaway git repo, copies the script into <repo>/scripts/, and invokes it
there — that makes the script scan the fixture repo instead of this one.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "sanitize_check.sh"

# Built via concatenation, not as a literal, so this file's own tracked source
# doesn't trip sanitize_check.sh's own /Users/<name> pattern when it scans
# this repo (these strings are only ever written into a throwaway tmp_path
# fixture repo, never into this file's tracked content).
FAKE_MACHINE_PATH = "/Users/" + "vishnu"
FAKE_EMAIL = "person" + "@" + "example.com"


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / "sanitize_check.sh")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t" + "@" + "example"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    return repo


def commit_all(repo, message="commit"):
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo, check=True)


def run_check(repo):
    return subprocess.run(
        ["bash", "scripts/sanitize_check.sh"],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def test_clean_repo_passes(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "clean.txt").write_text("hello world\n")
    commit_all(repo)

    result = run_check(repo)

    assert result.returncode == 0, result.stderr
    assert "sanitize_check: OK" in result.stdout


def test_bare_machine_path_without_trailing_slash_is_caught(tmp_path):
    """Round-1 finding 1: a /Users/<name> reference with no trailing slash
    (e.g. end of line) used to escape the old regex entirely."""
    repo = make_repo(tmp_path)
    (repo / "notes.txt").write_text(f"WORKDIR={FAKE_MACHINE_PATH}\n")
    commit_all(repo)

    result = run_check(repo)

    assert result.returncode != 0
    assert "machine-specific" in result.stdout + result.stderr


def test_machine_path_with_trailing_slash_still_caught(tmp_path):
    """Regression guard: the original (already-working) case must still fail."""
    repo = make_repo(tmp_path)
    (repo / "notes.txt").write_text(f"cd {FAKE_MACHINE_PATH}/projects\n")
    commit_all(repo)

    result = run_check(repo)

    assert result.returncode != 0


def test_placeholder_style_path_is_not_flagged(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "notes.txt").write_text("use /Users/<name>/ as a placeholder\n")
    commit_all(repo)

    result = run_check(repo)

    assert result.returncode == 0, result.stderr


def test_denylist_last_line_without_trailing_newline_is_scanned(tmp_path):
    """Round-1 finding 2: `read` skips a final line with no trailing newline,
    so a denylisted secret on the last line used to pass the gate."""
    repo = make_repo(tmp_path)
    (repo / ".sanitize-denylist").write_bytes(b"sekretpattern123")  # no trailing \n
    (repo / "leak.txt").write_text("token: sekretpattern123\n")
    commit_all(repo)

    result = run_check(repo)

    assert result.returncode != 0
    assert "sekretpattern123" in result.stdout + result.stderr


def test_denylist_match_with_trailing_newline_still_caught(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".sanitize-denylist").write_text("sekretpattern123\n")
    (repo / "leak.txt").write_text("token: sekretpattern123\n")
    commit_all(repo)

    result = run_check(repo)

    assert result.returncode != 0


def test_missing_denylist_file_falls_back_gracefully(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "clean.txt").write_text("hello\n")
    commit_all(repo)

    result = run_check(repo)

    assert result.returncode == 0
    assert "not present" in result.stdout


def test_git_ls_files_failure_fails_closed(tmp_path):
    """Round-1 finding 3: outside a git repo, git ls-files fails; the old
    process-substitution scan swallowed that and reported a false OK."""
    repo = tmp_path / "notarepo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / "sanitize_check.sh")

    result = run_check(repo)

    assert result.returncode != 0
    assert "git ls-files failed" in result.stdout + result.stderr


def test_dangling_tracked_file_grep_error_fails_closed(tmp_path):
    """Round-1 finding 4: a tracked-but-missing-on-disk file makes grep exit
    with an error (not just 'no match'); the old code suppressed stderr and
    treated any nonzero grep exit as a clean scan."""
    repo = make_repo(tmp_path)
    (repo / "ghost.txt").write_text("nothing sensitive\n")
    commit_all(repo)
    (repo / "ghost.txt").unlink()  # still tracked in the index, gone on disk

    result = run_check(repo)

    assert result.returncode != 0
    assert "grep error" in result.stdout + result.stderr


def test_email_address_is_caught(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "notes.txt").write_text(f"contact {FAKE_EMAIL}\n")
    commit_all(repo)

    result = run_check(repo)

    assert result.returncode != 0


@pytest.mark.parametrize("script_exists", [SCRIPT])
def test_real_repo_script_is_executable_bash(script_exists):
    assert script_exists.exists()
    assert script_exists.read_text().startswith("#!/usr/bin/env bash")
