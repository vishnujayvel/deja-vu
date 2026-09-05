import json
from pathlib import Path

import pytest

from scripts import doctor

GATE_SOURCE = (
    'POLECAT_POOL = ("furiosa", "nux")\n'
    'POLECAT_IDENTITIES = frozenset(\n'
    '    f"deja-vu/gastown.{name}" for name in POLECAT_POOL\n'
    ')\n'
)


def make_workspace(root: Path, *, gate_source=GATE_SOURCE, contract_modules=None):
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "refinery_gate.py").write_text(gate_source)
    contracts = root / "contracts"
    contracts.mkdir()
    if contract_modules is None:
        contract_modules = [{"path": "scripts/refinery_gate.py", "contract": "gate"}]
    (contracts / "module-contracts.json").write_text(
        json.dumps({"schema_version": "deja-vu.module-contracts/v1", "modules": contract_modules})
    )


def run_check(monkeypatch, root: Path):
    results = []
    monkeypatch.setattr(doctor, "results", results)
    doctor.check_refinery_gate(root=str(root))
    assert len(results) == 1
    return results[0]


def test_refinery_gate_present_passes(tmp_path, monkeypatch):
    make_workspace(tmp_path)
    level, name, detail = run_check(monkeypatch, tmp_path)
    assert level == "PASS"
    assert name == "refinery-gate"


def test_refinery_gate_missing_file_fails(tmp_path, monkeypatch):
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts" / "module-contracts.json").write_text(
        json.dumps({"schema_version": "v1", "modules": []})
    )
    level, name, detail = run_check(monkeypatch, tmp_path)
    assert level == "FAIL"
    assert "missing" in detail


def test_refinery_gate_missing_contract_entry_fails(tmp_path, monkeypatch):
    make_workspace(tmp_path, contract_modules=[{"path": "scripts/other.py", "contract": "x"}])
    level, name, detail = run_check(monkeypatch, tmp_path)
    assert level == "FAIL"
    assert "module-contracts.json" in detail


def test_refinery_gate_missing_declarations_fails(tmp_path, monkeypatch):
    make_workspace(tmp_path, gate_source="VALUE = 1\n")
    level, name, detail = run_check(monkeypatch, tmp_path)
    assert level == "FAIL"
    assert "POLECAT_POOL" in detail
    assert "POLECAT_IDENTITIES" in detail


def test_refinery_gate_import_error_fails(tmp_path, monkeypatch):
    make_workspace(tmp_path, gate_source="def broken(\n")
    level, name, detail = run_check(monkeypatch, tmp_path)
    assert level == "FAIL"
    assert "does not import cleanly" in detail
