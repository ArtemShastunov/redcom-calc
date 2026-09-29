from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import flet as ft

from redcom_calc.cli.app import parse_block_tag
from redcom_calc.domain.calculations import (
    calculate_paid_until,
    days_left,
    monthly_from_prorated,
    need_for_month,
    parse_days_input,
    validate_price,
)
from redcom_calc.domain.models import BlockType

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
    page.window.width = 900
    page.window.height = 920
    page.window.min_width = 760
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
        content=ft.Row(
            [
                ft.Radio(value="total", label="Знаю итоговую сумму"),
                ft.Radio(value="prorated", label="Восстановить из списания"),
            ],
            spacing=24,
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

    def _build_prorated_row(idx: int):
        name_field = ft.TextField(
            label="Услуга",
            hint_text="Интернет / Аренда / Интернет ФБ",
            width=220,
            expand=False,
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

    def _build_total_row(idx: int):
        total_field = ft.TextField(
            label="Абонплата в месяц, ₽",
            width=200,
        )
        return {
            "total": total_field,
            "row": ft.Row([total_field], spacing=12),
        }

    def rebuild_rows():
        rows_ref.clear()
        rows_column.controls.clear()
        add_row()
        page.update()

    def add_row(e=None):
        idx = len(rows_ref)
        if mode_ref["value"] == "prorated":
            entry = _build_prorated_row(idx)
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
                    ft.Text(
                        block,
                        font_family="Consolas",
                        size=12,
                        selectable=True,
                    )
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
                    ft.Text(
                        spans=spans,
                        font_family="Consolas",
                        size=12,
                        selectable=True,
                    )
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

    def _collect_prorated(today: date):
        rows_blocks: list = []
        sum_regular = Decimal(0)
        sum_db = Decimal(0)
        sum_fb = Decimal(0)
        total = Decimal(0)

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
            total += monthly

            marker = _MARKER[block]
            parts: list = [
                ("  • ", None),
                (f"{name}{marker}: ", None),
            ]
            if check.was_changed:
                parts.extend(
                    [
                        (f"{check.original}", _COLOR_RED),
                        (" → ", None),
                        (f"{monthly}", _COLOR_GREEN),
                    ]
                )
            else:
                parts.append((f"{monthly}", None))
            parts.append((" ₽/мес", None))

            if days_warning:
                parts.append((f"   ⚠ {days_warning}", _COLOR_ORANGE))

            rows_blocks.append(parts)

            if block is BlockType.NONE:
                sum_regular += monthly
            elif block is BlockType.VOLUNTARY:
                sum_db += monthly
            else:
                sum_fb += monthly

        if not rows_blocks:
            raise ValueError("Не добавлено ни одной строки.")

        return total, sum_regular, sum_db, sum_fb, rows_blocks

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

        try:
            if mode_ref["value"] == "total":
                total = Decimal(rows_ref[0]["total"].value.strip().replace(",", "."))
                full = total
                sum_db = Decimal(0)
                sum_fb = Decimal(0)
                lines = [f"Знаю итоговую сумму: {total} ₽"]
            else:
                total, full, sum_db, sum_fb, lines = _collect_prorated(today)
        except (ValueError, InvalidOperation) as exc:
            page.open(ft.SnackBar(ft.Text(f"Ошибка: {exc}")))
            return

        paid = calculate_paid_until(balance, total, today)
        dl = days_left(paid, today)
        need = need_for_month(balance, total)

        out = []
        out.append("Результат расчёта")
        out.append("=" * 60)
        out.append("")
        out.extend(lines)
        out.append("")
        out.append(f"Полная абонентская плата:  {full:>10} ₽")
        if sum_db > 0:
            out.append(f"Сумма за ДБ:               {sum_db:>10} ₽")
        if sum_fb > 0:
            out.append(f"Сумма за ФБ:               {sum_fb:>10} ₽")
        out.append(f"Всего в месяц:             {total:>10} ₽")
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
