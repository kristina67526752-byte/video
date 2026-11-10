#!/usr/bin/env python3
"""
Запуск интерактивной модели «Пучково-плазменная неустойчивость» (вариант И11).
Все величины в программе — в единицах СИ.

Самый простой способ: открыть этот файл в IDLE и нажать F5 (Run → Run Module).
Файл должен лежать в папке проекта рядом с папкой bpi/.

Из терминала:
    python run.py                      главное окно (PIC-модель в реальном времени)
    python run.py --window theory      окно линейной теории γ(k)
    python run.py --window single      одноволновая модель (огибающая + частицы)
    python run.py --window solitons    уравнения Захарова: каверны и солитоны
    python run.py --window table       таблица амплитуд насыщения
    python run.py --window formulas    все формулы по страницам
    python run.py --alpha 0.02 --vb 2e7 --dv 1e6     n_b/n_p, v_b [м/с], Δv_b [м/с]
    python run.py --np 1e14 --Te 1.5e6               n_p [м⁻³], T_e [К]
    python run.py --preset corona      готовая среда: lab, iono, corona, wind, reb
    python run.py --ions               подвижные ионы (каверны после насыщения)
    python run.py --two-stream         встречные пучки
    python run.py --npart 32768        вдвое меньше частиц — для слабого компьютера
    python run.py --light              светлая тема (для снимков в отчёт)
"""
import os
# numpy с многопоточным BLAS тратит время на запуск потоков для коротких
# операций; в этой задаче один поток быстрее. Ставится до import numpy.
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import importlib.util
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
NEEDED = ("numpy", "matplotlib", "scipy")
PIP_CMD = f'"{sys.executable}" -m pip install numpy matplotlib scipy'


def project_is_complete():
    """Программа живёт в папке bpi/ рядом с run.py. Если скачан один run.py — объясняем."""
    if os.path.isfile(os.path.join(HERE, "bpi", "pic.py")):
        return True
    print(
        "\nОШИБКА: рядом с run.py нет папки «bpi» — в ней находится сама программа.\n"
        "Похоже, скачан только файл run.py. Нужна вся папка проекта beam_plasma_I11:\n"
        "    beam_plasma_I11/\n"
        "        run.py        ← этот файл\n"
        "        bpi/          ← физика и окна программы (обязательно)\n"
        "        docs/  experiments/  results/  tests/  README.md\n\n"
        "Что сделать: скачать архив beam_plasma_I11.zip целиком, распаковать его\n"
        "(двойной щелчок) и открыть в IDLE файл run.py ИЗ распакованной папки.\n"
        f"Сейчас run.py лежит здесь: {HERE}\n")
    return False


def libraries_are_installed():
    """Проверяем numpy, matplotlib, scipy; если их нет — предлагаем установить."""
    missing = [m for m in NEEDED if importlib.util.find_spec(m) is None]
    if not missing:
        return True
    print(f"\nНе установлены библиотеки: {', '.join(missing)}.")
    try:
        ans = input("Установить их сейчас? Нужен интернет, 1–2 минуты (да/нет): ")
    except (EOFError, RuntimeError):
        ans = ""
    if ans.strip().lower() in ("да", "д", "yes", "y"):
        print("Устанавливаю… (подождите, окно может не отвечать до конца установки)")
        r = subprocess.run([sys.executable, "-m", "pip", "install", *NEEDED],
                           capture_output=True, text=True)
        if r.returncode == 0:
            print("Готово. Запустите run.py ещё раз (в IDLE — снова F5).")
        else:
            print((r.stdout + r.stderr)[-1500:])
            print("\nНе получилось установить автоматически. Выполните вручную в Терминале "
                  "(macOS) или в командной строке (Windows):\n    " + PIP_CMD)
        return False
    print("Установите их командой в Терминале (macOS) или командной строке (Windows):\n"
          "    " + PIP_CMD + "\nи запустите run.py ещё раз.")
    return False


def main():
    if not project_is_complete() or not libraries_are_installed():
        return None
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", default="main",
                    choices=["main", "theory", "single", "solitons", "table", "formulas"])
    ap.add_argument("--preset", default="lab", choices=["lab", "iono", "corona", "wind", "reb"],
                    help="готовый набор параметров реальной плазмы")
    ap.add_argument("--np", type=float, default=None, help="концентрация плазмы n_p, м⁻³")
    ap.add_argument("--Te", type=float, default=None, help="температура электронов T_e, К")
    ap.add_argument("--alpha", type=float, default=0.01, help="n_b/n_p (0.001…0.1)")
    ap.add_argument("--vb", type=float, default=None, help="скорость пучка v_b, м/с (< 2.9e8)")
    ap.add_argument("--dv", type=float, default=0.0, help="разброс скоростей пучка Δv_b, м/с")
    ap.add_argument("--ions", action="store_true", help="подвижные ионы")
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
    from bpi import presets

    style.use("light" if a.light else "dark")
    pr = presets.get(a.preset)
    p = PICParams(scenario="two_stream" if a.two_stream else "beam",
                  n_p=a.np or pr["n_p"], T_e=a.Te or pr["T_e"], T_i=pr["T_i"],
                  alpha=a.alpha, vb=a.vb or pr["vb"], dvb=a.dv,
                  ion=pr["ion"] if a.ions else "none", npart=a.npart)
    keep = None
    if a.window == "main":
        from bpi.gui.main_window import MainWindow
        keep = MainWindow(p, theme="light" if a.light else "dark", preset=a.preset)
    elif a.window == "theory":
        from bpi.gui.theory_window import TheoryWindow
        keep = TheoryWindow(n_p=p.n_p, T_e=p.T_e, alpha=p.alpha, vb=p.vb, dvb=p.dvb)
    elif a.window == "single":
        from bpi.gui.single_wave_window import SingleWaveWindow
        keep = SingleWaveWindow(n_p=p.n_p, alpha=p.alpha, vb=p.vb, dvb=p.dvb)
    elif a.window == "solitons":
        from bpi.gui.soliton_window import SolitonWindow
        keep = SolitonWindow(n_p=p.n_p, T_e=p.T_e, T_i=p.T_i, ion=pr["ion"], alpha=p.alpha, vb=p.vb)
    elif a.window == "table":
        from bpi.gui.table_window import TableWindow
        keep = TableWindow(base=p)
    else:
        from bpi.gui.formulas_window import FormulasWindow
        keep = FormulasWindow(params=p)
    print("Окно модели открыто. Закройте его, чтобы завершить программу.")
    plt.show()
    return keep


if __name__ == "__main__":
    main()
