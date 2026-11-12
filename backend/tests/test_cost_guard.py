from datetime import datetime, timezone

from app.providers.base import CostTier, UsageEstimate
from app.providers.cost_guard import Decision, check, next_utc_midnight

NOW = datetime(2026, 11, 12, 18, 30, tzinfo=timezone.utc)
EST = UsageEstimate("neurons", 60)


def run(**over):
    args = dict(
        tier=CostTier.FREE, authorized=False, estimate=EST, used_today=0,
        daily_limit=10_000, conservative_limit=None, now=NOW,
    )
    args.update(over)
    return check(**args)


def test_free_within_quota_is_allowed():
    assert run().decision == Decision.ALLOW


def test_paid_blocked_without_authorization():
    assert run(tier=CostTier.PAID).decision == Decision.BLOCK_UNAUTHORIZED


def test_paid_still_needs_quota_check_when_authorized():
    r = run(tier=CostTier.PAID, authorized=True, used_today=9_990)
    assert r.decision == Decision.WAIT_QUOTA


def test_optional_blocked_without_authorization_allowed_with():
    assert run(tier=CostTier.OPTIONAL).decision == Decision.BLOCK_UNAUTHORIZED
    assert run(tier=CostTier.OPTIONAL, authorized=True).decision == Decision.ALLOW


def test_exactly_at_limit_is_allowed():
    assert run(used_today=9_940).decision == Decision.ALLOW


def test_over_quota_waits_until_next_utc_midnight():
    r = run(used_today=9_950)
    assert r.decision == Decision.WAIT_QUOTA
    assert r.retry_after == datetime(2026, 11, 13, 0, 0, tzinfo=timezone.utc)


def test_unknown_limit_without_conservative_is_blocked():
    r = run(daily_limit=None, conservative_limit=None)
    assert r.decision == Decision.BLOCK_QUOTA_UNKNOWN


def test_unknown_limit_uses_conservative_limit():
    assert run(daily_limit=None, conservative_limit=100).decision == Decision.ALLOW
    assert run(daily_limit=None, conservative_limit=50).decision == Decision.WAIT_QUOTA


def test_next_midnight_handles_other_timezones():
    from datetime import timedelta
    brt = timezone(timedelta(hours=-3))
    # 22:00 em Sao Paulo = 01:00 UTC do dia seguinte -> proximo reset e 00:00 UTC do dia 14
    now = datetime(2026, 11, 12, 22, 0, tzinfo=brt)
    assert next_utc_midnight(now) == datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc)
