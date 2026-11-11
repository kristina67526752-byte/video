"""Общие элементы управления: ползунок по списку «круглых» значений в СИ и кнопка."""
from __future__ import annotations

import numpy as np
from matplotlib.widgets import Slider, Button

from ..constants import C_LIGHT
from ..units import sci
from . import style
from .style import C


def _decades(mults, e0, e1):
    return [m * 10.0 ** e for e in range(e0, e1 + 1) for m in mults]


# «Круглые» значения параметров (СИ)
ALPHAS = [v for v in _decades((1, 1.5, 2, 3, 5, 7), -3, -2) if v <= 0.1] + [0.1]   # n_b/n_p
VELOCITIES = ([2e6, 3e6, 4e6, 5e6, 6e6, 8e6]
              + [1e7, 1.2e7, 1.5e7, 2e7, 2.5e7, 3e7, 4e7, 5e7, 6e7, 8e7]
              + [1e8, 1.2e8, 1.5e8, 1.8e8, 2e8, 2.2e8, 2.4e8, 2.6e8, 2.7e8, 2.82e8, 2.9e8])  # v_b, м/с


def fmt_velocity(v):
    beta = v / C_LIGHT
    return f"{sci(v, 3)} м/с" + (f" = {beta:.2f}c" if beta > 0.05 else "")


class ListSlider:
    """Ползунок, который выбирает значение из списка (положение — номер в списке).
    Так на экране всегда «круглые» числа в СИ: 1.0·10¹⁶ м⁻³, 3.0·10⁴ К, 1.00·10⁷ м/с."""

    def __init__(self, fig, rect, label, values, init, fmt, fontsize=8.2):
        self.values = list(values)
        self.fmt = fmt
        ax = fig.add_axes(rect)
        style.style_widget_axes(ax)
        self.slider = s = Slider(ax, label, 0, len(self.values) - 1, valinit=self.index_of(init),
                                 valstep=1, color=C["main"], track_color=C["grid"],
                                 handle_style=dict(facecolor=C["text"], edgecolor=C["surface"],
                                                   size=8))
        s.label.set_color(C["text"])
        s.label.set_fontsize(fontsize)
        s.valtext.set_color(C["text"])
        s.valtext.set_fontsize(fontsize)
        s.on_changed(lambda v: self.sync())
        self.sync()

    def index_of(self, value):
        """Номер ближайшего значения в списке (в логарифмическом масштабе)."""
        v = np.asarray(self.values, dtype=float)
        return int(np.argmin(np.abs(np.log(v) - np.log(value))))

    @property
    def val(self):
        return float(self.values[int(round(self.slider.val))])

    def set_val(self, value):
        self.slider.set_val(self.index_of(value))

    def sync(self):
        self.slider.valtext.set_text(self.fmt(self.val))

    def on_changed(self, cb):
        self.slider.on_changed(lambda v: cb(self.val))


def plain_slider(fig, rect, label, vmin, vmax, vinit, step, fontsize=8.2):
    ax = fig.add_axes(rect)
    style.style_widget_axes(ax)
    s = Slider(ax, label, vmin, vmax, valinit=vinit, valstep=step, color=C["main"],
               track_color=C["grid"],
               handle_style=dict(facecolor=C["text"], edgecolor=C["surface"], size=8))
    s.label.set_color(C["text"])
    s.label.set_fontsize(fontsize)
    s.valtext.set_color(C["text"])
    s.valtext.set_fontsize(fontsize)
    return s


def button(fig, rect, label, cb, hl=False, fs=8.5):
    ax = fig.add_axes(rect)
    b = Button(ax, label, color=C["main"] if hl else C["panel"], hovercolor=C["grid"])
    b.label.set_color(C["surface"] if hl else C["text"])
    b.label.set_fontsize(fs)
    if hl:
        b.label.set_fontweight("bold")
    for sp in ax.spines.values():
        sp.set_color(C["grid"])
    b.on_clicked(cb)
    return b
