#!/usr/bin/env bash
# deja-vu sanitize_check.sh — public-repo hygiene gate (docs/design.md distribution work).
#
# Fails (nonzero exit) if the tracked tree contains:
#   1. a machine-specific /Users/<name>/ path (docs/scripts should use $HOME or a
#      repo-relative path instead — those are NOT flagged by this pattern)
#   2. an email address
#   3. any literal string listed in .sanitize-denylist, if that file is present
#
# .sanitize-denylist is gitignored on purpose — it holds private strings (e.g. a
# real username or email) that must never be committed. A fresh public clone will
# not have this file at all, so step 3 is skipped gracefully and only the generic
# patterns (1) and (2) run. This script must succeed either way.
#
# Excluded from every check: .git/, .beads/, and this script's own denylist file
# (which legitimately contains the strings being searched for).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DENYLIST_FILE="$REPO_ROOT/.sanitize-denylist"
DENYLIST_BASENAME="$(basename "$DENYLIST_FILE")"
GREP_COMMON=(-rIn --exclude-dir=.git --exclude-dir=.beads --exclude="$DENYLIST_BASENAME")
FOUND=0

echo "deja-vu sanitize_check: scanning $REPO_ROOT"

# 1. Machine-user paths: a literal /Users/<name>/ segment (placeholder-style
#    references like "/Users/<name>/" in this comment intentionally do not
#    match, since angle brackets are not in the allowed username character set).
if grep "${GREP_COMMON[@]}" -E '/Users/[A-Za-z0-9._-]+/' . 2>/dev/null; then
  echo "FAIL: found a machine-specific /Users/<name>/ path — use \$HOME or a repo-relative path" >&2
  FOUND=1
fi

# 2. Email addresses.
if grep "${GREP_COMMON[@]}" -E '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' . 2>/dev/null; then
  echo "FAIL: found an email address" >&2
  FOUND=1
fi

# 3. Private denylist — optional. Absent in a fresh public clone; fall back
#    silently to the generic checks above when it's missing.
if [ -f "$DENYLIST_FILE" ]; then
  while IFS= read -r pattern; do
    [ -z "$pattern" ] && continue
    case "$pattern" in
      \#*) continue ;;
    esac
    if grep "${GREP_COMMON[@]}" -F -- "$pattern" . 2>/dev/null; then
      echo "FAIL: found denylisted string: $pattern" >&2
      FOUND=1
    fi
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
