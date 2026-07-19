#!/usr/bin/env python3
"""deja-vu provenance — stage 6b judge (design.md §2.6b).

Stdlib only. No-throw discipline: every network call is wrapped; failures
are appended to an `errors[]` list and never crash the run. Missing data
never hard-fails a profile — it degrades to the "unknown-experimental"
signal instead.

Signal rules (tenure, footprint, org backing):
  established-practitioner - account_age_years >= 3 AND
                              (followers >= 50 OR public_repos >= 30 OR company set)
  active-builder           - account_age_years >= 1 AND
                              (followers >= 10 OR public_repos >= 5)
  unknown-experimental     - everything else, including any profile deja-vu
                              could not fetch at all.

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
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DEFAULT_HEADERS = {"User-Agent": "deja-vu-provenance/1.0", "Accept": "application/vnd.github+json"}


def fetch_json(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body.decode("utf-8"))


def safe_fetch_json(url, headers=None, timeout=10):
    try:
        return fetch_json(url, headers=headers, timeout=timeout), None
    except Exception as e:  # noqa: BLE001 - deliberate catch-all, no-throw contract
        return None, f"{type(e).__name__}: {e}"


def _gh_cli_user(login, errors):
    gh_path = shutil.which("gh")
    if not gh_path:
        return None
    try:
        proc = subprocess.run(
            [gh_path, "api", f"users/{login}"],
            capture_output=True, text=True, timeout=20,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout)
        if proc.stderr:
            errors.append(f"provenance(gh-cli {login}): {proc.stderr.strip()[:200]}")
        return None
    except Exception as e:  # noqa: BLE001
        errors.append(f"provenance(gh-cli {login}): {type(e).__name__}: {e}")
        return None


def _gh_cli_repos(login, errors):
    gh_path = shutil.which("gh")
    if not gh_path:
        return None
    try:
        proc = subprocess.run(
            [gh_path, "api", f"users/{login}/repos?per_page=100&sort=pushed"],
            capture_output=True, text=True, timeout=20,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout)
        return None
    except Exception:  # noqa: BLE001
        return None


def fetch_user(login, errors):
    data = _gh_cli_user(login, errors)
    if data is not None:
        return data
    url = f"https://api.github.com/users/{urllib.parse.quote(login)}"
    data, err = safe_fetch_json(url)
    if err:
        errors.append(f"provenance(api {login}): {err}")
        return None
    return data


def fetch_repos(login, errors):
    data = _gh_cli_repos(login, errors)
    if data is not None:
        return data
    url = f"https://api.github.com/users/{urllib.parse.quote(login)}/repos?per_page=100&sort=pushed"
    data, err = safe_fetch_json(url)
    if err:
        # Non-fatal: other_notable simply comes back empty.
        errors.append(f"provenance(repos {login}): {err}")
        return []
    return data or []


def account_age_years(created_at, now=None):
    if not created_at:
        return None
    try:
        created = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    now = now or datetime.now(timezone.utc)
    return round((now - created).days / 365.25, 2)


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


def top_notable_repos(repos, n=3):
    scored = [r for r in repos if isinstance(r, dict) and not r.get("fork")]
    scored.sort(key=lambda r: r.get("stargazers_count") or 0, reverse=True)
    return [
        {"name": r.get("name"), "stars": r.get("stargazers_count") or 0}
        for r in scored[:n]
    ]


def build_profile(login, errors, now=None):
    user = fetch_user(login, errors)
    if user is None:
        return {
            "login": login,
            "name": None,
            "company": None,
            "created_at": None,
            "followers": None,
            "public_repos": None,
            "account_age_years": None,
            "other_notable": [],
            "signal": "unknown-experimental",
        }

    created_at = user.get("created_at")
    age = account_age_years(created_at, now=now)
    followers = user.get("followers")
    public_repos = user.get("public_repos")
    company = user.get("company")

    repos = fetch_repos(login, errors)
    other_notable = top_notable_repos(repos)

    return {
        "login": user.get("login", login),
        "name": user.get("name"),
        "company": company,
        "created_at": created_at,
        "followers": followers,
        "public_repos": public_repos,
        "account_age_years": age,
        "other_notable": other_notable,
        "signal": classify_signal(age, followers, public_repos, company),
    }


def run_provenance(owners):
    errors = []
    profiles = [build_profile(login, errors) for login in owners]
    return {"profiles": profiles, "errors": errors}


def build_arg_parser():
    p = argparse.ArgumentParser(description="deja-vu provenance judge (design.md §2.6b)")
    p.add_argument("--owner", action="append", default=[], required=True,
                   help="GitHub login to profile; repeatable")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    result = run_provenance(args.owner)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
