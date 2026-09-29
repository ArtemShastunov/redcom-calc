from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation

from .models import BlockType, Service
from .rules import monthly_rate_for_state, monthly_rate_if_service

_TWO = Decimal("0.01")
_MAX_ITER = 1200


def _q(x: Decimal) -> Decimal:
    return x.quantize(_TWO, rounding=ROUND_HALF_UP)


def monthly_total(services: list[Service]) -> Decimal:
    return _q(sum((monthly_rate_for_state(s) for s in services), Decimal(0)))


def monthly_total_full(services: list[Service]) -> Decimal:
    """Полная абонплата: только неблокированные услуги по базовому тарифу."""
    return _q(
        sum(
            (monthly_rate_if_service(s) for s in services if s.block_type is BlockType.NONE),
            Decimal(0),
        )
    )


def need_for_month(balance: Decimal, monthly: Decimal) -> Decimal:
    """max(0, monthly − balance), с защитой на monthly = 0."""
    if monthly <= 0:
        return Decimal("0.00")
    raw = monthly - balance
    if raw < 0:
        return Decimal("0.00")
    return _q(raw)


def monthly_from_prorated(amount: Decimal, days: Decimal | int, year: int, month: int) -> Decimal:
    """Восстановить месячную ставку из списания за N дней.

    days — фактическое число дней (может быть дробным, если получено
    из коэффициента: coeff × days_in_month). Формула одна:
    monthly = amount × days_in_month / days.
    """
    if amount < 0:
        raise ValueError("Сумма не может быть отрицательной")

    days_dec = days if isinstance(days, Decimal) else Decimal(days)
    if days_dec <= 0:
        raise ValueError("Количество дней должно быть больше нуля")

    days_in_month = calendar.monthrange(year, month)[1]
    if days_dec > Decimal(days_in_month):
        raise ValueError(
            f"Дней ({days_dec}) больше, чем в {year:04d}-{month:02d} ({days_in_month})"
        )

    monthly = amount * Decimal(days_in_month) / days_dec
    return _q(monthly)


def _next_month_first(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def calculate_paid_until(balance: Decimal, monthly: Decimal, start_date: date) -> date | None:
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
            (remaining * Decimal(days_in_month) / monthly).to_integral_value(rounding=ROUND_FLOOR)
        )
        paid_until = date.fromordinal(current.toordinal() + days_can_pay - 1)
        break

    return paid_until if paid_until >= start_date else None


def days_left(paid_until: date | None, today: date) -> int | None:
    if paid_until is None:
        return None
    return (paid_until - today).days + 1


# ---------- валидация цен ----------

_NICE_STEP = Decimal(50)
_NICE_EXCEPTIONS = frozenset({Decimal(0), Decimal(1)})


@dataclass(frozen=True)
class PriceCheck:
    original: Decimal
    rounded: Decimal

    @property
    def was_changed(self) -> bool:
        return self.original != self.rounded


def is_nice_price(amount: Decimal) -> bool:
    if amount in _NICE_EXCEPTIONS:
        return True
    return amount % _NICE_STEP == 0


def round_to_nice(amount: Decimal) -> Decimal:
    if is_nice_price(amount):
        return amount
    lower = (amount // _NICE_STEP) * _NICE_STEP
    upper = lower + _NICE_STEP
    if (amount - lower) <= (upper - amount):
        return lower
    return upper


def validate_price(amount: Decimal) -> PriceCheck:
    return PriceCheck(original=amount, rounded=round_to_nice(amount))


# ---------- разбор дней / коэффициентов ----------


def parse_days_input(raw: str, today: date, year: int, month: int) -> tuple[Decimal, str | None]:
    """Разобрать поле «Дней» из Fastcom.

    Возвращает (days: Decimal, warning | None).

    Логика:
    - Значение < 1 → это КОЭФФИЦИЕНТ (доля месяца). Переводим в дни:
      days = coeff × days_in_month. Предупреждения нет.
    - Значение == 1 в текущем месяце при today.day > 3 → 1 день,
      но с предупреждением «может, это весь месяц».
    - Значение > 1 → это фактические дни.
    - Значение 0, отрицательное, больше дней в месяце — ошибка.
    """
    text = str(raw).strip().replace(",", ".")
    if not text:
        raise ValueError("Поле «Дней» пустое")

    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Некорректное значение: {raw}") from exc

    if value <= 0:
        raise ValueError("Значение должно быть больше нуля")

    days_in_month = calendar.monthrange(year, month)[1]

    if value < 1:
        # Коэффициент — доля месяца
        days = value * Decimal(days_in_month)
        return days, None

    if value > Decimal(days_in_month):
        raise ValueError(f"Дней ({value}) больше, чем в {year:04d}-{month:02d} ({days_in_month})")

    warning = None
    if value == 1 and year == today.year and month == today.month:
        if today.day > 3:
            warning = (
                f"Указан 1 день, но с начала месяца прошло {today.day}. "
                "Если услуга была весь месяц — проверьте данные Fastcom."
            )
    return value, warning
