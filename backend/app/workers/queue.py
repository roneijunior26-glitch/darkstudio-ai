"""Fila de tarefas em PostgreSQL: estados, retry com backoff e SQL de reserva.

A reserva e atomica (FOR UPDATE SKIP LOCKED): dois workers nunca pegam a mesma
tarefa. Tarefas RUNNING que passaram do timeout voltam para a fila (RECLAIM_SQL).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    WAITING_PROVIDER = "WAITING_PROVIDER"
    WAITING_APPROVAL = "WAITING_APPROVAL"


def backoff_seconds(attempt: int, base: int = 30, cap: int = 3600) -> int:
    """Espera antes da tentativa seguinte. `attempt` e o numero da tentativa que falhou (>= 1)."""
    if attempt < 1:
        raise ValueError("attempt deve ser >= 1")
    return min(cap, base * 2 ** (attempt - 1))


def status_after_failure(attempts: int, max_attempts: int) -> TaskStatus:
    return TaskStatus.FAILED if attempts >= max_attempts else TaskStatus.QUEUED


def retry_at(now: datetime, attempts: int) -> datetime:
    return now.astimezone(timezone.utc) + timedelta(seconds=backoff_seconds(attempts))


CLAIM_SQL = """
UPDATE tasks
   SET status = 'RUNNING',
       locked_by = %(worker)s,
       locked_at = now(),
       attempts = attempts + 1,
       updated_at = now()
 WHERE id = (
        SELECT t.id
          FROM tasks t
         WHERE t.status IN ('QUEUED', 'WAITING_PROVIDER')
           AND t.run_after <= now()
           AND NOT EXISTS (
                 SELECT 1 FROM tasks d
                  WHERE d.id = ANY(t.depends_on) AND d.status <> 'COMPLETED')
         ORDER BY t.priority DESC, t.run_after, t.created_at
         FOR UPDATE SKIP LOCKED
         LIMIT 1)
RETURNING *;
"""

RECLAIM_SQL = """
UPDATE tasks
   SET status = CASE WHEN attempts >= max_attempts THEN 'FAILED' ELSE 'QUEUED' END,
       locked_by = NULL,
       locked_at = NULL,
       last_error = 'timeout: worker nao respondeu',
       updated_at = now()
 WHERE status = 'RUNNING'
   AND locked_at < now() - make_interval(secs => timeout_s);
"""

# Colunas de `tasks` que os SQLs acima exigem; um teste confere com a migration.
REQUIRED_TASK_COLUMNS = (
    "id", "status", "run_after", "depends_on", "priority", "created_at",
    "locked_by", "locked_at", "attempts", "max_attempts", "timeout_s",
    "last_error", "updated_at",
)
