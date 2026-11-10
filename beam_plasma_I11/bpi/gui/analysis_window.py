"""Окно «Анализ»: что ещё можно узнать из того же PIC-счёта главного окна.

  * Дисперсионная диаграмма из счёта — спектр поля на плоскости (k, ω).
    Счёт сам «рисует» дисперсионное уравнение: светятся ленгмюровская ветвь
    ω² = ω_p² + 3k²v_Te² и пучковая ω = k·v_b; поверх наложены теоретические кривые.
  * Карты x–t: уровень поля W = ε₀⟨E²⟩/(2n k_BT_e) и концентрация ионов δn_i/n_i.
    На них видны бегущие волновые пакеты, каверны и расходящийся ионный звук.

Окно читает данные главного окна и обновляется раз в секунду.
"""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from .. import diagnostics as diag
from .. import dispersion as disp
from ..constants import ION_LABEL, ion_sound_speed
from ..units import Scale, fmt, sci
from . import style
from .style import C, MONO
from .widgets import button


class AnalysisWindow:
    def __init__(self, main):
        style.use(style.current_theme())
        self.main = main
        self._sim_id = None
        f = self.fig = plt.figure(figsize=(14.4, 8.1))
        try:
            f.canvas.manager.set_window_title("И11 · Анализ счёта: дисперсия ω–k и карты x–t")
        except Exception:
            pass
        f.text(0.04, 0.965, "Анализ PIC-счёта: дисперсионная диаграмма (k, ω) и карты x–t",
               fontsize=13, fontweight="bold", color=C["text"])
        self.ax_wk = f.add_axes([0.055, 0.2, 0.40, 0.70])
        self.ax_W = f.add_axes([0.53, 0.57, 0.40, 0.33])
        self.ax_n = f.add_axes([0.53, 0.14, 0.40, 0.33], sharex=self.ax_W, sharey=self.ax_W)
        self.cax_W = f.add_axes([0.94, 0.57, 0.01, 0.33])
        self.cax_n = f.add_axes([0.94, 0.14, 0.01, 0.33])
        for ax in (self.ax_wk, self.ax_W, self.ax_n):
            ax.grid(False)
        self.txt = f.text(0.04, 0.112, "", fontsize=8.4, color=C["text"], family=MONO, va="top",
                          linespacing=1.45)
        self.b_ref = button(f, [0.875, 0.945, 0.075, 0.038], "Обновить", lambda e: self.refresh(), hl=True)
        self.im_wk = self.im_W = self.im_n = None
        self.refresh()
        self.timer = f.canvas.new_timer(interval=1000)
        self.timer.add_callback(self._tick)
        self.timer.start()
        f.canvas.mpl_connect("close_event", lambda e: self.timer.stop())
        f.show()

    def _tick(self):
        if not plt.fignum_exists(self.fig.number):
            self.timer.stop()
            return
        if self.main.running:
            self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        m = self.main
        s, p = m.sim, m.params
        if id(s) != self._sim_id:                 # счёт перезапущен — строим оси заново
            self._sim_id = id(s)
            self._setup(s, p)
        self._update(s, p)
        self.fig.canvas.draw_idle()

    def _setup(self, s, p):
        for ax in (self.ax_wk, self.ax_W, self.ax_n, self.cax_W, self.cax_n):
            ax.clear()
            ax.grid(False)
        self.sc_k = Scale(s.k_modes[s.m_store], "рад/м")
        self.sc_w = Scale(2.5 * s.wpe, "рад/с")
        self.sc_x = Scale(s.L, "м")
        two = p.scenario == "two_stream"
        ax = self.ax_wk
        ax.set_title("Дисперсионная диаграмма из счёта: lg|E(k, ω)|²", loc="left")
        ax.set_xlabel(f"волновое число k, {self.sc_k.label}")
        ax.set_ylabel(f"частота ω, {self.sc_w.label}   (ω < 0 — волна бежит влево)")
        ax.xaxis.set_major_formatter(self.sc_k.formatter())
        ax.yaxis.set_major_formatter(self.sc_w.formatter())
        kmax = s.k_modes[s.m_store]
        dk = s.k_modes[1]
        self._ext_wk = [0.5 * dk, kmax + 0.5 * dk, -1.7 * s.wpe, 2.7 * s.wpe]
        self.im_wk = ax.imshow(np.zeros((2, 2)), origin="lower", aspect="auto", cmap=style.seq_cmap(),
                               extent=self._ext_wk, vmin=-7, vmax=0, interpolation="nearest")
        kk = np.linspace(0, kmax, 300)
        if not two:
            wbg = disp.bohm_gross(kk, p.n_p, p.T_e)
            ax.plot(kk, wbg, color=C["plasma"], ls="--", lw=1.2,
                    label="ленгмюровская волна ω² = ω_p² + 3k²v_Te²")
            ax.plot(kk, -wbg, color=C["plasma"], ls="--", lw=1.2)
            ax.plot(kk, kk * p.vb, color=C["beam"], ls="--", lw=1.2, label="пучок ω = k·v_b")
            ax.plot([s.k_modes[s.m_main]], [s.omega_ref], "o", ms=9, mfc="none", mec=C["main"],
                    mew=1.8, label="самая неустойчивая волна (теория)")
        else:
            u = 0.5 * p.vb
            ax.plot(kk, kk * u, color=C["beam"], ls="--", lw=1.2, label="потоки ω = ±k·v_b/2")
            ax.plot(kk, -kk * u, color=C["beam"], ls="--", lw=1.2)
            ax.axhline(s.wpe, color=C["plasma"], ls="--", lw=1.0, label="ω = ±ω_p1")
            ax.axhline(-s.wpe, color=C["plasma"], ls="--", lw=1.0)
        ax.axhline(0, color=C["grid"], lw=0.8)
        ax.set_xlim(self._ext_wk[0], self._ext_wk[1])
        ax.set_ylim(self._ext_wk[2], self._ext_wk[3])
        ax.legend(loc="lower right", fontsize=7.5)

        ax = self.ax_W
        ax.set_title("Уровень поля W(x, t) = ε₀⟨E²⟩/(2n k_BT_e)", loc="left")
        ax.tick_params(labelbottom=False)
        ax.set_ylabel(f"x, {self.sc_x.label}")
        ax.yaxis.set_major_formatter(self.sc_x.formatter())
        self.im_W = ax.imshow(np.zeros((2, 2)), origin="lower", aspect="auto", cmap=style.seq_cmap(),
                              interpolation="nearest")
        self.cb_W = self.fig.colorbar(self.im_W, cax=self.cax_W)
        ax = self.ax_n
        ion = ION_LABEL[p.ion]
        ax.set_title(f"Концентрация ионов δn_i/n_i (x, t), ионы {ion}" if s.m_i else
                     "Концентрация ионов: ионы неподвижны", loc="left")
        ax.set_ylabel(f"x, {self.sc_x.label}")
        self.im_n = ax.imshow(np.zeros((2, 2)), origin="lower", aspect="auto", cmap=style.div_cmap(),
                              interpolation="nearest", vmin=-0.1, vmax=0.1)
        self.cb_n = self.fig.colorbar(self.im_n, cax=self.cax_n)
        if not s.m_i:
            ax.text(0.5, 0.5, "Включите «ионы подвижны» в главном окне:\nпосле насыщения здесь "
                    "появятся ямы концентрации (каверны)\nи расходящийся от них ионный звук.",
                    transform=ax.transAxes, ha="center", va="center", color=C["text2"], fontsize=10)

    def _update(self, s, p):
        m = self.main
        lines = []
        # --- дисперсионная диаграмма
        r = diag.omega_k_spectrum(s, nwin=2048)
        if r is not None:
            om, k, P = r
            sel = (om >= self._ext_wk[2]) & (om <= self._ext_wk[3])
            Z = np.log10(np.maximum(P[sel] / P.max(), 1e-12))
            self.im_wk.set_data(Z)
            self.im_wk.set_extent([self._ext_wk[0], self._ext_wk[1], om[sel][0], om[sel][-1]])
            i, j = np.unravel_index(int(np.argmax(P)), P.shape)
            nw = min(s.h_n, 2048)
            lines.append(f"Диаграмма (k, ω): последние {nw} шагов = {fmt(nw * s.dt, 'с')}, "
                         f"разрешение δω = {sci(2 * np.pi / (nw * s.dt), 2)} рад/с")
            lines.append(f"Самая яркая точка: k = {sci(k[j])} рад/м, ω = {sci(om[i])} рад/с, "
                         f"фазовая скорость ω/k = {sci(om[i] / k[j])} м/с")
            if p.scenario == "beam":
                lines.append(f"Теория: k = {sci(s.k_modes[s.m_main])} рад/м, ω_r = {sci(s.omega_ref)} рад/с, "
                             f"v_ф = {sci(s.v_phase)} м/с;  v_b = {sci(p.vb)} м/с")
        else:
            lines.append("Диаграмма (k, ω) появится, когда наберётся 128 шагов счёта.")
        # --- карты x–t
        self.sc_t = Scale(max(s.t, 1e-30), "с")
        self.ax_n.set_xlabel(f"время t, {self.sc_t.label}")
        self.ax_n.xaxis.set_major_formatter(self.sc_t.formatter())
        if len(m.xt_t) >= 2:
            ext = [m.xt_t[0], m.xt_t[-1], 0, s.L]
            W = np.array(m.xt_W).T
            self.im_W.set_data(W)
            self.im_W.set_extent(ext)
            self.im_W.set_clim(0, max(float(np.percentile(W, 99.9)), 1e-6))
            self.ax_W.set_xlim(ext[0], ext[1])
            self.ax_W.set_ylim(0, s.L)
            if s.m_i and len(m.xt_ni) >= 2:
                N = np.array(m.xt_ni).T
                v = max(float(np.abs(N).max()), 1e-4)
                self.im_n.set_data(N)
                self.im_n.set_extent(ext)
                self.im_n.set_clim(-v, v)
                I = m.info
                lines.append(f"Ионы {ION_LABEL[p.ion]}: c_s = {sci(I['cs'], 2)} м/с, сейчас δn_i/n_i от "
                             f"{N[:, -1].min() * 100:+.1f}% до {N[:, -1].max() * 100:+.1f}%, "
                             f"W в пике {W[:, -1].max():.3f}")
        self.txt.set_text("\n".join(lines))
