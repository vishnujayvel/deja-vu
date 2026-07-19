import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class FakeHTTPResponse:
    """Minimal stand-in for the context manager urllib.request.urlopen returns."""

    def __init__(self, payload_bytes, status=200):
        self._payload = payload_bytes
        self.status = status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def fixture_bytes(name):
    return (FIXTURES_DIR / name).read_bytes()


def fixture_json(name):
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture
def load_fixture_bytes():
    return fixture_bytes


@pytest.fixture
def load_fixture_json():
    return fixture_json


@pytest.fixture
def no_gh_cli(monkeypatch):
    """Force every script's shutil.which('gh') to report the CLI absent, so
    lane code takes the unauthenticated-API fallback path deterministically.
    """
    import provenance
    import sweep

    monkeypatch.setattr(sweep.shutil, "which", lambda _name: None)
    monkeypatch.setattr(provenance.shutil, "which", lambda _name: None)
