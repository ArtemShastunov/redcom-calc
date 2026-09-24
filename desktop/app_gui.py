import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from redcom_calc.domain.calculations import (
    calculate_paid_until,
    days_left,
    monthly_from_prorated,
    monthly_total,
    monthly_total_full,
    need_for_month,
)
from redcom_calc.domain.models import BlockType, Service, ServiceState, ServiceType
from redcom_calc.domain.rules import monthly_rate_for_state
from redcom_calc.cli.app import parse_block_tag


class RedcomCalcApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Калькулятор абонентской платы «Рэдком»")
        self.root.geometry("700x780")
        self.rows = []
        self._build_ui()

    def _build_ui(self):
        base_frame = ttk.LabelFrame(self.root, text="Общие данные", padding=10)
        base_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(base_frame, text="Дата расчёта (ГГГГ-ММ-ДД):").grid(row=0, column=0, sticky="w")
        self.date_entry = ttk.Entry(base_frame, width=15)
        self.date_entry.insert(0, date.today().isoformat())
        self.date_entry.grid(row=0, column=1, sticky="w", padx=5)

        ttk.Label(base_frame, text="Баланс (₽):").grid(row=1, column=0, sticky="w")
        self.balance_entry = ttk.Entry(base_frame, width=15)
        self.balance_entry.insert(0, "500.00")
        self.balance_entry.grid(row=1, column=1, sticky="w", padx=5)

        mode_frame = ttk.LabelFrame(self.root, text="Режим ввода данных", padding=10)
        mode_frame.pack(fill="x", padx=10, pady=5)

        self.mode_var = tk.StringVar(value="prorated")
        for text, val in [("Знаю итоговую сумму", "total"), ("Восстановить из списания", "prorated")]:
            ttk.Radiobutton(
                mode_frame, text=text, variable=self.mode_var, value=val,
                command=self._on_mode_change,
            ).pack(anchor="w")

        self.rows_frame = ttk.Frame(self.root)
        self.rows_frame.pack(fill="both", expand=True, padx=10, pady=5)

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10)
        ttk.Button(btn_frame, text="+ Добавить строку", command=self._add_row).pack(side="left")
        ttk.Button(btn_frame, text="- Удалить последнюю", command=self._remove_last_row).pack(side="left", padx=5)

        result_frame = ttk.LabelFrame(self.root, text="Результат", padding=10)
        result_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.result_text = tk.Text(result_frame, height=16, state="disabled", font=("Consolas", 10))
        self.result_text.pack(fill="both", expand=True)

        ttk.Button(self.root, text="РАССЧИТАТЬ", command=self._calculate).pack(pady=10, ipadx=20)

        self._add_row()

    def _on_mode_change(self):
        for row in self.rows:
            row["frame"].destroy()
        self.rows.clear()
        self._add_row()

    def _add_row(self):
        row_frame = ttk.Frame(self.rows_frame, relief="groove", borderwidth=1)
        row_frame.pack(fill="x", pady=2)

        if self.mode_var.get() == "prorated":
            ttk.Label(row_frame, text="Услуга (с ДБ/ФБ при необходимости):").pack(side="left", padx=2)
            name_entry = ttk.Entry(row_frame, width=18)
            name_entry.pack(side="left", padx=2)

            ttk.Label(row_frame, text="Сумма:").pack(side="left", padx=2)
            amount_entry = ttk.Entry(row_frame, width=10)
            amount_entry.pack(side="left", padx=2)

            ttk.Label(row_frame, text="Дней:").pack(side="left", padx=2)
            days_entry = ttk.Entry(row_frame, width=5)
            days_entry.pack(side="left", padx=2)

            ttk.Label(row_frame, text="Месяц:").pack(side="left", padx=2)
            ym_entry = ttk.Entry(row_frame, width=8)
            ym_entry.insert(0, date.today().strftime("%Y-%m"))
            ym_entry.pack(side="left", padx=2)

            self.rows.append({
                "frame": row_frame, "name": name_entry,
                "amount": amount_entry, "days": days_entry, "ym": ym_entry,
            })
        else:
            ttk.Label(row_frame, text="Абонплата в месяц (₽):").pack(side="left", padx=2)
            total_entry = ttk.Entry(row_frame, width=15)
            total_entry.pack(side="left", padx=2)
            self.rows.append({"frame": row_frame, "total": total_entry})

    def _remove_last_row(self):
        if self.rows:
            self.rows.pop()["frame"].destroy()

    def _set_result(self, text: str):
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self.result_text.configure(state="disabled")

    def _calculate(self):
        try:
            today = datetime.strptime(self.date_entry.get().strip(), "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректная дата. Ожидается ГГГГ-ММ-ДД.")
            return
        try:
            balance = Decimal(self.balance_entry.get().strip().replace(",", "."))
        except InvalidOperation:
            messagebox.showerror("Ошибка", "Некорректный баланс.")
            return

        try:
            if self.mode_var.get() == "total":
                total = Decimal(self.rows[0]["total"].get().strip().replace(",", "."))
                full = total
                sum_db = Decimal("0")
                sum_fb = Decimal("0")
                lines = [f"Знаю итоговую сумму: {total} ₽"]
            else:
                total, full, sum_db, sum_fb, lines = self._collect_prorated(today)
        except (ValueError, InvalidOperation) as exc:
            messagebox.showerror("Ошибка", str(exc))
            return

        paid = calculate_paid_until(balance, total, today)
        dl = days_left(paid, today)
        need = need_for_month(balance, total)

        out = []
        out.append("=" * 60)
        out.append("  Результат расчёта")
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

        self._set_result("\n".join(out))

    def _collect_prorated(self, today):
        rows = []
        sum_regular = Decimal("0")
        sum_db = Decimal("0")
        sum_fb = Decimal("0")
        total = Decimal("0")

        for r in self.rows:
            raw_name = r["name"].get().strip()
            if not raw_name and not r["amount"].get().strip():
                continue
            name, block = parse_block_tag(raw_name)

            amount = Decimal(r["amount"].get().strip().replace(",", "."))
            days = int(r["days"].get().strip())
            y_s, m_s = r["ym"].get().strip().split("-")
            year, month = int(y_s), int(m_s)

            monthly = monthly_from_prorated(amount, days, year, month)
            total += monthly

            marker = {BlockType.NONE: "", BlockType.VOLUNTARY: " [ДБ]", BlockType.FINANCIAL: " [ФБ]"}[block]
            rows.append(f"  • {name}{marker}: {monthly} ₽/мес")

            if block is BlockType.NONE:
                sum_regular += monthly
            elif block is BlockType.VOLUNTARY:
                sum_db += monthly
            else:
                sum_fb += monthly

        if not rows:
            raise ValueError("Не добавлено ни одной строки.")

        lines = ["Разбивка:"]
        lines.extend(rows)
        return total, sum_regular, sum_db, sum_fb, lines


if __name__ == "__main__":
    root = tk.Tk()
    app = RedcomCalcApp(root)
    root.mainloop()
