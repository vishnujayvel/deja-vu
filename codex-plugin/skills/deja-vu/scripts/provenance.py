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
that is missing or does not parse (for example an unparsable or future-dated
`created_at`, an absent user profile, or a `followers`/`public_repos`/`name`/
`company` value with the wrong type) causes that single record to be
REJECTED -- it is left out of `profiles` and a reason is appended to
`errors[]`. A rejected record is never emitted as a plausible-looking
profile; degrading a required field into a "safe default" would let
unverifiable data pass as evidence. Individual malformed entries in the
optional `repos` list are dropped from `other_notable` rather than rejecting
the whole record, since that field is auxiliary best-effort ranking, not
required identity.

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
    """followers/public_repos must already be validated to int|None (see
    _validate_optional_int); this function never sees a non-numeric value."""
    followers = followers or 0
    public_repos = public_repos or 0
    if age_years is None:
        return "unknown-experimental"
    if age_years >= 3 and (followers >= 50 or public_repos >= 30 or bool(company)):
        return "established-practitioner"
    if age_years >= 1 and (followers >= 10 or public_repos >= 5):
        return "active-builder"
    return "unknown-experimental"


def _validate_optional_int(value, field, login):
    """Reject (not coerce) a present-but-wrong-typed numeric field. Booleans
    are rejected too, since `isinstance(True, int)` is True in Python but a
    bool is not a plausible follower/repo count."""
    if value is None:
        return True, None
    if isinstance(value, bool) or not isinstance(value, int):
        return False, f"provenance({login}): rejected -- malformed field {field}={value!r}, expected int or null"
    return True, value


def _validate_optional_str(value, field, login):
    if value is None:
        return True, None
    if not isinstance(value, str):
        return False, f"provenance({login}): rejected -- malformed field {field}={value!r}, expected string or null"
    return True, value


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


def _valid_star_count(value):
    return value is None or (isinstance(value, int) and not isinstance(value, bool))


def top_notable_repos(repos, n=3):
    """Auxiliary, best-effort ranking: a repo entry with a malformed `name`
    or `stargazers_count` is dropped rather than crashing the sort or being
    emitted with a value that violates the {"name": str, "stars": int}
    output schema."""
    scored = [
        r for r in repos
        if isinstance(r, dict)
        and not r.get("fork")
        and isinstance(r.get("name"), str)
        and _valid_star_count(r.get("stargazers_count"))
    ]
    scored.sort(key=lambda r: r.get("stargazers_count") or 0, reverse=True)
    return [
        {"name": r["name"], "stars": r.get("stargazers_count") or 0}
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
    if age < 0:
        return None, f"provenance({login}): rejected -- created_at={created_at!r} is after reference time --now (implausible future account creation)"

    ok, followers = _validate_optional_int(user.get("followers"), "followers", login)
    if not ok:
        return None, followers
    ok, public_repos = _validate_optional_int(user.get("public_repos"), "public_repos", login)
    if not ok:
        return None, public_repos
    ok, company = _validate_optional_str(user.get("company"), "company", login)
    if not ok:
        return None, company
    ok, name = _validate_optional_str(user.get("name"), "name", login)
    if not ok:
        return None, name
    repos = repos if isinstance(repos, list) else []

    return {
        "login": login,
        "name": name,
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
    if args.input == "-":
        raw = sys.stdin.read()
    else:
        with open(args.input, "r", encoding="utf-8") as f:
            raw = f.read()
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
