"""S13 calendar expiry and equity protection: behavior audit.

Entry-pause boundaries, weekend exemption, near-expiry refusal, and
conservative native-protection truth. No broker, no live calls.
"""
import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime


def _et_day(hour_utc, minute=0, day=2):
    return datetime(2026, 10, day, hour_utc, minute, tzinfo=UTC)


def test_entry_pause_boundaries_and_weekend():
    import services.public_execution_lifecycle as lc

    # 2026-10-02 is a Friday. 11:30–14:00 ET = 15:30–18:00 UTC.
    assert lc.is_entry_pause(_et_day(15, 29)) is False  # 11:29 ET open
    assert lc.is_entry_pause(_et_day(15, 30)) is True  # 11:30 ET paused
    assert lc.is_entry_pause(_et_day(17, 59)) is True  # 13:59 ET paused
    assert lc.is_entry_pause(_et_day(18, 0)) is False  # 14:00 ET open
    # 2026-10-03 is a Saturday: never paused.
    assert lc.is_entry_pause(_et_day(16, 0, day=3)) is False


def test_near_expiry_refuses_commissioned_entry():
    import services.execution_admission as adm

    # Same-day 13:00 ET cutoff semantics: malformed cutoff fails closed.
    from services import execution_protection as prot

    same_day = prot.entry_expiry_guard(
        "2026-10-02", datetime(2026, 10, 2, 15, 0, tzinfo=UTC),
        {"min_entry_dte": 5, "same_day_cutoff_et": "13:00"})
    assert same_day.get("ok") is False, same_day
    assert same_day.get("reason") == "EXPIRY_TOO_NEAR", same_day
    guard = prot.entry_expiry_guard(
        "2026-10-02", datetime(2026, 10, 2, 15, 0, tzinfo=UTC),
        {"min_entry_dte": 0, "same_day_cutoff_et": "not-a-time"})
    assert guard.get("ok") is False, guard
    assert guard.get("reason") == "GUARD_UNCONFIGURED", guard
    _ = adm.ADMISSION_VERSION


def test_native_protection_never_claimed():
    from services import public_execution_lifecycle as lc

    combos = [("OPTION", "LIMIT"), ("OPTION", "MARKET"),
              ("EQUITY", "LIMIT"), ("EQUITY", "STOP"),
              ("CRYPTO", "MARKET")]
    for product, order_type in combos:
        support = lc.native_protection_support(product, order_type)
        assert support.get("supported") is not True, (
            product, order_type, support)
