import argparse
import datetime
import json

import pytest

import provenance

NOW = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


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
    age = provenance.account_age_years("2016-01-01T00:00:00Z", now=NOW)
    assert age == 10.0


def test_account_age_years_none_for_missing_or_malformed_input():
    assert provenance.account_age_years(None, now=NOW) is None
    assert provenance.account_age_years("not-a-date", now=NOW) is None


def test_account_age_years_is_deterministic_given_explicit_now():
    # Same created_at + same explicit `now` -> identical result, regardless
    # of when the test actually runs (no wall-clock read anywhere).
    a = provenance.account_age_years("2016-01-01T00:00:00Z", now=NOW)
    b = provenance.account_age_years("2016-01-01T00:00:00Z", now=NOW)
    assert a == b == 10.0


def test_top_notable_repos_excludes_forks_and_sorts_by_stars(load_fixture_json):
    repos = load_fixture_json("github_repos_established.json")
    top = provenance.top_notable_repos(repos)

    assert len(top) == 3
    assert [r["name"] for r in top] == ["big-project", "mid-project", "small-project"]
    assert "forked-thing" not in [r["name"] for r in top]  # forks excluded


# ----------------------------------------------------------- build_profile ---

def test_build_profile_established_practitioner_happy_path(load_fixture_json):
    user = load_fixture_json("github_user_established.json")
    repos = load_fixture_json("github_repos_established.json")

    profile, err = provenance.build_profile("example-established-dev", user, repos, now=NOW)

    assert err is None
    assert profile["signal"] == "established-practitioner"
    assert profile["account_age_years"] is not None and profile["account_age_years"] > 9
    assert profile["other_notable"][0]["name"] == "big-project"


def test_build_profile_new_anonymous_account_is_unknown_experimental(load_fixture_json):
    user = load_fixture_json("github_user_new.json")

    profile, err = provenance.build_profile("example-new-anon", user, [], now=NOW)

    assert err is None
    assert profile["signal"] == "unknown-experimental"
    assert profile["other_notable"] == []


def test_build_profile_rejects_missing_user_data_instead_of_degrading():
    profile, err = provenance.build_profile("whoever", None, None, now=NOW)

    assert profile is None
    assert err is not None
    assert "whoever" in err
    assert "missing required user profile data" in err


def test_build_profile_rejects_malformed_created_at_instead_of_degrading():
    user = {"login": "whoever", "created_at": "not-a-date", "followers": 10000, "public_repos": 10000}

    profile, err = provenance.build_profile("whoever", user, [], now=NOW)

    assert profile is None
    assert err is not None
    assert "malformed" in err


def test_build_profile_never_lets_external_login_override_caller_supplied_identity():
    user = {"login": "attacker-controlled-login", "created_at": "2016-01-01T00:00:00Z"}

    profile, err = provenance.build_profile("trusted-caller-login", user, [], now=NOW)

    assert err is None
    assert profile["login"] == "trusted-caller-login"


# ----------------------------------------------------------- run_provenance ---

def test_run_provenance_covers_multiple_owners(load_fixture_json):
    owners = [
        {"login": "alice-example", "user": load_fixture_json("github_user_established.json"), "repos": []},
        {"login": "bob-example", "user": load_fixture_json("github_user_new.json"), "repos": []},
    ]

    result = provenance.run_provenance(owners, now=NOW)

    assert [p["login"] for p in result["profiles"]] == ["alice-example", "bob-example"]
    assert result["errors"] == []


def test_run_provenance_rejects_invalid_entries_without_crashing(load_fixture_json):
    owners = [
        {"login": "alice-example", "user": load_fixture_json("github_user_established.json"), "repos": []},
        {"login": "", "user": {}},  # missing login
        {"user": {}},  # no login key at all
        "not-a-dict",  # wrong shape entirely
        {"login": "broken", "user": None},  # missing user data
    ]

    result = provenance.run_provenance(owners, now=NOW)

    assert [p["login"] for p in result["profiles"]] == ["alice-example"]
    assert len(result["errors"]) == 4


def test_run_provenance_is_deterministic_given_identical_input(load_fixture_json):
    owners = [{"login": "alice-example", "user": load_fixture_json("github_user_established.json"), "repos": []}]

    first = provenance.run_provenance(owners, now=NOW)
    second = provenance.run_provenance(owners, now=NOW)

    assert first == second


def test_provenance_output_has_no_composite_score_field(load_fixture_json):
    owners = [{"login": "someone", "user": load_fixture_json("github_user_new.json"), "repos": []}]

    result = provenance.run_provenance(owners, now=NOW)

    assert "score" not in result
    for profile in result["profiles"]:
        assert "score" not in profile


# --------------------------------------------------------------------- CLI ---

def test_parse_now_accepts_utc_iso8601():
    now = provenance._parse_now("2026-01-01T00:00:00Z")
    assert now == NOW


def test_parse_now_rejects_malformed_timestamp():
    with pytest.raises(argparse.ArgumentTypeError):
        provenance._parse_now("not-a-timestamp")


# --------------------------------------- round-2 findings: type validation ---

def test_build_profile_rejects_non_numeric_followers_instead_of_crashing():
    # A string "followers" value used to crash classify_signal's `>= 50`
    # comparison with an uncaught TypeError instead of rejecting the record.
    user = {"created_at": "2016-01-01T00:00:00Z", "followers": "50", "public_repos": 10}

    profile, err = provenance.build_profile("whoever", user, [], now=NOW)

    assert profile is None
    assert err is not None
    assert "followers" in err and "malformed" in err


def test_build_profile_rejects_non_numeric_public_repos_instead_of_crashing():
    user = {"created_at": "2016-01-01T00:00:00Z", "followers": 10, "public_repos": {"x": 1}}

    profile, err = provenance.build_profile("whoever", user, [], now=NOW)

    assert profile is None
    assert "public_repos" in err and "malformed" in err


def test_build_profile_rejects_boolean_followers():
    # bool is a subclass of int in Python; True/False are not plausible counts.
    user = {"created_at": "2016-01-01T00:00:00Z", "followers": True, "public_repos": 10}

    profile, err = provenance.build_profile("whoever", user, [], now=NOW)

    assert profile is None
    assert "followers" in err


def test_build_profile_rejects_non_string_company_and_name():
    user = {"created_at": "2016-01-01T00:00:00Z", "followers": 10, "public_repos": 5, "company": 12345}
    profile, err = provenance.build_profile("whoever", user, [], now=NOW)
    assert profile is None
    assert "company" in err

    user = {"created_at": "2016-01-01T00:00:00Z", "followers": 10, "public_repos": 5, "name": ["not", "a", "string"]}
    profile, err = provenance.build_profile("whoever", user, [], now=NOW)
    assert profile is None
    assert "name" in err


def test_build_profile_accepts_null_optional_numeric_and_string_fields():
    user = {
        "created_at": "2016-01-01T00:00:00Z",
        "followers": None,
        "public_repos": None,
        "company": None,
        "name": None,
    }

    profile, err = provenance.build_profile("whoever", user, [], now=NOW)

    assert err is None
    assert profile["followers"] is None
    assert profile["public_repos"] is None
    assert profile["company"] is None
    assert profile["name"] is None


def test_top_notable_repos_drops_malformed_entries_instead_of_crashing():
    # Mixed str/int stargazers_count used to raise TypeError in sort(); a
    # non-string name would violate the {"name": str, "stars": int} schema.
    repos = [
        {"name": "good-repo", "stargazers_count": 5, "fork": False},
        {"name": "bad-stars-repo", "stargazers_count": "12", "fork": False},
        {"name": None, "stargazers_count": 100, "fork": False},
        {"name": "no-stars-repo", "stargazers_count": None, "fork": False},
    ]

    top = provenance.top_notable_repos(repos)

    names = [r["name"] for r in top]
    assert "bad-stars-repo" not in names
    assert None not in names
    assert "good-repo" in names
    assert "no-stars-repo" in names
    for r in top:
        assert isinstance(r["name"], str)
        assert isinstance(r["stars"], int)


def test_build_profile_rejects_future_dated_created_at():
    # created_at after --now is not plausible provenance data; it must be
    # rejected rather than normalized into a negative account_age_years.
    user = {"created_at": "2027-01-01T00:00:00Z", "followers": 10, "public_repos": 5}

    profile, err = provenance.build_profile("whoever", user, [], now=NOW)

    assert profile is None
    assert err is not None
    assert "future" in err or "after reference time" in err


def test_main_reads_input_file_via_context_manager(tmp_path, load_fixture_json, capsys):
    # Pins the fix from an unmanaged `open(...).read()` call to a `with`
    # block: exercises the --input file path end-to-end.
    doc = {"owners": [{"login": "alice-example", "user": load_fixture_json("github_user_established.json"), "repos": []}]}
    input_path = tmp_path / "owners.json"
    input_path.write_text(json.dumps(doc))

    rc = provenance.main(["--input", str(input_path), "--now", "2026-01-01T00:00:00Z"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert [p["login"] for p in out["profiles"]] == ["alice-example"]
