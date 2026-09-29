from datetime import date
from decimal import Decimal

import pytest

from redcom_calc.domain.calculations import (
    BreakdownRow,
    assign_periods,
    calculate_paid_until,
    compute_totals,
    days_left,
    is_nice_price,
    monthly_from_prorated,
    monthly_total,
    monthly_total_full,
    need_for_month,
    paid_until_from_breakdown,
    parse_days_input,
    round_to_nice,
    validate_intervals,
    validate_price,
)
from redcom_calc.domain.models import BlockType, Service, ServiceState, ServiceType


def _svc(type_, state, fee, block=BlockType.NONE):
    return Service(
        type=type_,
        monthly_fee=Decimal(fee),
        state=state,
        block_type=block,
    )


# ---------- базовые ----------


def test_monthly_total_mixed_states():
    services = [
        _svc(ServiceType.INTERNET, ServiceState.SERVICE, "500"),
        _svc(ServiceType.INTERNET, ServiceState.BLOCK, "500", BlockType.VOLUNTARY),
        _svc(ServiceType.KTV, ServiceState.SERVICE, "0"),
        _svc(ServiceType.CTV, ServiceState.SERVICE, "300"),
    ]
    assert monthly_total(services) == Decimal("900.00")
    assert monthly_total_full(services) == Decimal("850.00")


def test_paid_until_matches_tz_example():
    paid = calculate_paid_until(Decimal(500), Decimal(500), date(2026, 9, 18))
    assert paid == date(2026, 10, 17)
    assert days_left(paid, date(2026, 9, 18)) == 30


def test_paid_until_none_when_balance_zero():
    assert calculate_paid_until(Decimal(0), Decimal(500), date(2026, 9, 18)) is None


def test_paid_until_none_when_balance_negative():
    assert calculate_paid_until(Decimal(-100), Decimal(500), date(2026, 9, 18)) is None


def test_paid_until_none_when_monthly_zero():
    assert calculate_paid_until(Decimal(1000), Decimal(0), date(2026, 9, 18)) is None


def test_paid_until_insufficient_for_today():
    assert calculate_paid_until(Decimal(10), Decimal(500), date(2026, 9, 18)) is None


def test_paid_until_multi_month():
    paid = calculate_paid_until(Decimal(1000), Decimal(500), date(2026, 9, 18))
    assert paid is not None
    assert paid > date(2026, 10, 15)


def test_need_for_month_cases():
    assert need_for_month(Decimal(1500), Decimal(500)) == Decimal("0.00")
    assert need_for_month(Decimal(250), Decimal(500)) == Decimal("250.00")
    assert need_for_month(Decimal(0), Decimal(500)) == Decimal("500.00")
    assert need_for_month(Decimal(-50), Decimal(1250)) == Decimal("1300.00")
    assert need_for_month(Decimal(-100), Decimal(0)) == Decimal("0.00")


# ---------- monthly_from_prorated ----------


def test_prorated_september():
    assert monthly_from_prorated(Decimal(250), 15, 2026, 9) == Decimal("500.00")


def test_prorated_august():
    assert monthly_from_prorated(Decimal(125), 10, 2026, 8) == Decimal("387.50")


def test_prorated_february_non_leap():
    assert monthly_from_prorated(Decimal(100), 7, 2026, 2) == Decimal("400.00")


def test_prorated_february_leap():
    assert monthly_from_prorated(Decimal(145), 10, 2028, 2) == Decimal("420.50")


def test_prorated_rejects_zero_days():
    with pytest.raises(ValueError):
        monthly_from_prorated(Decimal(250), 0, 2026, 9)


def test_prorated_rejects_too_many_days():
    with pytest.raises(ValueError):
        monthly_from_prorated(Decimal(500), 31, 2026, 9)


def test_prorated_rejects_negative_amount():
    with pytest.raises(ValueError):
        monthly_from_prorated(Decimal(-10), 5, 2026, 9)


def test_prorated_is_inverse_of_forward_formula():
    monthly = monthly_from_prorated(Decimal(250), 15, 2026, 9)
    forward = (monthly / Decimal(30) * Decimal(15)).quantize(Decimal("0.01"))
    assert forward == Decimal("250.00")


# ---------- валидация цен ----------


def test_is_nice_price_typical():
    assert is_nice_price(Decimal(400))
    assert is_nice_price(Decimal(500))
    assert is_nice_price(Decimal(550))
    assert is_nice_price(Decimal(50))


def test_is_nice_price_exceptions():
    assert is_nice_price(Decimal(0))
    assert is_nice_price(Decimal(1))


def test_is_nice_price_not_nice():
    assert not is_nice_price(Decimal(404))
    assert not is_nice_price(Decimal(199))
    assert not is_nice_price(Decimal(425))


def test_round_to_nice_unchanged():
    assert round_to_nice(Decimal(400)) == Decimal(400)
    assert round_to_nice(Decimal(550)) == Decimal(550)
    assert round_to_nice(Decimal(1)) == Decimal(1)
    assert round_to_nice(Decimal(0)) == Decimal(0)


def test_round_to_nice_rounds_down():
    assert round_to_nice(Decimal(404)) == Decimal(400)
    assert round_to_nice(Decimal(420)) == Decimal(400)


def test_round_to_nice_rounds_up():
    assert round_to_nice(Decimal(476)) == Decimal(500)
    assert round_to_nice(Decimal(430)) == Decimal(450)


def test_round_to_nice_ties_go_down():
    assert round_to_nice(Decimal(425)) == Decimal(400)
    assert round_to_nice(Decimal(475)) == Decimal(450)


def test_validate_price_marks_change():
    check = validate_price(Decimal(404))
    assert check.original == Decimal(404)
    assert check.rounded == Decimal(400)
    assert check.was_changed


def test_validate_price_no_change():
    check = validate_price(Decimal(400))
    assert check.rounded == Decimal(400)
    assert not check.was_changed


# ---------- parse_days_input ----------


def test_parse_days_integer():
    days, warning = parse_days_input("28", date(2026, 9, 25), 2026, 9)
    assert days == Decimal(28)
    assert warning is None


def test_parse_days_coefficient_typical():
    days, warning = parse_days_input("0.72", date(2026, 9, 25), 2026, 9)
    assert days == Decimal("21.600")
    assert warning is None


def test_parse_days_coefficient_equipment():
    days, warning = parse_days_input("0.839294", date(2026, 9, 25), 2026, 9)
    assert days == Decimal("25.178820")
    assert warning is None


def test_parse_days_coefficient_tiny():
    days, warning = parse_days_input("0.024", date(2026, 9, 25), 2026, 9)
    assert days == Decimal("0.720")
    assert warning is None


def test_parse_days_comma_decimal():
    days, warning = parse_days_input("0,5", date(2026, 9, 25), 2026, 9)
    assert days == Decimal("15.0")
    assert warning is None


def test_parse_days_one_other_month():
    days, warning = parse_days_input("1", date(2026, 9, 25), 2026, 8)
    assert days == Decimal(1)
    assert warning is None


def test_parse_days_one_current_month_early():
    days, warning = parse_days_input("1", date(2026, 9, 2), 2026, 9)
    assert days == Decimal(1)
    assert warning is None


def test_parse_days_one_current_month_late():
    days, warning = parse_days_input("1", date(2026, 9, 25), 2026, 9)
    assert days == Decimal(1)
    assert warning is not None
    assert "1 день" in warning


def test_parse_days_zero_rejected():
    with pytest.raises(ValueError):
        parse_days_input("0", date(2026, 9, 25), 2026, 9)


def test_parse_days_negative_rejected():
    with pytest.raises(ValueError):
        parse_days_input("-5", date(2026, 9, 25), 2026, 9)


def test_parse_days_nonsense_rejected():
    with pytest.raises(ValueError):
        parse_days_input("abc", date(2026, 9, 25), 2026, 9)


def test_parse_days_empty_rejected():
    with pytest.raises(ValueError):
        parse_days_input("", date(2026, 9, 25), 2026, 9)


def test_parse_days_too_many_rejected():
    with pytest.raises(ValueError):
        parse_days_input("31", date(2026, 9, 25), 2026, 9)


# ---------- интеграционные ----------


def test_rent_125_coeff_0839_gives_150():
    days, _ = parse_days_input("0.839294", date(2026, 9, 25), 2026, 9)
    monthly = monthly_from_prorated(Decimal(125), days, 2026, 9)
    check = validate_price(monthly)
    assert check.rounded == Decimal(150)


def test_rent_1_coeff_0024_gives_1():
    days, _ = parse_days_input("0.024", date(2026, 9, 25), 2026, 9)
    monthly = monthly_from_prorated(Decimal("0.024"), days, 2026, 9)
    check = validate_price(monthly)
    assert check.rounded == Decimal(1)


def test_internet_400_28_days():
    days, _ = parse_days_input("28", date(2026, 9, 25), 2026, 9)
    monthly = monthly_from_prorated(Decimal(400), days, 2026, 9)
    check = validate_price(monthly)
    assert check.rounded == Decimal(450)


# ---------- интервалы ----------


def _interval_row(name, monthly, days, year, month, block=BlockType.NONE):
    return BreakdownRow(
        name=name,
        monthly=Decimal(monthly),
        block=block,
        days=Decimal(days),
        year=year,
        month=month,
    )


def test_validate_intervals_ok():
    rows = [
        _interval_row("Интернет", "600", "15", 2026, 9),
        _interval_row("Интернет", "900", "15", 2026, 9),
    ]
    validate_intervals(rows)


def test_validate_intervals_mismatch():
    rows = [
        _interval_row("Интернет", "600", "14", 2026, 9),
    ]
    with pytest.raises(ValueError) as exc:
        validate_intervals(rows)
    assert "Интернет" in str(exc.value)


def test_validate_intervals_no_days_ok():
    rows = [BreakdownRow(name="Интернет", monthly=Decimal(500))]
    validate_intervals(rows)


def test_assign_periods_two_intervals():
    rows = [
        _interval_row("Интернет", "600", "15", 2026, 9),
        _interval_row("Интернет", "900", "15", 2026, 9),
    ]
    assign_periods(rows)
    assert rows[0].period_start == 1
    assert rows[0].period_end == 15
    assert rows[1].period_start == 16
    assert rows[1].period_end == 30


def test_assign_periods_three_intervals():
    rows = [
        _interval_row("Интернет", "600", "10", 2026, 9),
        _interval_row("Интернет", "800", "10", 2026, 9),
        _interval_row("Интернет", "900", "10", 2026, 9),
    ]
    assign_periods(rows)
    assert (rows[0].period_start, rows[0].period_end) == (1, 10)
    assert (rows[1].period_start, rows[1].period_end) == (11, 20)
    assert (rows[2].period_start, rows[2].period_end) == (21, 30)


def test_assign_periods_skips_fractional():
    rows = [_interval_row("Интернет", "600", "15.5", 2026, 9)]
    assign_periods(rows)
    assert rows[0].period_start is None
    assert rows[0].period_end is None


def test_compute_totals_no_intervals():
    rows = [
        BreakdownRow(name="Интернет", monthly=Decimal(500)),
        BreakdownRow(name="КТВ", monthly=Decimal(50)),
    ]
    current, charged = compute_totals(rows)
    assert current == Decimal("550.00")
    assert charged == Decimal("550.00")


def test_compute_totals_two_intervals_same_service():
    # Интернет 600/15 + 900/15 в сентябре.
    # current = последняя = 900
    # charged = 600*15/30 + 900*15/30 = 300 + 450 = 750
    rows = [
        _interval_row("Интернет", "600", "15", 2026, 9),
        _interval_row("Интернет", "900", "15", 2026, 9),
    ]
    current, charged = compute_totals(rows)
    assert current == Decimal("900.00")
    assert charged == Decimal("750.00")


def test_compute_totals_two_services_with_intervals():
    rows = [
        _interval_row("Интернет", "600", "15", 2026, 9),
        _interval_row("Интернет", "900", "15", 2026, 9),
        BreakdownRow(name="Аренда", monthly=Decimal(1)),
    ]
    current, charged = compute_totals(rows)
    # current = 900 (последняя Интернета) + 1 (Аренда) = 901
    # charged = 750 (Интернета) + 1 (Аренда) = 751
    assert current == Decimal("901.00")
    assert charged == Decimal("751.00")


def test_compute_totals_filter_by_block():
    rows = [
        BreakdownRow(name="Интернет", monthly=Decimal(500)),
        BreakdownRow(name="Интернет ДБ", monthly=Decimal(50), block=BlockType.VOLUNTARY),
        BreakdownRow(name="Интернет ФБ", monthly=Decimal(150), block=BlockType.FINANCIAL),
    ]
    reg_cur, reg_chr = compute_totals(rows, BlockType.NONE)
    db_cur, db_chr = compute_totals(rows, BlockType.VOLUNTARY)
    fb_cur, fb_chr = compute_totals(rows, BlockType.FINANCIAL)
    assert reg_chr == Decimal("500.00")
    assert db_chr == Decimal("50.00")
    assert fb_chr == Decimal("150.00")


# ---------- paid_until_from_breakdown ----------


def test_paid_until_no_intervals_fallback():
    rows = [BreakdownRow(name="Интернет", monthly=Decimal(500))]
    paid = paid_until_from_breakdown(
        Decimal(500), rows, date(2026, 9, 18), fallback_monthly=Decimal(500)
    )
    assert paid == date(2026, 10, 17)


def test_paid_until_empty_breakdown_uses_fallback():
    paid = paid_until_from_breakdown(
        Decimal(500), [], date(2026, 9, 18), fallback_monthly=Decimal(500)
    )
    assert paid == date(2026, 10, 17)


def test_paid_until_single_interval_matches_regular():
    rows = [_interval_row("Интернет", "500", "30", 2026, 9)]
    paid = paid_until_from_breakdown(Decimal(500), rows, date(2026, 9, 18))
    assert paid == date(2026, 10, 17)


def test_paid_until_with_intervals_differs_from_average():
    # Баланс 400, две ставки: 600/мес (1-15), 900/мес (16-30).
    # С 25 сентября: 6 * (900/30) = 180. Остаток 220.
    # Октябрь: 900/31 ≈ 29.03. Хватит на 7 дней → 7 октября.
    rows = [
        _interval_row("Интернет", "600", "15", 2026, 9),
        _interval_row("Интернет", "900", "15", 2026, 9),
    ]
    paid = paid_until_from_breakdown(Decimal(400), rows, date(2026, 9, 25))
    assert paid == date(2026, 10, 7)


def test_paid_until_average_is_different():
    # Средняя 750/мес: 6 * (750/30) = 150. Остаток 250.
    # Октябрь: 750/31 ≈ 24.19. Хватит на 10 дней → 10 октября.
    paid = calculate_paid_until(Decimal(400), Decimal(750), date(2026, 9, 25))
    assert paid == date(2026, 10, 10)


def test_paid_until_intervals_with_second_service():
    rows = [
        _interval_row("Интернет", "600", "15", 2026, 9),
        _interval_row("Интернет", "900", "15", 2026, 9),
        BreakdownRow(name="Аренда", monthly=Decimal(1)),
    ]
    paid = paid_until_from_breakdown(Decimal(400), rows, date(2026, 9, 25))
    assert paid == date(2026, 10, 7)


def test_paid_until_intervals_none_when_balance_zero():
    rows = [
        _interval_row("Интернет", "600", "15", 2026, 9),
        _interval_row("Интернет", "900", "15", 2026, 9),
    ]
    assert paid_until_from_breakdown(Decimal(0), rows, date(2026, 9, 25)) is None


def test_paid_until_intervals_negative_balance():
    rows = [
        _interval_row("Интернет", "600", "15", 2026, 9),
        _interval_row("Интернет", "900", "15", 2026, 9),
    ]
    assert paid_until_from_breakdown(Decimal(-100), rows, date(2026, 9, 25)) is None
