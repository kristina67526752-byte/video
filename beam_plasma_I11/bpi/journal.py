"""Журнал экспериментов: каждая строка — один счёт со всеми параметрами
и результатами (results/journal.csv). Так любой вывод можно проверить и
воспроизвести: зерно генератора и параметры записаны."""
from __future__ import annotations

import csv
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
JOURNAL = os.path.join(RESULTS, "journal.csv")

COLUMNS = ["time", "series", "scenario", "alpha", "vb", "dvb", "vtp", "npart", "ng", "dt",
           "n_waves", "seed", "k_main", "gamma_th", "gamma_meas", "omega_th", "E_trap",
           "t_sat", "E_sat", "wB_over_g", "WE_sat_frac", "bounce_T", "t_end",
           "WE_end_frac", "plateau_v1", "plateau_v2", "WE_ql_frac", "energy_err", "wall_s"]


def append(row: dict, series: str = "", path: str = JOURNAL):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        if new:
            w.writeheader()
        r = dict(row)
        r["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        r["series"] = series
        for k, v in r.items():
            if isinstance(v, float):
                r[k] = f"{v:.6g}"
        w.writerow(r)
