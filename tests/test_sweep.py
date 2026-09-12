import json
import urllib.error
import urllib.request

import pytest

import sweep
from conftest import FakeHTTPResponse


# --------------------------------------------------------------- github ---

def test_github_lane_happy_path_api_fallback(monkeypatch, load_fixture_bytes, no_gh_cli):
    def fake_urlopen(req, timeout=10):
        assert "api.github.com/search/repositories" in req.full_url
        return FakeHTTPResponse(load_fixture_bytes("github_search.json"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.github_lane("rate limiter", None, 10, errors)

    assert errors == []
    assert len(candidates) == 2
    first = candidates[0]
    assert first["name"] == "example/rate-limiter"
    assert first["source_lane"] == "github"
    assert first["stars"] == 420
    assert first["license"] == "MIT"
    assert first["last_push"] == "2026-06-01T12:00:00Z"
    # second item's license was null in the fixture
    assert candidates[1]["license"] is None


def test_github_lane_http_failure_appends_error_no_crash(monkeypatch, no_gh_cli):
    def fake_urlopen(req, timeout=10):
        raise urllib.error.URLError("network is down")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.github_lane("rate limiter", None, 10, errors)

    assert candidates == []
    assert len(errors) == 1
    assert "github(api)" in errors[0]


@pytest.mark.parametrize("payload", [
    [1, 2, 3],  # top-level array instead of a dict
    {"items": "not-a-list"},  # items isn't a list
    {"items": ["not-a-dict", 42, None]},  # list elements aren't dicts
    {"items": [{"license": "MIT"}]},  # license isn't a dict (string, not {key:...})
])
def test_github_lane_api_fallback_malformed_shape_does_not_crash(monkeypatch, no_gh_cli, payload):
    """Round-3 finding 1: a malformed/hostile REST response must degrade to
    an empty (or best-effort) result, never raise AttributeError."""
    def fake_urlopen(req, timeout=10):
        return FakeHTTPResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.github_lane("rate limiter", None, 10, errors)

    assert errors == []
    for c in candidates:
        assert c["license"] is None or isinstance(c["license"], str)


def test_github_lane_gh_cli_exception_is_bounded(monkeypatch):
    monkeypatch.setattr(sweep.shutil, "which", lambda name: "/usr/bin/gh")

    def fake_run(args, capture_output=True, text=True, timeout=20):
        raise RuntimeError("x" * 500)

    monkeypatch.setattr(sweep.subprocess, "run", fake_run)

    def fake_urlopen(req, timeout=10):
        raise urllib.error.URLError("network is down")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    sweep.github_lane("rate limiter", None, 10, errors)

    gh_cli_errors = [e for e in errors if e.startswith("github(gh-cli):")]
    assert len(gh_cli_errors) == 1
    assert gh_cli_errors[0] == f"github(gh-cli): RuntimeError: {'x' * 200}"
    assert len(gh_cli_errors[0]) < 250  # bounded, not the full 500-char message


def test_github_lane_query_starting_with_dash_is_not_parsed_as_flag(monkeypatch):
    """Round-3 finding 3: a --query value beginning with '-' must be treated
    as the search term, not consumed as a gh CLI flag (e.g. '--web' would
    open a browser)."""
    monkeypatch.setattr(sweep.shutil, "which", lambda name: "/usr/bin/gh")

    captured = {}

    def fake_run(args, capture_output=True, text=True, timeout=20):
        captured["args"] = args
        assert "--" in args, "flag-parsing must be terminated before the query"
        dash_idx = args.index("--")
        assert args[dash_idx + 1:] == ["--web"], "query must be the sole positional after '--'"

        class FakeProc:
            returncode = 0
            stdout = "[]"
            stderr = ""

        return FakeProc()

    monkeypatch.setattr(sweep.subprocess, "run", fake_run)

    def fake_urlopen(req, timeout=10):
        raise urllib.error.URLError("network is down")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    sweep.github_lane("--web", None, 10, errors)

    assert captured["args"][-1] == "--web"


def test_github_lane_narrow_retry_exception_is_bounded(monkeypatch):
    monkeypatch.setattr(sweep.shutil, "which", lambda name: "/usr/bin/gh")

    class FakeProc:
        def __init__(self, returncode, stdout, stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls = {"n": 0}

    def fake_run(args, capture_output=True, text=True, timeout=20):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeProc(0, "[]")  # full query -> 0 repos, triggers narrowing
        raise RuntimeError("y" * 500)  # every narrowed retry also fails

    monkeypatch.setattr(sweep.subprocess, "run", fake_run)

    def fake_urlopen(req, timeout=10):
        raise urllib.error.URLError("network is down")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    sweep.github_lane("a b c d e", None, 10, errors)  # 5 terms -> narrows at 4w, 3w, 2w

    narrow_errors = [e for e in errors if e.startswith("github(narrow-")]
    assert len(narrow_errors) == 3
    for e in narrow_errors:
        assert e.endswith(f"RuntimeError: {'y' * 200}")
        assert len(e) < 250


# -------------------------------------------------------------- registry ---

def test_registry_lane_npm_happy_path(monkeypatch, load_fixture_bytes):
    def fake_urlopen(req, timeout=10):
        assert "registry.npmjs.org" in req.full_url
        return FakeHTTPResponse(load_fixture_bytes("npm_search.json"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.registry_lane("rate limiter", "javascript", 10, errors)

    assert errors == []
    assert len(candidates) == 1
    assert candidates[0]["source_lane"] == "registry:npm"
    assert candidates[0]["name"] == "example-rate-limiter"
    assert candidates[0]["license"] == "MIT"
    # "url" stays the npm package-page receipt; "repo_url" carries the
    # registry's own repository link for merge_candidates() to match on.
    assert candidates[0]["url"] == "https://www.npmjs.com/package/example-rate-limiter"
    assert candidates[0]["repo_url"] == "https://github.com/example/example-rate-limiter"


def test_registry_lane_pypi_happy_path(monkeypatch, load_fixture_bytes):
    def fake_urlopen(req, timeout=10):
        assert "pypi.org/pypi" in req.full_url
        return FakeHTTPResponse(load_fixture_bytes("pypi_package.json"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.registry_lane("example-rate-limiter", "python", 10, errors)

    assert errors == []
    assert len(candidates) == 1
    assert candidates[0]["source_lane"] == "registry:pypi"
    assert candidates[0]["description"] == "A simple rate limiter"


def test_registry_lane_pypi_404_is_not_an_error(monkeypatch):
    def fake_urlopen(req, timeout=10):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.registry_lane("totally-nonexistent-package", "python", 10, errors)

    assert candidates == []
    assert errors == []  # a 404 lookup miss is an expected empty result, not a failure


def test_registry_lane_crates_happy_path(monkeypatch, load_fixture_bytes):
    def fake_urlopen(req, timeout=10):
        assert "crates.io/api/v1/crates" in req.full_url
        return FakeHTTPResponse(load_fixture_bytes("crates_search.json"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.registry_lane("rate limiter", "rust", 10, errors)

    assert errors == []
    assert len(candidates) == 1
    assert candidates[0]["source_lane"] == "registry:crates"
    assert candidates[0]["registry_downloads"] == 15000


def test_registry_lane_no_language_hits_all_three(monkeypatch, load_fixture_bytes):
    fixtures_by_host = {
        "registry.npmjs.org": "npm_search.json",
        "pypi.org": "pypi_package.json",
        "crates.io": "crates_search.json",
    }

    def fake_urlopen(req, timeout=10):
        for host, fixture in fixtures_by_host.items():
            if host in req.full_url:
                return FakeHTTPResponse(load_fixture_bytes(fixture))
        raise AssertionError(f"unexpected URL {req.full_url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.registry_lane("rate limiter", None, 10, errors)

    assert errors == []
    lanes_hit = {c["source_lane"] for c in candidates}
    assert lanes_hit == {"registry:npm", "registry:pypi", "registry:crates"}


@pytest.mark.parametrize("payload", [
    ["a", "b"],  # top-level array instead of a dict
    {"objects": "not-a-list"},
    {"objects": ["not-a-dict"]},
])
def test_registry_lane_npm_malformed_shape_does_not_crash(monkeypatch, payload):
    """Round-3 finding 1: malformed npm search response must not raise."""
    def fake_urlopen(req, timeout=10):
        if "registry.npmjs.org" in req.full_url:
            return FakeHTTPResponse(json.dumps(payload).encode("utf-8"))
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.registry_lane("rate limiter", "javascript", 10, errors)

    assert candidates == []
    assert errors == []


def test_registry_lane_npm_non_dict_package_field_degrades_without_crash(monkeypatch):
    """Round-3 finding 1: a dict list-element whose nested 'package' field
    isn't itself a dict must degrade to a best-effort candidate, not raise."""
    payload = {"objects": [{"package": "not-a-dict"}]}

    def fake_urlopen(req, timeout=10):
        if "registry.npmjs.org" in req.full_url:
            return FakeHTTPResponse(json.dumps(payload).encode("utf-8"))
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.registry_lane("rate limiter", "javascript", 10, errors)

    assert errors == []
    assert len(candidates) == 1
    assert candidates[0]["name"] is None


@pytest.mark.parametrize("payload", [
    ["a", "b"],
    {"info": "not-a-dict"},
])
def test_registry_lane_pypi_malformed_shape_does_not_crash(monkeypatch, payload):
    """Round-3 finding 1: malformed PyPI response must not raise."""
    def fake_urlopen(req, timeout=10):
        return FakeHTTPResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.registry_lane("example-pkg", "python", 10, errors)

    assert errors == []
    assert len(candidates) == 1
    assert candidates[0]["name"] is None


@pytest.mark.parametrize("payload", [
    ["a", "b"],
    {"crates": "not-a-list"},
    {"crates": ["not-a-dict"]},
])
def test_registry_lane_crates_malformed_shape_does_not_crash(monkeypatch, payload):
    """Round-3 finding 1: malformed crates.io response must not raise."""
    def fake_urlopen(req, timeout=10):
        return FakeHTTPResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.registry_lane("rate limiter", "rust", 10, errors)

    assert candidates == []
    assert errors == []


def test_registry_lane_pypi_populates_repo_url_from_project_urls(monkeypatch):
    payload = {
        "info": {
            "name": "example-rate-limiter",
            "summary": "A simple rate limiter",
            "project_url": "https://pypi.org/project/example-rate-limiter/",
            "project_urls": {
                "Homepage": "https://example.com",
                "Source": "https://github.com/example/example-rate-limiter",
            },
        }
    }

    def fake_urlopen(req, timeout=10):
        return FakeHTTPResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.registry_lane("example-rate-limiter", "python", 10, errors)

    assert errors == []
    assert len(candidates) == 1
    # "url" stays the pypi.org package-page receipt.
    assert candidates[0]["url"] == "https://pypi.org/project/example-rate-limiter/"
    assert candidates[0]["repo_url"] == "https://github.com/example/example-rate-limiter"


def test_registry_lane_crates_populates_repo_url_from_repository_field(monkeypatch):
    payload = {"crates": [{
        "name": "example-ratelimit",
        "description": "rate limiting crate",
        "repository": "https://github.com/example/example-ratelimit",
    }]}

    def fake_urlopen(req, timeout=10):
        return FakeHTTPResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.registry_lane("rate limiter", "rust", 10, errors)

    assert errors == []
    assert len(candidates) == 1
    # "url" stays the crates.io package-page receipt.
    assert candidates[0]["url"] == "https://crates.io/crates/example-ratelimit"
    assert candidates[0]["repo_url"] == "https://github.com/example/example-ratelimit"


def test_registry_lane_npm_failure_appends_error(monkeypatch):
    def fake_urlopen(req, timeout=10):
        if "registry.npmjs.org" in req.full_url:
            raise urllib.error.URLError("timed out")
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    sweep.registry_lane("rate limiter", "javascript", 10, errors)

    assert any("registry(npm)" in e for e in errors)


# ------------------------------------------------------------------ grep ---

def test_grep_lane_happy_path_dedups_repo_hits(monkeypatch, load_fixture_bytes):
    def fake_urlopen(req, timeout=10):
        assert "grep.app/api/search" in req.full_url
        return FakeHTTPResponse(load_fixture_bytes("grep_search.json"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.grep_lane("token bucket", None, 10, errors)

    assert errors == []
    # 3 hits fixture, 2 of them share a repo -> deduped to 2 candidates, but
    # both matched paths for the shared repo must be preserved, not dropped.
    assert len(candidates) == 2
    by_name = {c["name"]: c for c in candidates}
    assert set(by_name) == {"example/rate-limiter", "another/project"}
    assert all(c["source_lane"] == "grep" for c in candidates)
    assert by_name["example/rate-limiter"]["paths"] == [
        "src/limiter.py", "tests/test_limiter.py",
    ]
    assert by_name["another/project"]["paths"] == ["lib/index.js"]


def test_grep_lane_429_then_success_retries(monkeypatch, load_fixture_bytes):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=10):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)
        return FakeHTTPResponse(load_fixture_bytes("grep_search.json"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    sleeps = []
    errors = []
    candidates = sweep.grep_lane(
        "token bucket", None, 10, errors, sleep_fn=lambda s: sleeps.append(s)
    )

    assert errors == []
    assert calls["n"] == 3
    assert sleeps == [1, 2]  # exponential backoff before the 3rd, successful attempt
    assert len(candidates) == 2


def test_grep_lane_429_exhausted_graceful_skip(monkeypatch):
    def fake_urlopen(req, timeout=10):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.grep_lane(
        "token bucket", None, 10, errors, max_retries=3, sleep_fn=lambda s: None
    )

    assert candidates == []
    assert len(errors) == 1
    assert "rate limited" in errors[0]


def test_grep_lane_generic_exception_is_bounded(monkeypatch):
    def fake_urlopen(req, timeout=10):
        raise ValueError("z" * 500)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    candidates = sweep.grep_lane("token bucket", None, 10, errors, sleep_fn=lambda s: None)

    assert candidates == []
    assert len(errors) == 1
    assert errors[0] == f"grep: ValueError: {'z' * 200}"
    assert len(errors[0]) < 250  # bounded, not the full 500-char message


def test_grep_lane_no_pattern_returns_empty_without_network(monkeypatch):
    def fake_urlopen(req, timeout=10):
        raise AssertionError("should never be called when pattern is empty")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    assert sweep.grep_lane(None, None, 10, errors) == []
    assert sweep.grep_lane("", None, 10, errors) == []
    assert errors == []


# ------------------------------------------------------------- scorecard ---

def test_scorecard_lane_enriches_github_candidates(monkeypatch, load_fixture_bytes):
    def fake_urlopen(req, timeout=10):
        assert "api.securityscorecards.dev" in req.full_url
        return FakeHTTPResponse(load_fixture_bytes("scorecard.json"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    candidates = [sweep.empty_candidate(name="example/rate-limiter", source_lane="github")]
    errors = []
    sweep.scorecard_lane(candidates, errors)

    assert errors == []
    assert candidates[0]["scorecard"] == {"score": 7.8, "date": "2026-06-15"}


def test_scorecard_lane_404_is_not_an_error(monkeypatch):
    def fake_urlopen(req, timeout=10):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    candidates = [sweep.empty_candidate(name="example/unscored", source_lane="github")]
    errors = []
    sweep.scorecard_lane(candidates, errors)

    assert errors == []
    assert candidates[0]["scorecard"] is None


def test_scorecard_lane_malformed_shape_does_not_crash(monkeypatch):
    """Round-3 finding 1: a top-level array (or non-dict score payload) from
    the scorecard API must not raise AttributeError."""
    def fake_urlopen(req, timeout=10):
        return FakeHTTPResponse(json.dumps(["not", "a", "dict"]).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    candidates = [sweep.empty_candidate(name="example/rate-limiter", source_lane="github")]
    errors = []
    sweep.scorecard_lane(candidates, errors)

    assert errors == []
    assert candidates[0]["scorecard"] == {"score": None, "date": None}


@pytest.mark.parametrize("hostile_name", [
    "x/../../projects/github.com/other/repo",
    "../..",
    "owner/..",
    "owner/repo?x=1",
    "owner/repo with spaces",
    "owner/repo#frag",
])
def test_scorecard_lane_rejects_path_traversal_names(monkeypatch, hostile_name):
    """Round-3 finding 2: quote(name, safe='/') never encodes '.', so a
    hostile name containing '../' must be rejected before it is ever
    interpolated into the scorecard request URL — not merely quoted."""
    def fake_urlopen(req, timeout=10):
        raise AssertionError(f"must never fetch for unsafe name, tried {req.full_url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    candidates = [sweep.empty_candidate(name=hostile_name, source_lane="github")]
    errors = []
    sweep.scorecard_lane(candidates, errors)

    assert candidates[0]["scorecard"] is None
    assert any("unsafe" in e for e in errors)


def test_scorecard_lane_rejects_non_string_name_without_raising(monkeypatch):
    """A truthy non-string name (e.g. an int) is unsafe by `_is_safe_github_name`,
    but the error message must not slice it as if it were a string — that raised
    TypeError and escaped the no-throw sweep."""
    def fake_urlopen(req, timeout=10):
        raise AssertionError(f"must never fetch for unsafe name, tried {req.full_url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    candidates = [sweep.empty_candidate(name=42, source_lane="github")]
    errors = []
    sweep.scorecard_lane(candidates, errors)

    assert candidates[0]["scorecard"] is None
    assert any("unsafe" in e for e in errors)


def test_scorecard_lane_enriches_narrowed_github_candidates(monkeypatch, load_fixture_bytes):
    def fake_urlopen(req, timeout=10):
        assert "api.securityscorecards.dev" in req.full_url
        return FakeHTTPResponse(load_fixture_bytes("scorecard.json"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    candidates = [sweep.empty_candidate(name="example/rate-limiter", source_lane="github(narrowed:3w)")]
    errors = []
    sweep.scorecard_lane(candidates, errors)

    assert errors == []
    assert candidates[0]["scorecard"] == {"score": 7.8, "date": "2026-06-15"}


def test_scorecard_lane_skips_non_github_candidates(monkeypatch):
    def fake_urlopen(req, timeout=10):
        raise AssertionError("scorecard must only be fetched for github-lane candidates")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    candidates = [sweep.empty_candidate(name="example/pkg", source_lane="registry:npm")]
    errors = []
    sweep.scorecard_lane(candidates, errors)

    assert candidates[0]["scorecard"] is None
    assert errors == []


# ------------------------------------------------------------------ merge ---

def test_first_github_url_finds_link_among_groups():
    project_urls = {"Homepage": "https://example.com", "Source": "https://github.com/example/pkg"}
    assert sweep._first_github_url(project_urls.values(), None) == "https://github.com/example/pkg"


def test_first_github_url_returns_none_when_nothing_matches():
    assert sweep._first_github_url([None, "https://example.com"], "not a url", None) is None


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/example/rate-limiter", "example/rate-limiter"),
    ("https://github.com/Example/Rate-Limiter", "example/rate-limiter"),  # case-insensitive
    ("https://github.com/example/rate-limiter.git", "example/rate-limiter"),  # .git suffix
    ("https://github.com/example/rate-limiter/", "example/rate-limiter"),  # trailing slash
    ("https://www.github.com/example/rate-limiter", "example/rate-limiter"),  # www host
    ("git+https://github.com/example/rate-limiter.git", "example/rate-limiter"),  # npm registry form
    ("git@" + "github.com:example/rate-limiter.git", "example/rate-limiter"),  # SSH remote
])
def test_canonical_github_identity_normalizes_equivalent_urls(url, expected):
    assert sweep._canonical_github_identity(url) == expected


@pytest.mark.parametrize("url", [
    None,
    "",
    "https://gitlab.com/example/rate-limiter",  # not GitHub
    "https://github.com/example",  # no repo segment
    "https://github.com/../evil",  # path-traversal segment
    "not a url at all",
    "https://registry.npmjs.org/rate-limiter",  # registry page, not a repo URL
])
def test_canonical_github_identity_returns_none_for_non_repo_urls(url):
    assert sweep._canonical_github_identity(url) is None


def test_merge_candidates_merges_github_and_grep_hits_for_same_repo():
    github_hit = sweep.empty_candidate(
        name="example/rate-limiter", url="https://github.com/example/rate-limiter",
        source_lane="github", description="A rate limiter", stars=420, license="MIT",
    )
    grep_hit = sweep.empty_candidate(
        name="example/rate-limiter", url="https://github.com/example/rate-limiter",
        source_lane="grep", description="pattern match in src/limiter.py",
        paths=["src/limiter.py"],
    )

    merged = sweep.merge_candidates([github_hit, grep_hit])

    assert len(merged) == 1
    record = merged[0]
    assert record["source_lane"] == "merged"
    assert record["canonical_repo"] == "example/rate-limiter"
    assert record["lanes"] == ["github", "grep"]
    assert record["observations"] == [github_hit, grep_hit]
    assert record["stars"] == 420  # only github supplied a value
    assert record["paths"] == ["src/limiter.py"]


def test_merge_candidates_merges_registry_result_with_matching_repository_url(monkeypatch, load_fixture_bytes):
    """End-to-end: run the real npm fixture through `_npm_search` itself
    (not a hand-constructed URL no live lane can produce) and confirm
    `merge_candidates()` still matches it against a github-lane hit on the
    same repo, while the npm candidate's own package-page receipt (`url`)
    survives untouched inside `observations`."""
    def fake_urlopen(req, timeout=10):
        assert "registry.npmjs.org" in req.full_url
        return FakeHTTPResponse(load_fixture_bytes("npm_search.json"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    npm_hits = sweep._npm_search("rate limiter", 10, errors)
    assert errors == []
    assert len(npm_hits) == 1
    npm_hit = npm_hits[0]
    assert npm_hit["url"] == "https://www.npmjs.com/package/example-rate-limiter"
    assert npm_hit["repo_url"] == "https://github.com/example/example-rate-limiter"

    github_hit = sweep.empty_candidate(
        name="example/example-rate-limiter",
        url="https://github.com/example/example-rate-limiter",
        source_lane="github", stars=420,
    )

    merged = sweep.merge_candidates([github_hit, npm_hit])

    assert len(merged) == 1
    record = merged[0]
    assert record["canonical_repo"] == "example/example-rate-limiter"
    assert record["lanes"] == ["github", "registry:npm"]
    assert record["observations"] == [github_hit, npm_hit]
    # the npm package-page receipt must not be discarded or overwritten
    assert record["observations"][1]["url"] == "https://www.npmjs.com/package/example-rate-limiter"


def test_merge_candidates_preserves_multiple_grep_paths_in_merged_group():
    github_hit = sweep.empty_candidate(
        name="example/rate-limiter", url="https://github.com/example/rate-limiter",
        source_lane="github",
    )
    grep_hit = sweep.empty_candidate(
        name="example/rate-limiter", url="https://github.com/example/rate-limiter",
        source_lane="grep", paths=["src/limiter.py", "tests/test_limiter.py"],
    )

    merged = sweep.merge_candidates([github_hit, grep_hit])

    assert merged[0]["paths"] == ["src/limiter.py", "tests/test_limiter.py"]


def test_merge_candidates_surfaces_conflicting_metadata():
    github_hit = sweep.empty_candidate(
        name="example/rate-limiter", url="https://github.com/example/rate-limiter",
        source_lane="github", description="A token-bucket rate limiter", license="MIT",
        last_push="2026-06-01T00:00:00Z",
    )
    registry_hit = sweep.empty_candidate(
        name="rate-limiter", url="https://github.com/example/rate-limiter",
        source_lane="registry:npm", description="Simple rate limiting middleware",
        license="Apache-2.0", last_push="2026-05-01T00:00:00Z",
    )

    merged = sweep.merge_candidates([github_hit, registry_hit])

    conflicts = merged[0]["conflicts"]
    assert conflicts["name"] == ["example/rate-limiter", "rate-limiter"]
    assert conflicts["description"] == [
        "A token-bucket rate limiter", "Simple rate limiting middleware",
    ]
    assert conflicts["license"] == ["MIT", "Apache-2.0"]
    assert conflicts["last_push"] == ["2026-06-01T00:00:00Z", "2026-05-01T00:00:00Z"]
    # a field neither observation actually disagreed on must not appear
    assert "url" not in conflicts


def test_merge_candidates_keeps_same_name_non_repo_candidates_distinct():
    """Two candidates that merely share a name — a manual/standards/registry
    entry with no established GitHub repository identity — must never be
    merged just because their names collide."""
    npm_package = sweep.empty_candidate(
        name="widget", url="https://www.npmjs.com/package/widget", source_lane="registry:npm",
    )
    unrelated_repo = sweep.empty_candidate(
        name="widget", url="https://github.com/someoneelse/widget", source_lane="github",
    )
    manual_pattern = sweep.empty_candidate(
        name="widget", url=None, source_lane="manual:pattern",
        description="A design pattern named 'widget' with no repository",
    )

    merged = sweep.merge_candidates([npm_package, unrelated_repo, manual_pattern])

    assert merged == [npm_package, unrelated_repo, manual_pattern]
    assert all(c["source_lane"] != "merged" for c in merged)


def test_merge_candidates_leaves_single_github_hit_unwrapped():
    """A github repo hit by only one lane is not a duplicate and must pass
    through in its original shape (no observations/conflicts wrapper)."""
    only_hit = sweep.empty_candidate(
        name="example/rate-limiter", url="https://github.com/example/rate-limiter",
        source_lane="github", stars=420,
    )

    merged = sweep.merge_candidates([only_hit])

    assert merged == [only_hit]


def test_run_sweep_merges_exact_github_duplicates_across_lanes(monkeypatch):
    monkeypatch.setattr(sweep, "github_lane", lambda *a, **kw: [
        sweep.empty_candidate(
            name="example/rate-limiter", url="https://github.com/example/rate-limiter",
            source_lane="github", stars=420,
        )
    ])
    monkeypatch.setattr(sweep, "registry_lane", lambda *a, **kw: [])
    monkeypatch.setattr(sweep, "grep_lane", lambda *a, **kw: [
        sweep.empty_candidate(
            name="example/rate-limiter", url="https://github.com/example/rate-limiter",
            source_lane="grep", paths=["src/limiter.py"],
        )
    ])

    result = sweep.run_sweep(
        query="rate limiter", pattern=None, language=None, limit=5,
        lanes="github,registry,grep", no_scorecard=True,
    )

    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["canonical_repo"] == "example/rate-limiter"
    assert result["candidates"][0]["lanes"] == ["github", "grep"]


# ------------------------------------------------------------------ driver ---

def test_run_sweep_respects_lanes_selection(monkeypatch):
    monkeypatch.setattr(sweep, "github_lane", lambda *a, **kw: [sweep.empty_candidate(name="gh", source_lane="github")])
    monkeypatch.setattr(sweep, "registry_lane", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("registry lane should not run")))
    monkeypatch.setattr(sweep, "grep_lane", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("grep lane should not run")))
    monkeypatch.setattr(sweep, "scorecard_lane", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("scorecard should not run")))

    result = sweep.run_sweep(
        query="rate limiter", pattern=None, language=None, limit=5,
        lanes="github", no_scorecard=False,
    )

    assert result["lanes_run"] == ["github"]
    assert result["candidates"][0]["name"] == "gh"
    assert result["errors"] == []


def test_run_sweep_no_scorecard_flag_excludes_lane_even_if_requested(monkeypatch):
    monkeypatch.setattr(sweep, "github_lane", lambda *a, **kw: [])
    monkeypatch.setattr(sweep, "registry_lane", lambda *a, **kw: [])
    monkeypatch.setattr(sweep, "grep_lane", lambda *a, **kw: [])

    def boom(*a, **kw):
        raise AssertionError("scorecard_lane must not run when --no-scorecard is set")

    monkeypatch.setattr(sweep, "scorecard_lane", boom)

    result = sweep.run_sweep(
        query="q", pattern=None, language=None, limit=5,
        lanes="github,registry,grep,scorecard", no_scorecard=True,
    )

    assert "scorecard" not in result["lanes_run"]


def test_run_sweep_unknown_lane_appends_error_but_keeps_going(monkeypatch):
    monkeypatch.setattr(sweep, "github_lane", lambda *a, **kw: [])

    result = sweep.run_sweep(
        query="q", pattern=None, language=None, limit=5,
        lanes="bogus-lane,github", no_scorecard=True,
    )

    assert result["lanes_run"] == ["github"]
    assert any("unknown lane" in e for e in result["errors"])


def test_run_sweep_pattern_defaults_to_query_for_grep_lane(monkeypatch):
    captured = {}

    def fake_grep_lane(pattern, language, limit, errors):
        captured["pattern"] = pattern
        return []

    monkeypatch.setattr(sweep, "github_lane", lambda *a, **kw: [])
    monkeypatch.setattr(sweep, "registry_lane", lambda *a, **kw: [])
    monkeypatch.setattr(sweep, "grep_lane", fake_grep_lane)

    sweep.run_sweep(
        query="rate limiter", pattern=None, language=None, limit=5,
        lanes="github,registry,grep", no_scorecard=True,
    )

    assert captured["pattern"] == "rate limiter"


def test_run_sweep_output_has_no_composite_score_field(monkeypatch):
    monkeypatch.setattr(sweep, "github_lane", lambda *a, **kw: [
        sweep.empty_candidate(name="example/rate-limiter", source_lane="github", stars=10)
    ])
    monkeypatch.setattr(sweep, "registry_lane", lambda *a, **kw: [])
    monkeypatch.setattr(sweep, "grep_lane", lambda *a, **kw: [])
    monkeypatch.setattr(sweep, "scorecard_lane", lambda candidates, errors: candidates)

    result = sweep.run_sweep(
        query="rate limiter", pattern=None, language=None, limit=5,
        lanes="github,registry,grep,scorecard", no_scorecard=False,
    )

    assert "score" not in result
    for candidate in result["candidates"]:
        assert "score" not in candidate  # no per-candidate composite score
    assert set(result.keys()) == {"query", "lanes_run", "candidates", "errors"}


# ------------------------------------------------------------------- cli ---

def test_limit_rejects_zero_and_negative():
    parser = sweep.build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--query", "q", "--limit", "0"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--query", "q", "--limit", "-1"])


def test_limit_accepts_positive_int():
    parser = sweep.build_arg_parser()
    args = parser.parse_args(["--query", "q", "--limit", "5"])
    assert args.limit == 5
