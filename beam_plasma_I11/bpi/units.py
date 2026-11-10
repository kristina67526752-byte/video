"""
Вывод чисел в СИ с десятичными приставками.

Данные внутри программы всегда хранятся в основных единицах СИ (м, с, В/м …).
Для осей графиков и таблиц подбирается удобный множитель 10^(3n):
    * простая единица получает приставку СИ:  0.0107 м → 10.7 мм,  1.8·10⁻⁹ с → 1.8 нс;
    * составная единица (м/с, рад/с, рад/м, м⁻³) — множитель «10ⁿ»:  1.0·10⁷ м/с.
"""
from __future__ import annotations

import math

PREFIX = {-15: "ф", -12: "п", -9: "н", -6: "мк", -3: "м", 0: "", 3: "к", 6: "М", 9: "Г", 12: "Т"}
_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
# единицы, к которым приставка СИ приписывается напрямую
SIMPLE = {"м", "с", "В/м", "Гц", "Дж/м³", "Дж", "В", "К", "Кл/м³", "А/м²", "Вт/м²", "Па"}


def sup(n: int) -> str:
    """Целое число верхними индексами: −3 → «⁻³»."""
    return str(int(n)).translate(_SUP)


def pow10(n: int) -> str:
    return "10" + sup(n)


def exp3(value: float) -> int:
    """Показатель степени, кратный 3, такой что value/10^exp ∈ [1, 1000)."""
    if not math.isfinite(value) or value == 0:
        return 0
    return int(math.floor(math.log10(abs(value)) / 3.0)) * 3


class Scale:
    """Масштаб оси: factor — на что умножать значения в СИ, label — подпись единицы.

        s = Scale(0.0107, "м")      →  s.factor = 1e3,  s.label = "мм"
        s = Scale(1.0e7, "м/с")     →  s.factor = 1e-6, s.label = "10⁶ м/с"
    """

    def __init__(self, typical: float, unit: str):
        e = exp3(typical)
        self.unit = unit
        if unit in SIMPLE and e in PREFIX:
            self.exp = e
            self.label = PREFIX[e] + unit
        elif unit in SIMPLE:
            self.exp = e
            self.label = f"{pow10(e)} {unit}"
        else:
            # составные единицы: множитель — точная степень десяти (значения оси от 1 до 10)
            self.exp = int(math.floor(math.log10(abs(typical)))) if typical else 0
            self.label = unit if self.exp == 0 else f"{pow10(self.exp)} {unit}"
        self.factor = 10.0 ** (-self.exp)

    def __call__(self, x):
        return x * self.factor

    def formatter(self, fmt="{:g}"):
        """Форматтер делений оси matplotlib: данные в СИ, подписи — в единицах масштаба."""
        from matplotlib.ticker import FuncFormatter
        f = self.factor
        return FuncFormatter(lambda v, pos: fmt.format(round(v * f, 10) + 0.0))


def sci(x: float, digits: int = 3) -> str:
    """Число в виде «1.23·10⁷» (или обычном, если порядок от 10⁻² до 10⁴)."""
    if x == 0 or not math.isfinite(x):
        return "0" if x == 0 else str(x)
    e = int(math.floor(math.log10(abs(x))))
    if -2 <= e < 4:
        d = max(digits - 1 - e, 0)
        return f"{x:.{d}f}"
    m = x / 10.0 ** e
    s = f"{m:.{digits - 1}f}"
    if s.startswith("10"):                 # 9.999 → 10.00
        e += 1
        s = f"{x / 10.0 ** e:.{digits - 1}f}"
    return f"{s}·{pow10(e)}"


def fmt(x: float, unit: str, digits: int = 3) -> str:
    """Число с единицей: приставка СИ для простых единиц, «·10ⁿ» для составных.
        fmt(8.98e8, "Гц") → «898 МГц»;  fmt(1e7, "м/с") → «1.00·10⁷ м/с»."""
    if x == 0 or not math.isfinite(x):
        return f"0 {unit}" if x == 0 else f"— {unit}"
    if unit in SIMPLE:
        e = exp3(x)
        if e in PREFIX:
            m = x / 10.0 ** e
            d = max(digits - 1 - int(math.floor(math.log10(abs(m)))), 0)
            s = f"{m:.{d}f}"
            if float(s) >= 1000 and (e + 3) in PREFIX:
                e += 3
                s = f"{x / 10.0 ** e:.{digits - 1}f}"
            return f"{s} {PREFIX[e]}{unit}"
    return f"{sci(x, digits)} {unit}"
