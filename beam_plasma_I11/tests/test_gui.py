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
    assert w.sim.m_i and w.sim.ns == 3           # ионы всегда подвижны: третий сорт частиц
    for _ in range(10):
        w.tick()
    a.refresh()
    assert "\n" in w.rt_exp.fit("слово " * 200, 200, 100)   # длинный текст переносится и обрезается
    w.r_scen.set_active(1)                       # встречные пучки
    for _ in range(10):
        w.tick()
    assert w.params.scenario == "two_stream"
