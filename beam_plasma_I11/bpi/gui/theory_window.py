"""Окно «Теория γ(k)»: точное решение дисперсионного уравнения.

Показывает:
  * γ(k) — инкремент (холодная теория и, при Δv > 0, кинетическая);
  * Re ω(k) — все 4 ветви: плазменная ω = ω_p и две пучковые ω = kv_b ± √α ω_p;
    неустойчивость там, где пучковая ветвь пересекает плазменную;
  * γ_max(α) — точный, по формуле из подсказки и по исправленной асимптотике;
  * 4 корня на комплексной плоскости ω при выбранном k (кнопка «пройти по k»
    анимирует, как два корня сливаются и уходят в комплексную область).
"""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button

from .. import dispersion as disp
from . import style
from .style import C, MONO
from .blit import Blitter, Region, SliderBlit, keep_drawn
from .fastdraw import MonoText, paste


class TheoryWindow:
    def __init__(self, alpha=0.01, vb=1.0, dvb=0.0):
        style.use(style.current_theme())
        self.alpha, self.vb, self.dvb = alpha, vb, dvb
        self.kq = 1.0                                   # выбранное k·v_b/ω_p
        self.sweep = False
        f = self.fig = plt.figure(figsize=(15, 8.6))
        try:
            f.canvas.manager.set_window_title("И11 · Теория: дисперсионное уравнение и γ(k)")
        except Exception:
            pass
        f.text(0.05, 0.965, "Линейная теория:  1 − ω_p²/ω² − ω_b²/(ω − k·v_b)² = 0,   "
               "α = ω_b²/ω_p² = n_b/n_p", fontsize=13, fontweight="bold", color=C["text"])
        self.ax_g = f.add_axes([0.06, 0.57, 0.40, 0.34])
        self.ax_w = f.add_axes([0.06, 0.15, 0.40, 0.34], sharex=self.ax_g)
        self.ax_a = f.add_axes([0.55, 0.57, 0.42, 0.34])
        self.ax_c = f.add_axes([0.55, 0.15, 0.20, 0.34])
        self.ax_t = f.add_axes([0.77, 0.15, 0.20, 0.34])
        for ax in (self.ax_t,):
            ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
        A = self._anim = []

        def anim(a):
            A.append(a)
            return a

        ax = self.ax_g
        ax.set_title("Инкремент γ(k)", loc="left")
        ax.set_ylabel("γ / ω_p")
        ax.tick_params(labelbottom=False)
        self.l_g, = ax.plot([], [], color=C["main"], lw=2, label="точно (холодная теория)")
        self.l_gk, = ax.plot([], [], color=C["beam"], lw=2, label="кинетика (тёплый пучок)")
        self.l_gh = ax.axhline(0, color=C["text2"], ls="--", lw=1.2, label="подсказка (√3/2)α^⅓")
        self.l_gw = ax.axhline(0, color=C["text2"], ls=":", lw=1.4, label="(√3/2)(α/2)^⅓")
        self.v_g = anim(ax.axvline(1, color=C["field"], lw=1.2))
        self.p_g = anim(ax.plot([], [], "o", ms=8, mfc=C["field"], mec=C["surface"], mew=2)[0])
        ax.legend(loc="upper right", fontsize=7.5)

        ax = self.ax_w
        ax.set_title("Ветви Re ω(k): где пучковая волна догоняет плазменную", loc="left")
        ax.set_xlabel("k·v_b/ω_p")
        ax.set_ylabel("Re ω / ω_p")
        self.l_w = [ax.plot([], [], ".", ms=2, color=C["text2"])[0] for _ in range(4)]
        self.l_wu, = ax.plot([], [], color=C["main"], lw=3, label="растущая волна (γ > 0)")
        self.l_p = ax.axhline(1, color=C["plasma"], ls="--", lw=1.2, label="плазма ω = ω_p")
        self.l_b1, = ax.plot([], [], color=C["beam"], ls="--", lw=1.2, label="пучок ω = kv_b ± ω_b")
        self.l_b2, = ax.plot([], [], color=C["beam"], ls="--", lw=1.2)
        self.v_w = anim(ax.axvline(1, color=C["field"], lw=1.2))
        ax.set_xlim(0, 2.0)
        ax.set_ylim(-1.6, 2.6)
        ax.legend(loc="upper left", fontsize=7.5)

        ax = self.ax_a
        ax.set_title("Максимальный инкремент γ_max(α)", loc="left")
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlabel("α = n_b/n_p")
        ax.set_ylabel("γ_max / ω_p")
        al = np.logspace(-4, 0, 60)
        gx = np.array([disp.most_unstable(disp.beam_plasma_species(a))[1] for a in al])
        ax.plot(al, gx, color=C["main"], lw=2.2, label="точный корень")
        ax.plot(al, disp.gamma_hint(al), color=C["text2"], ls="--", lw=1.3,
                label="подсказка (√3/2)α^⅓")
        ax.plot(al, disp.gamma_weak_beam(al), color=C["text2"], ls=":", lw=1.6,
                label="исправленная (√3/2)(α/2)^⅓")
        self.p_a, = ax.plot([], [], "o", ms=9, mfc=C["field"], mec=C["surface"], mew=2,
                            label="текущее α")
        sl = np.polyfit(np.log(al[(al >= 1e-3) & (al <= 0.1)]),
                        np.log(gx[(al >= 1e-3) & (al <= 0.1)]), 1)[0]
        ax.text(0.98, 0.04, f"на α = 0.001…0.1 точный закон γ_max ∝ α^{sl:.3f} (а не α^0.333)",
                transform=ax.transAxes, ha="right", fontsize=8, color=C["text2"])
        ax.legend(loc="upper left", fontsize=7.5)

        ax = self.ax_c
        ax.set_title("4 корня ω при выбранном k", loc="left")
        ax.set_xlabel("Re ω / ω_p")
        ax.set_ylabel("Im ω / ω_p")
        ax.axhline(0, color=C["grid"], lw=1)
        self.l_tr = [ax.plot([], [], ".", ms=1.5, color=C["muted"])[0] for _ in range(4)]
        ax.text(0.02, 0.97, "точки — путь корней при k от 0 до 2", transform=ax.transAxes,
                va="top", fontsize=7, color=C["text2"])
        self.p_c = anim(ax.plot([], [], "o", ms=7, mfc=C["text2"], mec=C["surface"], mew=1.5)[0])
        self.p_cu = anim(ax.plot([], [], "o", ms=10, mfc=C["main"], mec=C["surface"], mew=2)[0])

        self.ax_t.set_facecolor(C["panel"])
        self.rt = MonoText(MONO, 8, C["text"], C["main"], C["panel"], f.dpi)
        self.s_txt = ""

        def sl_(rect, label, a, b, v, st):
            axs = f.add_axes(rect)
            style.style_widget_axes(axs)
            s = Slider(axs, label, a, b, valinit=v, valstep=st, color=C["main"],
                       track_color=C["grid"])
            s.label.set_color(C["text"]); s.valtext.set_color(C["text"])
            return s
        self.s_a = sl_([0.10, 0.06, 0.22, 0.025], "n_b/n_p", -4, 0, np.log10(alpha), 0.05)
        self.s_d = sl_([0.42, 0.06, 0.18, 0.025], "Δv/v_b", 0, 0.3, dvb, 0.01)
        self.s_k = sl_([0.70, 0.06, 0.15, 0.025], "k·v_b/ω_p", 0.05, 2.0, 1.0, 0.005)
        self.s_a.valtext.set_text(f"{alpha:.3g}")
        self.s_a.on_changed(self._on_param)
        self.s_d.on_changed(self._on_param)
        self.s_k.on_changed(self._on_k)
        self._sb = [SliderBlit(f, x, C["surface"]) for x in (self.s_a, self.s_d, self.s_k)]
        self._dirty = False
        f.canvas.mpl_connect("button_release_event", self._on_release)
        axb = f.add_axes([0.87, 0.045, 0.1, 0.045])
        self.b_sw = Button(axb, "▶ пройти по k", color=C["main"], hovercolor=C["grid"])
        self.b_sw.label.set_color(C["surface"])
        self.b_sw.on_clicked(self._toggle_sweep)

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
    def _species(self):
        return disp.beam_plasma_species(self.alpha, 1.0)

    def _recompute(self):
        a = self.alpha
        sp = self._species()
        k = np.linspace(0.005, 2.0, 700)
        r = disp.fluid_roots(k, sp)
        wr, g = disp.fluid_growth(k, sp)
        self.l_g.set_data(k, g)
        if self.dvb > 0:
            _, gk = disp.kinetic_growth_curve(k, disp.beam_plasma_species(a, 1.0, 0.0, self.dvb))
            self._kk, self._gk = k, np.maximum(gk, 0)
            self.l_gk.set_data(k, self._gk)
        else:
            self.l_gk.set_data([], [])
        self.l_gk.set_label("кинетика (тёплый пучок)" if self.dvb > 0 else "_нет")
        self.ax_g.legend(loc="upper right", fontsize=7.5)
        self.l_gh.set_ydata([disp.gamma_hint(a)] * 2)
        self.l_gw.set_ydata([disp.gamma_weak_beam(a)] * 2)
        self.ax_g.set_ylim(0, 1.15 * max(disp.gamma_hint(a), g.max()))
        rs = np.sort_complex(r)
        for i in range(4):
            self.l_w[i].set_data(k, rs[:, i].real)
        self.l_wu.set_data(k, np.where(g > 1e-9, wr, np.nan))
        self.l_b1.set_data(k, k + np.sqrt(a))
        self.l_b2.set_data(k, k - np.sqrt(a))
        # траектории корней на комплексной плоскости
        rr = np.sort_complex(r)
        for i in range(4):
            self.l_tr[i].set_data(rr[:, i].real, rr[:, i].imag)
        gmax = g.max()
        self.ax_c.set_xlim(-1.6, 2.6)
        self.ax_c.set_ylim(-1.3 * gmax - 0.02, 1.3 * gmax + 0.02)
        self.k0, self.g0, self.w0 = disp.most_unstable(sp)
        self.p_a.set_data([a], [self.g0])
        self._update_k()
        self.fig.canvas.draw_idle()

    def _update_k(self):
        a, k = self.alpha, self.kq
        sp = self._species()
        r = disp.fluid_roots(np.array([k]), sp)[0]
        iu = int(np.argmax(r.imag))
        g = max(r[iu].imag, 0.0)
        self.v_g.set_xdata([k, k])
        self.v_w.set_xdata([k, k])
        self.p_g.set_data([k], [g])
        self.p_c.set_data(r.real, r.imag)
        if g > 1e-9:
            self.p_cu.set_data([r[iu].real], [r[iu].imag])
        else:
            self.p_cu.set_data([], [])
        D = lambda w: 1 - 1 / w**2 - a / (w - k) ** 2
        L = [f"§α = {a:.4g},  k·v_b/ω_p = {k:.3f}",
             "§корни ω/ω_p уравнения 4-й степени:"]
        for w in sorted(r, key=lambda z: -z.imag):
            L.append(f" {w.real:+.4f} {'+' if w.imag >= 0 else '−'} {abs(w.imag):.4f}i"
                     f"   |D| = {abs(D(w)):.0e}")
        L.append("")
        L.append(f"§при этом k: γ = {g:.4f} ω_p")
        L.append(f"§максимум: k_max = {self.k0:.4f} ω_p/v_b")
        L.append(f" γ_max = {self.g0:.4f},  ω_r = {self.w0:.4f}")
        gh, gw = disp.gamma_hint(a), disp.gamma_weak_beam(a)
        L.append(f" подсказка   {gh:.4f} ({(gh / self.g0 - 1) * 100:+.0f}%)")
        L.append(f" (α/2)^⅓     {gw:.4f} ({(gw / self.g0 - 1) * 100:+.1f}%)")
        if self.dvb > 0:
            gk = float(np.interp(k, self._kk, self._gk))
            L.append(f"§кинетика (Δv/v_b = {self.dvb:.2f}):")
            L.append(f" γ = {gk:.4f}  (холодная {g:.4f})")
            L.append(f" гидродинамический режим,")
            L.append(f" если Δv/v_b < (α/2)^⅓ = {np.cbrt(a / 2):.3f}")
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
        self.alpha = float(10 ** self.s_a.val)
        self.s_a.valtext.set_text(f"{self.alpha:.3g}")
        self.dvb = float(self.s_d.val)
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
        from .blit import blit_axes
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
