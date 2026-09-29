from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from ..domain.calculations import (
    BreakdownRow,
    assign_periods,
    compute_totals,
    days_left,
    monthly_from_prorated,
    monthly_total,
    monthly_total_full,
    need_for_month,
    paid_until_from_breakdown,
    parse_days_input,
    validate_intervals,
    validate_price,
)
from ..domain.models import BlockType, Service, ServiceState, ServiceType
from ..domain.rules import (
    KTV_BLOCK_RATE,
    KTV_MONTHLY_RATE,
    monthly_rate_for_state,
)

_TYPE_LABELS: dict[ServiceType, str] = {
    ServiceType.INTERNET: "Интернет",
    ServiceType.CTV: "ЦТВ",
    ServiceType.KTV: "КТВ",
    ServiceType.INTERCOM: "Домофон",
    ServiceType.PHONE: "Телефон",
    ServiceType.CAMERA: "Камера",
    ServiceType.EQUIPMENT: "Оборудование",
}

_STATE_LABELS: dict[ServiceState, str] = {
    ServiceState.SERVICE: "Активна (SERVICE)",
    ServiceState.BLOCK: "Блокировка (BLOCK)",
    ServiceState.ATTACH: "Подключение (ATTACH)",
    ServiceState.CANCEL: "Отмена (CANCEL)",
}

_BLOCK_LABELS: dict[BlockType, str] = {
    BlockType.VOLUNTARY: "ДБ (добровольная)",
    BlockType.FINANCIAL: "ФБ (финансовая)",
}

_DB_MARKERS = frozenset({"дб", "db"})
_FB_MARKERS = frozenset({"фб", "fb"})


def parse_block_tag(raw: str) -> tuple[str, BlockType]:
    text = raw.strip()
    if not text:
        return "без названия", BlockType.NONE

    parts = text.rsplit(None, 1)
    last = parts[-1].lower()

    if last in _DB_MARKERS:
        name = parts[0].strip() if len(parts) > 1 else "без названия"
        return name, BlockType.VOLUNTARY
    if last in _FB_MARKERS:
        name = parts[0].strip() if len(parts) > 1 else "без названия"
        return name, BlockType.FINANCIAL
    return text, BlockType.NONE


@dataclass
class CalcInput:
    today: date
    balance: Decimal
    total_current: Decimal
    total_charged: Decimal
    total_full: Decimal
    breakdown: list[BreakdownRow] = field(default_factory=list)


# ---------- ввод ----------


def _prompt_choice(title: str, options: list[tuple[object, str]]):
    print(f"\n{title}")
    for i, (_, label) in enumerate(options, 1):
        print(f"  {i}. {label}")
    while True:
        raw = input("Выбор: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        print("Некорректный выбор, попробуйте снова.")


def _prompt_decimal(title: str, default: Decimal | None = None) -> Decimal:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{title}{suffix}: ").strip().replace(",", ".")
        if not raw and default is not None:
            return default
        try:
            return Decimal(raw)
        except InvalidOperation:
            print("Некорректное число.")


def _prompt_date(title: str, default: date | None = None) -> date:
    suffix = f" [{default.isoformat()}]" if default else ""
    while True:
        raw = input(f"{title} (YYYY-MM-DD){suffix}: ").strip()
        if not raw and default is not None:
            return default
        try:
            y, m, d = (int(p) for p in raw.split("-"))
            return date(y, m, d)
        except (ValueError, TypeError):
            print("Некорректная дата.")


def _prompt_year_month(title: str, default: date) -> tuple[int, int]:
    default_str = f"{default.year:04d}-{default.month:02d}"
    while True:
        raw = input(f"{title} (YYYY-MM) [{default_str}]: ").strip()
        if not raw:
            return default.year, default.month
        try:
            y_s, m_s = raw.split("-")
            y, m = int(y_s), int(m_s)
            if 2000 <= y <= 2100 and 1 <= m <= 12:
                return y, m
        except (ValueError, AttributeError):
            pass
        print("Некорректно. Пример: 2026-09")


def _prompt_yes_no(title: str, *, default: bool | None = None) -> bool:
    suffix = " [Y/n]" if default is True else " [y/N]" if default is False else " [y/n]"
    while True:
        raw = input(f"{title}{suffix}: ").strip().lower()
        if not raw and default is not None:
            return default
        if raw in ("y", "yes", "д", "да"):
            return True
        if raw in ("n", "no", "н", "нет"):
            return False
        print("Введите y/n.")


def _prompt_service() -> Service:
    type_ = _prompt_choice("Тип услуги", [(t, _TYPE_LABELS[t]) for t in ServiceType])
    state = _prompt_choice("Состояние", [(s, _STATE_LABELS[s]) for s in ServiceState])
    block_type = BlockType.NONE
    if state is ServiceState.BLOCK:
        block_type = _prompt_choice(
            "Тип блокировки",
            [(b, _BLOCK_LABELS[b]) for b in (BlockType.VOLUNTARY, BlockType.FINANCIAL)],
        )

    if type_ is ServiceType.KTV:
        if state is ServiceState.BLOCK:
            monthly_fee = KTV_BLOCK_RATE
        else:
            monthly_fee = KTV_MONTHLY_RATE
    else:
        monthly_fee = _prompt_decimal("Тариф (₽/мес)")

    default_name = _TYPE_LABELS[type_]
    name = input(f"Название [{default_name}]: ").strip() or default_name

    return Service(
        type=type_,
        monthly_fee=monthly_fee,
        state=state,
        block_type=block_type,
        name=name,
    )


# ---------- три режима ----------


def _collect_by_total(today: date, balance: Decimal) -> CalcInput:
    total = _prompt_decimal("Абонплата в месяц (₽)")
    return CalcInput(
        today=today,
        balance=balance,
        total_current=total,
        total_charged=total,
        total_full=total,
    )


def _collect_by_services(today: date, balance: Decimal) -> CalcInput:
    services: list[Service] = []
    while True:
        print(f"\nВведено услуг: {len(services)}")
        if services and not _prompt_yes_no("Добавить ещё услугу?", default=False):
            break
        try:
            services.append(_prompt_service())
        except ValueError as exc:
            print(f"Ошибка ввода: {exc}")

    if not services:
        raise ValueError("Не добавлено ни одной услуги — считать нечего.")

    rows = [
        BreakdownRow(
            name=s.name,
            monthly=monthly_rate_for_state(s),
            block=s.block_type,
        )
        for s in services
    ]
    current = monthly_total(services)
    return CalcInput(
        today=today,
        balance=balance,
        total_current=current,
        total_charged=current,
        total_full=monthly_total_full(services),
        breakdown=rows,
    )


def _collect_by_prorated(today: date, balance: Decimal) -> CalcInput:
    rows: list[BreakdownRow] = []
    while True:
        print(f"\nВведено строк: {len(rows)}")
        if rows and not _prompt_yes_no("Добавить ещё строку?", default=False):
            break

        raw = input("Услуга (можно с пометкой ДБ/ФБ): ").strip()
        name, block = parse_block_tag(raw)

        amount = _prompt_decimal("Сумма списания (₽)")
        raw_days = input("За сколько дней / коэффициент (напр. 28 или 0.72): ").strip()
        year, month = _prompt_year_month("Месяц списания", today)

        try:
            days, days_warning = parse_days_input(raw_days, today, year, month)
        except ValueError as exc:
            print(f"Ошибка: {exc}")
            continue

        if days_warning:
            print(f"  ⚠ {days_warning}")

        try:
            monthly_raw = monthly_from_prorated(amount, days, year, month)
        except ValueError as exc:
            print(f"Ошибка: {exc}")
            continue

        check = validate_price(monthly_raw)
        rows.append(
            BreakdownRow(
                name=name,
                monthly=check.rounded,
                block=block,
                days=days,
                year=year,
                month=month,
                original_monthly=check.original if check.was_changed else None,
                days_input=days,
                days_warning=days_warning,
            )
        )

        marker = {
            BlockType.NONE: "",
            BlockType.VOLUNTARY: " [ДБ]",
            BlockType.FINANCIAL: " [ФБ]",
        }[block]

        if check.was_changed:
            print(f"  → {name}{marker}: было {check.original}, принято {check.rounded} ₽/мес")
        else:
            print(f"  → {name}{marker}: {check.rounded} ₽/мес")

    if not rows:
        raise ValueError("Не добавлено ни одной строки — считать нечего.")

    try:
        validate_intervals(rows)
    except ValueError as exc:
        raise ValueError(f"Интервалы: {exc}") from exc

    assign_periods(rows)
    current, charged = compute_totals(rows)

    return CalcInput(
        today=today,
        balance=balance,
        total_current=current,
        total_charged=charged,
        total_full=current,
        breakdown=rows,
    )


# ---------- вывод ----------

_MARKER = {
    BlockType.NONE: "",
    BlockType.VOLUNTARY: "[ДБ]",
    BlockType.FINANCIAL: "[ФБ]",
}


def _print_result(inp: CalcInput) -> None:
    paid = paid_until_from_breakdown(
        inp.balance, inp.breakdown, inp.today, fallback_monthly=inp.total_charged
    )
    dl = days_left(paid, inp.today)
    need = need_for_month(inp.balance, inp.total_charged)

    print("\n" + "=" * 60)
    print("  Результат расчёта")
    print("=" * 60)

    if inp.breakdown:
        _, reg_charged = compute_totals(inp.breakdown, BlockType.NONE)
        _, db_charged = compute_totals(inp.breakdown, BlockType.VOLUNTARY)
        _, fb_charged = compute_totals(inp.breakdown, BlockType.FINANCIAL)

        print("\nРазбивка:")
        for row in inp.breakdown:
            marker = _MARKER[row.block]
            period = ""
            if row.period_start is not None and row.period_end is not None:
                period = f" ({row.period_start}-{row.period_end}.{row.month:02d})"
            line = f"  • {row.name}{period} {marker:<6} → {row.monthly:>10} ₽/мес"
            if row.was_changed:
                line += f"   (было {row.original_monthly})"
            print(line)
            if row.days_warning:
                print(f"      ⚠ {row.days_warning}")

        print()
        print(f"Абонентская плата (текущая):  {inp.total_current:>10} ₽")
        print(f"Начислено за месяц:           {inp.total_charged:>10} ₽")
        if inp.total_full > inp.total_current:
            print(f"  при полном тарифе:          {inp.total_full:>10} ₽")
        if db_charged > 0:
            print(f"Сумма за ДБ:                  {db_charged:>10} ₽")
        if fb_charged > 0:
            print(f"Сумма за ФБ:                  {fb_charged:>10} ₽")

    print(f"\nДата расчёта:              {inp.today.isoformat()}")
    print(f"Баланс:                    {inp.balance:>10} ₽")
    if not inp.breakdown:
        print(f"Абонплата в месяц:         {inp.total_charged:>10} ₽")

    if paid is None:
        print("Оплачено по:               —")
        print("В запасе:                  —")
    else:
        print(f"Оплачено по:               {paid.isoformat()}")
        print(f"В запасе:                  {dl} дн.")

    print(f"Внести на месяц:           {need:>10} ₽")


def main() -> int:
    print("=" * 60)
    print("  Калькулятор абонентской платы «Рэдком»")
    print("=" * 60)

    try:
        today = _prompt_date("Дата расчёта", default=date.today())
        balance = _prompt_decimal("Баланс (₽, может быть отрицательным)")

        mode = _prompt_choice(
            "Как определить абонплату?",
            [
                ("total", "Знаю итоговую сумму (быстро)"),
                ("prorated", "Восстановить из списания за N дней"),
                ("services", "Введу услуги по одной"),
            ],
        )

        try:
            if mode == "total":
                inp = _collect_by_total(today, balance)
            elif mode == "prorated":
                inp = _collect_by_prorated(today, balance)
            else:
                inp = _collect_by_services(today, balance)
        except ValueError as exc:
            print(f"\n{exc}")
            return 1
    except (KeyboardInterrupt, EOFError):
        print("\nПрервано.")
        return 130

    _print_result(inp)
    return 0
