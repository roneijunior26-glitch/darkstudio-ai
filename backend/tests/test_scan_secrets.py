import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from scan_secrets import scan_text  # noqa: E402


def test_detects_google_key_new_format():
    fake = "AQ." + "A" * 40
    assert "chave Google API (novo formato)" in scan_text(f"k = {fake}")


def test_detects_google_key():
    fake = "AIza" + "A" * 35
    assert "chave Google API" in scan_text(f"key = {fake}")


def test_detects_private_key_header():
    assert "chave privada" in scan_text("-----BEGIN PRIVATE KEY-----")


def test_detects_suspicious_assignment():
    assert scan_text('api_key = "abcdefghijklmnopqrstuvwxyz123456"')


def test_ignores_env_var_reference_and_plain_text():
    assert not scan_text('api_key = os.environ["GEMINI_API_KEY"]')
    assert not scan_text("texto normal sem segredo")
