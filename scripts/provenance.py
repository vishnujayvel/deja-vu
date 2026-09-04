#!/usr/bin/env python3
"""deja-vu provenance -- stage 6b judge (design.md Section 2.6b).

Pure, deterministic normalizer. This module performs NO network access and
NO subprocess execution: it never fetches maintainer data itself. The caller
fetches raw GitHub user/repo data out of band (e.g. via `gh api` or the
GitHub REST API) and passes it in explicitly -- as a JSON document on stdin
or via `--input <path>` -- together with an explicit reference timestamp
(`--now`). Given the same input document and `--now`, the output is always
identical: no wall-clock or live-network state leaks into the result.

No-throw discipline at the process level: a malformed owner entry never
crashes the run. Instead the caller-supplied identity for a required field
that is missing or does not parse (for example an unparsable `created_at`,
or an absent user profile) causes that single record to be REJECTED -- it is
left out of `profiles` and a reason is appended to `errors[]`. A rejected
record is never emitted as a plausible-looking profile; degrading a required
field into a "safe default" would let unverifiable data pass as evidence.

Signal rules (tenure, footprint, org backing), computed only for accepted
records:
  established-practitioner - account_age_years >= 3 AND
                              (followers >= 50 OR public_repos >= 30 OR company set)
  active-builder           - account_age_years >= 1 AND
                              (followers >= 10 OR public_repos >= 5)
  unknown-experimental     - an accepted record whose signal thresholds are
                              simply not met (this is a scoring outcome, not
                              a stand-in for missing or malformed data).

Input (single JSON object on stdin, or via --input <path>):
  {
    "owners": [
      {
        "login": str,                 # required; caller-supplied identity
        "user": {...} | None,         # required; raw GitHub user API shape
        "repos": [...] | None         # optional; raw GitHub repos API shape
      }, ...
    ]
  }

Output (single JSON object to stdout):
  {
    "profiles": [
      {
        "login": str, "name": str|None, "company": str|None,
        "created_at": str|None, "followers": int|None,
        "public_repos": int|None, "account_age_years": float|None,
        "other_notable": [{"name": str, "stars": int}, ...],
        "signal": "established-practitioner"|"active-builder"|"unknown-experimental"
      }, ...
    ],
    "errors": [str, ...]
  }
"""

import argparse
import json
import sys
from datetime import datetime, timezone


def classify_signal(age_years, followers, public_repos, company):
    followers = followers or 0
    public_repos = public_repos or 0
    if age_years is None:
        return "unknown-experimental"
    if age_years >= 3 and (followers >= 50 or public_repos >= 30 or bool(company)):
        return "established-practitioner"
    if age_years >= 1 and (followers >= 10 or public_repos >= 5):
        return "active-builder"
    return "unknown-experimental"


def account_age_years(created_at, now):
    """Return years between created_at and now, or None if created_at is
    missing or does not parse. Pure and deterministic: takes `now` explicitly
    rather than reading the wall clock.
    """
    if not created_at:
        return None
    try:
        created = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    return round((now - created).days / 365.25, 2)


def top_notable_repos(repos, n=3):
    scored = [r for r in repos if isinstance(r, dict) and not r.get("fork")]
    scored.sort(key=lambda r: r.get("stargazers_count") or 0, reverse=True)
    return [
        {"name": r.get("name"), "stars": r.get("stargazers_count") or 0}
        for r in scored[:n]
    ]


def build_profile(login, user, repos, now):
    """Normalize one caller-supplied external profile into a validated record.

    `login` is always the caller-supplied identity and is never overridden by
    externally sourced content (external content is treated as data, not as
    a source of truth for identity). Returns (profile, None) on success, or
    (None, reason) when a required field is missing or malformed and the
    record must be rejected rather than degraded.
    """
    if not isinstance(user, dict):
        return None, f"provenance({login}): rejected -- missing required user profile data"

    created_at = user.get("created_at")
    age = account_age_years(created_at, now)
    if age is None:
        return None, f"provenance({login}): rejected -- missing or malformed required field created_at={created_at!r}"

    followers = user.get("followers")
    public_repos = user.get("public_repos")
    company = user.get("company")
    repos = repos if isinstance(repos, list) else []

    return {
        "login": login,
        "name": user.get("name"),
        "company": company,
        "created_at": created_at,
        "followers": followers,
        "public_repos": public_repos,
        "account_age_years": age,
        "other_notable": top_notable_repos(repos),
        "signal": classify_signal(age, followers, public_repos, company),
    }, None


def run_provenance(owners, now):
    """owners: iterable of {"login": str, "user": dict|None, "repos": list|None}."""
    errors = []
    profiles = []
    for entry in owners:
        if not isinstance(entry, dict):
            errors.append(f"provenance: rejected -- owner entry must be an object, got {type(entry).__name__}")
            continue
        login = entry.get("login")
        if not isinstance(login, str) or not login:
            errors.append("provenance: rejected -- owner entry missing required non-empty 'login' string")
            continue
        profile, err = build_profile(login, entry.get("user"), entry.get("repos"), now)
        if err:
            errors.append(err)
            continue
        profiles.append(profile)
    return {"profiles": profiles, "errors": errors}


def _parse_now(value):
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"--now must be UTC ISO-8601 'YYYY-MM-DDTHH:MM:SSZ': {e}") from e


def build_arg_parser():
    p = argparse.ArgumentParser(description="deja-vu provenance judge (design.md Section 2.6b)")
    p.add_argument(
        "--input", default="-",
        help="path to the owners JSON document (see module docstring); '-' (default) reads stdin",
    )
    p.add_argument(
        "--now", required=True, type=_parse_now,
        help="reference timestamp for age calculation, UTC ISO-8601 'YYYY-MM-DDTHH:MM:SSZ' "
             "(required explicitly so output is deterministic given the same input)",
    )
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    raw = sys.stdin.read() if args.input == "-" else open(args.input, "r", encoding="utf-8").read()
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"profiles": [], "errors": [f"provenance: rejected -- invalid input JSON: {e}"]}, indent=2))
        return 1
    owners = doc.get("owners") if isinstance(doc, dict) else None
    if not isinstance(owners, list):
        print(json.dumps({"profiles": [], "errors": ["provenance: rejected -- input must be an object with an 'owners' list"]}, indent=2))
        return 1
    result = run_provenance(owners, args.now)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
