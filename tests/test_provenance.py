import urllib.error
import urllib.request

import provenance
from conftest import FakeHTTPResponse


# --------------------------------------------------------- signal rules ---

def test_classify_signal_established_practitioner():
    assert provenance.classify_signal(10, 500, 80, "Example Corp") == "established-practitioner"


def test_classify_signal_active_builder():
    assert provenance.classify_signal(1.5, 15, 2, None) == "active-builder"


def test_classify_signal_new_anonymous_account_is_unknown_experimental():
    assert provenance.classify_signal(0.02, 0, 1, None) == "unknown-experimental"


def test_classify_signal_boundary_age_exactly_3_with_company_is_established():
    # age >= 3 boundary, low followers/repos but org backing present
    assert provenance.classify_signal(3.0, 0, 0, "Example Corp") == "established-practitioner"


def test_classify_signal_boundary_just_under_3_years_falls_to_active_builder():
    assert provenance.classify_signal(2.99, 20, 6, None) == "active-builder"


def test_classify_signal_missing_age_is_unknown_experimental_never_hard_fails():
    assert provenance.classify_signal(None, 10000, 10000, "Big Co") == "unknown-experimental"


# --------------------------------------------------------------- helpers ---

def test_account_age_years_computes_from_created_at():
    import datetime
    now = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    age = provenance.account_age_years("2016-01-01T00:00:00Z", now=now)
    assert age == 10.0


def test_account_age_years_none_for_missing_or_malformed_input():
    assert provenance.account_age_years(None) is None
    assert provenance.account_age_years("not-a-date") is None


def test_top_notable_repos_excludes_forks_and_sorts_by_stars(load_fixture_json):
    repos = load_fixture_json("github_repos_established.json")
    top = provenance.top_notable_repos(repos)

    assert len(top) == 3
    assert [r["name"] for r in top] == ["big-project", "mid-project", "small-project"]
    assert "forked-thing" not in [r["name"] for r in top]  # forks excluded


# ----------------------------------------------------------- build_profile ---

def test_build_profile_established_practitioner_happy_path(monkeypatch, load_fixture_bytes, no_gh_cli):
    def fake_urlopen(req, timeout=10):
        if "users/example-established-dev/repos" in req.full_url:
            return FakeHTTPResponse(load_fixture_bytes("github_repos_established.json"))
        if "users/example-established-dev" in req.full_url:
            return FakeHTTPResponse(load_fixture_bytes("github_user_established.json"))
        raise AssertionError(f"unexpected URL {req.full_url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    profile = provenance.build_profile("example-established-dev", errors)

    assert errors == []
    assert profile["signal"] == "established-practitioner"
    assert profile["account_age_years"] is not None and profile["account_age_years"] > 9
    assert profile["other_notable"][0]["name"] == "big-project"


def test_build_profile_new_anonymous_account_is_unknown_experimental(monkeypatch, load_fixture_bytes, no_gh_cli):
    def fake_urlopen(req, timeout=10):
        if "users/example-new-anon/repos" in req.full_url:
            return FakeHTTPResponse(b"[]")
        if "users/example-new-anon" in req.full_url:
            return FakeHTTPResponse(load_fixture_bytes("github_user_new.json"))
        raise AssertionError(f"unexpected URL {req.full_url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    profile = provenance.build_profile("example-new-anon", errors)

    assert errors == []
    assert profile["signal"] == "unknown-experimental"
    assert profile["other_notable"] == []


def test_build_profile_http_failure_degrades_gracefully_no_crash(monkeypatch, no_gh_cli):
    def fake_urlopen(req, timeout=10):
        raise urllib.error.URLError("network unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    errors = []
    profile = provenance.build_profile("whoever", errors)

    assert profile["signal"] == "unknown-experimental"
    assert profile["login"] == "whoever"
    assert profile["created_at"] is None
    assert len(errors) == 1
    assert "provenance(api whoever)" in errors[0]


def test_run_provenance_covers_multiple_owners(monkeypatch):
    seen = []

    def fake_build_profile(login, errors, now=None):
        seen.append(login)
        return {"login": login, "signal": "unknown-experimental"}

    monkeypatch.setattr(provenance, "build_profile", fake_build_profile)

    result = provenance.run_provenance(["alice-example", "bob-example"])

    assert seen == ["alice-example", "bob-example"]
    assert len(result["profiles"]) == 2
    assert result["errors"] == []


def test_provenance_output_has_no_composite_score_field(monkeypatch):
    monkeypatch.setattr(provenance, "build_profile", lambda login, errors, now=None: {
        "login": login, "signal": "active-builder", "followers": 10,
    })

    result = provenance.run_provenance(["someone"])

    assert "score" not in result
    for profile in result["profiles"]:
        assert "score" not in profile
