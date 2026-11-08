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
    from bpi.pic import PICParams
    w = MainWindow(PICParams(npart=8192), maximize=False)
    w.fig.canvas.draw()
    for _ in range(40):
        w.tick()
    assert w.sim.t > 15
    w.back()
    w.single_step()
    w.explain_key = "phase"
    w._update_artists(force=True)
    w.blit.update(force=True)
    w.r_scen.set_active(1)                       # встречные пучки
    for _ in range(10):
        w.tick()
    assert w.params.scenario == "two_stream"


def test_other_windows_build():
    from bpi.gui import style
    style.use("dark")
    from bpi.gui.theory_window import TheoryWindow
    from bpi.gui.single_wave_window import SingleWaveWindow
    from bpi.gui.formulas_window import FormulasWindow
    from bpi.gui.table_window import TableWindow
    t = TheoryWindow(alpha=0.02, dvb=0.1)
    t.sweep = True
    t._tick()
    s = SingleWaveWindow(alpha=0.01)
    for _ in range(5):
        s._tick()
    f = FormulasWindow()
    for i in range(len(f.pages)):
        f.go(1)
    tw = TableWindow()
    assert t.s_txt and s.s_txt and tw.s_tab
