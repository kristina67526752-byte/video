"""Быстрый вывод картинок и текста прямо в пиксельный буфер холста.

Зачем: в matplotlib ≥ 3.10 текст рисуется по одной букве (≈50 мкс на символ),
а картинки проходят через общий конвейер передискретизации. Таблица чисел
из ~1000 символов стоила бы 50 мс на кадр, фазовый портрет — ещё 20 мс.

Что делаем вместо этого:
  * фазовый портрет считаем сразу в разрешении экрана (один пиксель = одна
    клетка гистограммы) и копируем массивом в буфер холста;
  * для моноширинного текста один раз рисуем каждую букву в маленькую
    картинку («атлас глифов»), а строку собираем склейкой этих картинок —
    numpy делает это за доли миллисекунды;
  * абзацы обычного текста (меняются редко) рисуем matplotlib'ом в
    отдельный буфер только при изменении и потом просто копируем.

Все Agg-бэкенды (TkAgg, QtAgg, MacOSX, WebAgg) дают доступ к буферу через
canvas.get_renderer().buffer_rgba().
"""
from __future__ import annotations

import math

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib.colors as mcolors


def canvas_buffer(canvas):
    """Пиксельный буфер холста (высота × ширина × RGBA, строки сверху вниз)."""
    return np.asarray(canvas.get_renderer().buffer_rgba())


def paste(buf, img, x0, y_top):
    """Скопировать картинку img (h × w × 3, uint8) в буфер; (x0, y_top) — левый
    верхний угол в пикселях, отсчёт y сверху. Всё, что выходит за край, обрезается."""
    H, W = buf.shape[:2]
    h, w = img.shape[:2]
    x0, y_top = int(x0), int(y_top)
    xa, ya = max(x0, 0), max(y_top, 0)
    xb, yb = min(x0 + w, W), min(y_top + h, H)
    if xb <= xa or yb <= ya:
        return
    buf[ya:yb, xa:xb, :3] = img[ya - y_top:yb - y_top, xa - x0:xb - x0]


def rgb255(color):
    return np.array([int(round(c * 255)) for c in mcolors.to_rgb(color)], dtype=np.float32)


class GlyphAtlas:
    """Картинки отдельных символов моноширинного шрифта (альфа-маски)."""

    def __init__(self, family, size_pt, dpi, weight="normal"):
        self.family, self.size, self.dpi, self.weight = family, size_pt, dpi, weight
        px = size_pt * dpi / 72.0
        self.cw = max(1, int(math.ceil(0.602 * px)))       # ширина клетки (DejaVu Mono: 0.602 em)
        self.ch = max(1, int(math.ceil(1.30 * px)))        # высота строки
        self.base = int(round(1.0 * px))                   # базовая линия от верха клетки
        self.cells = {}
        self._rows = {}
        self._render(" 0123456789.,:;+-−=()[]/%|<>*·_ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                     "abcdefghijklmnopqrstuvwxyz")

    def _render(self, chars):
        chars = [c for c in dict.fromkeys(chars) if c not in self.cells]
        if not chars:
            return
        n = len(chars)
        w, h = n * self.cw, self.ch
        fig = Figure(figsize=(w / self.dpi, h / self.dpi), dpi=self.dpi, facecolor="black")
        FigureCanvasAgg(fig)
        for i, c in enumerate(chars):
            fig.text((i * self.cw) / w, 1 - self.base / h, c, color="white",
                     family=self.family, size=self.size, weight=self.weight,
                     va="baseline", ha="left")
        fig.canvas.draw()
        a = np.asarray(fig.canvas.buffer_rgba())[:h, :w, 0].astype(np.float32) / 255.0
        for i, c in enumerate(chars):
            self.cells[c] = a[:, i * self.cw:(i + 1) * self.cw]

    def text_alpha(self, lines, ncols=None):
        """Альфа-маска блока строк (h × w, float32)."""
        missing = set("".join(lines)) - self.cells.keys()
        if missing:
            self._render("".join(sorted(missing)))
        ncols = ncols or max((len(s) for s in lines), default=1)
        out = np.zeros((len(lines) * self.ch, max(ncols, 1) * self.cw), np.float32)
        for r, s in enumerate(lines):
            s = s[:ncols]
            if s:
                row = self._rows.get(s)
                if row is None:                      # строки кэшируются целиком:
                    row = np.hstack([self.cells[c] for c in s])   # меняются лишь некоторые
                    if len(self._rows) > 400:
                        self._rows.clear()
                    self._rows[s] = row
                out[r * self.ch:(r + 1) * self.ch, :row.shape[1]] = row
        return out


def compose(alpha_rows, colors, bg, ch):
    """Раскрасить альфа-маску: каждая строка — своим цветом, фон bg. → uint8 RGB."""
    h, w = alpha_rows.shape
    col = np.empty((h, 1, 3), np.float32)
    for r, c in enumerate(colors):
        col[r * ch:(r + 1) * ch, 0, :] = c
    a = alpha_rows[..., None]
    img = bg + a * (col - bg)
    return img.astype(np.uint8)


class MonoText:
    """Многострочный моноширинный текст, который можно менять в каждом кадре.
    Строка, начинающаяся с '§', выделяется цветом заголовка."""

    def __init__(self, family, size_pt, color, head_color, bg, dpi):
        self.family, self.size = family, size_pt
        self.color, self.head_color, self.bg_hex = color, head_color, bg
        self.dpi = None
        self.set_dpi(dpi)
        self._key = None
        self.img = None

    def set_dpi(self, dpi):
        if dpi != self.dpi:
            self.dpi = dpi
            self.atlas = GlyphAtlas(self.family, self.size, dpi)
            self._c = rgb255(self.color)
            self._hc = rgb255(self.head_color)
            self._bg = rgb255(self.bg_hex)
            self._key = None

    def render(self, text, max_cols=None, max_rows=None):
        if text == self._key and self.img is not None:
            return self.img
        lines = text.split("\n")
        if max_rows:
            lines = lines[:max_rows]
        cols = []
        clean = []
        for s in lines:
            if s.startswith("§"):
                clean.append(s[1:])
                cols.append(self._hc)
            else:
                clean.append(s)
                cols.append(self._c)
        a = self.atlas.text_alpha(clean, max_cols)
        self.img = compose(a, cols, self._bg, self.atlas.ch)
        self._key = text
        return self.img


class ParagraphText:
    """Обычный (пропорциональный) текст с переносами. Рисуется matplotlib'ом
    в отдельный буфер только когда текст меняется."""

    def __init__(self, size_pt, color, bg, dpi, weight="normal", linespacing=1.35):
        self.size, self.color, self.bg, self.dpi = size_pt, color, bg, dpi
        self.weight, self.linespacing = weight, linespacing
        self._key = None
        self.img = None

    def fit(self, text, w_px, h_px, dpi=None):
        """Разбить текст на строки по ИЗМЕРЕННОЙ ширине букв так, чтобы он целиком
        поместился в прямоугольник w_px × h_px; что не влезло по высоте — отрезается
        с многоточием. Так текст никогда не выходит за край панели."""
        dpi = dpi or self.dpi
        key = (dpi, self.size, self.weight)
        if getattr(self, "_mkey", None) != key:
            fig = Figure(figsize=(1, 1), dpi=dpi)
            FigureCanvasAgg(fig)
            self._rend = fig.canvas.get_renderer()
            from matplotlib.font_manager import FontProperties
            self._fp = FontProperties(size=self.size, weight=self.weight)
            self._wcache = {}
            self._mkey = key

        def width(word):
            w = self._wcache.get(word)
            if w is None:
                w = self._rend.get_text_width_height_descent(word, self._fp, False)[0]
                self._wcache[word] = w
            return w
        space = width("a a") - 2 * width("a")
        limit = 0.97 * w_px
        lines = []
        for par in text.split("\n"):
            cur, cw = [], 0.0
            for word in par.split():
                ww = width(word)
                if cur and cw + space + ww > limit:
                    lines.append(" ".join(cur))
                    cur, cw = [word], ww
                else:
                    cw = cw + space + ww if cur else ww
                    cur.append(word)
            lines.append(" ".join(cur))
        line_h = self.size * dpi / 72.0 * self.linespacing * 1.17
        nmax = max(1, int(h_px / line_h))
        if len(lines) > nmax:
            lines = lines[:nmax]
            lines[-1] = lines[-1].rstrip(" .,;:") + " …"
        return "\n".join(lines)

    def render(self, text, w_px, h_px, dpi=None):
        dpi = dpi or self.dpi
        key = (text, int(w_px), int(h_px), dpi)
        if key == self._key and self.img is not None:
            return self.img
        w_px, h_px = max(int(w_px), 1), max(int(h_px), 1)
        fig = Figure(figsize=(w_px / dpi, h_px / dpi), dpi=dpi, facecolor=self.bg)
        FigureCanvasAgg(fig)
        fig.text(0, 1, text, color=self.color, size=self.size, weight=self.weight,
                 va="top", ha="left", linespacing=self.linespacing)
        fig.canvas.draw()
        self.img = np.asarray(fig.canvas.buffer_rgba())[:h_px, :w_px, :3].copy()
        self._key = key
        return self.img
