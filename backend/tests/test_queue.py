import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.workers.queue import (
    CLAIM_SQL, RECLAIM_SQL, REQUIRED_TASK_COLUMNS, TaskStatus,
    backoff_seconds, retry_at, status_after_failure,
)

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "0001_init.sql"


def test_backoff_grows_and_is_capped():
    assert [backoff_seconds(n) for n in (1, 2, 3, 4)] == [30, 60, 120, 240]
    assert backoff_seconds(20) == 3600


def test_backoff_rejects_attempt_zero():
    with pytest.raises(ValueError):
        backoff_seconds(0)


def test_status_after_failure():
    assert status_after_failure(1, 3) == TaskStatus.QUEUED
    assert status_after_failure(3, 3) == TaskStatus.FAILED


def test_retry_at_adds_backoff():
    now = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    assert retry_at(now, 2) == datetime(2026, 11, 12, 12, 1, tzinfo=timezone.utc)


def _tasks_block() -> str:
    sql = MIGRATION.read_text(encoding="utf-8")
    m = re.search(r"create table tasks \((.*?)\n\);", sql, re.S)
    assert m, "tabela tasks nao encontrada na migration"
    return m.group(1)


def test_migration_has_every_column_used_by_queue_sql():
    block = _tasks_block()
    for col in REQUIRED_TASK_COLUMNS:
        assert re.search(rf"^\s*{col}\s", block, re.M), f"coluna ausente em tasks: {col}"


def test_claim_sql_is_atomic_and_skips_locked():
    assert "FOR UPDATE SKIP LOCKED" in CLAIM_SQL
    assert "depends_on" in CLAIM_SQL
    assert "RUNNING" in RECLAIM_SQL


def test_every_task_status_is_allowed_by_migration():
    block = _tasks_block()
    for s in TaskStatus:
        assert f"'{s.value}'" in block, f"status ausente na migration: {s.value}"
