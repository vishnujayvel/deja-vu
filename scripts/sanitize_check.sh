#!/usr/bin/env bash
# deja-vu sanitize_check.sh — public-repo hygiene gate (docs/design.md distribution work).
#
# Fails (nonzero exit) if the tracked tree contains:
#   1. a machine-specific /Users/<name> path (docs/scripts should use $HOME or a
#      repo-relative path instead — those are NOT flagged by this pattern)
#   2. an email address
#   3. any literal string listed in .sanitize-denylist, if that file is present
#
# .sanitize-denylist is gitignored on purpose — it holds private strings (e.g. a
# real username or email) that must never be committed. A fresh public clone will
# not have this file at all, so step 3 is skipped gracefully and only the generic
# patterns (1) and (2) run. This script must succeed either way.
#
# Scanned set: git-tracked files plus untracked-but-not-gitignored files
# (`git ls-files --cached --others --exclude-standard`). This automatically
# skips anything .gitignore covers (.beads/, .scratch/, .gc/, .claude/skills/,
# *.gate.lock, ...) without needing to enumerate exclusions here, and it never
# includes a `.git` entry — in a plain clone that's a directory git never
# tracks, and in a `git worktree` checkout it's a machine-path-bearing pointer
# *file* that a naive `grep -r --exclude-dir=.git` would still walk into.
# This script's own denylist file is excluded explicitly since it legitimately
# contains the strings being searched for and is gitignored on purpose (so it
# would already be skipped by the git-file-list scan, but the exclude below is
# kept as defense in depth in case it's ever committed by mistake).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DENYLIST_FILE="$REPO_ROOT/.sanitize-denylist"
DENYLIST_BASENAME="$(basename "$DENYLIST_FILE")"
FOUND=0

echo "deja-vu sanitize_check: scanning $REPO_ROOT"

# Runs `grep "$@" -- "${SCAN_FILES[@]}"` and fails the gate closed on either
# outcome that isn't a clean "no match": a real hit (grep exit 0), or a grep
# error such as a dangling git-index entry whose file is missing on disk
# (grep exit >=2). Treating an error the same as "no match" would let an
# unscanned file silently pass. $1 names the check for the failure message.
scan_for() {
  local label="$1"
  shift
  [ "${#SCAN_FILES[@]}" -eq 0 ] && return 0
  local rc=0
  grep "$@" -- "${SCAN_FILES[@]}" || rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "FAIL: found $label" >&2
    FOUND=1
  elif [ "$rc" -ge 2 ]; then
    echo "FAIL: grep error while scanning for $label (exit $rc) — treating as unscanned" >&2
    FOUND=1
  fi
}

# Enumerate the scan set via a plain redirect (not process substitution) so
# a git failure is caught by its own exit status instead of silently leaving
# SCAN_FILES empty — an empty set would otherwise make every check below a
# no-op and let the script print OK without having scanned anything.
SCAN_LIST_FILE="$(mktemp)"
trap 'rm -f "$SCAN_LIST_FILE"' EXIT
if ! git ls-files --cached --others --exclude-standard -z > "$SCAN_LIST_FILE"; then
  echo "FAIL: git ls-files failed to enumerate the tracked tree — refusing to report a false OK" >&2
  exit 1
fi

SCAN_FILES=()
while IFS= read -r -d '' f; do
  [ "$f" = "$DENYLIST_BASENAME" ] && continue
  SCAN_FILES+=("$f")
done < "$SCAN_LIST_FILE"

# 1. Machine-user paths: a literal /Users/<name> segment, with or without a
#    trailing slash (placeholder-style references like "/Users/<name>/" in
#    this comment intentionally do not match, since angle brackets are not
#    in the allowed username character set).
scan_for "a machine-specific /Users/<name> path — use \$HOME or a repo-relative path" -InE '/Users/[A-Za-z0-9._-]+'

# 2. Email addresses.
scan_for "an email address" -InE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'

# 3. Private denylist — optional. Absent in a fresh public clone; fall back
#    silently to the generic checks above when it's missing.
if [ -f "$DENYLIST_FILE" ]; then
  # `|| [ -n "$pattern" ]` keeps the loop body running for a final line that
  # has no trailing newline — plain `read` returns nonzero there, and without
  # this the last denylist pattern would never be scanned.
  while IFS= read -r pattern || [ -n "$pattern" ]; do
    [ -z "$pattern" ] && continue
    case "$pattern" in
      \#*) continue ;;
    esac
    scan_for "denylisted string: $pattern" -InF "$pattern"
  done < "$DENYLIST_FILE"
else
  echo "note: $DENYLIST_BASENAME not present — falling back to generic patterns only"
fi

if [ "$FOUND" -ne 0 ]; then
  echo "sanitize_check: FAILED" >&2
  exit 1
fi

echo "sanitize_check: OK"
exit 0
