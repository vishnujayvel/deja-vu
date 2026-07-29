#!/usr/bin/env python3
"""deja-vu sweep — deterministic multi-lane prior-art sweep (design.md §5).

Stdlib only. No-throw discipline: every network call is wrapped; failures
are appended to an `errors[]` list in the output and never crash the sweep.

Lanes:
  github     - `gh search repos` if the gh CLI is available, else the
               unauthenticated GitHub REST search API.
  registry   - npm / PyPI / crates.io package registry search.
  grep       - grep.app regex-over-~1M-repos pattern search, with 429
               backoff/retry and graceful skip.
  scorecard  - OpenSSF Scorecard fetch, per github-lane candidate.

Output (single JSON object to stdout):
  {
    "query": str,
    "lanes_run": [str, ...],
    "candidates": [
      {
        "name": str, "url": str, "source_lane": str, "description": str|None,
        "stars": int|None, "last_push": str|None, "license": str|None,
        "scorecard": {...}|None, "registry_downloads": int|None
      }, ...
    ],
    "errors": [str, ...]
  }

No composite score is ever emitted (design.md §5: per-dimension only).
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_HEADERS = {"User-Agent": "deja-vu-sweep/1.0"}
ALL_LANES = ["github", "registry", "grep", "scorecard"]


def empty_candidate(**overrides):
    base = {
        "name": None,
        "url": None,
        "source_lane": None,
        "description": None,
        "stars": None,
        "last_push": None,
        "license": None,
        "scorecard": None,
        "registry_downloads": None,
    }
    base.update(overrides)
    return base


def fetch_json(url, headers=None, timeout=10):
    """Low-level fetch. Raises on failure — callers decide how to handle it."""
    req = urllib.request.Request(url, headers=headers or DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return json.loads(body.decode("utf-8"))


def safe_fetch_json(url, headers=None, timeout=10):
    """Never raises. Returns (data, error_str)."""
    try:
        return fetch_json(url, headers=headers, timeout=timeout), None
    except Exception as e:  # noqa: BLE001 - deliberate catch-all, no-throw contract
        return None, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------- github ---

def github_lane(query, language, limit, errors):
    candidates = []
    gh_path = shutil.which("gh")
    if gh_path:
        try:
            args = [
                gh_path, "search", "repos", query,
                "--limit", str(limit),
                "--json", "fullName,description,stargazersCount,url,pushedAt,license",
            ]
            if language:
                args += ["--language", language]
            proc = subprocess.run(args, capture_output=True, text=True, timeout=20)
            if proc.returncode == 0 and proc.stdout.strip():
                items = json.loads(proc.stdout)
                for item in items:
                    lic = item.get("license") or {}
                    candidates.append(empty_candidate(
                        name=item.get("fullName"),
                        url=item.get("url"),
                        source_lane="github",
                        description=item.get("description"),
                        stars=item.get("stargazersCount"),
                        last_push=item.get("pushedAt"),
                        license=lic.get("key") or lic.get("name"),
                    ))
                # `gh search repos` ANDs every term across name+description, so a
                # long natural-language query matches nothing and still exits 0.
                # Returning here on an empty list is how a hunt silently reports
                # "no prior art exists" when it really means "query too long".
                # Verified 2026-07-28: a 9-word query returned [], the same intent
                # in 2 words returned 4 real hits. Retry progressively shorter
                # before giving up, and fall through to the REST lane if still dry.
                if candidates:
                    return candidates
                terms = query.split()
                for n in (4, 3, 2):
                    if len(terms) <= n:
                        continue
                    short = " ".join(terms[:n])
                    try:
                        retry_args = [a if a != query else short for a in args]
                        rp = subprocess.run(retry_args, capture_output=True, text=True, timeout=20)
                        if rp.returncode == 0 and rp.stdout.strip():
                            for item in json.loads(rp.stdout):
                                lic = item.get("license") or {}
                                candidates.append(empty_candidate(
                                    name=item.get("fullName"),
                                    url=item.get("url"),
                                    source_lane=f"github(narrowed:{n}w)",
                                    description=item.get("description"),
                                    stars=item.get("stargazersCount"),
                                    last_push=item.get("pushedAt"),
                                    license=lic.get("key") or lic.get("name"),
                                ))
                        if candidates:
                            errors.append(
                                f"github: full query matched 0 repos; narrowed to '{short}' "
                                f"and found {len(candidates)}. Broaden or shorten --query."
                            )
                            return candidates
                    except Exception as e:  # noqa: BLE001
                        errors.append(f"github(narrow-{n}w): {type(e).__name__}: {e}")
                errors.append(
                    "github(gh-cli): 0 repos for the full query AND every narrowed "
                    "retry — falling through to the REST lane. Treat a still-empty "
                    "result as inconclusive, not as evidence that no prior art exists."
                )
            if proc.stderr:
                errors.append(f"github(gh-cli): {proc.stderr.strip()[:200]}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"github(gh-cli): {type(e).__name__}: {e}")

    # Fallback: unauthenticated GitHub REST search API.
    q = query
    if language:
        q += f" language:{language}"
    url = (
        "https://api.github.com/search/repositories?q="
        + urllib.parse.quote(q)
        + f"&sort=stars&order=desc&per_page={limit}"
    )
    data, err = safe_fetch_json(url, headers={**DEFAULT_HEADERS, "Accept": "application/vnd.github+json"})
    if err:
        errors.append(f"github(api): {err}")
        return candidates
    for item in (data or {}).get("items", [])[:limit]:
        lic = item.get("license") or {}
        candidates.append(empty_candidate(
            name=item.get("full_name"),
            url=item.get("html_url"),
            source_lane="github",
            description=item.get("description"),
            stars=item.get("stargazers_count"),
            last_push=item.get("pushed_at"),
            license=lic.get("spdx_id"),
        ))
    return candidates


# --------------------------------------------------------------- registry ---

def _npm_search(query, limit, errors):
    out = []
    url = f"https://registry.npmjs.org/-/v1/search?text={urllib.parse.quote(query)}&size={limit}"
    data, err = safe_fetch_json(url)
    if err:
        errors.append(f"registry(npm): {err}")
        return out
    for obj in (data or {}).get("objects", [])[:limit]:
        pkg = obj.get("package", {})
        links = pkg.get("links", {})
        out.append(empty_candidate(
            name=pkg.get("name"),
            url=links.get("npm") or links.get("repository"),
            source_lane="registry:npm",
            description=pkg.get("description"),
            last_push=pkg.get("date"),
            license=pkg.get("license"),
        ))
    return out


def _pypi_search(query, limit, errors):
    # PyPI retired its search API (XML-RPC search was disabled in 2018) and
    # has no supported JSON search endpoint. Best-effort degrade: treat the
    # query as a candidate exact package name and look it up directly. This
    # is a documented deviation from "search" for this one registry.
    out = []
    slug = query.strip().replace(" ", "-")
    if not slug:
        return out
    url = f"https://pypi.org/pypi/{urllib.parse.quote(slug)}/json"
    data, err = safe_fetch_json(url)
    if err:
        # A 404 (package doesn't exist under this name) is an expected,
        # non-error empty result, not a lane failure. Only genuine
        # transport failures are recorded.
        if "404" not in err:
            errors.append(f"registry(pypi): {err}")
        return out
    info = (data or {}).get("info", {})
    out.append(empty_candidate(
        name=info.get("name"),
        url=info.get("project_url") or info.get("package_url"),
        source_lane="registry:pypi",
        description=info.get("summary"),
        license=info.get("license") or None,
    ))
    return out[:limit]


def _crates_search(query, limit, errors):
    out = []
    url = f"https://crates.io/api/v1/crates?q={urllib.parse.quote(query)}&per_page={limit}"
    data, err = safe_fetch_json(url, headers={**DEFAULT_HEADERS})
    if err:
        errors.append(f"registry(crates): {err}")
        return out
    for c in (data or {}).get("crates", [])[:limit]:
        out.append(empty_candidate(
            name=c.get("name"),
            url=f"https://crates.io/crates/{c.get('name')}" if c.get("name") else None,
            source_lane="registry:crates",
            description=c.get("description"),
            last_push=c.get("updated_at"),
            registry_downloads=c.get("downloads"),
        ))
    return out


_LANGUAGE_TO_REGISTRY = {
    "javascript": "npm", "typescript": "npm", "node": "npm", "npm": "npm",
    "python": "pypi", "pypi": "pypi",
    "rust": "crates", "crates": "crates",
}


def registry_lane(query, language, limit, errors):
    which = _LANGUAGE_TO_REGISTRY.get((language or "").lower())
    candidates = []
    if which in (None, "npm"):
        candidates += _npm_search(query, limit, errors)
    if which in (None, "pypi"):
        candidates += _pypi_search(query, limit, errors)
    if which in (None, "crates"):
        candidates += _crates_search(query, limit, errors)
    return candidates


# ------------------------------------------------------------------ grep ---

def grep_lane(pattern, language, limit, errors, max_retries=3, base_delay=1, sleep_fn=time.sleep):
    if not pattern:
        return []
    url = f"https://grep.app/api/search?q={urllib.parse.quote(pattern)}"
    if language:
        url += f"&filter[lang][0]={urllib.parse.quote(language)}"

    delay = base_delay
    for attempt in range(max_retries + 1):
        try:
            data = fetch_json(url, headers=DEFAULT_HEADERS)
            hits = (((data or {}).get("hits") or {}).get("hits")) or []
            seen = set()
            candidates = []
            for h in hits:
                repo = (((h.get("repo") or {}).get("raw")) or "").strip()
                if not repo or repo in seen:
                    continue
                seen.add(repo)
                path = ((h.get("path") or {}).get("raw")) or ""
                candidates.append(empty_candidate(
                    name=repo,
                    url=f"https://github.com/{repo}",
                    source_lane="grep",
                    description=f"pattern match in {path}" if path else "pattern match",
                ))
                if len(candidates) >= limit:
                    break
            return candidates
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                sleep_fn(delay)
                delay *= 2
                continue
            if e.code == 429:
                errors.append("grep: rate limited, skipped after retries")
            else:
                errors.append(f"grep: HTTPError {e.code}")
            return []
        except Exception as e:  # noqa: BLE001
            errors.append(f"grep: {type(e).__name__}: {e}")
            return []
    return []


# ------------------------------------------------------------- scorecard ---

def scorecard_lane(candidates, errors):
    """Enriches github-sourced candidates in place with an OpenSSF Scorecard."""
    for c in candidates:
        if c.get("source_lane") != "github" or not c.get("name"):
            continue
        url = f"https://api.securityscorecards.dev/projects/github.com/{c['name']}"
        data, err = safe_fetch_json(url)
        if err:
            # Not every repo has been scored; a 404 is expected, not an error.
            if "404" not in err:
                errors.append(f"scorecard({c['name']}): {err}")
            c["scorecard"] = None
            continue
        c["scorecard"] = {
            "score": (data or {}).get("score"),
            "date": (data or {}).get("date"),
        }
    return candidates


# --------------------------------------------------------------- driver ---

def run_sweep(query, pattern, language, limit, lanes, no_scorecard):
    errors = []
    requested = [lane.strip() for lane in lanes.split(",") if lane.strip()]
    unknown = [lane for lane in requested if lane not in ALL_LANES]
    for lane in unknown:
        errors.append(f"unknown lane requested, ignored: {lane}")
    requested = [lane for lane in requested if lane in ALL_LANES]

    candidates = []
    lanes_run = []

    if "github" in requested:
        candidates += github_lane(query, language, limit, errors)
        lanes_run.append("github")

    if "registry" in requested:
        candidates += registry_lane(query, language, limit, errors)
        lanes_run.append("registry")

    if "grep" in requested:
        effective_pattern = pattern or query
        candidates += grep_lane(effective_pattern, language, limit, errors)
        lanes_run.append("grep")

    if "scorecard" in requested and not no_scorecard:
        scorecard_lane(candidates, errors)
        lanes_run.append("scorecard")

    return {
        "query": query,
        "lanes_run": lanes_run,
        "candidates": candidates,
        "errors": errors,
    }


def build_arg_parser():
    p = argparse.ArgumentParser(description="deja-vu deterministic multi-lane prior-art sweep")
    p.add_argument("--query", required=True, help="problem/candidate search string")
    p.add_argument("--pattern", default=None, help="regex/pattern for the grep.app lane (defaults to --query)")
    p.add_argument("--language", default=None, help="language filter, also selects registry (python/javascript/rust)")
    p.add_argument("--limit", type=int, default=10, help="max candidates per lane")
    p.add_argument("--lanes", default=",".join(ALL_LANES), help="comma-separated lane list")
    p.add_argument("--no-scorecard", action="store_true", help="disable the OpenSSF Scorecard enrichment lane")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    result = run_sweep(
        query=args.query,
        pattern=args.pattern,
        language=args.language,
        limit=args.limit,
        lanes=args.lanes,
        no_scorecard=args.no_scorecard,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
