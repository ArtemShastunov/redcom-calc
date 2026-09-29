from datetime import date
from decimal import Decimal

import pytest

from redcom_calc.domain.calculations import (
    calculate_paid_until,
    days_left,
    is_nice_price,
    monthly_from_prorated,
    monthly_total,
    monthly_total_full,
    need_for_month,
    parse_days_input,
    round_to_nice,
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


def test_monthly_total_mixed_states():
    services = [
        _svc(ServiceType.INTERNET, ServiceState.SERVICE, "500"),
        _svc(ServiceType.INTERNET, ServiceState.BLOCK, "500", BlockType.VOLUNTARY),
        _svc(ServiceType.KTV, ServiceState.SERVICE, "0"),
        _svc(ServiceType.CTV, ServiceState.SERVICE, "300"),
    ]
    # monthly_total: Internet SERVICE 500 + Internet ДБ 50 + КТВ SERVICE 50 + ЦТВ 300
    assert monthly_total(services) == Decimal("900.00")
    # monthly_total_full: только неблокированные: Internet 500 + КТВ 50 + ЦТВ 300
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
    # Коэффициент 0.72 в сентябре (30 дней) → 21.6 дня
    days, warning = parse_days_input("0.72", date(2026, 9, 25), 2026, 9)
    assert days == Decimal("21.600")
    assert warning is None


def test_parse_days_coefficient_equipment():
    # Коэффициент 0.839294 в сентябре → 25.17882 дня
    days, warning = parse_days_input("0.839294", date(2026, 9, 25), 2026, 9)
    assert days == Decimal("25.178820")
    assert warning is None


def test_parse_days_coefficient_tiny():
    # Коэффициент 0.024 в сентябре → 0.72 дня
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


# ---------- интеграционные: коэффициент → месячная ставка ----------


def test_rent_125_coeff_0839_gives_150():
    # Аренда 125 ₽ за коэффициент 0.839294, сентябрь → ≈ 150 ₽/мес
    days, _ = parse_days_input("0.839294", date(2026, 9, 25), 2026, 9)
    monthly = monthly_from_prorated(Decimal(125), days, 2026, 9)
    check = validate_price(monthly)
    assert check.rounded == Decimal(150)


def test_rent_1_coeff_0024_gives_1():
    # Аренда 0.024 ₽ за коэффициент 0.024, сентябрь → 1 ₽/мес
    days, _ = parse_days_input("0.024", date(2026, 9, 25), 2026, 9)
    monthly = monthly_from_prorated(Decimal("0.024"), days, 2026, 9)
    check = validate_price(monthly)
    assert check.rounded == Decimal(1)


def test_internet_400_28_days():
    # Интернет 400 ₽ за 28 дней, сентябрь → 428.57 → 450 ₽/мес
    days, _ = parse_days_input("28", date(2026, 9, 25), 2026, 9)
    monthly = monthly_from_prorated(Decimal(400), days, 2026, 9)
    check = validate_price(monthly)
    assert check.rounded == Decimal(450)
