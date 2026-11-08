#!/usr/bin/env python3
"""
Запуск интерактивной модели «Пучково-плазменная неустойчивость» (вариант И11).

    python run.py                      главное окно (PIC-модель в реальном времени)
    python run.py --window theory      окно линейной теории γ(k)
    python run.py --window single      одноволновая модель (огибающая + частицы)
    python run.py --window table       таблица амплитуд насыщения
    python run.py --window formulas    все формулы по страницам
    python run.py --alpha 0.02 --vb 1.5 --dv 0.1
    python run.py --two-stream         встречные пучки
    python run.py --npart 32768        вдвое меньше частиц — для слабого компьютера
    python run.py --light              светлая тема (для снимков в отчёт)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", default="main",
                    choices=["main", "theory", "single", "table", "formulas"])
    ap.add_argument("--alpha", type=float, default=0.01, help="n_b/n_p (0.001…0.1)")
    ap.add_argument("--vb", type=float, default=1.0, help="скорость пучка v_b/v₀ (0.5…2)")
    ap.add_argument("--dv", type=float, default=0.0, help="разброс скоростей пучка Δv/v_b")
    ap.add_argument("--two-stream", action="store_true", help="встречные пучки")
    ap.add_argument("--npart", type=int, default=65536, help="макрочастиц каждого сорта")
    ap.add_argument("--light", action="store_true", help="светлая тема")
    ap.add_argument("--backend", default=None, help="бэкенд matplotlib, напр. TkAgg или QtAgg")
    a = ap.parse_args()

    import matplotlib
    if a.backend:
        matplotlib.use(a.backend)
    import matplotlib.pyplot as plt
    from bpi.gui import style
    from bpi.pic import PICParams

    style.use("light" if a.light else "dark")
    p = PICParams(scenario="two_stream" if a.two_stream else "beam", alpha=a.alpha,
                  vb=a.vb, dvb=a.dv, npart=a.npart)
    keep = None
    if a.window == "main":
        from bpi.gui.main_window import MainWindow
        keep = MainWindow(p, theme="light" if a.light else "dark")
    elif a.window == "theory":
        from bpi.gui.theory_window import TheoryWindow
        keep = TheoryWindow(alpha=a.alpha, vb=a.vb, dvb=a.dv)
    elif a.window == "single":
        from bpi.gui.single_wave_window import SingleWaveWindow
        keep = SingleWaveWindow(alpha=a.alpha, dvb=a.dv)
    elif a.window == "table":
        from bpi.gui.table_window import TableWindow
        keep = TableWindow(base=p)
    else:
        from bpi.gui.formulas_window import FormulasWindow
        keep = FormulasWindow()
    plt.show()
    return keep


if __name__ == "__main__":
    main()
