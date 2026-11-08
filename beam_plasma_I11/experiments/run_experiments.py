#!/usr/bin/env python3
"""
Вычислительные эксперименты варианта И11 — всё, что нужно для отчёта.

    python experiments/run_experiments.py           полный набор (~3–6 мин на 4 ядрах)
    python experiments/run_experiments.py --quick   быстрый набор (~1 мин)

Результаты (папка results/):
    journal.csv                  журнал всех счётов: параметры, зерно, результаты
    E1_gamma_k.csv/.png          инкремент γ(k): PIC против теории (+ встречные пучки)
    E2_saturation_alpha.csv/.png амплитуда насыщения от n_b/n_p, сравнение с теориями
    E3_saturation_vb.csv/.png    амплитуда насыщения от скорости пучка
    E4_warm_beam.csv/.png        тёплый пучок: кинетическая теория и переход к плато
    E5_quasilinear.csv/.png      длинные счёты: квазилинейный баланс, плато f(v)
    E6_numerics.csv/.png         сходимость: шаг по времени, сетка, число частиц
    E7_single_wave.csv           одноволновая модель: константа насыщения
    F1_stages.png                фазовые портреты на 4 стадиях
    F2_energy_spectrum.png       энергия, спектрограмма, спектр
    F3_dispersion.png            дисперсионные кривые
    СВОДКА.md                    все таблицы с числами и выводы (генерируется)

Задачи параллелизуются по наборам параметров (рекомендация 3 из сборника).
"""
from __future__ import annotations

import os
# Один поток BLAS на процесс: иначе 4 процесса × 4 потока OpenBLAS дерутся за
# ядра, и параллельная серия идёт в разы медленнее. Должно стоять до import numpy.
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bpi.pic import PIC, PICParams                      # noqa: E402
from bpi import dispersion as disp                       # noqa: E402
from bpi import diagnostics as diag                      # noqa: E402
from bpi.runs import SatRun                              # noqa: E402
from bpi.single_wave import SingleWave, saturation_constant   # noqa: E402
from bpi import journal                                  # noqa: E402

RES = os.path.join(ROOT, "results")


# --------------------------------------------------------------------------- рабочие
def job_sat(args):
    """Счёт до насыщения и дальше (t_end_factor·t_sat); возвращает строку журнала."""
    pdict, series, factor = args
    sr = SatRun(PICParams(**pdict), t_end_factor=factor)
    while not sr.advance(500):
        pass
    r = sr.result()
    r["series"] = series
    if series.startswith("E1"):
        r["modes"] = diag.measure_modes(sr.sim, min_frac=0.35)
    if series.startswith("E5"):
        s = sr.sim
        edges = np.linspace(-0.3, 1.8, 211)
        r["fv"] = s.velocity_hist(1, edges) / s.dens[1]
        r["fv_edges"] = edges
        h = s.hist
        st = max(1, s.h_n // 2000)
        r["hist_t"] = h["t"][::st]
        r["hist_WE"] = h["WE"][::st] / s.K0_beam
    return r


def job_numerics(args):
    pdict, label = args
    sr = SatRun(PICParams(**pdict), t_end_factor=2.5)
    while not sr.advance(500):
        pass
    r = sr.result()
    r["series"] = "E6 " + label
    return r


# --------------------------------------------------------------------------- утилиты
def save_csv(name, rows, cols):
    import csv
    path = os.path.join(RES, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cols)
        for r in rows:
            w.writerow([(f"{r[c]:.6g}" if isinstance(r[c], (float, np.floating)) else r[c])
                        for c in cols])
    return path


def md_table(rows, cols, fmt):
    head = "| " + " | ".join(c for c, _ in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    lines = [head, sep]
    def cell(r, k):
        v = r.get(k)
        if v is None or (isinstance(v, (float, np.floating)) and not np.isfinite(v)):
            return "—"
        return fmt.get(k, "{}").format(v)
    for r in rows:
        lines.append("| " + " | ".join(cell(r, k) for _, k in cols) + " |")
    return "\n".join(lines)


def style_cmap():
    from bpi.gui import style
    return style.seq_cmap()


def light_style():
    from bpi.gui import style
    style.use("light")
    import matplotlib as mpl
    mpl.rcParams["axes.titlesize"] = 10
    mpl.rcParams["axes.labelsize"] = 9
    return style.C


# --------------------------------------------------------------------------- основной сценарий
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="меньше частиц и точек")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    a = ap.parse_args()
    os.makedirs(RES, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    C = light_style()

    N = 32768 if a.quick else 65536
    base = PICParams(npart=N).as_dict()
    t_start = time.time()
    md = ["# Сводка вычислительных экспериментов (вариант И11)", "",
          f"Сгенерировано скриптом `experiments/run_experiments.py` "
          f"{time.strftime('%Y-%m-%d %H:%M')}. Частиц каждого сорта: {N}, сетка "
          f"{base['ng']} узлов, Δt = {base['dt']}/ω_p, ящик — {base['n_waves']} длин самой "
          "неустойчивой волны, тихий старт, зерно генератора 1.", ""]

    alphas = [0.002, 0.005, 0.01, 0.02, 0.05, 0.1] if a.quick else \
        [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1]
    vbs = [0.5, 1.0, 2.0] if a.quick else [0.5, 0.75, 1.0, 1.5, 2.0]
    dvs = [0.0, 0.05, 0.1, 0.2] if a.quick else [0.0, 0.03, 0.06, 0.1, 0.15, 0.2, 0.25]
    ql_alphas = [0.005, 0.01, 0.05] if a.quick else [0.002, 0.005, 0.01, 0.02, 0.05, 0.1]

    jobs = []
    # E1: γ(k) — все моды затравлены одинаково, чтобы каждую можно было измерить
    jobs.append((dict(base, alpha=0.01, seed_other=1.0), "E1 beam", 1.2))
    jobs.append((dict(base, scenario="two_stream", seed_other=1.0), "E1 two-stream", 1.2))
    for al in alphas:
        jobs.append((dict(base, alpha=al), "E2 alpha", 3.5))
    for vb in vbs:
        jobs.append((dict(base, vb=vb), "E3 vb", 2.0))
    for dv in dvs:
        jobs.append((dict(base, dvb=dv), "E4 dvb", 3.0))
    for al in ql_alphas:
        jobs.append((dict(base, alpha=al), "E5 ql", 6.0))
    num_jobs = []
    for dt in ([0.05, 0.1, 0.2, 0.4] if not a.quick else [0.1, 0.2, 0.4]):
        num_jobs.append((dict(base, dt=dt), f"dt={dt}"))
    for ng in ([256, 512, 1024, 2048] if not a.quick else [512, 1024]):
        num_jobs.append((dict(base, ng=ng), f"ng={ng}"))
    for npart in ([8192, 16384, 32768, 65536, 131072] if not a.quick else [8192, 32768]):
        num_jobs.append((dict(base, npart=npart), f"N={npart}"))
    for vtp in ([0.0, 0.01, 0.02, 0.04] if not a.quick else [0.0, 0.02]):
        num_jobs.append((dict(base, vtp=vtp), f"vtp={vtp}"))

    print(f"Запуск {len(jobs) + len(num_jobs)} счётов на {a.workers} процессах…", flush=True)
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        res = list(ex.map(job_sat, jobs))
        res_num = list(ex.map(job_numerics, num_jobs))
    print(f"  готово за {time.time() - t_start:.0f} с", flush=True)
    for r in res + res_num:
        journal.append(r, series=r["series"])

    # ------------------------------------------------------------------ E1 γ(k)
    rows = []
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    for ax, ser, sp_fn, title in (
            (axs[0], "E1 beam", lambda: disp.beam_plasma_species(0.01), "пучок в плазме, α = 0.01"),
            (axs[1], "E1 two-stream", lambda: disp.two_stream_species(1.0), "встречные пучки ±v_b/2")):
        r = next(x for x in res if x["series"] == ser)
        sp = sp_fn()
        k0, g0, _ = disp.most_unstable(sp)
        kk = np.linspace(0.01, 2.2, 400) * k0
        _, gg = disp.fluid_growth(kk, sp)
        ax.plot(kk / k0, gg, color=C["text2"], ls="--", label="теория (точный корень)")
        # медленные моды (γ < 0.6 γ_max) за время линейной стадии не успевают выделиться
        # на фоне комбинационных гармоник главной волны — их наклон честно не измерить
        ms = [m for m in r["modes"] if m["g_th"] > 0.6 * g0]
        ax.plot([m["k"] / k0 for m in ms], [m["g"] for m in ms], "o", ms=7,
                mfc=C["field"], mec=C["surface"], mew=1.5, label="PIC: наклон ln|E_k(t)|")
        ax.set_title(title, loc="left")
        ax.set_xlabel("k / k_max")
        ax.set_ylabel("γ / ω_p")
        ax.legend(fontsize=8)
        for m in ms:
            rows.append(dict(case=ser.split()[1], m=m["m"], k=m["k"], k_over_kmax=m["k"] / k0,
                             gamma_th=m["g_th"], gamma_pic=m["g"],
                             err_pct=(m["g"] / m["g_th"] - 1) * 100,
                             omega_th=m["w_th"], omega_pic=m["w"]))
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "E1_gamma_k.png"), dpi=150)
    plt.close(fig)
    cols = ["case", "m", "k", "k_over_kmax", "gamma_th", "gamma_pic", "err_pct", "omega_th", "omega_pic"]
    save_csv("E1_gamma_k.csv", rows, cols)
    md += ["## E1. Инкремент γ(k): PIC против точной теории", "",
           "Все моды ящика затравлены одинаково; в таблице — моды с γ > 0.6·γ_max (более "
           "медленные за время линейной стадии не выделяются на фоне гармоник главной волны). "
           "γ — наклон ln|E_k(t)| методом наименьших "
           "квадратов на отрезке линейной стадии [4/γ, момент, когда главная волна достигла "
           "5 % от уровня насыщения]; ω = −d arg E_k/dt.", "",
           md_table(rows, [("случай", "case"), ("m", "m"), ("k/k_max", "k_over_kmax"),
                           ("γ теория", "gamma_th"), ("γ PIC", "gamma_pic"), ("ошибка, %", "err_pct"),
                           ("ω теория", "omega_th"), ("ω PIC", "omega_pic")],
                    {"k_over_kmax": "{:.3f}", "gamma_th": "{:.4f}", "gamma_pic": "{:.4f}",
                     "err_pct": "{:+.2f}", "omega_th": "{:.4f}", "omega_pic": "{:.4f}"}),
           "", "![](E1_gamma_k.png)", ""]

    # ------------------------------------------------------------------ E2 E_sat(α)
    r2 = sorted([x for x in res if x["series"] == "E2 alpha"], key=lambda x: x["alpha"])
    al = np.array([x["alpha"] for x in r2])
    Es = np.array([x["E_sat"] for x in r2])
    Et = np.array([x["E_trap"] for x in r2])
    sl_pic = np.polyfit(np.log(al), np.log(Es), 1)[0]
    sl_th = np.polyfit(np.log(al), np.log(Et), 1)[0]
    sl_g = np.polyfit(np.log(al), np.log([x["gamma_th"] for x in r2]), 1)[0]
    for x in r2:
        x["ratio"] = x["E_sat"] / x["E_trap"]
        x["gamma_err"] = (x["gamma_meas"] / x["gamma_th"] - 1) * 100
        x["E_rms_ql"] = np.sqrt(2 * x["alpha"] / 3)     # полное плато: W_E = K_b0/3
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    ax = axs[0]
    aa = np.logspace(np.log10(al.min()) - 0.1, np.log10(al.max()) + 0.1, 50)
    th = []
    for a_ in aa:
        k_, g_, _ = disp.most_unstable(disp.beam_plasma_species(a_))
        th.append(diag.trapping_amplitude(g_, k_))
    ax.loglog(aa, th, color=C["text2"], ls="--", label="захват: 3.12γ²/k (точный γ)")
    ax.loglog(aa, 2 ** (1 / 3) * aa ** (2 / 3) * 1.15, color=C["muted"], ls=":",
              label="∝ α^(2/3) (слабый пучок)")
    ax.loglog(al, Es, "o", ms=7, mfc=C["field"], mec=C["surface"], label=f"PIC: ∝ α^{sl_pic:.2f}")
    ax.set_xlabel("α = n_b/n_p")
    ax.set_ylabel("E_sat, ед. m ω_p v_b/e")
    ax.set_title("Амплитуда насыщения от плотности пучка", loc="left")
    ax.legend(fontsize=8)
    ax = axs[1]
    ax.semilogx(al, [x["wB_over_g"] for x in r2], "o-", color=C["main"], label="PIC: ω_B/γ")
    ax.axhline(diag.OMEGA_B_OVER_GAMMA, color=C["text2"], ls="--", label="одноволновая модель 1.77")
    ax.set_xlabel("α = n_b/n_p")
    ax.set_ylabel("ω_B/γ в первом максимуме")
    ax.set_ylim(1.4, 2.2)
    ax.set_title("Условие захвата ω_B ≈ const·γ", loc="left")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "E2_saturation_alpha.png"), dpi=150)
    plt.close(fig)
    cols = ["alpha", "gamma_th", "gamma_meas", "gamma_err", "k_main", "t_sat", "E_sat", "E_trap",
            "ratio", "wB_over_g", "bounce_T", "WE_sat_frac", "WE_end_frac", "WE_ql_frac",
            "plateau_v1", "plateau_v2", "E_rms_ql", "energy_err"]
    save_csv("E2_saturation_alpha.csv", r2, cols)
    md += ["## E2. Амплитуда насыщения от плотности пучка α = n_b/n_p", "",
           md_table(r2, [("α", "alpha"), ("γ теор", "gamma_th"), ("γ PIC", "gamma_meas"),
                         ("ошибка γ, %", "gamma_err"), ("t_sat", "t_sat"), ("E_sat PIC", "E_sat"),
                         ("3.12γ²/k", "E_trap"), ("отношение", "ratio"), ("ω_B/γ", "wB_over_g"),
                         ("W_E,sat/K_b0", "WE_sat_frac"), ("невязка энергии", "energy_err")],
                    {"gamma_th": "{:.4f}", "gamma_meas": "{:.4f}", "gamma_err": "{:+.2f}",
                     "t_sat": "{:.1f}", "E_sat": "{:.4f}", "E_trap": "{:.4f}", "ratio": "{:.3f}",
                     "wB_over_g": "{:.2f}", "WE_sat_frac": "{:.3f}", "energy_err": "{:.1e}"}),
           "",
           f"Степенные законы на интервале α = {al.min():g}…{al.max():g}: "
           f"**E_sat(PIC) ∝ α^{sl_pic:.3f}**, теория захвата с точным γ ∝ α^{sl_th:.3f}, "
           f"γ_max ∝ α^{sl_g:.3f}; предел слабого пучка — α^(2/3) = α^0.667 "
           "(γ ∝ α^(1/3), k ≈ const). Отношение E_sat/(3.12γ²/k) = "
           f"{min(x['ratio'] for x in r2):.2f}…{max(x['ratio'] for x in r2):.2f}: константа захвата "
           "в многомодовом PIC чуть больше, чем в одноволновой модели "
           f"(ω_B/γ = {min(x['wB_over_g'] for x in r2):.2f}…{max(x['wB_over_g'] for x in r2):.2f} "
           "против 1.77).", "", "![](E2_saturation_alpha.png)", ""]

    # ------------------------------------------------------------------ E3 E_sat(v_b)
    r3 = sorted([x for x in res if x["series"] == "E3 vb"], key=lambda x: x["vb"])
    vb = np.array([x["vb"] for x in r3])
    sl_vb = np.polyfit(np.log(vb), np.log([x["E_sat"] for x in r3]), 1)[0]
    for x in r3:
        x["E_over_vb"] = x["E_sat"] / x["vb"]
        x["kvb"] = x["k_main"] * x["vb"]
        x["gamma_err"] = (x["gamma_meas"] / x["gamma_th"] - 1) * 100
    fig, ax = plt.subplots(figsize=(5.5, 4))
    ax.loglog(vb, [x["E_sat"] for x in r3], "o", ms=7, mfc=C["field"], mec=C["surface"],
              label=f"PIC: E_sat ∝ v_b^{sl_vb:.3f}")
    ax.loglog(vb, r3[len(r3) // 2]["E_sat"] / vb[len(r3) // 2] * vb, color=C["text2"], ls="--",
              label="∝ v_b (теория размерностей)")
    ax.set_xlabel("v_b / v₀")
    ax.set_ylabel("E_sat, ед. m ω_p v₀/e")
    ax.set_title("Насыщение от скорости пучка (α = 0.01)", loc="left")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "E3_saturation_vb.png"), dpi=150)
    plt.close(fig)
    save_csv("E3_saturation_vb.csv", r3, ["vb", "gamma_th", "gamma_meas", "gamma_err", "k_main",
                                          "kvb", "t_sat", "E_sat", "E_over_vb", "wB_over_g"])
    md += ["## E3. Амплитуда насыщения от скорости пучка v_b (α = 0.01)", "",
           md_table(r3, [("v_b/v₀", "vb"), ("γ теор", "gamma_th"), ("γ PIC", "gamma_meas"),
                         ("ошибка γ, %", "gamma_err"), ("k_max·v_b", "kvb"), ("t_sat", "t_sat"),
                         ("E_sat", "E_sat"), ("E_sat/v_b", "E_over_vb"), ("ω_B/γ", "wB_over_g")],
                    {"gamma_th": "{:.4f}", "gamma_meas": "{:.4f}", "gamma_err": "{:+.2f}",
                     "kvb": "{:.4f}", "t_sat": "{:.1f}", "E_sat": "{:.4f}", "E_over_vb": "{:.4f}",
                     "wB_over_g": "{:.2f}"}),
           "", f"**E_sat ∝ v_b^{sl_vb:.3f}**, инкремент от v_b не зависит, k_max ∝ 1/v_b. "
           "В холодной задаче скорость пучка — только масштаб: в переменных x·ω_p/v_b, v/v_b, "
           "E·e/(mω_p v_b) задача одна и та же (теория размерностей).", "",
           "![](E3_saturation_vb.png)", ""]

    # ------------------------------------------------------------------ E4 тёплый пучок
    r4 = sorted([x for x in res if x["series"] == "E4 dvb"], key=lambda x: x["dvb"])
    for x in r4:
        x["gamma_err"] = (x["gamma_meas"] / x["gamma_th"] - 1) * 100
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    dv = np.array([x["dvb"] for x in r4])
    ax = axs[0]
    ax.plot(dv, [x["gamma_th"] for x in r4], color=C["text2"], ls="--", label="кинетическая теория")
    ax.plot(dv, [x["gamma_meas"] for x in r4], "o", ms=7, mfc=C["field"], mec=C["surface"],
            label="PIC")
    ax.axvline(np.cbrt(0.005), color=C["muted"], ls=":", label="(α/2)^⅓ — граница режимов")
    ax.set_xlabel("Δv / v_b")
    ax.set_ylabel("γ / ω_p (главная мода)")
    ax.set_title("Инкремент тёплого пучка (α = 0.01)", loc="left")
    ax.legend(fontsize=8)
    ax = axs[1]
    ax.semilogy(dv, [x["E_sat"] for x in r4], "o-", color=C["main"], label="E_sat (первый максимум)")
    ax.semilogy(dv, [x["E_trap"] for x in r4], color=C["text2"], ls="--", label="3.12γ²/k")
    ax.axvline(np.cbrt(0.005), color=C["muted"], ls=":")
    ax.set_xlabel("Δv / v_b")
    ax.set_ylabel("E_sat")
    ax.set_title("Насыщение: захват → квазилинейный режим", loc="left")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "E4_warm_beam.png"), dpi=150)
    plt.close(fig)
    save_csv("E4_warm_beam.csv", r4, ["dvb", "gamma_th", "gamma_meas", "gamma_err", "t_sat",
                                      "E_sat", "E_trap", "wB_over_g", "WE_sat_frac",
                                      "WE_end_frac", "WE_ql_frac", "plateau_v1", "plateau_v2"])
    md += ["## E4. Тёплый пучок: кинетическая теория и переход к квазилинейному режиму", "",
           "γ теор — корень кинетического уравнения ε(ω,k) = 0 с функцией Z (максвелловский "
           "пучок с разбросом Δv), для самой быстрой моды ящика.", "",
           md_table(r4, [("Δv/v_b", "dvb"), ("γ кинет.", "gamma_th"), ("γ PIC", "gamma_meas"),
                         ("ошибка, %", "gamma_err"), ("E_sat", "E_sat"), ("3.12γ²/k", "E_trap"),
                         ("ω_B/γ", "wB_over_g"), ("W_E,sat/K_b0", "WE_sat_frac"),
                         ("W_E,конец", "WE_end_frac"), ("W_E^КЛ", "WE_ql_frac")],
                    {"gamma_th": "{:.4f}", "gamma_meas": "{:.4f}", "gamma_err": "{:+.2f}",
                     "E_sat": "{:.4f}", "E_trap": "{:.4f}", "wB_over_g": "{:.2f}",
                     "WE_sat_frac": "{:.3f}", "WE_end_frac": "{:.3f}", "WE_ql_frac": "{:.3f}"}),
           "", f"Граница гидродинамического режима Δv ≈ (α/2)^(1/3)·v_b = {np.cbrt(0.005):.3f}·v_b: "
           "при меньшем разбросе пучок ведёт себя как холодный (захват, ω_B/γ ≈ 1.8), при большем "
           "инкремент быстро падает, яркого первого максимума нет — волна растёт и насыщается "
           "плавно, как в квазилинейной теории.", "", "![](E4_warm_beam.png)", ""]

    # ------------------------------------------------------------------ E5 квазилинейная теория
    r5 = sorted([x for x in res if x["series"] == "E5 ql"], key=lambda x: x["alpha"])
    for x in r5:
        x["ql_diff"] = (x["WE_ql_frac"] / x["WE_end_frac"] - 1) * 100
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    ax = axs[0]
    for x, col in zip(r5, ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#e87ba4", "#008300"]):
        e = x["fv_edges"]
        ax.plot(0.5 * (e[1:] + e[:-1]), x["fv"], color=col, lw=1.4, label=f"α = {x['alpha']:g}")
    ax.set_yscale("log")
    ax.set_ylim(1e-2, 30)
    ax.set_xlabel("v / v_b")
    ax.set_ylabel("f_b(v)  (∫f dv = 1)")
    ax.set_title(f"Распределение пучка в конце счёта (t ≈ 6·t_sat)", loc="left")
    ax.legend(fontsize=8)
    ax = axs[1]
    for x, col in zip(r5, ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#e87ba4", "#008300"]):
        ax.semilogy(x["hist_t"] / x["t_sat"], x["hist_WE"], color=col, lw=1.2, label=f"α = {x['alpha']:g}")
    ax.set_xlabel("t / t_sat")
    ax.set_ylabel("W_E / K_b0")
    ax.set_ylim(1e-4, 1)
    ax.set_title("Энергия поля: насыщение и поздняя стадия", loc="left")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "E5_quasilinear.png"), dpi=150)
    plt.close(fig)
    save_csv("E5_quasilinear.csv", r5, ["alpha", "t_sat", "t_end", "plateau_v1", "plateau_v2",
                                        "WE_end_frac", "WE_ql_frac", "ql_diff", "WE_sat_frac",
                                        "energy_err"])
    md += ["## E5. Сравнение с квазилинейной теорией насыщения", "",
           "Квазилинейная теория: резонансные электроны пучка размазываются в плато f = const на "
           "[v₁, v₂]. Энергия пучка с плато K_пл = n_b L (v₁² + v₁v₂ + v₂²)/6; отданная энергия "
           "K_b0 − K_пл уходит в ленгмюровские волны, половина её — электрическое поле: "
           "W_E^КЛ = (K_b0 − K_пл)/2. Края плато измеряются по f(v) на уровне половины высоты, "
           "W_E — среднее за последние 50/ω_p.", "",
           md_table(r5, [("α", "alpha"), ("t_sat", "t_sat"), ("t_конец", "t_end"),
                         ("v₁", "plateau_v1"), ("v₂", "plateau_v2"), ("W_E PIC", "WE_end_frac"),
                         ("W_E^КЛ", "WE_ql_frac"), ("разница, %", "ql_diff"),
                         ("W_E в максимуме", "WE_sat_frac")],
                    {"t_sat": "{:.0f}", "t_end": "{:.0f}", "plateau_v1": "{:.2f}",
                     "plateau_v2": "{:.2f}", "WE_end_frac": "{:.3f}", "WE_ql_frac": "{:.3f}",
                     "ql_diff": "{:+.0f}", "WE_sat_frac": "{:.3f}"}),
           "", "Полная квазилинейная релаксация холодного пучка в плато [0, v_b] дала бы "
           "W_E = K_b0/3 ≈ 0.333 — это верхняя оценка; за время счёта плато ещё не дошло до нуля "
           "скоростей. При α ≳ 0.1 энергия заметно уходит в нагрев электронов плазмы, и "
           "баланс «пучок ↔ волны» перестаёт выполняться — это результат, а не ошибка.", "",
           "![](E5_quasilinear.png)", ""]

    # ------------------------------------------------------------------ E6 численная схема
    rows6 = []
    for x in res_num:
        lab = x["series"].split(" ", 1)[1]
        x["param"] = lab
        x["gamma_err"] = (x["gamma_meas"] / x["gamma_th"] - 1) * 100
        rows6.append(x)
    save_csv("E6_numerics.csv", rows6, ["param", "dt", "ng", "npart", "vtp", "gamma_th",
                                        "gamma_meas", "gamma_err", "E_sat", "wB_over_g",
                                        "energy_err", "wall_s"])
    fig, axs = plt.subplots(1, 3, figsize=(13, 3.8))
    for ax, key, lab in ((axs[0], "dt", "Δt·ω_p"), (axs[1], "ng", "узлов сетки N_g"),
                         (axs[2], "npart", "частиц каждого сорта")):
        xs = [x for x in rows6 if x["param"].startswith({"dt": "dt", "ng": "ng", "npart": "N"}[key])]
        xs.sort(key=lambda x: x[key])
        ax.semilogx([x[key] for x in xs], [abs(x["gamma_err"]) for x in xs], "o-", color=C["field"],
                    label="|ошибка γ|, %")
        ax.semilogx([x[key] for x in xs], [x["energy_err"] * 100 for x in xs], "s-", color=C["beam"],
                    label="невязка энергии, % K_b0")
        ax.set_xlabel(lab)
        ax.set_yscale("log")
        ax.legend(fontsize=8)
    axs[0].set_title("Сходимость по шагу времени", loc="left")
    axs[1].set_title("По размеру сетки", loc="left")
    axs[2].set_title("По числу частиц", loc="left")
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "E6_numerics.png"), dpi=150)
    plt.close(fig)
    md += ["## E6. Погрешности и устойчивость численной схемы", "",
           "Базовый расчёт: α = 0.01, Δt = 0.1, N_g = 1024, N = 65 536, v_Tp = 0.02 v_b; "
           "меняется один параметр. Невязка энергии — max |W_E + K_плазмы + K_пучка − const| "
           "за весь счёт в долях начальной энергии пучка.", "",
           md_table(rows6, [("вариант", "param"), ("γ PIC", "gamma_meas"), ("ошибка γ, %", "gamma_err"),
                            ("E_sat", "E_sat"), ("ω_B/γ", "wB_over_g"), ("невязка энергии", "energy_err"),
                            ("время счёта, с", "wall_s")],
                    {"gamma_meas": "{:.4f}", "gamma_err": "{:+.2f}", "E_sat": "{:.4f}",
                     "wB_over_g": "{:.2f}", "energy_err": "{:.1e}", "wall_s": "{:.0f}"}),
           "", "Схема «чехарда» устойчива при ω_p Δt < 2; при Δt = 0.4 ошибка частоты "
           "(ω_pΔt)²/24 ≈ 0.7 %. Холодная плазма (v_Tp = 0) на сетке численно нагревается — "
           "поэтому взята малая температура v_Tp = 0.02 v_b (Δx ≈ 2.4 λ_D) и сглаживание "
           "F(k) = cos⁴(kΔx/2).", "", "![](E6_numerics.png)", ""]

    # ------------------------------------------------------------------ E7 одноволновая модель
    rows7 = []
    for a_ in [0.001, 0.01, 0.1]:
        Cc, wbg, tg = saturation_constant(a_)
        rows7.append(dict(alpha=a_, C=Cc, wB_over_g=wbg, t_sat_gamma=tg))
    save_csv("E7_single_wave.csv", rows7, ["alpha", "C", "wB_over_g", "t_sat_gamma"])
    md += ["## E7. Одноволновая модель: универсальная константа насыщения", "",
           "Модель огибающей: dÊ/dt = (α/k)⟨e^(−iψ)⟩, dψ/dt = kv − ω_p, dv/dt = −Re(Ê e^(iψ)); "
           "РК4, 4096 частиц. При kv_b = ω_p параметр α убирается масштабированием, поэтому "
           "k·E_sat/γ² не зависит от α:", "",
           md_table(rows7, [("α", "alpha"), ("k·E_sat/γ²", "C"), ("ω_B/γ", "wB_over_g"),
                            ("γ·t_sat (от E₀ = 10⁻⁷)", "t_sat_gamma")],
                    {"C": "{:.4f}", "wB_over_g": "{:.4f}", "t_sat_gamma": "{:.2f}"}), ""]

    # ------------------------------------------------------------------ F1–F3 иллюстрации
    figures_stages(C, N)
    figures_dispersion(C)
    md += ["## Иллюстрации", "", "![](F1_stages.png)", "", "![](F2_energy_spectrum.png)", "",
           "![](F3_dispersion.png)", ""]
    md += [f"_Полное время всех расчётов: {time.time() - t_start:.0f} с._", ""]
    with open(os.path.join(RES, "СВОДКА.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("Готово. Сводка: results/СВОДКА.md", flush=True)


def figures_stages(C, N):
    """Фазовые портреты на четырёх стадиях + энергия, спектрограмма, спектр."""
    import matplotlib.pyplot as plt
    s = PIC(PICParams(npart=N))
    tr = diag.StageTracker(s)
    snaps = {}
    targets = [("1. затравка, t = 15", 15.0), ("2. линейный рост, t = 60", 60.0)]
    got3 = got4 = False
    while s.t < 250:
        s.step(10)
        tr.update()
        for name, tt in targets:
            if name not in snaps and s.t >= tt:
                snaps[name] = (s.x.copy(), s.v.copy(), s.Ek.copy())
        if tr.sat is not None and not got3:
            snaps[f"3. захват (насыщение), t = {s.t:.0f}"] = (s.x.copy(), s.v.copy(), s.Ek.copy())
            got3 = True
        if s.t >= 240 and not got4:
            snaps[f"4. перемешивание, t = {s.t:.0f}"] = (s.x.copy(), s.v.copy(), s.Ek.copy())
            got4 = True
    fig, axs = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey=True)
    for ax, (name, (x, v, Ek)) in zip(axs.flat, sorted(snaps.items())):
        N_ = s.N
        ax.plot(x[:N_], v[:N_], ",", color=C["plasma"], alpha=0.5, rasterized=True)
        ax.plot(x[N_:], v[N_:], ",", color=C["beam"], alpha=0.7, rasterized=True)
        m = s.m_main
        A = 2 * abs(Ek[m]) / s.p.ng
        k = s.k_modes[m]
        xs = np.linspace(0, s.L, 400)
        r = np.sqrt(np.maximum(2 * A / k * (1 - np.sin(k * xs + np.angle(Ek[m]))), 0))
        vph = s.omega_ref / k
        ax.plot(xs, vph + r, color=C["text"], lw=0.8)
        ax.plot(xs, vph - r, color=C["text"], lw=0.8)
        ax.set_title(name, loc="left")
        ax.set_ylim(-0.6, 1.6)
        ax.set_xlim(0, s.L)
    for ax in axs[1]:
        ax.set_xlabel("x, ед. v_b/ω_p")
    for ax in axs[:, 0]:
        ax.set_ylabel("v / v_b")
    fig.suptitle("Фазовые портреты (α = 0.01): синие — электроны плазмы, оранжевые — пучка, "
                 "линия — сепаратриса главной волны", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "F1_stages.png"), dpi=150)
    plt.close(fig)

    h = s.hist
    fig, axs = plt.subplots(1, 3, figsize=(15, 4))
    ax = axs[0]
    K0 = s.K0_beam
    ax.semilogy(h["t"], h["WE"] / K0, color=C["field"], label="поле W_E")
    ax.semilogy(h["t"], s.L * (2 * np.abs(h["Ek"][:, s.m_main - 1])) ** 2 / 4 / K0,
                color=C["main"], label="главная волна")
    ax.semilogy(h["t"], np.maximum((h["K"][0, 1] - h["K"][:, 1]) / K0, 1e-12), color=C["beam"],
                label="−ΔK пучка")
    t1 = 4 / s.gamma_ref
    j = int(t1 / s.p.dt)
    W1 = s.L * (2 * abs(h["Ek"][j, s.m_main - 1])) ** 2 / 4 / K0
    tt = np.array([t1 - 20, 110])
    ax.semilogy(tt, W1 * np.exp(2 * s.gamma_ref * (tt - t1)), "--", color=C["text2"],
                label=f"exp(2γt), γ = {s.gamma_ref:.4f}")
    for st_t in tr.t_stage[1:]:
        if st_t:
            ax.axvline(st_t, color=C["muted"], lw=0.8, ls=":")
    ax.set_ylim(1e-9, 1)
    ax.set_xlabel("t·ω_p")
    ax.set_ylabel("энергия / K_b0")
    ax.set_title("Энергия (пунктир — границы стадий)", loc="left")
    ax.legend(fontsize=8)
    ax = axs[1]
    A2 = (2 * np.abs(h["Ek"])) ** 2
    im = ax.imshow(np.log10(A2.T + 1e-30), origin="lower", aspect="auto",
                   extent=[0, h["t"][-1], 0.5 / s.p.n_waves, (s.m_store + 0.5) / s.p.n_waves],
                   vmin=np.log10(A2.max()) - 9, vmax=np.log10(A2.max()), cmap=style_cmap())
    ax.set_ylim(0, 3)
    ax.set_xlabel("t·ω_p")
    ax.set_ylabel("k / k_max")
    ax.set_title("Спектрограмма lg|E_k|²", loc="left")
    fig.colorbar(im, ax=ax)
    ax = axs[2]
    kk = s.k_modes[1:s.m_store + 1] / s.k_max
    for tt_, col in ((40, C["plasma"]), (tr.sat["t"] if tr.sat else 85, C["main"]), (240, C["beam"])):
        j = int(tt_ / s.p.dt)
        ax.semilogy(kk, A2[j], "o-", ms=3, color=col, label=f"t = {tt_:.0f}")
    ax.set_xlabel("k / k_max")
    ax.set_ylabel("|E_k|²")
    ax.set_title("Спектр волн: линейная стадия → турбулентность", loc="left")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "F2_energy_spectrum.png"), dpi=150)
    plt.close(fig)


def figures_dispersion(C):
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 3, figsize=(15, 4))
    k = np.linspace(0.005, 2, 600)
    ax = axs[0]
    for a_, col in ((0.001, C["plasma"]), (0.01, C["main"]), (0.1, C["beam"])):
        _, g = disp.fluid_growth(k, disp.beam_plasma_species(a_))
        ax.plot(k, g, color=col, label=f"α = {a_:g}")
    ax.set_xlabel("k·v_b/ω_p")
    ax.set_ylabel("γ/ω_p")
    ax.set_title("Инкремент γ(k) — точное решение", loc="left")
    ax.legend(fontsize=8)
    ax = axs[1]
    r = disp.fluid_roots(k, disp.beam_plasma_species(0.01))
    for i in range(4):
        ax.plot(k, r[:, i].real, ".", ms=1.5, color=C["text2"])
    wr, g = disp.fluid_growth(k, disp.beam_plasma_species(0.01))
    ax.plot(k, np.where(g > 0, wr, np.nan), color=C["main"], lw=2.5, label="растущая волна")
    ax.axhline(1, color=C["plasma"], ls="--", label="ω = ω_p")
    ax.plot(k, k + 0.1, color=C["beam"], ls="--", label="ω = kv_b ± ω_b")
    ax.plot(k, k - 0.1, color=C["beam"], ls="--")
    ax.set_ylim(-1.5, 2.5)
    ax.set_xlabel("k·v_b/ω_p")
    ax.set_ylabel("Re ω/ω_p")
    ax.set_title("Ветви Re ω(k), α = 0.01", loc="left")
    ax.legend(fontsize=8)
    ax = axs[2]
    al = np.logspace(-4, 0, 60)
    gx = [disp.most_unstable(disp.beam_plasma_species(a_))[1] for a_ in al]
    ax.loglog(al, gx, color=C["main"], lw=2, label="точный корень")
    ax.loglog(al, disp.gamma_hint(al), "--", color=C["text2"], label="подсказка (√3/2)α^⅓")
    ax.loglog(al, disp.gamma_weak_beam(al), ":", color=C["text2"], label="(√3/2)(α/2)^⅓")
    ax.set_xlabel("α = n_b/n_p")
    ax.set_ylabel("γ_max/ω_p")
    ax.set_title("γ_max(α): формула подсказки завышает", loc="left")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "F3_dispersion.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
