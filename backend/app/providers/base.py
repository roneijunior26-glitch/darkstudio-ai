"""Contrato dos fornecedores de IA (texto, imagem, video, voz, transcricao).

Todo fornecedor declara sua categoria de custo (CostTier). A guarda de custo
(`cost_guard.check`) decide se uma chamada pode ser executada ANTES de `run`.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Protocol

Category = Literal["text", "image", "video", "voice", "transcription", "translation"]


class CostTier(str, Enum):
    FREE = "FREE"
    OPTIONAL = "OPTIONAL"  # exige autorizacao explicita do usuario
    PAID = "PAID"  # bloqueado por padrao


@dataclass(frozen=True)
class UsageEstimate:
    unit: str  # ex.: "neurons", "requests", "tokens", "seconds"
    amount: float


@dataclass(frozen=True)
class ProviderHealth:
    available: bool
    remaining: float | None  # None = cota restante desconhecida
    detail: str = ""


@dataclass(frozen=True)
class ProviderResult:
    asset_key: str | None
    usage: UsageEstimate
    metadata: dict[str, Any]


class Provider(Protocol):
    name: str
    category: Category
    tier: CostTier

    def estimate(self, request: dict[str, Any]) -> UsageEstimate:
        """Consumo previsto da chamada, na unidade de cota do fornecedor."""

    async def health(self) -> ProviderHealth:
        """Disponibilidade e cota restante (None quando o fornecedor nao informa)."""

    async def run(self, request: dict[str, Any]) -> ProviderResult:
        """Executa a chamada. So pode ser invocado depois de `cost_guard.check`."""
