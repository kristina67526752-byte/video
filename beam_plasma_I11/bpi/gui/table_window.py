"""Окно «Таблица насыщения»: серия PIC-счётов по параметру пучка.

Вычислительный эксперимент из задания: «найти зависимость насыщенной
амплитуды волн от параметров пучка, сравнить с теорией». Счёты идут
по очереди небольшими порциями (интерфейс не замирает), строки таблицы
появляются по мере готовности и записываются в журнал results/journal.csv.
"""
from __future__ import annotations

import csv
import os
import time

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Button, RadioButtons

from .. import dispersion as disp
from .. import diagnostics as diag
from ..runs import SatRun
from .. import journal
from . import style
from .style import C, MONO
from .blit import Blitter, Region, keep_drawn
from .fastdraw import MonoText, paste

SERIES = {
    "по плотности n_b/n_p": ("alpha", [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1]),
    "по скорости v_b": ("vb", [0.5, 0.75, 1.0, 1.5, 2.0]),
    "по разбросу Δv/v_b": ("dvb", [0.0, 0.05, 0.1, 0.15, 0.2]),
}


class TableWindow:
    def __init__(self, base=None, npart=32768):
        from ..pic import PICParams
        style.use(style.current_theme())
        self.base = (base or PICParams()).copy(scenario="beam", npart=npart, alpha=0.01,
                                               vb=1.0, dvb=0.0)
        self.series = list(SERIES)[0]
        self.rows = []
        self.queue = []
        self.cur = None
        self.running = False
        f = self.fig = plt.figure(figsize=(15, 8.6))
        try:
            f.canvas.manager.set_window_title("И11 · Таблица амплитуд насыщения")
        except Exception:
            pass
        f.text(0.04, 0.965, "Вычислительный эксперимент: амплитуда насыщения в зависимости "
               "от параметров пучка", fontsize=13, fontweight="bold", color=C["text"])
        self.ax_t = f.add_axes([0.04, 0.2, 0.52, 0.72])
        self.ax_t.set_xticks([]); self.ax_t.set_yticks([]); self.ax_t.grid(False)
        self.ax_t.set_facecolor(C["panel"])
        self.ax_p = f.add_axes([0.63, 0.2, 0.34, 0.72])
        A = []
        self.pt = self.ax_p.plot([], [], "o", ms=9, mfc=C["field"], mec=C["surface"], mew=2,
                                 label="PIC: первый максимум E₀")[0]
        A.append(self.pt)
        self.ln_th, = self.ax_p.plot([], [], color=C["text2"], ls="--", lw=1.4,
                                     label="теория захвата 3.12·γ²/k")
        self.ln_fit = self.ax_p.plot([], [], color=C["main"], lw=1.4, label="степенная подгонка")[0]
        A.append(self.ln_fit)

        axr = f.add_axes([0.04, 0.04, 0.17, 0.12])
        style.style_widget_axes(axr)
        self.r = RadioButtons(axr, list(SERIES), active=0, activecolor=C["main"])
        for t in self.r.labels:
            t.set_color(C["text"])
        self.r.on_clicked(self._on_series)

        def bt(rect, label, cb, hl=False):
            ax = f.add_axes(rect)
            b = Button(ax, label, color=C["main"] if hl else C["panel"], hovercolor=C["grid"])
            b.label.set_color(C["surface"] if hl else C["text"])
            b.on_clicked(cb)
            return b
        self.b_go = bt([0.23, 0.10, 0.12, 0.05], "▶ Посчитать серию", self._start, hl=True)
        self.b_stop = bt([0.36, 0.10, 0.09, 0.05], "Стоп", self._stop)
        self.b_csv = bt([0.46, 0.10, 0.10, 0.05], "Сохранить CSV", self._save)

        self.rt = MonoText(MONO, 8.2, C["text"], C["main"], C["panel"], f.dpi)
        self.rt_st = MonoText(MONO, 8.5, C["text2"], C["main"], C["surface"], f.dpi)
        self.s_tab = ""
        self.s_status = "Выберите серию и нажмите «Посчитать серию» (≈10–40 с на серию)."
        self.blit = Blitter(f, regions=[Region(
            lambda: (0, 0.165 * f.bbox.height, f.bbox.width, f.bbox.height), A, self._raw)])
        self._setup_plot()
        self._render_table()
        self.timer = f.canvas.new_timer(interval=20)
        self.timer.add_callback(self._tick)
        self.timer.start()
        f.canvas.mpl_connect("close_event", lambda e: self.timer.stop())
        f.show()

    # ------------------------------------------------------------------
    def _setup_plot(self):
        ax = self.ax_p
        key, vals = SERIES[self.series]
        ax.set_xscale("log" if key in ("alpha", "vb") else "linear")
        ax.set_yscale("log")
        if key == "alpha":
            ax.set_xlabel("α = n_b/n_p")
            ax.set_title("E_sat(α): ∝ α^(2/3) при α → 0", loc="left")
            al = np.logspace(-3.1, -0.9, 60)
            th = []
            for a in al:
                k, g, _ = disp.most_unstable(disp.beam_plasma_species(a))
                th.append(diag.trapping_amplitude(g, k))
            self.ln_th.set_data(al, th)
            ax.set_xlim(7e-4, 0.14)
            ax.set_ylim(5e-3, 0.5)
        elif key == "vb":
            ax.set_xlabel("v_b / v₀")
            ax.set_title("E_sat(v_b): ∝ v_b (γ от v_b не зависит)", loc="left")
            vb = np.linspace(0.45, 2.2, 30)
            k, g, _ = disp.most_unstable(disp.beam_plasma_species(0.01))
            self.ln_th.set_data(vb, diag.trapping_amplitude(g, k / vb))
            ax.set_xlim(0.42, 2.4)
            ax.set_ylim(0.02, 0.3)
        else:
            ax.set_xlabel("Δv / v_b")
            ax.set_title("E_sat(Δv): тёплый пучок насыщается слабее", loc="left")
            dv = np.linspace(0, 0.22, 23)
            th = []
            for d in dv:
                sp = disp.beam_plasma_species(0.01, 1.0, 0.0, d)
                km = np.linspace(0.6, 1.6, 60)
                if d > 0:
                    _, gk = disp.kinetic_growth_curve(km, sp)
                else:
                    _, gk = disp.fluid_growth(km, sp)
                i = int(np.argmax(gk))
                th.append(diag.trapping_amplitude(gk[i], km[i]))
            self.ln_th.set_data(dv, th)
            ax.axvline(np.cbrt(0.01 / 2), color=C["muted"], ls=":", lw=1)
            ax.text(np.cbrt(0.005) + 0.004, 0.012, "(α/2)^⅓ — граница\nгидродин. режима",
                    fontsize=7.5, color=C["text2"])
            ax.set_xlim(-0.01, 0.23)
            ax.set_ylim(1e-3, 0.2)
        ax.set_ylabel("амплитуда насыщения E_sat (ед. m ω_p v₀/e)")
        ax.legend(loc="lower right", fontsize=8)
        self.fig.canvas.draw_idle()

    def _on_series(self, label):
        if self.running:
            return
        self.series = label
        self.rows = []
        self.pt.set_data([], [])
        self.ln_fit.set_data([], [])
        for t in list(self.ax_p.texts) + list(self.ax_p.lines[3:]):
            t.remove()
        self._setup_plot()
        self._render_table()

    def _start(self, _=None):
        if self.running:
            return
        key, vals = SERIES[self.series]
        self.rows = []
        self.queue = [self.base.copy(**{key: v}) for v in vals]
        self.running = True
        self.t_start = time.perf_counter()
        self._next()

    def _stop(self, _=None):
        self.running = False
        self.queue = []
        self.cur = None
        self.s_status = "Остановлено."

    def _next(self):
        if not self.queue:
            self.cur = None
            self.running = False
            self.s_status = (f"Готово за {time.perf_counter() - self.t_start:.0f} с. "
                             "Строки добавлены в results/journal.csv.")
            return
        self.cur = SatRun(self.queue.pop(0), t_end_factor=3.5)

    def _tick(self):
        if not plt.fignum_exists(self.fig.number):
            self.timer.stop()
            return
        if not self.running or self.cur is None:
            keep_drawn(self.fig)
            return
        done = self.cur.advance(60)
        key, vals = SERIES[self.series]
        i = len(self.rows) + 1
        p = self.cur.p
        self.s_status = (f"Счёт {i}/{len(vals)}: {key} = {getattr(p, key):g},  "
                         f"t = {self.cur.sim.t:.0f}/ω_p,  стадия "
                         f"{self.cur.tr.stage + 1}/4  [{'█' * int(20 * self.cur.progress()):<20}]")
        if done:
            r = self.cur.result()
            self.rows.append(r)
            journal.append(r, series=f"таблица {key}")
            self._update_plot()
            self._render_table()
            self._next()
        self.blit.update()

    def _update_plot(self):
        key, _ = SERIES[self.series]
        xs = np.array([r[key] for r in self.rows])
        ys = np.array([r["E_sat"] for r in self.rows])
        ok = np.isfinite(ys)
        self.pt.set_data(xs[ok], ys[ok])
        if key in ("alpha", "vb") and ok.sum() >= 3:
            sl, c = np.polyfit(np.log(xs[ok]), np.log(ys[ok]), 1)
            xx = np.array([xs[ok].min(), xs[ok].max()])
            self.ln_fit.set_data(xx, np.exp(c) * xx ** sl)
            self.ln_fit.set_label(f"подгонка: E_sat ∝ {'α' if key == 'alpha' else 'v_b'}^{sl:.2f}")
            self.fit_slope = sl
            self.ax_p.legend(loc="lower right", fontsize=8)
            self.fig.canvas.draw_idle()

    def _render_table(self):
        key, vals = SERIES[self.series]
        L = []
        if key == "alpha":
            L.append("§  α      γ_теор  γ_изм  ошибка  E_sat   3.12γ²/k  ω_B/γ  "
                     "W_E,sat  W_E,кон  W_E^КЛ")
        elif key == "vb":
            L.append("§ v_b     γ_теор  γ_изм  ошибка  E_sat   3.12γ²/k  ω_B/γ  "
                     "E_sat/v_b  k_max·v_b")
        else:
            L.append("§Δv/v_b   γ_теор  γ_изм  ошибка  E_sat   3.12γ²/k  ω_B/γ  "
                     "W_E,sat  W_E,кон  W_E^КЛ")
        for r in self.rows:
            err = (r["gamma_meas"] / r["gamma_th"] - 1) * 100
            head = f"{r[key]:<7.4g}  {r['gamma_th']:.4f}  {r['gamma_meas']:.4f} {err:+5.1f}%  " \
                   f"{r['E_sat']:.4f}  {r['E_trap']:.4f}   {r['wB_over_g']:.2f}  "
            if key == "vb":
                tail = f"  {r['E_sat'] / r['vb']:.4f}    {r['k_main'] * r['vb']:.3f}"
            else:
                tail = (f" {r['WE_sat_frac'] * 100:5.1f}%   {r['WE_end_frac'] * 100:5.1f}%  "
                        f" {r['WE_ql_frac'] * 100:5.1f}%")
            L.append(" " + head + tail)
        for v in vals[len(self.rows):]:
            L.append(f" {v:<7.4g}  …")
        L.append("")
        L.append("§Обозначения")
        L.append(" γ_теор — точный корень дисп. уравнения (тёплый пучок — кинетика)")
        L.append(" γ_изм  — наклон ln E₀(t) в линейной стадии PIC-счёта")
        L.append(" E_sat  — амплитуда главной волны в первом максимуме")
        L.append(" 3.12γ²/k — теория захвата (ω_B/γ = 1.77 из одноволновой модели)")
        L.append(" W_E,sat, W_E,кон — энергия поля / K_b0 в максимуме и в конце счёта")
        L.append(" W_E^КЛ — квазилинейный баланс: (K_b0 − K_плато)/2 по краям плато")
        if len(self.rows) >= 3 and key in ("alpha", "vb") and hasattr(self, "fit_slope"):
            L.append("")
            if key == "alpha":
                al = np.array([r["alpha"] for r in self.rows])
                th = np.array([r["E_trap"] for r in self.rows])
                st = np.polyfit(np.log(al), np.log(th), 1)[0]
                L.append(f"§Вывод: E_sat ∝ α^{self.fit_slope:.2f} в PIC; теория захвата с")
                L.append(f" точным γ даёт α^{st:.2f}; предел слабого пучка α → 0: α^(2/3).")
            else:
                L.append(f"§Вывод: E_sat ∝ v_b^{self.fit_slope:.2f} (теория: ровно 1),")
                L.append(" γ не зависит от v_b — v_b задаёт лишь масштаб длины и поля.")
        self.s_tab = "\n".join(L)

    def _raw(self, buf):
        H, W = buf.shape[:2]
        for rt in (self.rt, self.rt_st):
            rt.set_dpi(self.fig.dpi)
        bb = self.ax_t.bbox
        img = self.rt.render(self.s_tab)
        paste(buf, img[: int(bb.height) - 16, : int(bb.width) - 16], bb.x0 + 10, H - bb.y1 + 10)
        im = self.rt_st.render(self.s_status)
        paste(buf, im, 0.04 * W, H - 0.18 * H)

    def _save(self, _=None):
        if not self.rows:
            return
        key, _ = SERIES[self.series]
        path = os.path.join(journal.RESULTS, f"таблица_{key}.csv")
        os.makedirs(journal.RESULTS, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(self.rows[0]), delimiter=";")
            w.writeheader()
            for r in self.rows:
                w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in r.items()})
        self.s_status = f"Сохранено: results/таблица_{key}.csv (открывается в Excel)"
        self.blit.update()
