from pathlib import Path

from scripts import doctor

_NO_OP_LANES = (
    "check_github_lane",
    "check_scorecard",
    "check_grep_app",
    "check_octocode",
    "check_skills_cli",
    "check_last30days",
)


def _stub_optional_lanes(monkeypatch):
    for name in _NO_OP_LANES:
        monkeypatch.setattr(doctor, name, lambda: None)


def make_minimal_packaged_payload(root: Path):
    """Exactly the file set scripts/sync_codex_plugin.py ships -- proves
    default doctor validates a real packaged install."""
    for relative in doctor.REQUIRED_SKILL_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder")


def test_main_passes_on_minimal_packaged_payload(tmp_path, monkeypatch):
    make_minimal_packaged_payload(tmp_path)
    monkeypatch.setattr(doctor, "ROOT", str(tmp_path))
    monkeypatch.setattr(doctor, "results", [])
    monkeypatch.setattr(doctor, "check_python", lambda: None)
    _stub_optional_lanes(monkeypatch)

    exit_code = doctor.main()

    assert exit_code == 0
    levels = {name: level for level, name, _, _ in doctor.results}
    assert levels["deja-vu-skill"] == "PASS"


def test_check_deja_vu_skill_fails_on_missing_design_doc(tmp_path, monkeypatch):
    make_minimal_packaged_payload(tmp_path)
    (tmp_path / "docs" / "design.md").unlink()
    monkeypatch.setattr(doctor, "ROOT", str(tmp_path))
    monkeypatch.setattr(doctor, "results", [])

    doctor.check_deja_vu_skill()

    level, name, detail, _ = doctor.results[0]
    assert level == "FAIL"
    assert name == "deja-vu-skill"
    assert "docs/design.md" in detail


def test_main_fails_when_required_skill_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "ROOT", str(tmp_path))
    monkeypatch.setattr(doctor, "results", [])
    monkeypatch.setattr(doctor, "check_python", lambda: None)
    _stub_optional_lanes(monkeypatch)

    exit_code = doctor.main()

    assert exit_code == 1
    levels = {name: level for level, name, _, _ in doctor.results}
    assert levels["deja-vu-skill"] == "FAIL"


def test_scorecard_and_grep_app_severity_is_stable_across_network_outcomes(monkeypatch):
    """Optional remote probes must not flip PASS/WARN with remote availability --
    only the message may vary (deja-vu-0li)."""
    for status in (200, 429, 503, None):
        monkeypatch.setattr(doctor, "http_status", lambda *_a, **_kw: status)
        monkeypatch.setattr(doctor, "results", [])

        doctor.check_scorecard()
        doctor.check_grep_app()

        levels = [level for level, _, _, _ in doctor.results]
        assert levels == ["WARN", "WARN"], f"status={status} produced {levels}"


def test_scorecard_and_grep_app_only_count_degraded_when_unreachable(monkeypatch):
    """A reachable-but-always-WARN probe must not be flagged degraded, so a
    fully healthy run still reaches a clean READY verdict (deja-vu-0li round 2:
    F1 -- clean READY became unreachable and reachable lanes were mislabeled
    degraded)."""
    for status, expect_degraded in ((200, False), (429, False), (503, True), (None, True)):
        monkeypatch.setattr(doctor, "http_status", lambda *_a, **_kw: status)
        monkeypatch.setattr(doctor, "results", [])

        doctor.check_scorecard()
        doctor.check_grep_app()

        degraded_flags = [degraded for _, _, _, degraded in doctor.results]
        assert degraded_flags == [expect_degraded, expect_degraded], (
            f"status={status} produced {degraded_flags}"
        )


def test_main_reaches_clean_ready_verdict_when_optional_probes_are_reachable(
    tmp_path, monkeypatch, capsys
):
    make_minimal_packaged_payload(tmp_path)
    monkeypatch.setattr(doctor, "ROOT", str(tmp_path))
    monkeypatch.setattr(doctor, "results", [])
    monkeypatch.setattr(doctor, "check_python", lambda: None)
    monkeypatch.setattr(doctor, "check_github_lane", lambda: None)
    monkeypatch.setattr(doctor, "http_status", lambda *_a, **_kw: 200)
    monkeypatch.setattr(doctor, "check_octocode", lambda: None)
    monkeypatch.setattr(doctor, "check_skills_cli", lambda: None)
    monkeypatch.setattr(doctor, "check_last30days", lambda: None)

    exit_code = doctor.main()

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "DOCTOR: VERDICT -- READY" in out
    assert "degraded" not in out
