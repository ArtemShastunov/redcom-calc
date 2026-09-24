from datetime import date
from decimal import Decimal

import pytest

from redcom_calc.domain.calculations import (
    calculate_paid_until,
    days_left,
    monthly_from_prorated,
    monthly_total,
    monthly_total_full,
    need_for_month,
)
from redcom_calc.domain.models import BlockType, Service, ServiceState, ServiceType


def _svc(type_, state, fee, block=BlockType.NONE):
    return Service(
        type=type_,
        monthly_fee=Decimal(fee),
        state=state,
        block_type=block,
    )


def test_monthly_total_mixed_states():
    services = [
        _svc(ServiceType.INTERNET, ServiceState.SERVICE, "500"),
        _svc(ServiceType.INTERNET, ServiceState.BLOCK, "500", BlockType.VOLUNTARY),
        _svc(ServiceType.KTV, ServiceState.SERVICE, "0"),
        _svc(ServiceType.CTV, ServiceState.SERVICE, "300"),
    ]
    # monthly_total: ставки блокировок входят (Internet ДБ = 50, KTV = 150)
    assert monthly_total(services) == Decimal("1000.00")
    # monthly_total_full: только неблокированные (Internet 500 + KTV 150 + CTV 300)
    assert monthly_total_full(services) == Decimal("950.00")


def test_paid_until_matches_tz_example():
    paid = calculate_paid_until(Decimal("500"), Decimal("500"), date(2026, 9, 18))
    assert paid == date(2026, 10, 17)
    assert days_left(paid, date(2026, 9, 18)) == 30


def test_paid_until_none_when_balance_zero():
    assert calculate_paid_until(Decimal("0"), Decimal("500"), date(2026, 9, 18)) is None


def test_paid_until_none_when_balance_negative():
    assert calculate_paid_until(Decimal("-100"), Decimal("500"), date(2026, 9, 18)) is None


def test_paid_until_none_when_monthly_zero():
    assert calculate_paid_until(Decimal("1000"), Decimal("0"), date(2026, 9, 18)) is None


def test_paid_until_insufficient_for_today():
    assert calculate_paid_until(Decimal("10"), Decimal("500"), date(2026, 9, 18)) is None


def test_paid_until_multi_month():
    paid = calculate_paid_until(Decimal("1000"), Decimal("500"), date(2026, 9, 18))
    assert paid is not None
    assert paid > date(2026, 10, 15)


def test_need_for_month_cases():
    assert need_for_month(Decimal("1500"), Decimal("500")) == Decimal("0.00")
    assert need_for_month(Decimal("250"), Decimal("500")) == Decimal("250.00")
    assert need_for_month(Decimal("0"), Decimal("500")) == Decimal("500.00")
    assert need_for_month(Decimal("-50"), Decimal("1250")) == Decimal("1300.00")
    assert need_for_month(Decimal("-100"), Decimal("0")) == Decimal("0.00")


# ---------- monthly_from_prorated ----------

def test_prorated_september():
    # Сентябрь — 30 дней. 250 ₽ за 15 дн. → 500 ₽/мес.
    assert monthly_from_prorated(Decimal("250"), 15, 2026, 9) == Decimal("500.00")


def test_prorated_august():
    # Август — 31 день. 125 ₽ за 10 дн. → 387.50 ₽/мес.
    assert monthly_from_prorated(Decimal("125"), 10, 2026, 8) == Decimal("387.50")


def test_prorated_february_non_leap():
    # Февраль 2026 — 28 дней. 100 ₽ за 7 дн. → 400 ₽/мес.
    assert monthly_from_prorated(Decimal("100"), 7, 2026, 2) == Decimal("400.00")


def test_prorated_february_leap():
    # Февраль 2028 — 29 дней. 145 ₽ за 10 дн. → 420.50 ₽/мес.
    assert monthly_from_prorated(Decimal("145"), 10, 2028, 2) == Decimal("420.50")


def test_prorated_rejects_zero_days():
    with pytest.raises(ValueError):
        monthly_from_prorated(Decimal("250"), 0, 2026, 9)


def test_prorated_rejects_too_many_days():
    with pytest.raises(ValueError):
        monthly_from_prorated(Decimal("500"), 31, 2026, 9)


def test_prorated_rejects_negative_amount():
    with pytest.raises(ValueError):
        monthly_from_prorated(Decimal("-10"), 5, 2026, 9)


def test_prorated_is_inverse_of_forward_formula():
    # 500/30 × 15 = 250 — обращаем и получаем снова 500.
    monthly = monthly_from_prorated(Decimal("250"), 15, 2026, 9)
    forward = (monthly / Decimal(30) * Decimal(15)).quantize(Decimal("0.01"))
    assert forward == Decimal("250.00")
