import json
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


def test_check_octocode_passes_when_registered_in_claude(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"octocode": {}}}))
    monkeypatch.setattr(doctor, "results", [])

    doctor.check_octocode()

    level, _, detail = doctor.results[0]
    assert level == "PASS"
    assert "Claude Code" in detail


def test_check_octocode_passes_when_registered_in_codex(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text("[mcp_servers.octocode]\ncommand = \"octocode-mcp\"\n")
    monkeypatch.setattr(doctor, "results", [])

    doctor.check_octocode()

    level, _, detail = doctor.results[0]
    assert level == "PASS"
    assert "Codex" in detail


def test_check_octocode_warns_with_both_hosts_install_commands_when_unregistered(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(doctor, "results", [])

    doctor.check_octocode()

    level, _, detail = doctor.results[0]
    assert level == "WARN"
    assert "claude mcp add-json" in detail
    assert "codex mcp add" in detail


def test_check_last30days_passes_when_installed_under_codex(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    skill_dir = tmp_path / ".codex" / "skills" / "last30days"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("placeholder")
    monkeypatch.setattr(doctor, "results", [])

    doctor.check_last30days()

    level, _, _ = doctor.results[0]
    assert level == "PASS"


def test_check_last30days_warns_when_installed_under_neither_host(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(doctor, "results", [])

    doctor.check_last30days()

    level, _, _ = doctor.results[0]
    assert level == "WARN"
