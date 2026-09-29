from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import flet as ft

from redcom_calc.cli.app import parse_block_tag
from redcom_calc.domain.calculations import (
    BreakdownRow,
    assign_periods,
    compute_totals,
    days_left,
    monthly_from_prorated,
    need_for_month,
    paid_until_from_breakdown,
    parse_days_input,
    validate_intervals,
    validate_price,
)
from redcom_calc.domain.models import (
    BlockType,
    Service,
    ServiceState,
    ServiceType,
)
from redcom_calc.domain.rules import monthly_rate_for_state

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
    ServiceState.SERVICE: "Активна",
    ServiceState.BLOCK: "Блокировка",
    ServiceState.ATTACH: "Подключение",
    ServiceState.CANCEL: "Отмена",
}

_BLOCK_LABELS: dict[BlockType, str] = {
    BlockType.VOLUNTARY: "ДБ (добровольная)",
    BlockType.FINANCIAL: "ФБ (финансовая)",
}

_MARKER = {
    BlockType.NONE: "",
    BlockType.VOLUNTARY: " [ДБ]",
    BlockType.FINANCIAL: " [ФБ]",
}

_COLOR_MUTED = "#5F6368"
_COLOR_SURFACE_SOFT = "#F1F3F4"
_COLOR_BTN_NEUTRAL = "#E8EAED"
_COLOR_RED = "#D32F2F"
_COLOR_GREEN = "#2E7D32"
_COLOR_ORANGE = "#E65100"


def main(page: ft.Page):
    page.title = "Калькулятор абонентской платы — Рэдком"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.padding = 24
    page.window.width = 980
    page.window.height = 980
    page.window.min_width = 820
    page.window.min_height = 700
    page.scroll = ft.ScrollMode.AUTO

    rows_ref: list[dict] = []
    result_column = ft.Column(spacing=2)
    result_plain: list[str] = []

    header = ft.Column(
        [
            ft.Text(
                "Калькулятор абонентской платы",
                size=22,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                "Рэдком · внутренний инструмент менеджера",
                size=13,
                color=_COLOR_MUTED,
            ),
        ],
        spacing=2,
    )

    date_field = ft.TextField(
        label="Дата расчёта",
        value=date.today().isoformat(),
        width=180,
        hint_text="ГГГГ-ММ-ДД",
    )
    balance_field = ft.TextField(
        label="Баланс, ₽",
        value="500.00",
        width=200,
        hint_text="может быть отрицательным",
    )

    base_card = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text("Общие данные", size=15, weight=ft.FontWeight.BOLD),
                    ft.Row([date_field, balance_field], spacing=16),
                ],
                spacing=12,
            ),
            padding=20,
        ),
    )

    mode_ref = {"value": "prorated"}

    def on_mode_change(e):
        mode_ref["value"] = e.control.value
        rebuild_rows()

    mode_radio = ft.RadioGroup(
        value="prorated",
        on_change=on_mode_change,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Radio(value="total", label="Знаю итоговую сумму"),
                        ft.Radio(value="prorated", label="Восстановить из списания"),
                    ],
                    spacing=24,
                ),
                ft.Row(
                    [
                        ft.Radio(value="services", label="Услуги с типом и списанием"),
                    ],
                    spacing=24,
                ),
            ],
            spacing=8,
        ),
    )

    mode_card = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text("Режим ввода", size=15, weight=ft.FontWeight.BOLD),
                    mode_radio,
                ],
                spacing=12,
            ),
            padding=20,
        ),
    )

    rows_column = ft.Column(spacing=8)

    def _build_total_row(idx: int):
        total_field = ft.TextField(label="Абонплата в месяц, ₽", width=200)
        return {
            "total": total_field,
            "row": ft.Row([total_field], spacing=12),
        }

    def _build_prorated_row(idx: int):
        name_field = ft.TextField(
            label="Услуга",
            hint_text="Интернет / Аренда / Интернет ФБ",
            width=220,
        )
        amount_field = ft.TextField(label="Сумма ₽", width=110)
        days_field = ft.TextField(
            label="Дней или коэф.",
            width=140,
            hint_text="28 или 0.72",
        )
        ym_field = ft.TextField(
            label="Месяц",
            value=date.today().strftime("%Y-%m"),
            width=110,
        )
        return {
            "name": name_field,
            "amount": amount_field,
            "days": days_field,
            "ym": ym_field,
            "row": ft.Row(
                [name_field, amount_field, days_field, ym_field],
                spacing=12,
                wrap=True,
            ),
        }

    def _build_services_row(idx: int):
        type_dd = ft.Dropdown(
            label="Тип услуги",
            width=170,
            options=[
                ft.dropdown.Option(key=t.value, text=label) for t, label in _TYPE_LABELS.items()
            ],
            value=ServiceType.INTERNET.value,
        )
        state_dd = ft.Dropdown(
            label="Состояние",
            width=170,
            options=[
                ft.dropdown.Option(key=s.value, text=label) for s, label in _STATE_LABELS.items()
            ],
            value=ServiceState.SERVICE.value,
        )
        block_dd = ft.Dropdown(
            label="Тип блокировки",
            width=200,
            options=[
                ft.dropdown.Option(key=b.value, text=label) for b, label in _BLOCK_LABELS.items()
            ],
            value=BlockType.VOLUNTARY.value,
            visible=False,
        )
        name_field = ft.TextField(
            label="Название",
            width=220,
            hint_text="опционально",
        )

        amount_field = ft.TextField(
            label="Сумма списания, ₽",
            width=180,
            hint_text="что показал Fastcom",
        )
        days_field = ft.TextField(
            label="Дней / коэф.",
            width=140,
            hint_text="28 или 0.72",
        )
        ym_field = ft.TextField(
            label="Месяц",
            value=date.today().strftime("%Y-%m"),
            width=110,
        )

        def refresh_visibility(e=None):
            state = ServiceState(state_dd.value)
            block_dd.visible = state is ServiceState.BLOCK
            page.update()

        state_dd.on_change = refresh_visibility

        entry = {
            "type": type_dd,
            "state": state_dd,
            "block": block_dd,
            "name": name_field,
            "amount": amount_field,
            "days": days_field,
            "ym": ym_field,
        }
        entry["row"] = ft.Column(
            [
                ft.Row([type_dd, state_dd, block_dd, name_field], spacing=12, wrap=True),
                ft.Row([amount_field, days_field, ym_field], spacing=12, wrap=True),
            ],
            spacing=8,
        )
        refresh_visibility()
        return entry

    def rebuild_rows():
        rows_ref.clear()
        rows_column.controls.clear()
        add_row()
        page.update()

    def add_row(e=None):
        idx = len(rows_ref)
        m = mode_ref["value"]
        if m == "prorated":
            entry = _build_prorated_row(idx)
        elif m == "services":
            entry = _build_services_row(idx)
        else:
            entry = _build_total_row(idx)
        rows_ref.append(entry)
        rows_column.controls.append(entry["row"])
        page.update()

    def remove_last_row(e=None):
        if rows_ref:
            entry = rows_ref.pop()
            rows_column.controls.remove(entry["row"])
            page.update()

    rows_card = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text("Строки ввода", size=15, weight=ft.FontWeight.BOLD),
                    rows_column,
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "+ Добавить строку",
                                icon=ft.Icons.ADD,
                                on_click=add_row,
                            ),
                            ft.ElevatedButton(
                                "— Удалить последнюю",
                                icon=ft.Icons.REMOVE,
                                on_click=remove_last_row,
                                style=ft.ButtonStyle(bgcolor=_COLOR_BTN_NEUTRAL),
                            ),
                        ],
                        spacing=12,
                    ),
                ],
                spacing=14,
            ),
            padding=20,
        ),
    )

    def _set_result_rich(blocks: list) -> None:
        flat: list[str] = []
        result_column.controls.clear()
        for block in blocks:
            if isinstance(block, str):
                flat.append(block)
                result_column.controls.append(
                    ft.Text(block, font_family="Consolas", size=12, selectable=True)
                )
            else:
                spans = []
                plain = []
                for text, color in block:
                    plain.append(text)
                    if color:
                        spans.append(ft.TextSpan(text, style=ft.TextStyle(color=color)))
                    else:
                        spans.append(ft.TextSpan(text))
                flat.append("".join(plain))
                result_column.controls.append(
                    ft.Text(spans=spans, font_family="Consolas", size=12, selectable=True)
                )
        result_plain.clear()
        result_plain.extend(flat)
        page.update()

    def copy_result(e):
        if result_plain:
            page.set_clipboard("\n".join(result_plain))
            page.open(ft.SnackBar(ft.Text("Результат скопирован")))

    result_card = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Результат", size=15, weight=ft.FontWeight.BOLD),
                            ft.TextButton(
                                "Копировать",
                                icon=ft.Icons.COPY,
                                on_click=copy_result,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Container(
                        content=result_column,
                        padding=12,
                        border_radius=8,
                        bgcolor=_COLOR_SURFACE_SOFT,
                    ),
                ],
                spacing=10,
            ),
            padding=20,
        ),
    )

    def _render_breakdown_lines(breakdown: list[BreakdownRow]) -> list:
        """Собрать строки разбивки с учётом периодов."""
        blocks: list = []
        for row in breakdown:
            marker = _MARKER[row.block]
            name_label = row.name
            if row.period_start is not None and row.period_end is not None:
                name_label += f" ({row.period_start}-{row.period_end}.{row.month:02d})"

            parts: list = [
                ("  • ", None),
                (f"{name_label}{marker}: ", None),
            ]
            if row.was_changed:
                parts.extend(
                    [
                        (f"{row.original_monthly}", _COLOR_RED),
                        (" → ", None),
                        (f"{row.monthly}", _COLOR_GREEN),
                    ]
                )
            else:
                parts.append((f"{row.monthly}", None))
            parts.append((" ₽/мес", None))

            if row.days_warning:
                parts.append((f"   ⚠ {row.days_warning}", _COLOR_ORANGE))

            blocks.append(parts)
        return blocks

    def _collect_prorated(today: date):
        breakdown: list[BreakdownRow] = []

        for r in rows_ref:
            raw_name = (r["name"].value or "").strip()
            amount_raw = (r["amount"].value or "").strip()
            if not raw_name and not amount_raw:
                continue

            name, block = parse_block_tag(raw_name)
            amount = Decimal(amount_raw.replace(",", "."))
            raw_days = (r["days"].value or "").strip()

            y_s, m_s = (r["ym"].value or "").strip().split("-")
            year, month = int(y_s), int(m_s)

            try:
                days, days_warning = parse_days_input(raw_days, today, year, month)
            except ValueError as exc:
                raise ValueError(f"{name}: {exc}") from exc

            monthly_raw = monthly_from_prorated(amount, days, year, month)
            check = validate_price(monthly_raw)
            monthly = check.rounded

            breakdown.append(
                BreakdownRow(
                    name=name,
                    monthly=monthly,
                    block=block,
                    days=days,
                    year=year,
                    month=month,
                    original_monthly=check.original if check.was_changed else None,
                    days_warning=days_warning,
                )
            )

        if not breakdown:
            raise ValueError("Не добавлено ни одной строки.")

        validate_intervals(breakdown)
        assign_periods(breakdown)

        total_current, total_charged = compute_totals(breakdown)
        lines = _render_breakdown_lines(breakdown)

        return {
            "total_current": total_current,
            "total_charged": total_charged,
            "total_full": total_current,
            "lines": lines,
            "breakdown": breakdown,
        }

    def _collect_services(today: date):
        breakdown: list[BreakdownRow] = []
        services: list[Service] = []

        for r in rows_ref:
            typ = ServiceType(r["type"].value)
            state = ServiceState(r["state"].value)
            if state is ServiceState.BLOCK:
                block = BlockType(r["block"].value)
            else:
                block = BlockType.NONE

            name = (r["name"].value or "").strip() or _TYPE_LABELS[typ]

            amount_raw = (r["amount"].value or "").strip()
            raw_days = (r["days"].value or "").strip()
            ym_raw = (r["ym"].value or "").strip()

            if not amount_raw:
                raise ValueError(f"{name}: укажите сумму списания")

            try:
                amount = Decimal(amount_raw.replace(",", "."))
            except InvalidOperation as exc:
                raise ValueError(f"{name}: некорректная сумма") from exc

            try:
                y_s, m_s = ym_raw.split("-")
                year, month = int(y_s), int(m_s)
            except (ValueError, AttributeError) as exc:
                raise ValueError(f"{name}: некорректный месяц") from exc

            try:
                days, days_warning = parse_days_input(raw_days, today, year, month)
            except ValueError as exc:
                raise ValueError(f"{name}: {exc}") from exc

            monthly_from_fastcom = monthly_from_prorated(amount, days, year, month)
            check = validate_price(monthly_from_fastcom)
            monthly_rounded = check.rounded

            temp_svc = Service(
                type=typ,
                monthly_fee=monthly_rounded,
                state=state,
                block_type=block,
                name=name,
            )
            monthly_final = monthly_rate_for_state(temp_svc)
            services.append(temp_svc)

            breakdown.append(
                BreakdownRow(
                    name=name,
                    monthly=monthly_final,
                    block=block,
                    days=days,
                    year=year,
                    month=month,
                    original_monthly=check.original if check.was_changed else None,
                    days_warning=days_warning,
                )
            )

        if not breakdown:
            raise ValueError("Не добавлено ни одной услуги.")

        validate_intervals(breakdown)
        assign_periods(breakdown)

        total_current, total_charged = compute_totals(breakdown)
        lines = _render_breakdown_lines(breakdown)

        return {
            "total_current": total_current,
            "total_charged": total_charged,
            "total_full": total_current,
            "lines": lines,
            "breakdown": breakdown,
        }

    def calculate(e):
        try:
            today = datetime.strptime(date_field.value.strip(), "%Y-%m-%d").date()
        except ValueError:
            page.open(ft.SnackBar(ft.Text("Некорректная дата. Ожидается ГГГГ-ММ-ДД.")))
            return
        try:
            balance = Decimal(balance_field.value.strip().replace(",", "."))
        except InvalidOperation:
            page.open(ft.SnackBar(ft.Text("Некорректный баланс.")))
            return

        m = mode_ref["value"]
        breakdown: list[BreakdownRow] = []
        try:
            if m == "total":
                total = Decimal(rows_ref[0]["total"].value.strip().replace(",", "."))
                total_current = total
                total_charged = total
                total_full = total
                lines = [f"Знаю итоговую сумму: {total} ₽"]
            elif m == "services":
                res = _collect_services(today)
                total_current = res["total_current"]
                total_charged = res["total_charged"]
                total_full = res["total_full"]
                lines = res["lines"]
                breakdown = res["breakdown"]
            else:
                res = _collect_prorated(today)
                total_current = res["total_current"]
                total_charged = res["total_charged"]
                total_full = res["total_full"]
                lines = res["lines"]
                breakdown = res["breakdown"]
        except (ValueError, InvalidOperation) as exc:
            page.open(ft.SnackBar(ft.Text(f"Ошибка: {exc}")))
            return

        paid = paid_until_from_breakdown(balance, breakdown, today, fallback_monthly=total_charged)
        dl = days_left(paid, today)
        need = need_for_month(balance, total_charged)

        out = []
        out.append("Результат расчёта")
        out.append("=" * 60)
        out.append("")
        out.extend(lines)
        out.append("")

        if breakdown:
            _, db_charged = compute_totals(breakdown, BlockType.VOLUNTARY)
            _, fb_charged = compute_totals(breakdown, BlockType.FINANCIAL)

            out.append(f"Абонентская плата (текущая):  {total_current:>10} ₽")
            out.append(f"Начислено за месяц:           {total_charged:>10} ₽")
            if total_full > total_current:
                out.append(f"  при полном тарифе:          {total_full:>10} ₽")
            if db_charged > 0:
                out.append(f"Сумма за ДБ:                  {db_charged:>10} ₽")
            if fb_charged > 0:
                out.append(f"Сумма за ФБ:                  {fb_charged:>10} ₽")
        else:
            out.append(f"Абонплата в месяц:            {total_charged:>10} ₽")

        out.append("")
        out.append(f"Дата расчёта:              {today.isoformat()}")
        out.append(f"Баланс:                    {balance:>10} ₽")
        if paid is None:
            out.append("Оплачено по:               —")
            out.append("В запасе:                  —")
        else:
            out.append(f"Оплачено по:               {paid.isoformat()}")
            out.append(f"В запасе:                  {dl} дн.")
        out.append(f"Внести на месяц:           {need:>10} ₽")

        _set_result_rich(out)

    calc_button = ft.ElevatedButton(
        "РАССЧИТАТЬ",
        icon=ft.Icons.CALCULATE,
        on_click=calculate,
        height=46,
        style=ft.ButtonStyle(
            text_style=ft.TextStyle(size=15, weight=ft.FontWeight.BOLD),
        ),
    )

    page.add(
        ft.Column(
            [
                header,
                base_card,
                mode_card,
                rows_card,
                calc_button,
                result_card,
            ],
            spacing=16,
            expand=True,
        )
    )

    add_row()


if __name__ == "__main__":
    ft.app(main)
