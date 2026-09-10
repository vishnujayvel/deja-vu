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
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_HEADERS = {"User-Agent": "deja-vu-sweep/1.0"}
ALL_LANES = ["github", "registry", "grep", "scorecard"]

# A remote JSON response is untrusted data: it may not have the dict shape
# every lane assumes (e.g. a top-level array, or list elements that are
# strings/numbers instead of objects). These helpers narrow any such shape
# down to something `.get()` can be called on safely, so a hostile or
# malformed payload degrades to an empty result instead of an AttributeError
# that would crash the sweep (contradicts the module's no-throw discipline).
def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _dict_items(seq):
    if not isinstance(seq, list):
        return []
    return [item for item in seq if isinstance(item, dict)]


# GitHub owner/repo names that are safe to interpolate into a request path.
# Rejects anything that isn't exactly two "owner" and "repo" segments made of
# the charset GitHub actually allows, and specifically rejects a segment that
# is "." or ".." -- the shape a path-traversal payload needs to rewrite the
# request path (see scorecard_lane).
_GITHUB_NAME_SEGMENT_RE = re.compile(r"^(?!\.{1,2}$)[A-Za-z0-9._-]+$")


def _is_safe_github_name(name):
    if not isinstance(name, str):
        return False
    parts = name.split("/")
    return len(parts) == 2 and all(_GITHUB_NAME_SEGMENT_RE.match(p) for p in parts)


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


def _bounded_exc(e):
    """Format an exception as "Type: message", capped at 200 chars.

    Exception text can embed arbitrary-length remote response content
    (e.g. HTTPError bodies, JSONDecodeError snippets); bound it like the
    gh-CLI stderr path so every error string stays boundedly sized.
    """
    return f"{type(e).__name__}: {str(e)[:200]}"


def safe_fetch_json(url, headers=None, timeout=10):
    """Never raises. Returns (data, error_str)."""
    try:
        return fetch_json(url, headers=headers, timeout=timeout), None
    except Exception as e:  # noqa: BLE001 - deliberate catch-all, no-throw contract
        return None, _bounded_exc(e)


# ---------------------------------------------------------------- github ---

def github_lane(query, language, limit, errors):
    candidates = []
    gh_path = shutil.which("gh")
    if gh_path:
        try:
            args = [
                gh_path, "search", "repos",
                "--limit", str(limit),
                "--json", "fullName,description,stargazersCount,url,pushedAt,license",
            ]
            if language:
                args += ["--language", language]
            # '--' ends flag parsing so a --query value that begins with '-'
            # (e.g. '--web', which would open a browser) is consumed as the
            # search term rather than as a gh CLI flag.
            args += ["--", query]
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
                        # Substitute the trailing positional (the query,
                        # placed last after '--'), not by value equality — an
                        # equality substitution would also clobber --language
                        # or --limit if either happened to equal the query
                        # text.
                        retry_args = list(args)
                        retry_args[-1] = short
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
                        errors.append(f"github(narrow-{n}w): {_bounded_exc(e)}")
                errors.append(
                    "github(gh-cli): 0 repos for the full query AND every narrowed "
                    "retry — falling through to the REST lane. Treat a still-empty "
                    "result as inconclusive, not as evidence that no prior art exists."
                )
            if proc.stderr:
                errors.append(f"github(gh-cli): {proc.stderr.strip()[:200]}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"github(gh-cli): {_bounded_exc(e)}")

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
    for item in _dict_items(_as_dict(data).get("items"))[:limit]:
        lic = _as_dict(item.get("license"))
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
    for obj in _dict_items(_as_dict(data).get("objects"))[:limit]:
        pkg = _as_dict(obj.get("package"))
        links = _as_dict(pkg.get("links"))
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
    info = _as_dict(_as_dict(data).get("info"))
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
    for c in _dict_items(_as_dict(data).get("crates"))[:limit]:
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
    # With no --language filter this lane fans out across npm/pypi/crates,
    # each individually capped at `limit` — enforce the documented per-lane
    # cap on the concatenated result too.
    return candidates[:limit]


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
                    url=f"https://github.com/{urllib.parse.quote(repo, safe='/')}",
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
            errors.append(f"grep: {_bounded_exc(e)}")
            return []
    return []


# ------------------------------------------------------------- scorecard ---

def scorecard_lane(candidates, errors):
    """Enriches github-sourced candidates in place with an OpenSSF Scorecard.

    A github-sourced candidate carries source_lane "github" (full-query hit)
    or "github(narrowed:<n>w)" (narrowed-retry hit, see github_lane) — both
    are per-candidate github repos and must be enriched.
    """
    for c in candidates:
        source_lane = c.get("source_lane") or ""
        if not source_lane.startswith("github") or not c.get("name"):
            continue
        # c['name'] is untrusted (from GitHub search / gh CLI output).
        # urllib.parse.quote() never encodes '.', so a hostile name
        # containing a '../' segment would pass through quoting unchanged
        # and rewrite the request path. Validate the shape is exactly
        # "owner/repo" in GitHub's allowed charset, with no '.' / '..'
        # segment, before it's ever interpolated into the URL.
        if not _is_safe_github_name(c["name"]):
            errors.append(f"scorecard: skipped unsafe candidate name {c['name'][:80]!r}")
            c["scorecard"] = None
            continue
        url = f"https://api.securityscorecards.dev/projects/github.com/{urllib.parse.quote(c['name'], safe='/')}"
        data, err = safe_fetch_json(url)
        if err:
            # Not every repo has been scored; a 404 is expected, not an error.
            if "404" not in err:
                errors.append(f"scorecard({c['name']}): {err}")
            c["scorecard"] = None
            continue
        data = _as_dict(data)
        c["scorecard"] = {
            "score": data.get("score"),
            "date": data.get("date"),
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


def _positive_int(value):
    """argparse type: reject zero/negative --limit values.

    A non-positive limit produces degenerate slice/URL semantics downstream
    (candidates[:limit] returning all-but-last, per_page=-1 in remote query
    strings, grep_lane's len(candidates) >= limit short-circuiting
    immediately) instead of enforcing a cap, so it is rejected here.
    """
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f"--limit must be a positive integer, got {value}")
    return ivalue


def build_arg_parser():
    p = argparse.ArgumentParser(description="deja-vu deterministic multi-lane prior-art sweep")
    p.add_argument("--query", required=True, help="problem/candidate search string")
    p.add_argument("--pattern", default=None, help="regex/pattern for the grep.app lane (defaults to --query)")
    p.add_argument("--language", default=None, help="language filter, also selects registry (python/javascript/rust)")
    p.add_argument("--limit", type=_positive_int, default=10, help="max candidates per lane (must be positive)")
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
