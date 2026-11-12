"""Проверка, что все окна создаются и анимация считает кадры без ошибок
(без экрана, бэкенд Agg)."""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_main_window_runs():
    from bpi.gui.main_window import MainWindow
    from bpi.gui.analysis_window import AnalysisWindow
    from bpi.pic import PICParams
    w = MainWindow(PICParams(npart=8192), maximize=False)
    w.fig.canvas.draw()
    for _ in range(40):
        w.tick()
    assert w.sim.t * w.sim.wpe > 15
    w.back()
    w.single_step()
    for key in ("phase", "energy"):
        w.explain_key = key
        w._update_artists(force=True)
        w.blit.update(force=True)
    a = AnalysisWindow(w)
    a.refresh()
    w.c_opts.set_active(2)                       # ионы подвижны
    assert w.sim.m_i and w.sim.ns == 3
    for _ in range(10):
        w.tick()
    a.refresh()
    assert "\n" in w.rt_exp.fit("слово " * 200, 200, 100)   # длинный текст переносится и обрезается
    w.r_scen.set_active(1)                       # встречные пучки
    for _ in range(10):
        w.tick()
    assert w.params.scenario == "two_stream"


def test_explanations_fit_panel():
    """Все пояснения (по графикам и по стадиям) помещаются в правую нижнюю панель
    целиком — без обрезки многоточием."""
    from bpi.gui.main_window import MainWindow, SPLIT
    from bpi.gui import texts
    from bpi.pic import PICParams
    w = MainWindow(PICParams(npart=4096), maximize=False)
    w.fig.canvas.draw()
    bi, dpi = w.ax_info.bbox, w.fig.dpi
    pad = int(0.006 * w.fig.bbox.width)
    we = bi.x1 - (bi.x0 + SPLIT * bi.width + pad) - pad
    kw = dict(N=5, g="7.67·10⁸ с⁻¹", t1="5.22 нс", vb="1.00·10⁷ м/с", vph="8.99·10⁶ м/с",
              gm="7.72·10⁸ с⁻¹", wB="1.03·10⁹ с⁻¹", Es="19.1 кВ/м", ts="13.1 нс", Et="17.8 кВ/м",
              Tb="4.70 нс (2π/ω_B = 4.48 нс)", ion="H⁺", ions_hint=texts.IONS_HINT,
              dni="2.7%", dnmin="-12%", Wmax="0.74")
    items = [(h, b + "\n(Пробел — продолжить.)") for h, b in texts.PANELS.values()]
    items += [(h.format(N=5), b.format(**kw)) for h, b in texts.STAGES_BEAM + texts.STAGES_TWO]
    for head, body in items:
        hh = 8.5 * dpi / 72 * 1.6 * (w.rt_exp_h.fit(head, we, 0.3 * bi.height, dpi).count("\n") + 1) + 4
        assert not w.rt_exp.fit(body, we, bi.height - 2 * pad - hh, dpi).endswith("…"), head
