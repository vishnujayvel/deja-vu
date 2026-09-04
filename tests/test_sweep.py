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
    # 3 hits fixture, 2 of them share a repo -> deduped to 2 candidates
    assert len(candidates) == 2
    names = {c["name"] for c in candidates}
    assert names == {"example/rate-limiter", "another/project"}
    assert all(c["source_lane"] == "grep" for c in candidates)


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
