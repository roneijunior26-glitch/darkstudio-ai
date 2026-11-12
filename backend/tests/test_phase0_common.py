import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "phase0"))
import common  # noqa: E402


def test_redact_removes_secret_values(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AQ.supersecretvalue123")
    out = common.redact("erro com chave AQ.supersecretvalue123 no texto")
    assert "supersecretvalue" not in out
    assert "<GEMINI_API_KEY>" in out


def test_redact_ignores_empty_secret(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert common.redact("abc") == "abc"
