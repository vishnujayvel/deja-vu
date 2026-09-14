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
        "name": str, "url": str, "repo_url": str|None, "source_lane": str,
        "description": str|None, "stars": int|None, "last_push": str|None,
        "license": str|None, "scorecard": {...}|None,
        "registry_downloads": int|None, "paths": [str, ...]|None
      }, ...
    ],
    "errors": [str, ...]
  }

"url" is each candidate's own source-page receipt (the page a human would open:
a GitHub repo, an npm/PyPI/crates.io package page, ...). "repo_url" is set only
when a lane can additionally identify the canonical GitHub repository behind
that receipt (registries expose this in their own metadata; for the `github`
and `grep` lanes the receipt already *is* the repo, so `repo_url` stays None
there and merge falls back to `url`). merge_candidates() below matches on
`repo_url` when present, else `url` — never overwriting or discarding either.

candidates that share an exact canonical GitHub repository identity (see
merge_candidates() below) are collapsed into one record with
"source_lane": "merged", plus "canonical_repo", "lanes" (contributing lane
names), "observations" (every original per-lane candidate, unmodified), and
"conflicts" (fields the observations disagreed on).

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
        "repo_url": None,
        "source_lane": None,
        "description": None,
        "stars": None,
        "last_push": None,
        "license": None,
        "scorecard": None,
        "registry_downloads": None,
        "paths": None,
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

def _first_github_url(*value_groups):
    """First string among `value_groups` (each a value or iterable of values)
    that looks like it names a GitHub URL, or None.

    A cheap pre-filter only — `_canonical_github_identity` does the real
    parsing/validation once this reaches merge_candidates(); this just picks
    which registry-declared link is worth carrying as `repo_url`.
    """
    for group in value_groups:
        values = [group] if isinstance(group, str) or not hasattr(group, "__iter__") else group
        for value in values:
            if isinstance(value, str) and "github.com" in value.lower():
                return value
    return None


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
        repo_link = links.get("repository")
        out.append(empty_candidate(
            name=pkg.get("name"),
            # "url" is the receipt (the npm package page a human would open);
            # "repo_url" is the registry's own repository metadata, carried
            # separately so merge_candidates() can match on the canonical
            # GitHub identity without discarding the npm page.
            url=links.get("npm") or repo_link,
            repo_url=repo_link,
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
        # "url" is the receipt (the pypi.org package page); "repo_url" is
        # pulled from the project's own declared links, when it names one.
        url=info.get("project_url") or info.get("package_url"),
        repo_url=_first_github_url(_as_dict(info.get("project_urls")).values(), info.get("home_page")),
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
            # "url" is the receipt (the crates.io page); "repo_url" is the
            # crate's own declared repository field, when it names one.
            url=f"https://crates.io/crates/{c.get('name')}" if c.get("name") else None,
            repo_url=_first_github_url(c.get("repository")),
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
            # Collect every matched path per repo before capping — a repo can
            # have several hits, and the limit caps distinct *repos*, not
            # matches; capping mid-scan would silently drop later paths for
            # repos already accepted.
            repo_order = []
            paths_by_repo = {}
            for h in hits:
                repo = (((h.get("repo") or {}).get("raw")) or "").strip()
                if not repo:
                    continue
                if repo not in paths_by_repo:
                    repo_order.append(repo)
                    paths_by_repo[repo] = []
                path = ((h.get("path") or {}).get("raw")) or ""
                if path and path not in paths_by_repo[repo]:
                    paths_by_repo[repo].append(path)

            candidates = []
            for repo in repo_order[:limit]:
                paths = paths_by_repo[repo]
                if len(paths) > 1:
                    description = f"pattern match in {len(paths)} files: {', '.join(paths)}"
                elif paths:
                    description = f"pattern match in {paths[0]}"
                else:
                    description = "pattern match"
                candidates.append(empty_candidate(
                    name=repo,
                    url=f"https://github.com/{urllib.parse.quote(repo, safe='/')}",
                    source_lane="grep",
                    description=description,
                    paths=paths,
                ))
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
            errors.append(
                f"scorecard: skipped unsafe candidate name {repr(c['name'])[:80]}"
            )
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


# ------------------------------------------------------------------ merge ---

# Matches a `git+` prefix some registries (npm) put on repository URLs.
_GIT_PLUS_PREFIX_RE = re.compile(r"^git\+", re.IGNORECASE)
# Matches SSH-form GitHub remotes: git@ + github.com + :owner/repo(.git)
_SSH_GITHUB_RE = re.compile(r"^git@github\.com:(?P<path>.+)$", re.IGNORECASE)

# Fields tracked for cross-observation conflicts when merging. Excludes
# "source_lane" (each observation's lane is recorded separately) and
# "paths" (paths are unioned, not treated as a contradiction).
_CONFLICT_FIELDS = [k for k in empty_candidate().keys() if k not in ("source_lane", "paths")]


def _canonical_github_identity(url):
    """Return the normalized "owner/repo" GitHub identity a URL points at,
    or None if `url` does not identify an exact GitHub repository.

    Handles the plain https form, a `git+https://...` registry-metadata
    prefix, an SSH remote (`git@` + `github.com:owner/repo.git`), and a trailing
    `.git` suffix. Case-insensitive (GitHub repo paths are). Reuses
    `_is_safe_github_name`'s charset/traversal rules so a hostile or
    malformed URL degrades to "no identity" rather than a false match.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    candidate = _GIT_PLUS_PREFIX_RE.sub("", url.strip())
    ssh_match = _SSH_GITHUB_RE.match(candidate)
    if ssh_match:
        candidate = "https://github.com/" + ssh_match.group("path")
    try:
        parsed = urllib.parse.urlsplit(candidate)
    except ValueError:
        return None
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "github.com":
        return None
    path = parsed.path.strip("/")
    if path.lower().endswith(".git"):
        path = path[: -len(".git")]
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if not _is_safe_github_name(f"{owner}/{repo}"):
        return None
    return f"{owner.lower()}/{repo.lower()}"


def _dedup_json_values(values):
    """Distinct non-None values from `values`, first-seen order.

    De-dups by JSON-canonical form so unhashable values (e.g. the
    `scorecard` dict) can still be compared for equality.
    """
    seen = set()
    out = []
    for value in values:
        if value is None:
            continue
        key = json.dumps(value, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _merge_group(identity, members):
    """Collapse `members` (2+ candidates sharing `identity`) into one record
    that keeps every contributing observation and surfaces field conflicts.
    """
    merged = empty_candidate(source_lane="merged", canonical_repo=identity)

    for field in ("name", "url", "repo_url", "description", "stars", "last_push",
                  "license", "scorecard", "registry_downloads"):
        for member in members:
            if member.get(field) is not None:
                merged[field] = member[field]
                break

    lanes = []
    paths = []
    for member in members:
        lane = member.get("source_lane")
        if lane and lane not in lanes:
            lanes.append(lane)
        for path in member.get("paths") or []:
            if path not in paths:
                paths.append(path)

    merged["lanes"] = lanes
    merged["paths"] = paths or None
    merged["observations"] = members
    merged["conflicts"] = {
        field: values
        for field in _CONFLICT_FIELDS
        for values in [_dedup_json_values(member.get(field) for member in members)]
        if len(values) > 1
    }
    return merged


def _merge_identity(candidate):
    """The canonical GitHub identity to merge `candidate` on: its own
    registry-declared `repo_url` when the lane found one, else its `url`
    (already the repo itself for the `github`/`grep` lanes)."""
    return _canonical_github_identity(candidate.get("repo_url") or candidate.get("url"))


def merge_candidates(candidates):
    """Deterministic post-lane merge (design.md §5, deja-vu-v2.10).

    Collapses candidates that share an exact canonical GitHub repository
    identity — regardless of which lane(s) found them — into one record that
    retains every contributing observation (lane, original url/name,
    metadata) and surfaces conflicting field values. Everything else —
    same-named packages, services, standards, research, patterns, or manual
    candidates without an established shared repository identity — is left
    untouched and distinct, even when names collide.

    Does not add a graph store, controller, or persistent runtime: this is a
    single pass over the existing in-memory candidate list, called once after
    all lanes (including scorecard enrichment) have returned.
    """
    groups = {}
    group_order = []
    for candidate in candidates:
        identity = _merge_identity(candidate)
        if identity is None:
            continue
        if identity not in groups:
            groups[identity] = []
            group_order.append(identity)
        groups[identity].append(candidate)

    merged_by_identity = {
        identity: _merge_group(identity, groups[identity])
        for identity in group_order
        if len(groups[identity]) >= 2
    }

    result = []
    emitted = set()
    for candidate in candidates:
        identity = _merge_identity(candidate)
        if identity is None or identity not in merged_by_identity:
            result.append(candidate)
            continue
        if identity in emitted:
            continue
        emitted.add(identity)
        result.append(merged_by_identity[identity])
    return result


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
        "candidates": merge_candidates(candidates),
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
