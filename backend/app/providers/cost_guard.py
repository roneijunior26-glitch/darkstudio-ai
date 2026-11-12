"""Guarda de custo: roda antes de toda chamada a um fornecedor.

Regras (spec secao 21):
- PAID e OPTIONAL so passam com autorizacao explicita.
- Cota desconhecida nunca vale como ilimitada: exige um limite conservador.
- Passou da cota: a tarefa espera o proximo reset (00:00 UTC), sem cobrar.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from .base import CostTier, UsageEstimate


class Decision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK_UNAUTHORIZED = "BLOCK_UNAUTHORIZED"
    BLOCK_QUOTA_UNKNOWN = "BLOCK_QUOTA_UNKNOWN"
    WAIT_QUOTA = "WAIT_QUOTA"


@dataclass(frozen=True)
class GuardResult:
    decision: Decision
    reason: str
    retry_after: datetime | None = None


def next_utc_midnight(now: datetime) -> datetime:
    now = now.astimezone(timezone.utc)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def check(
    *,
    tier: CostTier,
    authorized: bool,
    estimate: UsageEstimate,
    used_today: float,
    daily_limit: float | None,
    conservative_limit: float | None,
    now: datetime,
) -> GuardResult:
    if tier in (CostTier.PAID, CostTier.OPTIONAL) and not authorized:
        return GuardResult(
            Decision.BLOCK_UNAUTHORIZED,
            f"fornecedor {tier.value} sem autorizacao explicita",
        )

    limit = daily_limit if daily_limit is not None else conservative_limit
    if limit is None:
        return GuardResult(
            Decision.BLOCK_QUOTA_UNKNOWN,
            "cota desconhecida e nenhum limite conservador configurado",
        )

    if used_today + estimate.amount > limit:
        return GuardResult(
            Decision.WAIT_QUOTA,
            f"cota diaria excedida ({used_today + estimate.amount:g} > {limit:g} {estimate.unit})",
            retry_after=next_utc_midnight(now),
        )

    return GuardResult(Decision.ALLOW, "dentro da cota")
