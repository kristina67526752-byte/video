"""Окно «Таблица насыщения»: серия PIC-счётов по параметру пучка (всё в СИ).

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
from matplotlib.widgets import RadioButtons

from .. import dispersion as disp
from .. import diagnostics as diag
from ..constants import lorentz_gamma
from ..runs import SatRun
from ..units import Scale, fmt, sci
from .. import journal
from . import style
from .style import C, MONO
from .blit import Blitter, Region, keep_drawn
from .fastdraw import MonoText, paste
from .widgets import button

SERIES = {
    "по плотности n_b/n_p": ("alpha", [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1]),
    "по скорости v_b, м/с": ("vb", [5e6, 1e7, 2e7, 5e7, 1e8, 2e8, 2.7e8]),
    "по разбросу Δv_b/v_b": ("dvf", [0.0, 0.05, 0.1, 0.15, 0.2]),
}


def _trap(n_p, alpha, vb, T_e=0.0, dvb=0.0):
    """Теория захвата для заданных параметров: (E_trap [В/м], γ [с⁻¹], k [рад/м])."""
    sp = disp.beam_plasma_species(n_p, alpha, vb)
    k, g, w = disp.most_unstable(sp)
    if dvb > 0:
        k, g, w = disp.kinetic_most_unstable(disp.beam_plasma_species(n_p, alpha, vb, T_e, dvb), k)
    return diag.trapping_amplitude(g, k, float(lorentz_gamma(w / k))), g, k


class TableWindow:
    def __init__(self, base=None, npart=32768):
        from ..pic import PICParams
        style.use(style.current_theme())
        b = base or PICParams()
        # серия считается вокруг текущей плазмы (n_p, T_e); ионы неподвижны — до насыщения
        # они не успевают сдвинуться
        self.base = b.copy(scenario="beam", npart=npart, alpha=0.01, dvb=0.0, ion="none")
        self.series = list(SERIES)[0]
        self.rows = []
        self.queue = []
        self.cur = None
        self.running = False
        f = self.fig = plt.figure(figsize=(14.4, 8.1))
        try:
            f.canvas.manager.set_window_title("И11 · Таблица амплитуд насыщения")
        except Exception:
            pass
        f.text(0.04, 0.965, "Вычислительный эксперимент: амплитуда насыщения E_sat [В/м] в "
               "зависимости от параметров пучка", fontsize=13, fontweight="bold", color=C["text"])
        self.ax_t = f.add_axes([0.04, 0.2, 0.55, 0.72])
        self.ax_t.set_xticks([]); self.ax_t.set_yticks([]); self.ax_t.grid(False)
        self.ax_t.set_facecolor(C["panel"])
        self.ax_p = f.add_axes([0.66, 0.2, 0.31, 0.72])
        A = []
        self.pt = self.ax_p.plot([], [], "o", ms=9, mfc=C["field"], mec=C["surface"], mew=2,
                                 label="PIC: первый максимум E₀")[0]
        A.append(self.pt)
        self.ln_th, = self.ax_p.plot([], [], color=C["text2"], ls="--", lw=1.4,
                                     label="теория захвата 3.12·γ²mγ_ф³/(ek)")
        self.ln_fit = self.ax_p.plot([], [], color=C["main"], lw=1.4, label="степенная подгонка")[0]
        A.append(self.ln_fit)

        axr = f.add_axes([0.04, 0.04, 0.17, 0.12])
        style.style_widget_axes(axr)
        self.r = RadioButtons(axr, list(SERIES), active=0, activecolor=C["main"])
        for t in self.r.labels:
            t.set_color(C["text"])
        self.r.on_clicked(self._on_series)
        self.b_go = button(f, [0.23, 0.10, 0.12, 0.05], "▶ Посчитать серию", self._start, hl=True)
        self.b_stop = button(f, [0.36, 0.10, 0.09, 0.05], "Стоп", self._stop)
        self.b_csv = button(f, [0.46, 0.10, 0.10, 0.05], "Сохранить CSV", self._save)

        self.rt = MonoText(MONO, 7.8, C["text"], C["main"], C["panel"], f.dpi)
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
    def _params(self, key, v):
        if key == "dvf":
            return self.base.copy(dvb=v * self.base.vb)
        return self.base.copy(**{key: v})

    def _setup_plot(self):
        ax = self.ax_p
        b = self.base
        key, vals = SERIES[self.series]
        ax.set_xscale("log" if key in ("alpha", "vb") else "linear")
        ax.set_yscale("log")
        if key == "alpha":
            ax.set_xlabel("n_b/n_p")
            ax.set_title("E_sat(n_b/n_p): ∝ (n_b/n_p)^(2/3) при слабом пучке", loc="left")
            xs = np.logspace(-3.1, -0.9, 40)
            th = [_trap(b.n_p, a, b.vb)[0] for a in xs]
        elif key == "vb":
            ax.set_xlabel("v_b, м/с")
            ax.set_title("E_sat(v_b): ∝ v_b при v_b ≪ c, быстрее при v_b → c", loc="left")
            xs = np.logspace(np.log10(4e6), np.log10(2.85e8), 40)
            th = [_trap(b.n_p, 0.01, v)[0] for v in xs]
        else:
            ax.set_xlabel("Δv_b/v_b")
            ax.set_title("E_sat(Δv_b): тёплый пучок насыщается слабее", loc="left")
            xs = np.linspace(0, 0.22, 23)
            th = [_trap(b.n_p, 0.01, b.vb, b.T_e, d * b.vb)[0] for d in xs]
            ax.axvline(np.cbrt(0.01 / 2), color=C["muted"], ls=":", lw=1)
        th = np.array(th)
        self.ln_th.set_data(xs, th)
        ax.set_xlim(xs[0] - (0.01 if key == "dvf" else 0), xs[-1])
        ax.set_ylim(0.3 * th.min(), 3 * th.max())
        ax.set_ylabel("амплитуда насыщения E_sat, В/м")
        ax.legend(loc="lower right", fontsize=8)
        self.fig.canvas.draw_idle()

    def _on_series(self, label):
        if self.running:
            return
        self.series = label
        self.rows = []
        self.pt.set_data([], [])
        self.ln_fit.set_data([], [])
        for t in list(self.ax_p.lines[3:]):
            t.remove()
        self._setup_plot()
        self._render_table()

    def _start(self, _=None):
        if self.running:
            return
        key, vals = SERIES[self.series]
        self.rows = []
        self.queue = [(v, self._params(key, v)) for v in vals]
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
        self.cur_x, p = self.queue.pop(0)
        self.cur = SatRun(p, t_end_factor=3.5)

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
        self.s_status = (f"Счёт {i}/{len(vals)}: {self.cur_x:g},  "
                         f"t = {fmt(self.cur.sim.t, 'с')},  стадия "
                         f"{self.cur.tr.stage + 1}/4  [{'█' * int(20 * self.cur.progress()):<20}]")
        if done:
            r = self.cur.result()
            r["x"] = self.cur_x
            self.rows.append(r)
            journal.append(r, series=f"таблица {key}")
            self._update_plot()
            self._render_table()
            self._next()
        self.blit.update()

    def _update_plot(self):
        key, _ = SERIES[self.series]
        xs = np.array([r["x"] for r in self.rows])
        ys = np.array([r["E_sat"] for r in self.rows])
        ok = np.isfinite(ys)
        self.pt.set_data(xs[ok], ys[ok])
        if key in ("alpha", "vb") and ok.sum() >= 3:
            # для скорости — подгонка только по нерелятивистским точкам
            sel = ok & ((xs < 6e7) if key == "vb" else True)
            if sel.sum() >= 3:
                sl, c = np.polyfit(np.log(xs[sel]), np.log(ys[sel]), 1)
                xx = np.array([xs[sel].min(), xs[sel].max()])
                self.ln_fit.set_data(xx, np.exp(c) * xx ** sl)
                self.ln_fit.set_label(f"подгонка: E_sat ∝ {'(n_b/n_p)' if key == 'alpha' else 'v_b'}^{sl:.2f}")
                self.fit_slope = sl
                self.ax_p.legend(loc="lower right", fontsize=8)
                self.fig.canvas.draw_idle()

    def _render_table(self):
        key, vals = SERIES[self.series]
        b = self.base
        L = [f"§Плазма: n_p = {sci(b.n_p, 2)} м⁻³, T_e = {sci(b.T_e, 2)} К; "
             f"пучок: " + ("v_b = " + sci(b.vb) + " м/с" if key != "vb" else "n_b/n_p = 0.01"), ""]
        name = {"alpha": "n_b/n_p", "vb": "v_b,м/с", "dvf": "Δv_b/v_b"}[key]
        L.append(f"§{name:<8} γ_теор,с⁻¹ γ_изм,с⁻¹ ошибка E_sat,В/м  захват,В/м ω_B/γ "
                 "W_E,sat  W_E,кон  W_E^КЛ")
        for r in self.rows:
            err = (r["gamma_meas"] / r["gamma_th"] - 1) * 100
            xs = f"{r['x']:.3g}" if key != "vb" else sci(r["x"], 2)
            L.append(f" {xs:<8} {sci(r['gamma_th']):>9} {sci(r['gamma_meas']):>9} {err:+5.1f}%  "
                     f"{sci(r['E_sat']):>9} {sci(r['E_trap']):>9}  {r['wB_over_g']:.2f}  "
                     f"{r['WE_sat_frac'] * 100:5.1f}%  {r['WE_end_frac'] * 100:5.1f}%  "
                     f"{r['WE_ql_frac'] * 100:5.1f}%")
        for v in vals[len(self.rows):]:
            L.append(f" {(f'{v:.3g}' if key != 'vb' else sci(v, 2)):<8} …")
        L.append("")
        L.append("§Обозначения (все размерные величины — в СИ)")
        L.append(" γ_теор — корень дисперсионного уравнения с реальными температурами (кинетика)")
        L.append(" γ_изм  — наклон ln E₀(t) в линейной стадии PIC-счёта")
        L.append(" E_sat  — амплитуда главной волны в первом максимуме, В/м")
        L.append(" захват — теория захвата 3.12·γ²·mγ_ф³/(ek)  (ω_B/γ = 1.77, одноволновая модель)")
        L.append(" W_E,sat, W_E,кон — энергия поля в долях K_b0 в максимуме и в конце счёта")
        L.append(" W_E^КЛ — квазилинейный баланс: (K_b0 − K_плато)/2 по краям плато")
        if len(self.rows) >= 3 and key in ("alpha", "vb") and hasattr(self, "fit_slope"):
            L.append("")
            if key == "alpha":
                al = np.array([r["alpha"] for r in self.rows])
                th = np.array([r["E_trap"] for r in self.rows])
                st = np.polyfit(np.log(al), np.log(th), 1)[0]
                L.append(f"§Вывод: E_sat ∝ (n_b/n_p)^{self.fit_slope:.2f} в PIC; теория захвата с")
                L.append(f" точным γ даёт показатель {st:.2f}; предел слабого пучка: 2/3.")
            else:
                L.append(f"§Вывод: при v_b ≪ c E_sat ∝ v_b^{self.fit_slope:.2f} (теория: ровно 1);")
                L.append(" при v_b → c инкремент падает как 1/γ_b, а E_sat ∝ γ²mγ_ф³/k растёт быстрее.")
        self.s_tab = "\n".join(L).replace("≪", "<<")

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
