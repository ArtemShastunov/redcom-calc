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


# ---------- BreakdownRow ----------


@dataclass
class BreakdownRow:
    """Одна строка разбивки.

    Если у услуги несколько строк с одинаковыми (name, block, year, month),
    это интервалы внутри месяца. Сумма их days = дней в месяце.
    Если days=None — обычная месячная ставка без интервалов.
    """

    name: str
    monthly: Decimal
    block: BlockType = BlockType.NONE
    days: Decimal | None = None
    year: int | None = None
    month: int | None = None
    original_monthly: Decimal | None = None
    days_input: Decimal | None = None
    days_warning: str | None = None
    period_start: int | None = None
    period_end: int | None = None

    @property
    def was_changed(self) -> bool:
        return self.original_monthly is not None and self.original_monthly != self.monthly


# ---------- абонплата ----------


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


# ---------- восстановление ставки ----------


def monthly_from_prorated(amount: Decimal, days: Decimal | int, year: int, month: int) -> Decimal:
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


# ---------- paid_until (старая, без интервалов) ----------


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


# ---------- работа с интервалами ----------


def validate_intervals(breakdown: list[BreakdownRow]) -> None:
    """Сумма дней интервалов каждой (услуга, месяц) = длина месяца."""
    grouped: dict[tuple, Decimal] = {}
    for row in breakdown:
        if row.days is None or row.year is None or row.month is None:
            continue
        key = (row.name, row.block, row.year, row.month)
        grouped[key] = grouped.get(key, Decimal(0)) + row.days

    for (name, _block, year, month), total_days in grouped.items():
        days_in_month = calendar.monthrange(year, month)[1]
        if total_days != Decimal(days_in_month):
            raise ValueError(
                f"«{name}» за {year:04d}-{month:02d}: сумма дней "
                f"интервалов {total_days}, а в месяце {days_in_month}"
            )


def assign_periods(breakdown: list[BreakdownRow]) -> None:
    """Проставить period_start / period_end для строк-интервалов.

    Идём по списку в порядке добавления. Для каждой группы
    (name, block, year, month) накапливаем позицию дня месяца.
    Дробные days не дают осмысленного периода — пропускаем.
    """
    positions: dict[tuple, int] = {}
    for row in breakdown:
        if row.days is None or row.year is None or row.month is None:
            continue
        if row.days != row.days.to_integral_value():
            continue
        key = (row.name, row.block, row.year, row.month)
        start = positions.get(key, 1)
        days_int = int(row.days)
        row.period_start = start
        row.period_end = start + days_int - 1
        positions[key] = start + days_int


def compute_totals(
    breakdown: list[BreakdownRow],
    block_filter: BlockType | None = None,
) -> tuple[Decimal, Decimal]:
    """Вернуть (текущий_тариф, начислено_за_месяц) для среза.

    block_filter=None — все строки. Иначе — только с этим block.

    Группировка по (name, block, year, month):
    - Одна услуга с интервалами: current = последняя ставка,
      charged = Σ(rate × days / days_in_month).
    - Строки без days (обычная месячная ставка): current = charged = monthly.
    """
    rows = [r for r in breakdown if block_filter is None or r.block == block_filter]

    # Отбираем строки-интервалы и standalone
    interval_groups: dict[tuple, list[BreakdownRow]] = {}
    standalone: list[BreakdownRow] = []

    for r in rows:
        if r.days is not None and r.year is not None and r.month is not None:
            key = (r.name, r.block, r.year, r.month)
            interval_groups.setdefault(key, []).append(r)
        else:
            standalone.append(r)

    current_total = Decimal(0)
    charged_total = Decimal(0)

    for (name, block, year, month), group in interval_groups.items():
        days_in_month = calendar.monthrange(year, month)[1]
        charged = sum(
            (r.monthly * r.days / Decimal(days_in_month) for r in group),
            Decimal(0),
        )
        current_total += group[-1].monthly
        charged_total += charged

    for r in standalone:
        current_total += r.monthly
        charged_total += r.monthly

    return _q(current_total), _q(charged_total)


def _rate_for_day(day: int, intervals: list[tuple[Decimal, Decimal]]) -> Decimal:
    """Ставка интервала, в который попадает день месяца."""
    pos = Decimal(1)
    for rate, days in intervals:
        end_pos = pos + days - 1
        if Decimal(day) <= end_pos:
            return rate
        pos = end_pos + 1
    return intervals[-1][0]


def paid_until_from_breakdown(
    balance: Decimal,
    breakdown: list[BreakdownRow],
    start_date: date,
    fallback_monthly: Decimal | None = None,
) -> date | None:
    """Последний покрытый день с учётом интервалов внутри месяца.

    Если интервалов нет — использует fallback_monthly (или сумму monthly).
    Для интервалов каждая услуга даёт свою дневную ставку на каждый день.
    Для месяцев без интервалов — последняя ставка услуги.
    """
    if balance <= 0:
        return None

    if not breakdown:
        if fallback_monthly is not None and fallback_monthly > 0:
            return calculate_paid_until(balance, fallback_monthly, start_date)
        return None

    # Группировка по (name, block) -> {(year, month): [(rate, days), ...]}
    service_intervals: dict[tuple, dict[tuple[int, int], list]] = {}
    service_last_rate: dict[tuple, Decimal] = {}

    for row in breakdown:
        key = (row.name, row.block)
        service_last_rate[key] = row.monthly
        if row.days is not None and row.year is not None and row.month is not None:
            mk = (row.year, row.month)
            service_intervals.setdefault(key, {}).setdefault(mk, [])
            service_intervals[key][mk].append((row.monthly, row.days))

    has_intervals = any(len(m) > 0 for m in service_intervals.values())

    if not has_intervals:
        total = (
            fallback_monthly
            if fallback_monthly is not None
            else sum((row.monthly for row in breakdown), Decimal(0))
        )
        return calculate_paid_until(balance, total, start_date)

    remaining = balance
    current = start_date
    paid_until = start_date - timedelta(days=1)
    max_iter = 365 * 20

    for _ in range(max_iter):
        days_in_month = calendar.monthrange(current.year, current.month)[1]
        daily = Decimal(0)

        for key, months in service_intervals.items():
            month_key = (current.year, current.month)
            if month_key in months:
                rate = _rate_for_day(current.day, months[month_key])
            else:
                last_month = max(months.keys())
                rate = months[last_month][-1][0]
            daily += rate / Decimal(days_in_month)

        for key, rate in service_last_rate.items():
            if key not in service_intervals:
                daily += rate / Decimal(days_in_month)

        if daily <= 0:
            break

        if remaining >= daily:
            remaining -= daily
            paid_until = current
            current += timedelta(days=1)
        else:
            break

    return paid_until if paid_until >= start_date else None


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
