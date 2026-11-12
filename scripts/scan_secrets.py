"""Varredura simples de segredos nos arquivos versionados (repositorio publico).

Uso: python scripts/scan_secrets.py            (arquivos rastreados pelo git)
     python scripts/scan_secrets.py arq1 arq2  (arquivos especificos)
Sai com codigo 1 se achar algo.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PATTERNS: dict[str, re.Pattern[str]] = {
    "chave privada": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "chave Google API": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "JWT": re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    "segredo Supabase": re.compile(r"sb_secret_[A-Za-z0-9_\-]{10,}"),
    "token GitHub": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "atribuicao suspeita": re.compile(
        r"""(?ix)(api[_-]?key|secret|token|password|senha)\s*[:=]\s*['"][A-Za-z0-9_\-/+=]{20,}['"]"""
    ),
}

# Arquivos que podem conter exemplos de padroes sem ser segredos reais.
IGNORE = {"scripts/scan_secrets.py", "backend/tests/test_scan_secrets.py"}


def scan_text(text: str) -> list[str]:
    return [name for name, pat in PATTERNS.items() if pat.search(text)]


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    return [f for f in out.stdout.splitlines() if f]


def main(argv: list[str]) -> int:
    files = argv or tracked_files()
    found = 0
    for f in files:
        if f in IGNORE:
            continue
        p = Path(f)
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name in scan_text(text):
            print(f"POSSIVEL SEGREDO ({name}) em {f}")
            found += 1
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
