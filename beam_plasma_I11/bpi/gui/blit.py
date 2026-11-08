"""Быстрая перерисовка (blitting) по областям окна.

Обычная перерисовка matplotlib заново рисует ВСЁ: оси, подписи, сетку,
легенды — это 0.2–0.5 с на кадр. Здесь неподвижный фон рисуется один раз
и запоминается, а в каждом кадре для каждой области окна:
    1) фон области восстанавливается из памяти;
    2) raw(buf) — наши картинки и тексты копируются прямо в пиксели (fastdraw);
    3) поверх рисуются меняющиеся линии и точки matplotlib;
    4) на экран передаётся только эта область (blit).
Области можно обновлять с разной частотой: фазовый портрет — каждый кадр,
медленно меняющиеся графики — через кадр.
"""
from matplotlib.transforms import Bbox

from .fastdraw import canvas_buffer


class Region:
    def __init__(self, bbox_fn=None, artists=(), raw=None, period=1):
        self.bbox_fn = bbox_fn          # () -> (x0, y0, x1, y1) в пикселях, ось y вверх
        self.artists = list(artists)
        self.raw = raw
        self.period = period


class Blitter:
    def __init__(self, fig, artists=(), raw=None, regions=None):
        self.fig = fig
        self.canvas = fig.canvas
        self.bg = None
        self.frame = 0
        if regions is None:
            regions = [Region(None, artists, raw, 1)]
        self.regions = regions
        for r in regions:
            for a in r.artists:
                a.set_animated(True)
        self.cid = self.canvas.mpl_connect("draw_event", self._on_draw)

    @property
    def artists(self):
        return [a for r in self.regions for a in r.artists]

    def _on_draw(self, event):
        # после полной перерисовки (запуск, изменение размера окна, виджеты)
        # запоминаем фон и дорисовываем подвижные элементы
        if event is not None and event.canvas is not self.canvas:
            return                    # это savefig в другой холст — не трогаем
        self.bg = self.canvas.copy_from_bbox(self.fig.bbox)
        buf = canvas_buffer(self.canvas)
        for r in self.regions:
            self._draw_region(r, buf)

    def _draw_region(self, r, buf):
        if r.raw is not None:
            r.raw(buf)
        for a in r.artists:
            if a.get_visible():
                self.fig.draw_artist(a)

    def update(self, force=False):
        # Если что-то неподвижное изменилось (пределы осей после «Заново»,
        # масштабирование, размер окна), фигура помечается stale. Отложенная
        # перерисовка draw_idle при непрерывной анимации может так и не наступить
        # (цикл событий Tk никогда не простаивает), поэтому рисуем сразу.
        if self.bg is None or self.fig.stale:
            self.canvas.draw()
            return
        self.frame += 1
        H = int(round(self.fig.bbox.height))
        buf = canvas_buffer(self.canvas)
        for r in self.regions:
            if not force and self.frame % r.period:
                continue
            if r.bbox_fn is None:
                x0, y0, x1, y1 = self.fig.bbox.extents
            else:
                x0, y0, x1, y1 = r.bbox_fn()
            x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
            # прямоугольник задаётся в координатах Agg (ось y вниз); xy — смещение
            # всей сохранённой области, у нас она начинается в (0, 0)
            self.canvas.restore_region(self.bg, bbox=(x0, H - y1, x1, H - y0), xy=(0, 0))
            self._draw_region(r, buf)
            self.canvas.blit(Bbox.from_extents(x0, y0, x1, y1))
        # flush_events() не нужен: мы внутри таймера, и после возврата в цикл
        # событий окно само обновится


def blit_axes(fig, ax):
    """Перерисовать только одну ось (кнопку) без полной перерисовки окна."""
    if fig.canvas.get_renderer() is None:
        return
    fig.draw_artist(ax)
    fig.canvas.blit(ax.bbox)
    fig.stale = False               # изменение уже на экране — полная перерисовка не нужна


class SliderBlit:
    """Ползунок matplotlib при каждом движении вызывает полную перерисовку окна
    (0.2–0.5 с). Здесь он перерисовывает только себя: область ползунка
    заливается цветом фона, и поверх рисуется сам ползунок с подписями."""

    def __init__(self, fig, slider, bg_color):
        import matplotlib.colors as mcolors
        import numpy as np
        self.fig, self.s = fig, slider
        self.rgb = (np.array(mcolors.to_rgb(bg_color)) * 255).astype("uint8")
        self.last = None
        slider.drawon = False
        slider.on_changed(lambda v: self.draw())

    def _extent(self):
        r = self.fig.canvas.get_renderer()
        bbs = [self.s.ax.bbox, self.s.label.get_window_extent(r),
               self.s.valtext.get_window_extent(r)]
        x0 = min(b.x0 for b in bbs) - 3
        x1 = max(b.x1 for b in bbs) + 3
        y0 = min(b.y0 for b in bbs) - 3
        y1 = max(b.y1 for b in bbs) + 3
        return x0, y0, x1, y1

    def draw(self):
        c = self.fig.canvas
        try:
            buf = canvas_buffer(c)
        except Exception:
            return
        e = self._extent()
        if self.last is not None:                 # стираем и старую надпись значения
            e = (min(e[0], self.last[0]), min(e[1], self.last[1]),
                 max(e[2], self.last[2]), max(e[3], self.last[3]))
        H, W = buf.shape[:2]
        x0, y0, x1, y1 = max(int(e[0]), 0), max(int(e[1]), 0), min(int(e[2]) + 1, W), min(int(e[3]) + 1, H)
        buf[H - y1:H - y0, x0:x1, :3] = self.rgb
        self.fig.draw_artist(self.s.ax)
        c.blit(Bbox.from_extents(x0, y0, x1, y1))
        self.last = self._extent()
        self.fig.stale = False          # ползунок уже на экране


def keep_drawn(fig):
    """Вызывается из таймеров окон: если фигура устарела — перерисовать сразу."""
    if fig.stale:
        fig.canvas.draw()
