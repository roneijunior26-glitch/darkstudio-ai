from __future__ import annotations

from datetime import datetime


class PermanentError(RuntimeError):
    """Sem sentido tentar de novo (tipo desconhecido, dado invalido)."""


class WaitQuota(RuntimeError):
    """Cota diaria do provedor acabou: a tarefa espera ate `until` sem gastar tentativas."""

    def __init__(self, until: datetime, msg: str = "cota diaria excedida"):
        super().__init__(msg)
        self.until = until
