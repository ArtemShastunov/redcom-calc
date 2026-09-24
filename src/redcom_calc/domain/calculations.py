from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from .models import BlockType, Service
from .rules import monthly_rate_for_state, monthly_rate_if_service

_TWO = Decimal("0.01")
_MAX_ITER = 1200


def _q(x: Decimal) -> Decimal:
    return x.quantize(_TWO, rounding=ROUND_HALF_UP)


def monthly_total(services: list[Service]) -> Decimal:
    return _q(sum((monthly_rate_for_state(s) for s in services), Decimal("0")))


def monthly_total_full(services: list[Service]) -> Decimal:
    """Полная абонплата: только неблокированные услуги по базовому тарифу.

    Услуги с block_type != NONE (ДБ/ФБ) исключаются из полной абонплаты —
    их ставки учитываются отдельно в суммах за ДБ/ФБ.
    """
    return _q(sum(
        (monthly_rate_if_service(s) for s in services if s.block_type is BlockType.NONE),
        Decimal("0"),
    ))


def need_for_month(balance: Decimal, monthly: Decimal) -> Decimal:
    """max(0, monthly − balance), с защитой на monthly = 0."""
    if monthly <= 0:
        return Decimal("0.00")
    raw = monthly - balance
    if raw < 0:
        return Decimal("0.00")
    return _q(raw)


def monthly_from_prorated(
    amount: Decimal, days: int, year: int, month: int
) -> Decimal:
    """Восстановить месячную ставку из списания за N дней."""
    if amount < 0:
        raise ValueError("amount must be >= 0")
    if days <= 0:
        raise ValueError("days must be > 0")
    days_in_month = calendar.monthrange(year, month)[1]
    if days > days_in_month:
        raise ValueError(
            f"days ({days}) exceeds days in {year:04d}-{month:02d} ({days_in_month})"
        )
    monthly = amount * Decimal(days_in_month) / Decimal(days)
    return _q(monthly)


def _next_month_first(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def calculate_paid_until(
    balance: Decimal, monthly: Decimal, start_date: date
) -> date | None:
    if balance <= 0 or monthly <= 0:
        return None

    remaining = balance
    current = start_date
    paid_until = start_date - timedelta(days=1)

    for _ in range(_MAX_ITER):
        days_in_month = calendar.monthrange(current.year, current.month)[1]
        daily = monthly / Decimal(days_in_month)
        days_left_in_month = days_in_month - current.day + 1
        cost_to_end = daily * Decimal(days_left_in_month)

        if remaining >= cost_to_end:
            remaining -= cost_to_end
            paid_until = date(current.year, current.month, days_in_month)
            current = _next_month_first(current)
            continue

        days_can_pay = int(
            (remaining * Decimal(days_in_month) / monthly).to_integral_value(
                rounding=ROUND_FLOOR
            )
        )
        paid_until = date.fromordinal(current.toordinal() + days_can_pay - 1)
        break

    return paid_until if paid_until >= start_date else None


def days_left(paid_until: date | None, today: date) -> int | None:
    if paid_until is None:
        return None
    return (paid_until - today).days + 1
