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
    for key in ("phase", "help"):
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
    for _ in range(5):                           # все готовые среды
        w.next_preset()
        w.tick()
        assert np.isfinite(w.sim.gamma_ref) and w.sim.gamma_ref > 0
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
    from bpi.gui.soliton_window import SolitonWindow, SCENARIOS
    t = TheoryWindow(alpha=0.02, dvb=1e6)
    t.sweep = True
    t._tick()
    s = SingleWaveWindow(alpha=0.01, vb=2e8)
    for _ in range(5):
        s._tick()
    f = FormulasWindow()
    for i in range(len(f.pages)):
        f.go(1)
    tw = TableWindow()
    z = SolitonWindow()
    for i in range(3):
        z.r.set_active(i)
        assert z.scenario == SCENARIOS[i]
        for _ in range(3):
            z._tick()
    assert t.s_txt and s.s_txt and tw.s_tab and z.s_txt
