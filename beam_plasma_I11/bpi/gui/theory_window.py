"""Окно «Теория γ(k)»: точное решение дисперсионного уравнения (всё в СИ).

Показывает:
  * γ(k) [с⁻¹] — уравнение из задания (холодное) и кинетическая теория с реальными
    температурами плазмы и пучка;
  * Re ω(k) — все 4 ветви: плазменная ω = ω_p и две пучковые ω = kv_b ± ω_b;
    неустойчивость там, где пучковая ветвь пересекает плазменную;
  * γ_max(n_b/n_p) — точный, по формуле из подсказки и по исправленной асимптотике;
  * γ_max(v_b) — релятивистское падение инкремента: γ ∝ 1/γ_b;
  * 4 корня на комплексной плоскости ω при выбранном k (кнопка «пройти по k»).
"""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from .. import dispersion as disp
from ..constants import C_LIGHT, plasma_frequency, lorentz_gamma
from ..units import Scale, fmt, sci
from . import style
from .style import C, MONO
from .blit import Blitter, Region, SliderBlit, keep_drawn, blit_axes
from .fastdraw import MonoText, paste
from .widgets import ListSlider, plain_slider, button, fmt_velocity, ALPHAS, VELOCITIES

ALPHAS_T = [1e-4, 2e-4, 5e-4] + ALPHAS + [0.2, 0.5, 1.0]


class TheoryWindow:
    def __init__(self, n_p=1.0e16, T_e=3.0e4, alpha=0.01, vb=1.0e7, dvb=0.0):
        style.use(style.current_theme())
        self.n_p, self.T_e = n_p, T_e
        self.wp = float(plasma_frequency(n_p))
        self.alpha, self.vb, self.dvf = alpha, vb, dvb / vb
        self.kq = 1.0                                   # выбранное k·v_b/ω_p
        self.sweep = False
        f = self.fig = plt.figure(figsize=(14.4, 8.1))
        try:
            f.canvas.manager.set_window_title("И11 · Теория: дисперсионное уравнение и γ(k)")
        except Exception:
            pass
        f.text(0.05, 0.965, "Линейная теория:  1 − ω_p²/ω² − ω_b²/(ω − k·v_b)² = 0,   "
               "ω_p² = n_p e²/(ε₀m),  ω_b² = n_b e²/(ε₀mγ_b³)", fontsize=13, fontweight="bold",
               color=C["text"])
        self.ax_g = f.add_axes([0.06, 0.57, 0.40, 0.34])
        self.ax_w = f.add_axes([0.06, 0.15, 0.40, 0.34], sharex=self.ax_g)
        self.ax_a = f.add_axes([0.55, 0.57, 0.19, 0.34])
        self.ax_v = f.add_axes([0.79, 0.57, 0.19, 0.34])
        self.ax_c = f.add_axes([0.55, 0.15, 0.19, 0.34])
        self.ax_t = f.add_axes([0.76, 0.15, 0.22, 0.34])
        self.ax_t.set_xticks([]); self.ax_t.set_yticks([]); self.ax_t.grid(False)
        A = self._anim = []

        def anim(a):
            A.append(a)
            return a

        ax = self.ax_g
        ax.set_title("Инкремент γ(k)", loc="left")
        ax.tick_params(labelbottom=False)
        self.l_g, = ax.plot([], [], color=C["main"], lw=2, label="уравнение из задания (точно)")
        self.l_gk, = ax.plot([], [], color=C["beam"], lw=2, label="кинетика (T_e, Δv_b)")
        self.l_gh = ax.axhline(0, color=C["text2"], ls="--", lw=1.2,
                               label="подсказка (√3/2)(n_b/n_p)^⅓ω_p")
        self.l_gw = ax.axhline(0, color=C["text2"], ls=":", lw=1.4,
                               label="(√3/2)(n_b/2n_p)^⅓ω_p/γ_b")
        self.v_g = anim(ax.axvline(1, color=C["field"], lw=1.2))
        self.p_g = anim(ax.plot([], [], "o", ms=8, mfc=C["field"], mec=C["surface"], mew=2)[0])

        ax = self.ax_w
        ax.set_title("Ветви Re ω(k): где пучковая волна догоняет плазменную", loc="left")
        self.l_w = [ax.plot([], [], ".", ms=2, color=C["text2"])[0] for _ in range(4)]
        self.l_wu, = ax.plot([], [], color=C["main"], lw=3, label="растущая волна (γ > 0)")
        self.l_p = ax.axhline(1, color=C["plasma"], ls="--", lw=1.2, label="плазма ω = ω_p")
        self.l_b1, = ax.plot([], [], color=C["beam"], ls="--", lw=1.2, label="пучок ω = kv_b ± ω_b")
        self.l_b2, = ax.plot([], [], color=C["beam"], ls="--", lw=1.2)
        self.v_w = anim(ax.axvline(1, color=C["field"], lw=1.2))
        ax.legend(loc="upper left", fontsize=7.5)

        ax = self.ax_a
        ax.set_title("γ_max от n_b/n_p", loc="left")
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlabel("n_b/n_p")
        self.l_a = [ax.plot([], [], color=C["main"], lw=2.2, label="точный корень")[0],
                    ax.plot([], [], color=C["text2"], ls="--", lw=1.3, label="подсказка")[0],
                    ax.plot([], [], color=C["text2"], ls=":", lw=1.6, label="исправленная")[0]]
        self.p_a, = ax.plot([], [], "o", ms=9, mfc=C["field"], mec=C["surface"], mew=2)
        self.t_a = ax.text(0.97, 0.04, "", transform=ax.transAxes, ha="right", fontsize=7.5,
                           color=C["text2"])
        ax.legend(loc="upper left", fontsize=7)

        ax = self.ax_v
        ax.set_title("γ_max от скорости пучка", loc="left")
        ax.set_xlabel("v_b/c")
        self.l_v = [ax.plot([], [], color=C["main"], lw=2.2, label="точный корень")[0],
                    ax.plot([], [], color=C["text2"], ls=":", lw=1.6, label="∝ 1/γ_b")[0],
                    ax.plot([], [], color=C["text2"], ls="--", lw=1.0, label="без релятивизма")[0]]
        self.p_v, = ax.plot([], [], "o", ms=9, mfc=C["field"], mec=C["surface"], mew=2)
        ax.legend(loc="lower left", fontsize=7)

        ax = self.ax_c
        ax.set_title("4 корня ω при выбранном k", loc="left")
        ax.axhline(0, color=C["grid"], lw=1)
        self.l_tr = [ax.plot([], [], ".", ms=1.5, color=C["muted"])[0] for _ in range(4)]
        self.p_c = anim(ax.plot([], [], "o", ms=7, mfc=C["text2"], mec=C["surface"], mew=1.5)[0])
        self.p_cu = anim(ax.plot([], [], "o", ms=10, mfc=C["main"], mec=C["surface"], mew=2)[0])

        self.ax_t.set_facecolor(C["panel"])
        self.rt = MonoText(MONO, 7.6, C["text"], C["main"], C["panel"], f.dpi)
        self.s_txt = ""

        self.s_a = ListSlider(f, [0.09, 0.06, 0.15, 0.025], "n_b/n_p", ALPHAS_T, alpha,
                              lambda v: f"{v:.3g}")
        self.s_v = ListSlider(f, [0.31, 0.06, 0.13, 0.025], "v_b", VELOCITIES, vb, fmt_velocity)
        self.s_d = plain_slider(f, [0.59, 0.06, 0.10, 0.025], "Δv_b/v_b", 0, 0.3, self.dvf, 0.01)
        self.s_k = plain_slider(f, [0.775, 0.06, 0.09, 0.025], "k·v_b/ω_p", 0.05, 2.0, 1.0, 0.005)
        self.s_a.on_changed(self._on_param)
        self.s_v.on_changed(self._on_param)
        self.s_d.on_changed(self._on_param)
        self.s_k.on_changed(self._on_k)
        self._sb = [SliderBlit(f, x, C["surface"]) for x in
                    (self.s_a.slider, self.s_v.slider, self.s_d, self.s_k)]
        self._dirty = False
        f.canvas.mpl_connect("button_release_event", self._on_release)
        self.b_sw = button(f, [0.90, 0.05, 0.085, 0.045], "▶ пройти по k", self._toggle_sweep, hl=True)

        # перерисовываем только область графиков (ползунки внизу рисуют себя сами)
        self.blit = Blitter(f, regions=[Region(
            lambda: (0, 0.115 * f.bbox.height, f.bbox.width, f.bbox.height), A, self._raw)])
        self._recompute()
        self.timer = f.canvas.new_timer(interval=30)
        self.timer.add_callback(self._tick)
        self.timer.start()
        f.canvas.mpl_connect("close_event", lambda e: self.timer.stop())
        f.show()

    # ------------------------------------------------------------------
    def _species(self, alpha=None, vb=None):
        return disp.beam_plasma_species(self.n_p, self.alpha if alpha is None else alpha,
                                        self.vb if vb is None else vb)

    def _recompute(self):
        a, vb, wp = self.alpha, self.vb, self.wp
        gb = float(lorentz_gamma(vb))
        sp = self._species()
        self.k_unit = wp / vb                              # рад/м
        k = np.linspace(0.005, 2.0, 700) * self.k_unit
        self.sc_k = Scale(2.0 * self.k_unit, "рад/м")
        self.sc_w = Scale(2.5 * wp, "рад/с")
        r = disp.fluid_roots(k, sp)
        wr, g = disp.fluid_growth(k, sp)
        self.l_g.set_data(k, g)
        spk = disp.beam_plasma_species(self.n_p, a, vb, self.T_e, self.dvf * vb)
        _, gk = disp.kinetic_growth_curve(k, spk)
        self._kk, self._gk = k, np.maximum(gk, 0)
        self.l_gk.set_data(k, self._gk)
        gh, gw = disp.gamma_hint(a, wp), disp.gamma_weak_beam(a, wp, gb)
        self.l_gh.set_ydata([gh] * 2)
        self.l_gw.set_ydata([gw] * 2)
        self.sc_g = Scale(max(gh, g.max()), "с⁻¹")
        ax = self.ax_g
        ax.set_ylim(0, 1.15 * max(gh, g.max()))
        ax.set_ylabel(f"γ, {self.sc_g.label}")
        ax.yaxis.set_major_formatter(self.sc_g.formatter())
        ax.legend(loc="upper right", fontsize=7.2)
        rs = np.sort_complex(r)
        for i in range(4):
            self.l_w[i].set_data(k, rs[:, i].real)
            self.l_tr[i].set_data(rs[:, i].real, rs[:, i].imag)
        self.l_wu.set_data(k, np.where(g > 1e-9 * wp, wr, np.nan))
        self.l_p.set_ydata([wp, wp])
        wb = np.sqrt(a / gb ** 3) * wp
        self.l_b1.set_data(k, k * vb + wb)
        self.l_b2.set_data(k, k * vb - wb)
        ax = self.ax_w
        ax.set_xlim(0, 2.0 * self.k_unit)
        ax.set_ylim(-1.6 * wp, 2.6 * wp)
        ax.set_xlabel(f"волновое число k, {self.sc_k.label}")
        ax.xaxis.set_major_formatter(self.sc_k.formatter())
        ax.set_ylabel(f"Re ω, {self.sc_w.label}")
        ax.yaxis.set_major_formatter(self.sc_w.formatter())
        gmax = g.max()
        ax = self.ax_c
        ax.set_xlim(-1.6 * wp, 2.6 * wp)
        ax.set_ylim(-1.3 * gmax - 0.02 * wp, 1.3 * gmax + 0.02 * wp)
        ax.set_xlabel(f"Re ω, {self.sc_w.label}")
        ax.xaxis.set_major_formatter(self.sc_w.formatter())
        ax.set_ylabel(f"Im ω, {self.sc_g.label}")
        ax.yaxis.set_major_formatter(self.sc_g.formatter())
        self.k0, self.g0, self.w0 = disp.most_unstable(sp)
        # γ_max(n_b/n_p)
        al = np.logspace(-4, 0, 50)
        gx = np.array([disp.most_unstable(self._species(alpha=x))[1] for x in al])
        self.l_a[0].set_data(al, gx)
        self.l_a[1].set_data(al, disp.gamma_hint(al, wp))
        self.l_a[2].set_data(al, disp.gamma_weak_beam(al, wp, gb))
        self.p_a.set_data([a], [self.g0])
        sel = (al >= 1e-3) & (al <= 0.1)
        sl = np.polyfit(np.log(al[sel]), np.log(gx[sel]), 1)[0]
        self.t_a.set_text(f"0.001…0.1: γ_max ∝ (n_b/n_p)^{sl:.3f}")
        self.ax_a.set_xlim(1e-4, 1)
        self.ax_a.set_ylim(0.5 * gx.min(), 3 * gx.max())
        self.ax_a.set_ylabel("γ_max, с⁻¹")
        # γ_max(v_b)
        be = np.linspace(0.02, 0.97, 40)
        gv = np.array([disp.most_unstable(self._species(vb=b * C_LIGHT))[1] for b in be])
        self.l_v[0].set_data(be, gv)
        self.l_v[1].set_data(be, gv[0] * np.sqrt(1 - be ** 2))
        self.l_v[2].set_data(be, np.full_like(be, gv[0]))
        self.p_v.set_data([vb / C_LIGHT], [self.g0])
        self.ax_v.set_xlim(0, 1)
        self.ax_v.set_ylim(0, 1.15 * gv[0])
        self.ax_v.yaxis.set_major_formatter(self.sc_g.formatter())
        self.ax_v.set_ylabel(f"γ_max, {self.sc_g.label}")
        self._update_k()
        self.fig.canvas.draw_idle()

    def _update_k(self):
        a, wp, vb = self.alpha, self.wp, self.vb
        k = self.kq * self.k_unit
        sp = self._species()
        r = disp.fluid_roots(np.array([k]), sp)[0]
        iu = int(np.argmax(r.imag))
        g = max(r[iu].imag, 0.0)
        self.v_g.set_xdata([k, k])
        self.v_w.set_xdata([k, k])
        self.p_g.set_data([k], [g])
        self.p_c.set_data(r.real, r.imag)
        if g > 1e-9 * wp:
            self.p_cu.set_data([r[iu].real], [r[iu].imag])
        else:
            self.p_cu.set_data([], [])
        wb2 = sp[1][0]
        D = lambda w: 1 - wp ** 2 / w ** 2 - wb2 / (w - k * vb) ** 2
        gb = float(lorentz_gamma(vb))
        L = [f"§n_p = {sci(self.n_p, 2)} м⁻³, T_e = {sci(self.T_e, 2)} К",
             f" ω_p = {sci(wp)} с⁻¹, f_p = {fmt(wp / 2 / np.pi, 'Гц')}",
             f"§n_b/n_p = {a:.4g}, v_b = {sci(vb)} м/с",
             f" γ_b = {gb:.4f},  ω_b = {sci(np.sqrt(wb2))} с⁻¹",
             f"§k = {sci(k)} рад/м (λ = {fmt(2 * np.pi / k, 'м')})",
             "§4 корня ω, рад/с:"]
        for w in sorted(r, key=lambda z: -z.imag):
            L.append(f" {sci(w.real):>10} {'+' if w.imag >= 0 else '−'} {sci(abs(w.imag))}i"
                     f" |D|={abs(D(w)):.0e}")
        L.append(f"§при этом k: γ = {sci(g)} с⁻¹")
        L.append(f"§максимум: k_max = {sci(self.k0)} рад/м")
        L.append(f" γ_max = {sci(self.g0)} с⁻¹ = {self.g0 / wp:.4f}ω_p")
        L.append(f" 1/γ_max = {fmt(1 / self.g0, 'с')}, ω_r = {sci(self.w0)}")
        gh, gw = disp.gamma_hint(a, wp), disp.gamma_weak_beam(a, wp, gb)
        L.append(f" подсказка    {sci(gh)} ({(gh / self.g0 - 1) * 100:+.0f}%)")
        L.append(f" исправленная {sci(gw)} ({(gw / self.g0 - 1) * 100:+.1f}%)")
        gk = float(np.interp(k, self._kk, self._gk))
        L.append(f"§кинетика (T_e, Δv_b = {sci(self.dvf * vb, 2)} м/с):")
        L.append(f" γ = {sci(gk)} с⁻¹; холодный режим,")
        L.append(f" если Δv_b < (n_b/2n_p)^⅓v_b/γ_b = {sci(np.cbrt(a / 2) * vb / gb, 2)}")
        self.s_txt = "\n".join(L)

    def _raw(self, buf):
        H = buf.shape[0]
        bb = self.ax_t.bbox
        self.rt.set_dpi(self.fig.dpi)
        img = self.rt.render(self.s_txt)
        w = int(bb.width) - 12
        paste(buf, img[: int(bb.height) - 12, :w], bb.x0 + 6, H - bb.y1 + 6)

    # ------------------------------------------------------------------
    def _on_param(self, _):
        # пересчёт графиков — когда кнопку мыши отпустят (иначе тормозит перетаскивание)
        self.alpha, self.vb, self.dvf = self.s_a.val, self.s_v.val, float(self.s_d.val)
        self._dirty = True

    def _on_release(self, _):
        if self._dirty:
            self._dirty = False
            self._recompute()

    def _on_k(self, v):
        self.kq = float(v)
        self._update_k()
        self.blit.update()

    def _toggle_sweep(self, _):
        self.sweep = not self.sweep
        self.b_sw.label.set_text("|| стоп" if self.sweep else "▶ пройти по k")
        blit_axes(self.fig, self.b_sw.ax)

    def _tick(self):
        if not plt.fignum_exists(self.fig.number):
            self.timer.stop()
            return
        if not self.sweep:
            keep_drawn(self.fig)
            return
        self.kq += 0.006
        if self.kq > 2.0:
            self.kq = 0.05
        self._update_k()
        self.blit.update()
