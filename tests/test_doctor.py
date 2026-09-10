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
    levels = {name: level for level, name, _ in doctor.results}
    assert levels["deja-vu-skill"] == "PASS"


def test_check_deja_vu_skill_fails_on_missing_design_doc(tmp_path, monkeypatch):
    make_minimal_packaged_payload(tmp_path)
    (tmp_path / "docs" / "design.md").unlink()
    monkeypatch.setattr(doctor, "ROOT", str(tmp_path))
    monkeypatch.setattr(doctor, "results", [])

    doctor.check_deja_vu_skill()

    level, name, detail = doctor.results[0]
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
    levels = {name: level for level, name, _ in doctor.results}
    assert levels["deja-vu-skill"] == "FAIL"
