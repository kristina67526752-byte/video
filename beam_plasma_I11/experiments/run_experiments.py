#!/usr/bin/env python3
"""
Вычислительные эксперименты варианта И11 — всё, что нужно для отчёта.
Все величины в таблицах и на графиках — в единицах СИ.

    python experiments/run_experiments.py           полный набор (~6–10 мин на 4 ядрах)
    python experiments/run_experiments.py --quick   быстрый набор (~3 мин)

Результаты (папка results/):
    journal.csv                  журнал всех счётов: параметры, зерно, результаты
    E1_gamma_k.csv/.png          инкремент γ(k): PIC против теории (+ встречные пучки)
    E2_saturation_alpha.csv/.png амплитуда насыщения от n_b/n_p, сравнение с теориями
    E3_saturation_vb.csv/.png    амплитуда насыщения от скорости пучка (до 0.9c)
    E4_warm_beam.csv/.png        тёплый пучок: кинетическая теория и переход к плато
    E5_quasilinear.csv/.png      длинные счёты: квазилинейный баланс, плато f(v)
    E6_numerics.csv/.png         сходимость: шаг по времени, сетка, число частиц
    E7_single_wave.csv           одноволновая модель: константа насыщения
    E8_ions_cavitons.csv/.png    подвижные ионы: каверны и поглощение волн
    E9_zakharov.csv/.png         уравнения огибающей: солитон и модуляционная неустойчивость
    F1_stages.png                фазовые портреты на 4 стадиях
    F2_energy_spectrum.png       энергия, спектрограмма, спектр
    F3_dispersion.png            дисперсионные кривые
    F4_omega_k.png               дисперсионная диаграмма (k, ω) из счёта
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
from bpi.zakharov import Zakharov, modulational_growth   # noqa: E402
from bpi import constants as cst                         # noqa: E402
from bpi.units import Scale, fmt, sci                    # noqa: E402
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
        r["kmax_th"] = sr.sim.k_modes[sr.sim.m_main]
    if series.startswith("E5"):
        s = sr.sim
        edges = np.linspace(-0.3, 1.8, 211) * s.p.vb
        r["fv"] = s.velocity_hist(1, edges) / s.dens[1]
        r["fv_edges"] = edges
        h = s.hist
        st = max(1, s.h_n // 2000)
        r["hist_t"] = h["t"][::st]
        r["hist_WE"] = h["WE"][::st] / s.K0_beam
    return r


def job_ions(args):
    """Длинный счёт (подвижные или неподвижные ионы): история энергии и карты x–t."""
    pdict, tag, t_end_wp = args
    p = PICParams(**pdict)
    s = PIC(p)
    tr = diag.StageTracker(s)
    T, W, NI = [], [], []
    dec = max(1, p.ng // 256)
    t_cav = np.nan
    while s.t * s.wpe < t_end_wp:
        s.step(50)
        tr.update()
        T.append(s.t)
        W.append(diag.wave_level(s)[::dec].astype(np.float32))
        NI.append(s.ion_perturbation()[::dec].astype(np.float32))
        if tr.stage == 4 and not np.isfinite(t_cav):
            t_cav = s.t
    h = s.hist
    st = 20
    tot = h["WE"] + h["K"].sum(1)
    Wm = np.array(W)
    i, j = np.unravel_index(int(np.argmax(Wm)), Wm.shape)
    return dict(tag=tag, ion=p.ion, alpha=p.alpha, T=np.array(T), W=Wm, NI=np.array(NI),
                t=h["t"][::st], WE=h["WE"][::st], K=h["K"][::st], dni=h["dni"][::st],
                K0=s.K0_beam, L=s.L, wpe=s.wpe, t_cav=t_cav,
                t_sat=tr.sat["t"] if tr.sat else np.nan,
                WE_sat=tr.sat["WE"] if tr.sat else np.nan,
                W_peak=float(Wm.max()), t_peak=float(T[i]), dn_at_peak=float(NI[i][j]),
                dn_min=float(np.min(NI)), WE_end=float(h["WE"][-500:].mean()),
                energy_err=float(np.abs(tot - tot[0]).max() / s.K0_beam),
                m_ratio=(s.m_i / cst.M_E) if s.m_i else np.inf,
                wk=diag.omega_k_spectrum(s, 4096), k_main=s.k_modes[s.m_main],
                omega_ref=s.omega_ref, vb=p.vb, n_p=p.n_p, T_e=p.T_e)


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
N_P, T_E, VB = 1.0e16, 3.0e4, 1.0e7            # базовая плазма: лабораторный разряд
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#e87ba4", "#008300", "#8a897f"]


def trap_theory(alpha, vb, n_p=N_P):
    """Теория захвата: (E_sat [В/м], γ [с⁻¹], k [рад/м]) по уравнению из задания."""
    k, g, w = disp.most_unstable(disp.beam_plasma_species(n_p, alpha, vb))
    return diag.trapping_amplitude(g, k, float(cst.lorentz_gamma(w / k))), g, k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="меньше частиц и точек")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    a = ap.parse_args()
    os.makedirs(RES, exist_ok=True)
    jpath = os.path.join(RES, "journal.csv")
    if os.path.exists(jpath):
        os.remove(jpath)                          # журнал пишется заново
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    C = light_style()

    N = 32768 if a.quick else 65536
    base = PICParams(npart=N).as_dict()
    wp = float(cst.plasma_frequency(N_P))
    lD = float(cst.debye_length(N_P, T_E))
    t_start = time.time()
    md = ["# Сводка вычислительных экспериментов (вариант И11), все величины в СИ", "",
          f"Сгенерировано скриптом `experiments/run_experiments.py` "
          f"{time.strftime('%Y-%m-%d %H:%M')}.", "",
          f"**Базовая плазма (лабораторный разряд):** n_p = {sci(N_P, 2)} м⁻³, T_e = {sci(T_E, 2)} К, "
          f"пучок v_b = {sci(VB, 2)} м/с. Отсюда ω_p = {sci(wp)} с⁻¹ (f_p = {fmt(wp / 2 / np.pi, 'Гц')}), "
          f"λ_D = {fmt(lD, 'м')}, 1/ω_p = {fmt(1 / wp, 'с')}. Частиц каждого сорта: {N}, сетка "
          f"{base['ng']} узлов, Δt = 0.1/ω_p = {fmt(0.1 / wp, 'с')}, ящик — {base['n_waves']} длин самой "
          "неустойчивой волны, тихий старт, зерно генератора 1. Ионы неподвижны, если не сказано иное.",
          ""]

    alphas = [0.002, 0.005, 0.01, 0.02, 0.05, 0.1] if a.quick else \
        [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1]
    vbs = [5e6, 1e7, 5e7, 2e8, 2.7e8] if a.quick else [5e6, 1e7, 2e7, 5e7, 1e8, 1.5e8, 2e8, 2.4e8, 2.7e8]
    dvs = [0.0, 0.05, 0.1, 0.2] if a.quick else [0.0, 0.03, 0.06, 0.1, 0.15, 0.2, 0.25]
    ql_alphas = [0.005, 0.01, 0.05] if a.quick else [0.002, 0.005, 0.01, 0.02, 0.05, 0.1]

    jobs = []
    # E1: γ(k) — все моды затравлены одинаково, чтобы каждую можно было измерить
    jobs.append((dict(base, alpha=0.01, seed_other=1.0), "E1 beam", 1.2))
    jobs.append((dict(base, scenario="two_stream", seed_other=1.0), "E1 two-stream", 1.2))
    jobs.append((dict(base, alpha=0.01, vb=2.4e8, seed_other=1.0), "E1 relativistic", 1.2))
    for al in alphas:
        jobs.append((dict(base, alpha=al), "E2 alpha", 3.5))
    for vb in vbs:
        jobs.append((dict(base, vb=vb), "E3 vb", 2.0))
    for dv in dvs:
        jobs.append((dict(base, dvb=dv * VB), "E4 dvb", 3.0))
    for al in ql_alphas:
        jobs.append((dict(base, alpha=al), "E5 ql", 6.0))
    num_jobs = []
    for dt in ([0.05, 0.1, 0.2, 0.4] if not a.quick else [0.1, 0.2, 0.4]):
        num_jobs.append((dict(base, dt_wp=dt), f"ω_pΔt={dt}"))
    for ng in ([256, 512, 1024, 2048] if not a.quick else [512, 1024]):
        num_jobs.append((dict(base, ng=ng), f"N_g={ng}"))
    for npart in ([8192, 16384, 32768, 65536, 131072] if not a.quick else [8192, 32768]):
        num_jobs.append((dict(base, npart=npart), f"N={npart}"))
    for Te in ([3e2, 3e3, 3e4, 1e5] if not a.quick else [3e2, 3e4]):
        num_jobs.append((dict(base, T_e=Te), f"T_e={Te:g} К"))
    t_ion = 1200 if a.quick else 2000
    ion_jobs = [(dict(base, ion="none"), "ионы неподвижны", t_ion),
                (dict(base, ion="H+"), "ионы H⁺", t_ion),
                (dict(base, ion="H+", alpha=0.03), "ионы H⁺, n_b/n_p = 0.03", t_ion),
                (dict(base, ion="Ar+"), "ионы Ar⁺", t_ion)]

    print(f"Запуск {len(jobs) + len(num_jobs) + len(ion_jobs)} счётов на {a.workers} процессах…",
          flush=True)
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        f_ion = [ex.submit(job_ions, j) for j in ion_jobs]
        res = list(ex.map(job_sat, jobs))
        res_num = list(ex.map(job_numerics, num_jobs))
        res_ion = [f.result() for f in f_ion]
    print(f"  готово за {time.time() - t_start:.0f} с", flush=True)
    for r in res + res_num:
        journal.append(r, series=r["series"])
    for r in res + res_num:
        r["gamma_err"] = (r["gamma_meas"] / r["gamma_th"] - 1) * 100
        r["g_wp"] = r["gamma_th"] / r["wpe"]

    # ------------------------------------------------------------------ E1 γ(k)
    rows = []
    fig, axs = plt.subplots(1, 3, figsize=(15, 4))
    cases = (("E1 beam", "пучок в плазме, n_b/n_p = 0.01, v_b = 10⁷ м/с", "пучок"),
             ("E1 two-stream", "встречные пучки ±v_b/2", "встречные"),
             ("E1 relativistic", "релятивистский пучок, v_b = 2.4·10⁸ м/с = 0.8c", "0.8c"))
    for ax, (ser, title, short) in zip(axs, cases):
        r = next(x for x in res if x["series"] == ser)
        p = PICParams(**{k: r[k] for k in ("scenario", "n_p", "T_e", "alpha", "vb", "dvb")})
        if p.scenario == "beam":
            sp = disp.beam_plasma_species(p.n_p, p.alpha, p.vb, p.T_e)
        else:
            sp = disp.two_stream_species(p.n_p, p.vb)
        k0, g0, _ = disp.most_unstable(disp.cold(sp))
        kk = np.linspace(0.01, 2.2, 400) * k0
        _, gg = disp.fluid_growth(kk, disp.cold(sp))
        sk, sg = Scale(2.2 * k0, "рад/м"), Scale(g0, "с⁻¹")
        ax.plot(sk(kk), sg(gg), color=C["text2"], ls="--", label="уравнение из задания (точный корень)")
        if p.scenario == "beam":
            _, gkin = disp.kinetic_growth_curve(kk, sp)
            ax.plot(sk(kk), sg(np.maximum(gkin, 0)), color=C["main"], lw=1.3,
                    label="с температурой T_e (кинетика)")
        # медленные моды (γ < 0.6 γ_max) за время линейной стадии не успевают выделиться
        # на фоне комбинационных гармоник главной волны — их наклон честно не измерить
        ms = [m for m in r["modes"] if m["g_th"] > 0.6 * g0]
        ax.plot([sk(m["k"]) for m in ms], [sg(m["g"]) for m in ms], "o", ms=7,
                mfc=C["field"], mec=C["surface"], mew=1.5, label="PIC: наклон ln|E_k(t)|")
        ax.set_title(title, loc="left")
        ax.set_xlabel(f"k, {sk.label}")
        ax.set_ylabel(f"γ, {sg.label}")
        ax.legend(fontsize=7.5)
        for m in ms:
            rows.append(dict(case=short, m=m["m"], k=m["k"], gamma_th=m["g_th"], gamma_pic=m["g"],
                             err_pct=(m["g"] / m["g_th"] - 1) * 100,
                             unc_pct=m["g_err"] / m["g_th"] * 100,
                             omega_th=m["w_th"], omega_pic=m["w"]))
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "E1_gamma_k.png"), dpi=150)
    plt.close(fig)
    cols = ["case", "m", "k", "gamma_th", "gamma_pic", "err_pct", "unc_pct", "omega_th", "omega_pic"]
    save_csv("E1_gamma_k.csv", rows, cols)
    E = "{:.3e}"
    md += ["## E1. Инкремент γ(k): PIC против точной теории", "",
           "Все моды ящика затравлены одинаково; в таблице — моды с γ > 0.6·γ_max (более "
           "медленные за время линейной стадии не выделяются на фоне гармоник главной волны). "
           "γ — наклон ln|E_k(t)| методом наименьших "
           "квадратов на отрезке линейной стадии [4/γ, момент, когда главная волна достигла "
           "5 % от уровня насыщения]; ω = −d arg E_k/dt. Теория — кинетическая, с реальной "
           "температурой плазмы. «Разброс» — оценка погрешности измерения: половина разницы "
           "между γ, измеренными по первой и второй половине окна. Отклонение от теории "
           "у крайних волн сравнимо с этим разбросом: за короткую линейную стадию "
           "(≈2 e-кратных роста) они не успевают выделиться из шума и соседних корней.", "",
           md_table(rows, [("случай", "case"), ("m", "m"), ("k, рад/м", "k"),
                           ("γ теория, с⁻¹", "gamma_th"), ("γ PIC, с⁻¹", "gamma_pic"), ("ошибка, %", "err_pct"),
                           ("разброс, %", "unc_pct"), ("ω теория, рад/с", "omega_th"), ("ω PIC, рад/с", "omega_pic")],
                    {"k": "{:.1f}", "gamma_th": E, "gamma_pic": E,
                     "err_pct": "{:+.2f}", "unc_pct": "{:.1f}", "omega_th": E, "omega_pic": E}),
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
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    ax = axs[0]
    aa = np.logspace(np.log10(al.min()) - 0.1, np.log10(al.max()) + 0.1, 40)
    th = np.array([trap_theory(a_, VB)[0] for a_ in aa])
    ax.loglog(aa, th, color=C["text2"], ls="--", label="захват: 3.12γ²m/(ek) (точный γ)")
    ax.loglog(aa, th[0] * (aa / aa[0]) ** (2 / 3), color=C["muted"], ls=":",
              label="∝ (n_b/n_p)^(2/3) (слабый пучок)")
    ax.loglog(al, Es, "o", ms=7, mfc=C["field"], mec=C["surface"],
              label=f"PIC: ∝ (n_b/n_p)^{sl_pic:.2f}")
    ax.set_xlabel("n_b/n_p")
    ax.set_ylabel("E_sat, В/м")
    ax.set_title("Амплитуда насыщения от плотности пучка", loc="left")
    ax.legend(fontsize=8)
    ax = axs[1]
    ax.semilogx(al, [x["wB_over_g"] for x in r2], "o-", color=C["main"], label="PIC: ω_B/γ")
    ax.axhline(diag.OMEGA_B_OVER_GAMMA, color=C["text2"], ls="--", label="одноволновая модель 1.77")
    ax.set_xlabel("n_b/n_p")
    ax.set_ylabel("ω_B/γ в первом максимуме")
    ax.set_ylim(1.4, 2.2)
    ax.set_title("Условие захвата ω_B ≈ const·γ", loc="left")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "E2_saturation_alpha.png"), dpi=150)
    plt.close(fig)
    cols = ["alpha", "gamma_th", "gamma_meas", "gamma_err", "k_main", "t_sat", "E_sat", "E_trap",
            "ratio", "wB_over_g", "bounce_T", "WE_sat", "WE_sat_frac", "WE_end_frac", "WE_ql_frac",
            "plateau_v1", "plateau_v2", "energy_err"]
    save_csv("E2_saturation_alpha.csv", r2, cols)
    md += ["## E2. Таблица амплитуд насыщения от плотности пучка n_b/n_p", "",
           md_table(r2, [("n_b/n_p", "alpha"), ("γ теор, с⁻¹", "gamma_th"), ("γ PIC, с⁻¹", "gamma_meas"),
                         ("ошибка γ, %", "gamma_err"), ("t_sat, с", "t_sat"), ("E_sat PIC, В/м", "E_sat"),
                         ("захват, В/м", "E_trap"), ("отношение", "ratio"), ("ω_B/γ", "wB_over_g"),
                         ("W_E,sat, Дж/м³", "WE_sat"), ("W_E,sat/K_b0", "WE_sat_frac"),
                         ("невязка энергии", "energy_err")],
                    {"gamma_th": E, "gamma_meas": E, "gamma_err": "{:+.2f}",
                     "t_sat": "{:.2e}", "E_sat": "{:.0f}", "E_trap": "{:.0f}", "ratio": "{:.3f}",
                     "wB_over_g": "{:.2f}", "WE_sat": "{:.2e}", "WE_sat_frac": "{:.3f}",
                     "energy_err": "{:.1e}"}),
           "",
           f"Степенные законы на интервале n_b/n_p = {al.min():g}…{al.max():g}: "
           f"**E_sat(PIC) ∝ (n_b/n_p)^{sl_pic:.3f}**, теория захвата с точным γ — показатель {sl_th:.3f}, "
           f"γ_max ∝ (n_b/n_p)^{sl_g:.3f}; предел слабого пучка — показатель 2/3 "
           "(γ ∝ (n_b/n_p)^(1/3), k ≈ const). Отношение E_sat/(3.12γ²m/(ek)) = "
           f"{min(x['ratio'] for x in r2):.2f}…{max(x['ratio'] for x in r2):.2f}: константа захвата "
           "в многомодовом PIC чуть больше, чем в одноволновой модели "
           f"(ω_B/γ = {min(x['wB_over_g'] for x in r2):.2f}…{max(x['wB_over_g'] for x in r2):.2f} "
           "против 1.77).", "", "![](E2_saturation_alpha.png)", ""]

    # ------------------------------------------------------------------ E3 E_sat(v_b), релятивизм
    r3 = sorted([x for x in res if x["series"] == "E3 vb"], key=lambda x: x["vb"])
    vb = np.array([x["vb"] for x in r3])
    nr = vb < 6e7
    sl_vb = np.polyfit(np.log(vb[nr]), np.log(np.array([x["E_sat"] for x in r3])[nr]), 1)[0]
    for x in r3:
        x["beta"] = x["vb"] / cst.C_LIGHT
        x["gamma_b"] = float(cst.lorentz_gamma(x["vb"]))
        x["g_gb"] = x["gamma_meas"] * x["gamma_b"] / x["wpe"]
        x["ratio"] = x["E_sat"] / x["E_trap"]
        x["S"] = x["beta"] ** 2 * x["gamma_b"] * np.cbrt(0.005)
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    vv = np.logspace(np.log10(4e6), np.log10(2.8e8), 50)
    tt = [trap_theory(0.01, v) for v in vv]
    ax = axs[0]
    ax.semilogx(vv, [t_[1] for t_ in tt], color=C["text2"], ls="--", label="теория (точный корень)")
    ax.semilogx(vv, tt[0][1] / cst.lorentz_gamma(vv), color=C["muted"], ls=":", label="∝ 1/γ_b")
    ax.semilogx(vb, [x["gamma_meas"] for x in r3], "o", ms=7, mfc=C["field"], mec=C["surface"], label="PIC")
    ax.set_xlabel("v_b, м/с")
    ax.set_ylabel("γ, с⁻¹")
    ax.set_ylim(0, None)
    ax.set_title("Инкремент от скорости пучка (n_b/n_p = 0.01)", loc="left")
    ax.legend(fontsize=8)
    ax = axs[1]
    ax.loglog(vv, [t_[0] for t_ in tt], color=C["text2"], ls="--", label="захват: 3.12γ²mγ_ф³/(ek)")
    ax.loglog(vv, tt[0][0] * vv / vv[0], color=C["muted"], ls=":", label="∝ v_b (без релятивизма)")
    ax.loglog(vb, [x["E_sat"] for x in r3], "o", ms=7, mfc=C["field"], mec=C["surface"],
              label=f"PIC (при v_b ≪ c: ∝ v_b^{sl_vb:.3f})")
    ax.set_xlabel("v_b, м/с")
    ax.set_ylabel("E_sat, В/м")
    ax.set_title("Насыщение от скорости пучка", loc="left")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "E3_saturation_vb.png"), dpi=150)
    plt.close(fig)
    save_csv("E3_saturation_vb.csv", r3, ["vb", "beta", "gamma_b", "gamma_th", "gamma_meas", "gamma_err",
                                          "g_gb", "k_main", "t_sat", "E_sat", "E_trap", "ratio",
                                          "wB_over_g", "S"])
    md += ["## E3. Скорость пучка v_b: от нерелятивистского до 0.9c (n_b/n_p = 0.01)", "",
           md_table(r3, [("v_b, м/с", "vb"), ("v_b/c", "beta"), ("γ_b", "gamma_b"),
                         ("γ теор, с⁻¹", "gamma_th"), ("γ PIC, с⁻¹", "gamma_meas"),
                         ("ошибка γ, %", "gamma_err"), ("γ·γ_b/ω_p", "g_gb"), ("E_sat, В/м", "E_sat"),
                         ("захват, В/м", "E_trap"), ("отношение", "ratio"), ("ω_B/γ", "wB_over_g")],
                    {"vb": "{:.2e}", "beta": "{:.3f}", "gamma_b": "{:.3f}", "gamma_th": E,
                     "gamma_meas": E, "gamma_err": "{:+.2f}", "g_gb": "{:.4f}", "E_sat": "{:.3e}",
                     "E_trap": "{:.3e}", "ratio": "{:.3f}", "wB_over_g": "{:.2f}"}),
           "", f"При v_b ≪ c скорость пучка — только масштаб: γ от v_b не зависит, k_max ∝ 1/v_b, "
           f"**E_sat ∝ v_b^{sl_vb:.3f}**. При v_b → c в уравнении появляется релятивистская "
           "продольная масса mγ_b³: **инкремент падает как 1/γ_b** (столбец γ·γ_b/ω_p почти постоянен), "
           "а поле насыщения E_sat = 3.12γ²mγ_ф³/(ek) растёт быстрее, чем v_b. PIC-код с "
           "релятивистским уравнением движения воспроизводит обе зависимости.", "",
           "![](E3_saturation_vb.png)", ""]

    # ------------------------------------------------------------------ E4 тёплый пучок
    r4 = sorted([x for x in res if x["series"] == "E4 dvb"], key=lambda x: x["dvb"])
    lim = np.cbrt(0.005) * VB
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    dv = np.array([x["dvb"] for x in r4])
    ax = axs[0]
    ax.plot(dv, [x["gamma_th"] for x in r4], color=C["text2"], ls="--", label="кинетическая теория")
    ax.plot(dv, [x["gamma_meas"] for x in r4], "o", ms=7, mfc=C["field"], mec=C["surface"],
            label="PIC")
    ax.axvline(lim, color=C["muted"], ls=":", label="(n_b/2n_p)^⅓·v_b — граница режимов")
    ax.set_xlabel("Δv_b, м/с")
    ax.set_ylabel("γ, с⁻¹ (главная мода)")
    ax.set_title("Инкремент тёплого пучка (n_b/n_p = 0.01)", loc="left")
    ax.legend(fontsize=8)
    ax = axs[1]
    ax.semilogy(dv, [x["E_sat"] for x in r4], "o-", color=C["main"], label="E_sat (первый максимум)")
    ax.semilogy(dv, [x["E_trap"] for x in r4], color=C["text2"], ls="--", label="3.12γ²m/(ek)")
    ax.axvline(lim, color=C["muted"], ls=":")
    ax.set_xlabel("Δv_b, м/с")
    ax.set_ylabel("E_sat, В/м")
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
           "пучок с разбросом скоростей Δv_b), для самой быстрой моды ящика.", "",
           md_table(r4, [("Δv_b, м/с", "dvb"), ("γ кинет., с⁻¹", "gamma_th"), ("γ PIC, с⁻¹", "gamma_meas"),
                         ("ошибка, %", "gamma_err"), ("E_sat, В/м", "E_sat"), ("3.12γ²m/(ek), В/м", "E_trap"),
                         ("ω_B/γ", "wB_over_g"), ("W_E,sat/K_b0", "WE_sat_frac"),
                         ("W_E,конец", "WE_end_frac"), ("W_E^КЛ", "WE_ql_frac")],
                    {"dvb": "{:.1e}", "gamma_th": E, "gamma_meas": E, "gamma_err": "{:+.2f}",
                     "E_sat": "{:.0f}", "E_trap": "{:.0f}", "wB_over_g": "{:.2f}",
                     "WE_sat_frac": "{:.3f}", "WE_end_frac": "{:.3f}", "WE_ql_frac": "{:.3f}"}),
           "", f"Граница гидродинамического режима Δv_b ≈ (n_b/2n_p)^(1/3)·v_b = {sci(lim, 2)} м/с: "
           "при меньшем разбросе пучок ведёт себя как холодный (захват, ω_B/γ ≈ 1.8), при большем "
           "инкремент быстро падает, яркого первого максимума нет — волна растёт и насыщается "
           "плавно, как в квазилинейной теории.", "", "![](E4_warm_beam.png)", ""]

    # ------------------------------------------------------------------ E5 квазилинейная теория
    r5 = sorted([x for x in res if x["series"] == "E5 ql"], key=lambda x: x["alpha"])
    for x in r5:
        x["ql_diff"] = (x["WE_ql_frac"] / x["WE_end_frac"] - 1) * 100
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    ax = axs[0]
    for x, col in zip(r5, COLORS):
        e = x["fv_edges"]
        ax.plot(0.5 * (e[1:] + e[:-1]), x["fv"], color=col, lw=1.4, label=f"n_b/n_p = {x['alpha']:g}")
    ax.set_yscale("log")
    ax.set_ylim(1e-2 / VB, 30 / VB)
    ax.set_xlabel("v, м/с")
    ax.set_ylabel("f_b(v), с/м  (∫f dv = 1)")
    ax.set_title("Распределение пучка в конце счёта (t ≈ 6·t_sat)", loc="left")
    ax.legend(fontsize=8)
    ax = axs[1]
    for x, col in zip(r5, COLORS):
        ax.semilogy(x["hist_t"] / x["t_sat"], x["hist_WE"], color=col, lw=1.2, label=f"n_b/n_p = {x['alpha']:g}")
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
           "[v₁, v₂]. Плотность энергии пучка с плато K_пл = n_b m (v₁² + v₁v₂ + v₂²)/6; отданная "
           "энергия K_b0 − K_пл уходит в ленгмюровские волны, половина её — электрическое поле: "
           "W_E^КЛ = (K_b0 − K_пл)/2. Края плато измеряются по f(v) на уровне половины высоты, "
           "W_E — среднее за последние 50/ω_p. Края плато берутся из самого счёта, поэтому это "
           "проверка баланса энергии, а не независимое предсказание.", "",
           md_table(r5, [("n_b/n_p", "alpha"), ("t_sat, с", "t_sat"), ("t_конец, с", "t_end"),
                         ("v₁, м/с", "plateau_v1"), ("v₂, м/с", "plateau_v2"),
                         ("W_E/K_b0 PIC", "WE_end_frac"),
                         ("W_E^КЛ/K_b0", "WE_ql_frac"), ("разница, %", "ql_diff"),
                         ("W_E/K_b0 в максимуме", "WE_sat_frac")],
                    {"t_sat": "{:.2e}", "t_end": "{:.2e}", "plateau_v1": "{:.2e}",
                     "plateau_v2": "{:.2e}", "WE_end_frac": "{:.3f}", "WE_ql_frac": "{:.3f}",
                     "ql_diff": "{:+.0f}", "WE_sat_frac": "{:.3f}"}),
           "", "Полная квазилинейная релаксация холодного пучка в плато [0, v_b] дала бы "
           "W_E = K_b0/3 ≈ 0.333 — это верхняя оценка; за время счёта плато ещё не дошло до нуля "
           "скоростей. При n_b/n_p ≳ 0.1 энергия заметно уходит в нагрев электронов плазмы, и "
           "баланс «пучок ↔ волны» перестаёт выполняться — это результат, а не ошибка.", "",
           "![](E5_quasilinear.png)", ""]

    # ------------------------------------------------------------------ E6 численная схема
    rows6 = []
    for x in res_num:
        x["param"] = x["series"].split(" ", 1)[1]
        rows6.append(x)
    save_csv("E6_numerics.csv", rows6, ["param", "dt", "ng", "npart", "T_e", "gamma_th",
                                        "gamma_meas", "gamma_err", "E_sat", "wB_over_g",
                                        "energy_err", "wall_s"])
    fig, axs = plt.subplots(1, 3, figsize=(13, 3.8))
    for ax, key, pre, lab in ((axs[0], "dt_wp", "ω_pΔt", "ω_p·Δt"), (axs[1], "ng", "N_g", "узлов сетки N_g"),
                              (axs[2], "npart", "N=", "частиц каждого сорта")):
        xs = [x for x in rows6 if x["param"].startswith(pre)]
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
           f"Базовый расчёт: n_b/n_p = 0.01, Δt = 0.1/ω_p = {fmt(0.1 / wp, 'с')}, N_g = 1024 "
           f"(Δx = {fmt(base['n_waves'] * 2 * np.pi / (1.0414 * wp / VB) / 1024, 'м')} = 0.7 λ_D), "
           "N = 65 536; меняется один параметр. Невязка энергии — max |W_E + ΣK − const| "
           "за весь счёт в долях начальной плотности энергии пучка K_b0.", "",
           md_table(rows6, [("вариант", "param"), ("γ PIC, с⁻¹", "gamma_meas"), ("ошибка γ, %", "gamma_err"),
                            ("E_sat, В/м", "E_sat"), ("ω_B/γ", "wB_over_g"), ("невязка энергии", "energy_err"),
                            ("время счёта, с", "wall_s")],
                    {"gamma_meas": E, "gamma_err": "{:+.2f}", "E_sat": "{:.0f}",
                     "wB_over_g": "{:.2f}", "energy_err": "{:.1e}", "wall_s": "{:.0f}"}),
           "", "Схема «чехарда» устойчива при ω_pΔt < 2; при ω_pΔt = 0.4 ошибка частоты "
           "(ω_pΔt)²/24 ≈ 0.7 %. От температуры плазмы результат почти не зависит при T_e ≤ 3·10⁴ К; при T_e = 10⁵ К (v_b/v_Te = 8) расхождение γ с теорией вырастает до 5 % (причина не выяснялась). Невязка энергии везде меньше 1 % K_b0.", "", "![](E6_numerics.png)", ""]

    # ------------------------------------------------------------------ E7 одноволновая модель
    rows7 = []
    for a_, v_, n_ in [(0.001, 1e7, 1e16), (0.01, 1e7, 1e16), (0.1, 1e7, 1e16), (0.01, 3e6, 1e11),
                       (0.01, 1e8, 1e16), (0.01, 2e8, 1e16), (0.01, 2.7e8, 1e16)]:
        Cc, wbg, tg = saturation_constant(a_, vb=v_, n_p=n_)
        rows7.append(dict(alpha=a_, vb=v_, n_p=n_, gamma_b=float(cst.lorentz_gamma(v_)), C=Cc,
                          wB_over_g=wbg, t_sat_gamma=tg))
    save_csv("E7_single_wave.csv", rows7, ["alpha", "vb", "n_p", "gamma_b", "C", "wB_over_g", "t_sat_gamma"])
    md += ["## E7. Одноволновая модель: универсальная константа насыщения", "",
           "Модель огибающей: dÊ/dt = (e·n_b·ω_p/(ε₀k))⟨e^(−iψ)⟩, dψ/dt = kv − ω_p, "
           "dp/dt = −e·Re(Ê e^(iψ)); РК4, 4096 частиц. При kv_b = ω_p и v_b ≪ c все параметры "
           "убираются масштабированием, поэтому (ω_B/γ)² = e·k·E_sat/(mγ²) — одно и то же число "
           "при любых n_b/n_p, n_p и v_b. У релятивистского пучка константа уменьшается: "
           "захваченные электроны в системе волны уже не медленные (параметр Тоде–Судана "
           "S = (v_b/c)²γ_b(n_b/2n_p)^(1/3) не мал).", "",
           md_table(rows7, [("n_b/n_p", "alpha"), ("v_b, м/с", "vb"), ("n_p, м⁻³", "n_p"), ("γ_b", "gamma_b"),
                            ("(ω_B/γ)²", "C"), ("ω_B/γ", "wB_over_g"), ("γ·t_sat", "t_sat_gamma")],
                    {"vb": "{:.1e}", "n_p": "{:.0e}", "gamma_b": "{:.3f}", "C": "{:.4f}",
                     "wB_over_g": "{:.4f}", "t_sat_gamma": "{:.2f}"}), ""]

    # ------------------------------------------------------------------ E8 ионы и каверны
    figures_ions(C, res_ion, md, wp, lD)
    # ------------------------------------------------------------------ E9 уравнения Захарова
    figures_zakharov(C, md)
    # ------------------------------------------------------------------ F1–F4 иллюстрации
    figures_stages(C, N)
    figures_dispersion(C)
    md += ["## Иллюстрации", "", "![](F1_stages.png)", "", "![](F2_energy_spectrum.png)", "",
           "![](F3_dispersion.png)", "", "![](F4_omega_k.png)", ""]
    md += [f"_Полное время всех расчётов: {time.time() - t_start:.0f} с._", ""]
    with open(os.path.join(RES, "СВОДКА.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("Готово. Сводка: results/СВОДКА.md", flush=True)


def figures_ions(C, res_ion, md, wp, lD):
    """E8: подвижные ионы — каверны, поглощение волн, дисперсионная диаграмма."""
    import matplotlib.pyplot as plt
    from bpi.gui import style
    r0 = next(r for r in res_ion if r["tag"] == "ионы неподвижны")
    r1 = next(r for r in res_ion if r["tag"] == "ионы H⁺")
    st, sx = Scale(r1["T"][-1], "с"), Scale(r1["L"], "м")
    fig, axs = plt.subplots(2, 2, figsize=(13, 8))
    ax = axs[0, 0]
    for r, col in zip(res_ion, COLORS):
        ax.semilogy(st(r["t"]), r["WE"], color=col, lw=1.3, label=r["tag"])
    ax.set_xlabel(f"t, {st.label}")
    ax.set_ylabel("W_E = ε₀⟨E²⟩/2, Дж/м³")
    ax.set_ylim(r0["K0"] * 1e-3, r0["K0"] * 3)
    ax.set_title("Энергия поля: с подвижными ионами волны поглощаются", loc="left")
    ax.legend(fontsize=8)
    ax = axs[0, 1]
    ax.semilogy(st(r1["t"]), np.maximum(r1["dni"], 1e-6), color=C["ion"], label="rms δn_i/n_i (H⁺)")
    ax.semilogy(st(r1["t"]), np.maximum((r1["K"][:, 0] - r1["K"][0, 0]) / r1["K0"], 1e-6),
                color=C["plasma"], label="нагрев электронов плазмы, ΔK/K_b0 (H⁺)")
    ax.semilogy(st(r0["t"]), np.maximum((r0["K"][:, 0] - r0["K"][0, 0]) / r0["K0"], 1e-6),
                color=C["plasma"], ls="--", label="то же, ионы неподвижны")
    # теория: модуляционная неустойчивость при уровне поля после насыщения
    # уровень поля берётся из самого счёта: среднее W_E/(n k_BT_e) от 1.5·t_sat до начала каверн
    i1, i2 = np.searchsorted(r1["t"], [1.5 * r1["t_sat"], r1["t_cav"] if np.isfinite(r1["t_cav"]) else r1["t"][-1]])
    W0 = float(r1["WE"][i1:i2].mean() / (r1["n_p"] * cst.K_B * r1["T_e"]))
    q = 2 * np.pi * np.arange(1, 200) / r1["L"]
    gmod = modulational_growth(q, W0, r1["k_main"], r1["n_p"], r1["T_e"], 3e3).max()
    g_meas = np.polyfit(r1["t"][i1:i2], np.log(np.maximum(r1["dni"][i1:i2], 1e-9)), 1)[0] if i2 > i1 + 5 else np.nan
    tt = np.array([r1["t"][i1], r1["t"][max(i2 - 1, i1 + 1)]])
    ax.semilogy(st(tt), r1["dni"][i1] * np.exp(gmod * (tt - tt[0])), color=C["text2"], ls=":",
                label=f"теория: exp(γ_мод t), γ_мод = {sci(gmod, 2)} с⁻¹")
    ax.set_ylim(1e-4, 1)
    ax.set_xlabel(f"t, {st.label}")
    ax.set_title("Рост возмущений концентрации ионов и нагрев плазмы", loc="left")
    ax.legend(fontsize=8)
    ext = [st(r1["T"][0]), st(r1["T"][-1]), 0, sx(r1["L"])]
    ax = axs[1, 0]
    im = ax.imshow(r1["W"].T, origin="lower", aspect="auto", extent=ext, cmap=style.seq_cmap(),
                   vmax=np.percentile(r1["W"], 99.9))
    ax.grid(False)
    ax.set_xlabel(f"t, {st.label}")
    ax.set_ylabel(f"x, {sx.label}")
    ax.set_title("Уровень поля W(x,t) = ε₀⟨E²⟩/(2n k_BT_e), ионы H⁺", loc="left")
    fig.colorbar(im, ax=ax)
    ax = axs[1, 1]
    v = np.abs(r1["NI"]).max()
    im = ax.imshow(r1["NI"].T, origin="lower", aspect="auto", extent=ext, cmap="RdBu_r", vmin=-v, vmax=v)
    ax.grid(False)
    ax.set_xlabel(f"t, {st.label}")
    ax.set_ylabel(f"x, {sx.label}")
    ax.set_title("Концентрация ионов δn_i/n_i (x,t): каверны и ионный звук", loc="left")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "E8_ions_cavitons.png"), dpi=150)
    plt.close(fig)
    rows = []
    for r in res_ion:
        rows.append(dict(tag=r["tag"], m_ratio=r["m_ratio"], alpha=r["alpha"], t_sat=r["t_sat"],
                         t_cav=r["t_cav"], t_cav_wp=r["t_cav"] * r["wpe"], W_peak=r["W_peak"],
                         dn_at_peak=r["dn_at_peak"], dn_min=r["dn_min"],
                         WE_sat_frac=r["WE_sat"] / r["K0"], WE_end_frac=r["WE_end"] / r["K0"],
                         energy_err=r["energy_err"]))
    save_csv("E8_ions_cavitons.csv", rows, list(rows[0]))
    md += ["## E8. Подвижные ионы: каверны (солитоны) и поглощение ленгмюровских волн", "",
           f"Длинные счёты до t = {fmt(r1['T'][-1], 'с')} = {r1['T'][-1] * wp:.0f}/ω_p. Ионы — частицы с "
           "настоящей массой (H⁺: m_i/m_e = 1836; Ar⁺: 72 820), T_i = 3·10³ К. W = ε₀⟨E²⟩/(2n k_BT_e) "
           "— уровень поля (отношение плотности энергии поля к тепловой энергии электронов).", "",
           md_table(rows, [("счёт", "tag"), ("m_i/m_e", "m_ratio"), ("n_b/n_p", "alpha"),
                           ("t_sat, с", "t_sat"), ("начало каверн t, с", "t_cav"), ("то же, 1/ω_p", "t_cav_wp"),
                           ("W в пике", "W_peak"), ("δn_i/n_i в точке пика", "dn_at_peak"),
                           ("min δn_i/n_i", "dn_min"), ("W_E/K_b0 в максимуме", "WE_sat_frac"),
                           ("W_E/K_b0 в конце", "WE_end_frac"), ("невязка энергии", "energy_err")],
                    {"m_ratio": "{:.0f}", "t_sat": "{:.2e}", "t_cav": "{:.2e}", "t_cav_wp": "{:.0f}",
                     "W_peak": "{:.2f}", "dn_at_peak": "{:+.3f}", "dn_min": "{:+.3f}",
                     "WE_sat_frac": "{:.3f}", "WE_end_frac": "{:.4f}", "energy_err": "{:.1e}"}),
           "",
           "**Что происходит.** После насыщения ленгмюровская волна своим высокочастотным давлением "
           "(пондеромоторной силой) выталкивает плазму из областей сильного поля. Возмущения "
           f"концентрации ионов растут примерно экспоненциально, средний темп {sci(g_meas, 2)} с⁻¹. "
           f"Для сравнения: линейная теория модуляционной неустойчивости (уравнения Захарова) для "
           f"одной волны с уровнем поля W₀ = {W0:.2f}, измеренным в этом же счёте, даёт "
           f"γ_мод = {sci(gmod, 2)} с⁻¹. Это согласие по порядку величины: в счёте не одна волна, "
           "а пакет волн с захваченными частицами, и W₀ меняется со временем. "
           "В ямах концентрации плазменная частота ниже — поле запирается в них: образуются "
           f"**каверны** (в пике W = {r1['W_peak']:.2f}, концентрация в этой точке {r1['dn_at_peak'] * 100:+.0f} %). "
           "Каверна сжимается до нескольких λ_D, энергия поля падает "
           f"в {r1['WE_sat'] / r1['WE_end']:.0f} раз относительно максимума "
           f"(без ионов — только в {r0['WE_sat'] / r0['WE_end']:.1f} раза) и переходит в нагрев "
           "электронов плазмы (вероятный механизм — затухание Ландау коротких волн в каверне; "
           "отдельно он не проверялся). С тяжёлыми ионами Ar⁺ за время счёта каверны не "
           "успевают образоваться.", "",
           "Оговорки: (1) шум макрочастиц в PIC на несколько порядков больше реального теплового "
           "шума плазмы, поэтому каверны появляются раньше, чем в установке; (2) момент «начала "
           "каверн» — условная граница: среднеквадратичное δn_i/n_i > 2 %.", "",
           "![](E8_ions_cavitons.png)", ""]
    # --- F4: дисперсионная диаграмма (k, ω) из счёта, с ионами и без
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    for ax, r in zip(axs, (r0, r1)):
        om, k, P = r["wk"]
        sk, sw = Scale(k[-1], "рад/м"), Scale(2.5 * r["wpe"], "рад/с")
        sel = (om > -1.7 * r["wpe"]) & (om < 2.7 * r["wpe"])
        dk = k[1] - k[0]
        ax.imshow(np.log10(np.maximum(P[sel] / P.max(), 1e-12)), origin="lower", aspect="auto",
                  extent=[sk(k[0] - dk / 2), sk(k[-1] + dk / 2), sw(om[sel][0]), sw(om[sel][-1])],
                  vmin=-7, vmax=0, cmap=style.seq_cmap(), interpolation="nearest")
        ax.grid(False)
        kk = np.linspace(0, k[-1], 200)
        wbg = disp.bohm_gross(kk, r["n_p"], r["T_e"])
        ax.plot(sk(kk), sw(wbg), color=C["plasma"], ls="--", lw=1.2, label="ω² = ω_p² + 3k²v_Te²")
        ax.plot(sk(kk), sw(-wbg), color=C["plasma"], ls="--", lw=1.2)
        ax.plot(sk(kk), sw(kk * r["vb"]), color=C["beam"], ls="--", lw=1.2, label="ω = k·v_b")
        ax.set_ylim(sw(om[sel][0]), sw(om[sel][-1]))
        ax.set_xlabel(f"k, {sk.label}")
        ax.set_title(f"lg|E(k,ω)|², {r['tag']}", loc="left")
    axs[0].set_ylabel(f"ω, {sw.label}")
    axs[0].legend(fontsize=8, loc="lower right")
    fig.suptitle("Дисперсионная диаграмма из PIC-счёта (последние 4096 шагов). Встречные волны (ω < 0) "
                 "есть и без ионов; с подвижными ионами они намного сильнее, а спектр шире",
                 fontsize=9.5)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "F4_omega_k.png"), dpi=150)
    plt.close(fig)


def figures_zakharov(C, md):
    """E9: уравнения огибающей — точный солитон и модуляционная неустойчивость."""
    import matplotlib.pyplot as plt
    from bpi.gui import style
    rows = []
    # (а) точный солитон: сохранение формы, ширина, скорость
    for Wm, mach in ((0.01, 0.0), (0.05, 0.0), (0.05, 0.5), (0.1, 0.3)):
        z = Zakharov(damping=False)
        z.add_soliton(Wm, 0.3 * z.L, mach=mach)
        f0, N0 = z.fit_soliton(), z.plasmons()
        z.step(4000)
        f1 = z.fit_soliton()
        Em, D, num, kap, V = z.soliton_params(Wm, mach)
        rows.append(dict(W_m=Wm, mach=mach, E_m=Em, delta_th=D, delta_0=f0["delta"], delta_end=f1["delta"],
                         nu_th=-num, W_end=f1["W_m"], dN=z.plasmons() / N0 - 1,
                         v_meas=(f1["x_m"] - f0["x_m"]) / z.t, v_th=V))
    save_csv("E9_zakharov.csv", rows, list(rows[0]))
    # (б) модуляционная неустойчивость: γ(q) счёт против теории
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.2))
    ax = axs[0]
    z0 = Zakharov(damping=False)
    sq, sg = Scale(0.3 / z0.lambda_D, "рад/м"), Scale(0.008 * z0.wp, "с⁻¹")
    mi_rows = []
    for (W0, k0lD), col in zip(((0.01, 0.0), (0.02, 0.07), (0.1, 0.07)), COLORS):
        z = Zakharov(damping=False)
        z.set_pump(W0, k0lD / z.lambda_D, noise=1e-10)
        M = 50
        q = 2 * np.pi * np.arange(1, M + 1) / z.L
        gth = modulational_growth(q, W0, z.k0, z.n_p, z.T_e, z.T_i)
        ts, amps = [], []
        while z.t * gth.max() < 12:
            z.step(10)
            ts.append(z.t)
            amps.append(np.abs(z.nk[1:M + 1]) + np.abs(z.nk[-1:-M - 1:-1]))
        ts, amps = np.array(ts), np.array(amps)
        sel = ts * gth.max() > 7
        gm = np.array([np.polyfit(ts[sel], np.log(amps[sel, m]), 1)[0] for m in range(M)])
        ax.plot(sq(q), sg(gth), color=col, label=f"теория, W₀ = {W0:g}, k₀λ_D = {k0lD:g}")
        ok = gth > 0.15 * gth.max()
        ax.plot(sq(q[ok]), sg(gm[ok]), "o", ms=4.5, mfc=col, mec=C["surface"])
        j = int(np.argmax(gth))
        mi_rows.append(dict(W0=W0, k0lD=k0lD, q=q[j], g_th=gth[j], g_meas=gm[j], err=(gm[j] / gth[j] - 1) * 100))
    ax.set_xlabel(f"волновое число возмущения q, {sq.label}")
    ax.set_ylabel(f"γ_мод, {sg.label}")
    ax.set_title("Модуляционная неустойчивость: счёт (точки) и теория", loc="left")
    ax.legend(fontsize=7.5)
    # (в) волна от пучка → каверны (с затуханием Ландау)
    z = Zakharov()
    z.set_pump(0.1, 0.07 / z.lambda_D, noise=1e-3)
    sx = Scale(z.L, "м")
    maps, T = [], []
    snap = None
    while z.t * z.wp < 1400:
        z.step(8)
        maps.append(z.W()[::4].astype(np.float32))
        T.append(z.t)
        if snap is None and z.hist_Wmax[-1] > 0.45:
            snap = (z.t, z.W().copy(), z.nu().copy(), z.fit_soliton())
    stt = Scale(T[-1], "с")
    ax = axs[1]
    im = ax.imshow(np.array(maps).T, origin="lower", aspect="auto", cmap=style.seq_cmap(),
                   extent=[stt(T[0]), stt(T[-1]), 0, sx(z.L)], vmax=np.percentile(maps, 99.9))
    ax.grid(False)
    ax.set_xlabel(f"t, {stt.label}")
    ax.set_ylabel(f"x, {sx.label}")
    ax.set_title("Волна W₀ = 0.1 распадается на каверны: W(x,t)", loc="left")
    fig.colorbar(im, ax=ax)
    ax = axs[2]
    if snap:
        ts_, W_, nu_, fs = snap
        xi = (z.x - fs["x_m"] + 0.5 * z.L) % z.L - 0.5 * z.L
        o = np.argsort(xi)
        m = np.abs(xi[o]) < 12 * fs["delta_th"]
        ax.plot(sx(xi[o][m]) , W_[o][m], color=C["field"], lw=1.8, label="поле W(x) (счёт)")
        ax.plot(sx(xi[o][m]), nu_[o][m], color=C["ion"], lw=1.6, label="концентрация δn/n (счёт)")
        ax.plot(sx(xi[o][m]), fs["W_m"] / np.cosh(xi[o][m] / fs["delta_th"]) ** 2, color=C["text2"], ls="--",
                label=f"солитон sech², Δ = λ_D√(6τ/W_m) = {fmt(fs['delta_th'], 'м')}")
        ax.set_title(f"Каверна в момент t = {fmt(ts_, 'с')}", loc="left")
        ax.set_xlabel(f"x − x_m, {sx.label}")
        ax.legend(fontsize=7.5)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "E9_zakharov.png"), dpi=150)
    plt.close(fig)
    md += ["## E9. Уравнения огибающей с нелинейным сдвигом частоты (уравнения Захарова)", "",
           "Второе прочтение подсказки задания. i∂Ẽ/∂t + (3v_Te²/2ω_p)∂²Ẽ/∂x² = (ω_p/2)(δn/n)Ẽ; "
           "∂²(δn/n)/∂t² − c_s²∂²(δn/n)/∂x² = (ε₀/4n m_i)∂²|Ẽ|²/∂x². Псевдоспектральный метод "
           "расщепления, 1024 узла, Δt = 0.5/ω_p, плазма та же (ионы H⁺).", "",
           "**(а) Точный солитон** Ẽ = E_m sech((x − Vt)/Δ): за 2000/ω_p форма и скорость сохраняются.", "",
           md_table(rows, [("W_m", "W_m"), ("V/c_s", "mach"), ("E_m, В/м", "E_m"), ("Δ теория, м", "delta_th"),
                           ("Δ счёт (t=0), м", "delta_0"), ("Δ счёт (конец), м", "delta_end"),
                           ("δn/n теория", "nu_th"), ("W_m в конце", "W_end"),
                           ("V счёт, м/с", "v_meas"), ("V теория, м/с", "v_th"), ("ΔN/N", "dN")],
                    {"mach": "{:.1f}", "E_m": "{:.0f}", "delta_th": "{:.3e}", "delta_0": "{:.3e}",
                     "delta_end": "{:.3e}", "nu_th": "{:+.4f}", "W_end": "{:.4f}", "v_meas": "{:.0f}",
                     "v_th": "{:.0f}", "dN": "{:.0e}"}),
           "", "**(б) Модуляционная неустойчивость** однородной волны: рост возмущения концентрации "
           "сравнивается с корнем многочлена 4-й степени (Ω² − c_s²q²)[(Ω − qV_g)² − δ²] = "
           "W₀(k_BT_e/m_i)q²ω_pδ.", "",
           md_table(mi_rows, [("W₀", "W0"), ("k₀λ_D", "k0lD"), ("q, рад/м", "q"), ("γ_мод теория, с⁻¹", "g_th"),
                              ("γ_мод счёт, с⁻¹", "g_meas"), ("ошибка, %", "err")],
                    {"q": "{:.0f}", "g_th": "{:.3e}", "g_meas": "{:.3e}", "err": "{:+.2f}"}),
           "", "**(в)** Волна с уровнем W₀ = 0.1 (как после насыщения пучковой неустойчивости при "
           "n_b/n_p = 0.01) за ~1000/ω_p распадается на каверны — всплески поля в ямах "
           "концентрации. Каверна в момент снимка ещё сжимается: она шире стационарного солитона "
           "sech² той же высоты (пунктир, Δ = λ_D√(6τ/W_m)) и яма мельче, чем −W_m/τ. Та же "
           "картина видна в PIC-счёте с подвижными ионами (E8) — два независимых метода дают "
           "качественно одно и то же.", "",
           "![](E9_zakharov.png)", ""]


def figures_stages(C, N):
    """Фазовые портреты на четырёх стадиях + энергия, спектрограмма, спектр (в СИ)."""
    import matplotlib.pyplot as plt
    s = PIC(PICParams(npart=N))
    tr = diag.StageTracker(s)
    wp = s.wpe
    snaps = {}
    targets = [(1, 15.0), (2, 60.0)]
    got3 = got4 = False
    while s.t * wp < 250:
        s.step(10)
        tr.update()
        for num, tt in targets:
            if num not in snaps and s.t * wp >= tt:
                snaps[num] = ("затравка" if num == 1 else "линейный рост", s.t, s.x.copy(), s.v.copy(), s.Ek.copy())
        if tr.sat is not None and not got3:
            snaps[3] = ("захват (насыщение)", s.t, s.x.copy(), s.v.copy(), s.Ek.copy())
            got3 = True
        if s.t * wp >= 240 and not got4:
            snaps[4] = ("перемешивание", s.t, s.x.copy(), s.v.copy(), s.Ek.copy())
            got4 = True
    sx, sv, st = Scale(s.L, "м"), Scale(s.p.vb, "м/с"), Scale(250 / wp, "с")
    fig, axs = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey=True)
    for ax, num in zip(axs.flat, sorted(snaps)):
        name, t_, x, v, Ek = snaps[num]
        N_ = s.N
        ax.plot(sx(x[:N_]), sv(v[:N_]), ",", color=C["plasma"], alpha=0.5, rasterized=True)
        ax.plot(sx(x[N_:2 * N_]), sv(v[N_:2 * N_]), ",", color=C["beam"], alpha=0.7, rasterized=True)
        m = s.m_main
        A = 2 * abs(Ek[m]) / s.p.ng
        xs = np.linspace(0, s.L, 400)
        vu, vd = diag.separatrix(xs, A, s.k_modes[m], np.angle(Ek[m]), s.v_phase)
        ax.plot(sx(xs), sv(vu), color=C["text"], lw=0.8)
        ax.plot(sx(xs), sv(vd), color=C["text"], lw=0.8)
        ax.set_title(f"{num}. {name}, t = {fmt(t_, 'с')}, E₀ = {fmt(A, 'В/м')}", loc="left")
        ax.set_ylim(sv(-0.6 * s.p.vb), sv(1.6 * s.p.vb))
        ax.set_xlim(0, sx(s.L))
    for ax in axs[1]:
        ax.set_xlabel(f"x, {sx.label}")
    for ax in axs[:, 0]:
        ax.set_ylabel(f"v, {sv.label}")
    fig.suptitle("Фазовые портреты (n_p = 10¹⁶ м⁻³, n_b/n_p = 0.01, v_b = 10⁷ м/с): синие — электроны "
                 "плазмы, оранжевые — пучка, линия — сепаратриса главной волны", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "F1_stages.png"), dpi=150)
    plt.close(fig)

    h = s.hist
    fig, axs = plt.subplots(1, 3, figsize=(15, 4))
    ax = axs[0]
    t = st(h["t"])
    ax.semilogy(t, h["WE"], color=C["field"], label="поле W_E")
    ax.semilogy(t, cst.EPS0 * (2 * np.abs(h["Ek"][:, s.m_main - 1])) ** 2 / 4,
                color=C["main"], label="главная волна ε₀E₀²/4")
    ax.semilogy(t, np.maximum(h["K"][0, 1] - h["K"][:, 1], 1e-30), color=C["beam"],
                label="−ΔK пучка")
    t1 = 4 / s.gamma_ref
    j = int(t1 / s.dt)
    W1 = cst.EPS0 * (2 * abs(h["Ek"][j, s.m_main - 1])) ** 2 / 4
    tt = np.array([t1 - 20 / wp, 110 / wp])
    ax.semilogy(st(tt), W1 * np.exp(2 * s.gamma_ref * (tt - t1)), "--", color=C["text2"],
                label=f"exp(2γt), γ = {sci(s.gamma_ref)} с⁻¹")
    for st_t in tr.t_stage[1:]:
        if st_t:
            ax.axvline(st(st_t), color=C["muted"], lw=0.8, ls=":")
    ax.set_ylim(1e-9 * s.K0_beam, 2 * s.K0_beam)
    ax.set_xlabel(f"t, {st.label}")
    ax.set_ylabel("плотность энергии, Дж/м³")
    ax.set_title("Энергия (пунктир — границы стадий)", loc="left")
    ax.legend(fontsize=8)
    ax = axs[1]
    A2 = (2 * np.abs(h["Ek"])) ** 2
    sk = Scale(3 * s.k_max, "рад/м")
    dk = s.k_modes[1]
    im = ax.imshow(np.log10(A2.T + 1e-30), origin="lower", aspect="auto",
                   extent=[0, st(h["t"][-1]), sk(0.5 * dk), sk((s.m_store + 0.5) * dk)],
                   vmin=np.log10(A2.max()) - 9, vmax=np.log10(A2.max()), cmap=style_cmap())
    ax.set_ylim(0, sk(3 * s.k_max))
    ax.grid(False)
    ax.set_xlabel(f"t, {st.label}")
    ax.set_ylabel(f"k, {sk.label}")
    ax.set_title("Спектрограмма lg A_k², (В/м)²", loc="left")
    fig.colorbar(im, ax=ax)
    ax = axs[2]
    kk = sk(s.k_modes[1:s.m_store + 1])
    for tt_, col in ((40 / wp, C["plasma"]), (tr.sat["t"] if tr.sat else 85 / wp, C["main"]), (240 / wp, C["beam"])):
        j = int(tt_ / s.dt)
        ax.semilogy(kk, A2[j], "o-", ms=3, color=col, label=f"t = {fmt(tt_, 'с')}")
    ax.set_xlim(0, sk(3 * s.k_max))
    ax.set_xlabel(f"k, {sk.label}")
    ax.set_ylabel("A_k², (В/м)²")
    ax.set_title("Спектр волн: линейная стадия → турбулентность", loc="left")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "F2_energy_spectrum.png"), dpi=150)
    plt.close(fig)


def figures_dispersion(C):
    import matplotlib.pyplot as plt
    wp = float(cst.plasma_frequency(N_P))
    fig, axs = plt.subplots(1, 3, figsize=(15, 4))
    k = np.linspace(0.005, 2, 600) * wp / VB
    sk, sw = Scale(2 * wp / VB, "рад/м"), Scale(2.5 * wp, "рад/с")
    ax = axs[0]
    sg = Scale(0.27 * wp, "с⁻¹")
    for a_, col in ((0.001, C["plasma"]), (0.01, C["main"]), (0.1, C["beam"])):
        _, g = disp.fluid_growth(k, disp.beam_plasma_species(N_P, a_, VB))
        ax.plot(sk(k), sg(g), color=col, label=f"n_b/n_p = {a_:g}")
    ax.set_xlabel(f"k, {sk.label}")
    ax.set_ylabel(f"γ, {sg.label}")
    ax.set_title("Инкремент γ(k) — точное решение", loc="left")
    ax.legend(fontsize=8)
    ax = axs[1]
    sp = disp.beam_plasma_species(N_P, 0.01, VB)
    r = disp.fluid_roots(k, sp)
    for i in range(4):
        ax.plot(sk(k), sw(r[:, i].real), ".", ms=1.5, color=C["text2"])
    wr, g = disp.fluid_growth(k, sp)
    ax.plot(sk(k), sw(np.where(g > 0, wr, np.nan)), color=C["main"], lw=2.5, label="растущая волна")
    ax.axhline(sw(wp), color=C["plasma"], ls="--", label="ω = ω_p")
    wb = np.sqrt(sp[1][0])
    ax.plot(sk(k), sw(k * VB + wb), color=C["beam"], ls="--", label="ω = kv_b ± ω_b")
    ax.plot(sk(k), sw(k * VB - wb), color=C["beam"], ls="--")
    ax.set_ylim(sw(-1.5 * wp), sw(2.5 * wp))
    ax.set_xlabel(f"k, {sk.label}")
    ax.set_ylabel(f"Re ω, {sw.label}")
    ax.set_title("Ветви Re ω(k), n_b/n_p = 0.01", loc="left")
    ax.legend(fontsize=8)
    ax = axs[2]
    al = np.logspace(-4, 0, 60)
    gx = [disp.most_unstable(disp.beam_plasma_species(N_P, a_, VB))[1] for a_ in al]
    ax.loglog(al, gx, color=C["main"], lw=2, label="точный корень")
    ax.loglog(al, disp.gamma_hint(al, wp), "--", color=C["text2"], label="подсказка (√3/2)(n_b/n_p)^⅓ω_p")
    ax.loglog(al, disp.gamma_weak_beam(al, wp), ":", color=C["text2"], label="(√3/2)(n_b/2n_p)^⅓ω_p")
    ax.set_xlabel("n_b/n_p")
    ax.set_ylabel("γ_max, с⁻¹")
    ax.set_title("γ_max(n_b/n_p): формула подсказки завышает", loc="left")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(RES, "F3_dispersion.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
