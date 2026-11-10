"""Окно «Солитоны»: уравнения огибающей с нелинейным сдвигом частоты
(уравнения Захарова) в реальном времени.  Все величины — в СИ.

Сценарии:
  * «волна от пучка → каверны»  — однородная ленгмюровская волна с амплитудой
    насыщения пучковой неустойчивости (волна накачки) модуляционно неустойчива:
    она разбивается на сгустки поля, запертые в ямах концентрации;
  * «точный солитон (проверка)» — аналитическое решение sech: форма и скорость
    должны сохраняться; измеренная ширина сравнивается с Δ = λ_D√(6τ/W_m);
  * «столкновение двух солитонов» — два солитона летят навстречу друг другу.
"""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import RadioButtons, CheckButtons

from .. import dispersion as disp
from .. import diagnostics as diag
from ..constants import EPS0, K_B, ION_LABEL, lorentz_gamma
from ..units import Scale, fmt, sci
from ..zakharov import Zakharov, modulational_growth
from . import style
from .style import C, MONO
from .blit import Blitter, Region, SliderBlit, blit_axes, keep_drawn
from .fastdraw import MonoText, paste
from .widgets import ListSlider, plain_slider, button

SCENARIOS = ("волна от пучка → каверны", "точный солитон (проверка)", "столкновение двух солитонов")
LEVELS = [0.002, 0.005, 0.01, 0.02, 0.03, 0.05, 0.07, 0.1, 0.15, 0.2, 0.3]
NT = 320            # столбцов в карте x–t


class SolitonWindow:
    def __init__(self, n_p=1.0e16, T_e=3.0e4, T_i=3.0e3, ion="H+", alpha=0.01, vb=1.0e7):
        style.use(style.current_theme())
        if ion == "none":
            ion = "H+"
        self.n_p, self.T_e, self.T_i, self.ion = n_p, T_e, T_i, ion
        self.alpha, self.vb = alpha, vb
        self.running = True
        self.scenario = SCENARIOS[0]
        # пучковая волна: самая неустойчивая мода и её амплитуда насыщения (теория захвата)
        sp = disp.beam_plasma_species(n_p, alpha, vb)
        self.k0, g, wr = disp.most_unstable(sp)
        self.L = 2 * np.pi * 8 / self.k0                       # те же 8 длин волны, что в PIC
        E_trap = diag.trapping_amplitude(g, self.k0, float(lorentz_gamma(wr / self.k0)))
        # средний по времени уровень поля после насыщения ≈ половина пикового
        self.W_beam = float(0.5 * EPS0 * E_trap ** 2 / (4 * n_p * K_B * T_e))
        f = self.fig = plt.figure(figsize=(14.4, 8.1))
        try:
            f.canvas.manager.set_window_title("И11 · Солитоны: уравнения огибающей (Захарова)")
        except Exception:
            pass
        f.text(0.04, 0.965, "Огибающая ленгмюровской волны с нелинейным сдвигом частоты: "
               "каверны и солитоны (уравнения Захарова)", fontsize=13, fontweight="bold",
               color=C["text"])
        A = []

        def anim(a):
            A.append(a)
            return a

        self.ax_p = f.add_axes([0.05, 0.60, 0.44, 0.30])
        self.ax_xt = f.add_axes([0.05, 0.27, 0.44, 0.27], sharex=self.ax_p)
        self.ax_h = f.add_axes([0.56, 0.60, 0.41, 0.30])
        self.ax_t = f.add_axes([0.56, 0.035, 0.41, 0.50])
        self.ax_t.set_xticks([]); self.ax_t.set_yticks([]); self.ax_t.grid(False)
        self.ax_t.set_facecolor(C["panel"])

        ax = self.ax_p
        ax.set_title("Уровень поля W(x) = ε₀|Ẽ|²/(4n k_BT_e) и концентрация δn/n", loc="left")
        ax.tick_params(labelbottom=False)
        ax.axhline(0, color=C["grid"], lw=0.8)
        self.l_W = anim(ax.plot([], [], color=C["field"], lw=1.8, label="поле W(x)")[0])
        self.l_n = anim(ax.plot([], [], color=C["ion"], lw=1.6, label="концентрация δn/n")[0])
        self.l_fit = anim(ax.plot([], [], color=C["text"], lw=1.0, ls="--",
                                  label="солитон sech² той же высоты (теория)")[0])
        ax.legend(loc="upper right", fontsize=7.5, ncol=3)

        ax = self.ax_xt
        ax.set_title("Карта x–t уровня поля W", loc="left")
        ax.grid(False)
        self.im = anim(ax.imshow(np.zeros((2, 2)), origin="lower", aspect="auto",
                                 cmap=style.seq_cmap(), interpolation="nearest"))

        ax = self.ax_h
        ax.set_title("Максимум поля, глубина ямы и число плазмонов", loc="left")
        ax.set_yscale("log")
        self.l_Wm = anim(ax.plot([], [], color=C["field"], lw=1.6, label="max W")[0])
        self.l_nm = anim(ax.plot([], [], color=C["ion"], lw=1.6, label="−min δn/n")[0])
        self.l_N = anim(ax.plot([], [], color=C["main"], lw=1.4, label="N(t)/N(0), N = ∫|Ẽ|²dx")[0])
        self.l_th = anim(ax.plot([], [], color=C["text2"], lw=1.2, ls="--",
                                 label="теория: рост ∝ exp(γ_мод t)")[0])
        ax.legend(loc="lower right", fontsize=7.5)

        # --- управление
        axr = f.add_axes([0.05, 0.055, 0.19, 0.125])
        style.style_widget_axes(axr)
        axr.set_title("Сценарий", fontsize=8, loc="left", color=C["text2"], pad=2)
        self.r = RadioButtons(axr, SCENARIOS, active=0, activecolor=C["main"])
        for t in self.r.labels:
            t.set_color(C["text"])
            t.set_fontsize(8.3)
        self.r.on_clicked(self._on_scenario)
        self.s_W = ListSlider(f, [0.30, 0.150, 0.12, 0.022], "уровень W₀", LEVELS,
                              min(max(self.W_beam, LEVELS[0]), LEVELS[-1]), lambda v: f"{v:g}")
        self.s_sp = plain_slider(f, [0.30, 0.112, 0.12, 0.022], "скорость", 5, 200, 40, 5)
        self.s_sp.valtext.set_text("40 шаг/кадр")
        self.s_sp.on_changed(lambda v: self.s_sp.valtext.set_text(f"{int(v)} шаг/кадр"))
        self.s_W.on_changed(lambda v: setattr(self, "_dirty", True))
        self._sb = [SliderBlit(f, x, C["surface"]) for x in (self.s_W.slider, self.s_sp)]
        axc = f.add_axes([0.255, 0.04, 0.115, 0.05])
        style.style_widget_axes(axc)
        self.c_damp = CheckButtons(axc, ("затухание Ландау",), (True,))
        for t in self.c_damp.labels:
            t.set_color(C["text"])
            t.set_fontsize(8.3)
        self.c_damp.on_clicked(lambda lab: self.reset())
        self._dirty = False
        f.canvas.mpl_connect("button_release_event", self._on_release)
        self.b_play = button(f, [0.38, 0.04, 0.055, 0.05], "|| Пауза", self._toggle, hl=True)
        self.b_reset = button(f, [0.44, 0.04, 0.05, 0.05], "↺ Заново", lambda e: self.reset())

        self.rt = MonoText(MONO, 7.9, C["text"], C["main"], C["panel"], f.dpi)
        self.s_txt = ""
        W_ = lambda: f.bbox.width
        H_ = lambda: f.bbox.height
        self.blit = Blitter(f, regions=[
            Region(lambda: (0, 0.2 * H_(), 0.525 * W_(), 0.945 * H_()),
                   [a for a in A if a.axes in (self.ax_p, self.ax_xt)], None),
            Region(lambda: (0.525 * W_(), 0, W_(), 0.945 * H_()),
                   [a for a in A if a.axes is self.ax_h], self._raw)])
        self.reset()
        self.timer = f.canvas.new_timer(interval=20)
        self.timer.add_callback(self._tick)
        self.timer.start()
        f.canvas.mpl_connect("close_event", lambda e: self.timer.stop())
        f.show()

    # ------------------------------------------------------------------
    def reset(self):
        self._dirty = False
        damping = self.c_damp.get_status()[0]
        z = self.z = Zakharov(n_p=self.n_p, T_e=self.T_e, T_i=self.T_i, ion=self.ion, L=self.L,
                              ng=1024, dt_wp=0.5, damping=damping)
        W0 = self.s_W.val
        self.W0 = W0
        self.g_mod = None
        if self.scenario == SCENARIOS[0]:
            z.set_pump(W0, self.k0, noise=1e-3)
            q = 2 * np.pi * np.arange(1, 200) / z.L
            gth = modulational_growth(q, W0, z.k0, self.n_p, self.T_e, self.T_i, self.ion)
            j = int(np.argmax(gth))
            self.g_mod, self.q_mod = float(gth[j]), float(q[j])
            self.T = 14.0 / max(self.g_mod, 1e-6 * z.wp)
        elif self.scenario == SCENARIOS[1]:
            z.add_soliton(W0, 0.3 * z.L, mach=0.3)
            self.T = 0.9 * z.L / (0.3 * z.cs)
        else:
            z.add_soliton(W0, 0.25 * z.L, mach=0.4)
            z.add_soliton(0.6 * W0, 0.75 * z.L, mach=-0.4, phase=0.7)
            self.T = 1.2 * z.L / (0.8 * z.cs)
        self.N0 = z.plasmons()
        self.sc_x = Scale(z.L, "м")
        self.sc_t = Scale(self.T, "с")
        self.xt = np.zeros((256, NT), dtype=np.float32)
        self.xt_col = 0
        self._xdec = z.ng // 256
        ax = self.ax_p
        ax.set_xlim(0, z.L)
        top = 3.2 * W0 if self.scenario == SCENARIOS[0] else 1.35 * W0
        ax.set_ylim(-0.75 * top, top)
        self.ax_xt.set_xlabel(f"координата x, {self.sc_x.label}")
        self.ax_xt.xaxis.set_major_formatter(self.sc_x.formatter())
        self.ax_xt.set_ylabel(f"время t, {self.sc_t.label}")
        self.ax_xt.yaxis.set_major_formatter(self.sc_t.formatter())
        self.im.set_extent([0, z.L, 0, self.T])
        self.im.set_clim(0, top)
        self.ax_xt.set_ylim(0, self.T)
        self.ax_h.set_xlim(0, self.T)
        self.ax_h.set_xlabel(f"время t, {self.sc_t.label}", labelpad=1)
        self.ax_h.xaxis.set_major_formatter(self.sc_t.formatter())
        self.ax_h.set_ylim(1e-4 * W0 if self.scenario == SCENARIOS[0] else 0.05 * W0, 8.0)
        self._update()
        self.fig.canvas.draw_idle()

    def _tick(self):
        if not plt.fignum_exists(self.fig.number):
            self.timer.stop()
            return
        if self._dirty or not self.running or self.z.t >= self.T:
            keep_drawn(self.fig)
            return
        self.z.step(int(self.s_sp.val))
        self._update()
        self.blit.update()

    def _update(self):
        z = self.z
        W, nu = z.W(), z.nu()
        self.l_W.set_data(z.x, W)
        self.l_n.set_data(z.x, nu)
        fs = z.fit_soliton()
        # sech²-профиль покоящегося солитона той же высоты (ширина — из теории)
        xi = (z.x - fs["x_m"] + 0.5 * z.L) % z.L - 0.5 * z.L
        prof = fs["W_m"] / np.cosh(xi / fs["delta_th"]) ** 2
        show = np.abs(xi) < 6 * fs["delta_th"]
        self.l_fit.set_data(z.x[show], prof[show])
        # карта x–t
        col = min(int(z.t / self.T * NT), NT - 1)
        while self.xt_col <= col:
            self.xt[:, self.xt_col] = W[::self._xdec]
            self.xt_col += 1
        self.im.set_data(self.xt.T)
        t = np.array(z.hist_t)
        self.l_Wm.set_data(t, z.hist_Wmax)
        self.l_nm.set_data(t, np.maximum(-np.array(z.hist_numin), 1e-12))
        self.l_N.set_data(t, np.array(z.hist_N) / self.N0)
        if self.g_mod:
            tt = np.array([0.0, self.T])
            self.l_th.set_data(tt, 1e-3 * np.exp(np.minimum(self.g_mod * tt, 50.0)))
        else:
            self.l_th.set_data([], [])

        L = ["§УРАВНЕНИЯ ОГИБАЮЩЕЙ, E = Re[Ẽ(x,t)·exp(−iω_p t)]",
             " i∂Ẽ/∂t + (3v_Te²/2ω_p)∂²Ẽ/∂x² = (ω_p/2)·(δn/n)·Ẽ",
             " ∂²(δn/n)/∂t² − c_s²∂²(δn/n)/∂x² = (ε₀/4n m_i)∂²|Ẽ|²/∂x²",
             " нелинейный сдвиг частоты: δω = (ω_p/2)·δn/n ≈ −ω_p·W/(2τ)",
             f"§ПЛАЗМА n = {sci(self.n_p, 2)} м⁻³, T_e = {sci(self.T_e, 2)} К, ионы {ION_LABEL[self.ion]}",
             f" λ_D = {fmt(z.lambda_D, 'м')}  ω_p = {sci(z.wp)} с⁻¹  c_s = {sci(z.cs)} м/с",
             f" ящик L = {fmt(z.L, 'м')} = {z.L / z.lambda_D:.0f} λ_D, {z.ng} узлов, "
             f"Δt = {fmt(z.dt, 'с')}",
             f" τ = 1 + 3T_i/T_e = {z.tau:.2f};  1 В/м ↔ W = {EPS0 / (4 * z.nT):.2e}",
             f"§СЧЁТ t = {fmt(z.t, 'с')} = {z.t * z.wp:.0f}/ω_p",
             f" max W = {fs['W_m']:.4f}  (max|Ẽ| = {fmt(fs['E_m'], 'В/м')})",
             f" min δn/n = {float(nu.min()) * 100:+.2f}%   N(t)/N(0) = {z.plasmons() / self.N0:.4f}"]
        if self.scenario == SCENARIOS[0]:
            L += [f"§НАКАЧКА W₀ = {self.W0:g}: E₀ = {fmt(float(z.field_from_W(self.W0)), 'В/м')}, "
                  f"k₀ = {sci(z.k0)} рад/м",
                  f" (пучок n_b/n_p = {self.alpha:g}, v_b = {sci(self.vb)} м/с даёт W ≈ {self.W_beam:.3f})",
                  f" модуляционная неустойчивость (теория):",
                  f"  γ_мод = {sci(self.g_mod)} с⁻¹ = {self.g_mod / z.wp:.4f}·ω_p, 1/γ_мод = "
                  f"{fmt(1 / self.g_mod, 'с')}",
                  f"  масштаб 2π/q = {fmt(2 * np.pi / self.q_mod, 'м')} = "
                  f"{2 * np.pi / self.q_mod / z.lambda_D:.0f} λ_D"]
        L += ["§САМЫЙ СИЛЬНЫЙ ПИК ↔ ТЕОРИЯ СОЛИТОНА",
              f" ширина Δ: счёт {fmt(fs['delta'], 'м')} = {fs['delta'] / z.lambda_D:.1f} λ_D",
              f"   теория λ_D√(6τ/W_m) = {fmt(fs['delta_th'], 'м')} = {fs['delta_th'] / z.lambda_D:.1f} λ_D",
              f" яма δn/n: счёт {fs['nu_min'] * 100:+.2f}%  теория −W_m/τ = {fs['nu_th'] * 100:+.2f}%"]
        if self.scenario != SCENARIOS[0]:
            L.append(" (для движущегося солитона Δ и яма содержат множитель 1 − V²/c_s²)")
        self.s_txt = "\n".join(L)

    def _raw(self, buf):
        H = buf.shape[0]
        bb = self.ax_t.bbox
        self.rt.set_dpi(self.fig.dpi)
        img = self.rt.render(self.s_txt)
        paste(buf, img[: int(bb.height) - 12, : int(bb.width) - 12], bb.x0 + 8, H - bb.y1 + 8)

    # ------------------------------------------------------------------
    def _on_scenario(self, label):
        self.scenario = label
        if label != SCENARIOS[0] and self.s_W.val > 0.1:
            self.s_W.set_val(0.05)          # солитон — решение при W ≪ 1
        self.reset()

    def _on_release(self, e):
        if self._dirty:
            self.reset()

    def _toggle(self, _):
        self.running = not self.running
        self.b_play.label.set_text("|| Пауза" if self.running else "▶ Пуск")
        blit_axes(self.fig, self.b_play.ax)
