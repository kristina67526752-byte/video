"""Окно «Одна волна»: огибающая волны + частицы пучка (РК4), всё в СИ.

Фазовый портрет показан в системе отсчёта волны: по горизонтали фаза
частицы относительно волны Φ' (дно потенциальной ямы — в центре, Φ' = 0),
по вертикали скорость [м/с]. Белая линия — сепаратриса (точная, релятивистская).
"""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from ..single_wave import SingleWave
from ..diagnostics import C_TRAP, fit_exp, separatrix
from ..constants import E_CHARGE, M_E
from ..units import Scale, fmt, sci
from . import style
from .style import C, MONO
from .blit import Blitter, Region, SliderBlit, blit_axes, keep_drawn
from .fastdraw import MonoText, paste
from .widgets import ListSlider, plain_slider, button, fmt_velocity, ALPHAS, VELOCITIES


class SingleWaveWindow:
    def __init__(self, n_p=1.0e16, alpha=0.01, vb=1.0e7, dvb=0.0):
        style.use(style.current_theme())
        self.n_p, self.alpha, self.vb, self.dvf = n_p, alpha, vb, dvb / vb
        self.running = True
        f = self.fig = plt.figure(figsize=(14.4, 8.1))
        try:
            f.canvas.manager.set_window_title("И11 · Одноволновая модель (огибающая + частицы)")
        except Exception:
            pass
        f.text(0.05, 0.965, "Одноволновая модель: уравнение огибающей с нелинейным сдвигом "
               "частоты + точное движение электронов пучка", fontsize=13, fontweight="bold",
               color=C["text"])
        A = []

        def anim(a):
            A.append(a)
            return a

        self.ax_ph = f.add_axes([0.05, 0.42, 0.40, 0.48])
        self.ax_fv = f.add_axes([0.455, 0.42, 0.05, 0.48], sharey=self.ax_ph)
        self.ax_A = f.add_axes([0.56, 0.69, 0.41, 0.21])
        self.ax_w = f.add_axes([0.56, 0.42, 0.41, 0.21], sharex=self.ax_A)
        self.ax_t = f.add_axes([0.05, 0.05, 0.455, 0.30])
        self.ax_t.set_xticks([]); self.ax_t.set_yticks([]); self.ax_t.grid(False)
        self.ax_t.set_facecolor(C["panel"])

        ax = self.ax_ph
        ax.set_title("Фазовый портрет пучка в системе волны", loc="left")
        ax.set_xlabel("фаза относительно волны Φ', рад (дно ямы — 0)")
        ax.set_xlim(-np.pi, np.pi)
        ax.set_xticks([-np.pi, -np.pi / 2, 0, np.pi / 2, np.pi])
        ax.set_xticklabels(["−π", "−π/2", "0", "π/2", "π"])
        self.l_pts = anim(ax.plot([], [], ".", ms=2.4, color=C["beam_glow"])[0])
        self.l_sep = anim(ax.plot([], [], color=C["text"], lw=1.2)[0])
        self.l_vph = anim(ax.axhline(1, color=C["text2"], lw=0.8, ls=":"))
        ax.text(0.99, 0.98, "— сепаратриса   ··· фазовая скорость", transform=ax.transAxes,
                ha="right", va="top", fontsize=8, color=C["text2"])

        ax = self.ax_fv
        ax.set_title("f(v)", loc="left")
        ax.tick_params(labelleft=False)
        ax.set_xticks([])
        self.l_fv = anim(ax.plot([], [], color=C["beam"], lw=1.4)[0])

        ax = self.ax_A
        ax.set_title("Амплитуда волны |Ê|(t), В/м (лог. шкала)", loc="left")
        ax.set_yscale("log")
        ax.tick_params(labelbottom=False)
        self.l_A = anim(ax.plot([], [], color=C["field"], lw=1.8, label="|Ê| (счёт)")[0])
        self.l_At = anim(ax.plot([], [], color=C["text2"], lw=1.2, ls="--",
                                 label="теория ∝ exp(γt)")[0])
        self.l_trap = ax.axhline(1, color=C["text2"], lw=1, ls=":", label="3.12γ²mγ_b³/(ek)")
        self.p_max = anim(ax.plot([], [], "o", ms=8, mfc=C["main"], mec=C["surface"], mew=2)[0])
        ax.legend(loc="lower right", fontsize=7.5)

        ax = self.ax_w
        ax.set_title("Сдвиг частоты ω(t) − ω_p = −dθ/dt,  θ = arg Ê", loc="left")
        self.l_w = anim(ax.plot([], [], color=C["main"], lw=1.6, label="счёт")[0])
        self.l_wt = ax.axhline(0, color=C["text2"], ls="--", lw=1.2,
                               label="линейная теория −½(n_b/2n_p)^⅓ω_p/γ_b")
        ax.legend(loc="lower left", fontsize=7.5)

        self.s_a = ListSlider(f, [0.63, 0.29, 0.22, 0.024], "n_b/n_p", ALPHAS, alpha,
                              lambda v: f"{v:.3g}")
        self.s_v = ListSlider(f, [0.63, 0.25, 0.22, 0.024], "v_b", VELOCITIES, vb, fmt_velocity)
        self.s_d = plain_slider(f, [0.63, 0.21, 0.22, 0.024], "Δv_b/v_b", 0, 0.3, self.dvf, 0.01)
        self.s_sp = plain_slider(f, [0.63, 0.17, 0.22, 0.024], "скорость", 1, 40, 10, 1)
        self.s_sp.valtext.set_text("10 шаг/кадр")
        self.s_sp.on_changed(lambda v: self.s_sp.valtext.set_text(f"{int(v)} шаг/кадр"))
        for s_ in (self.s_a, self.s_v, self.s_d):
            s_.on_changed(self._on_param)
        self._sb = [SliderBlit(f, x, C["surface"]) for x in
                    (self.s_a.slider, self.s_v.slider, self.s_d, self.s_sp)]
        self._dirty = False
        f.canvas.mpl_connect("button_release_event", self._on_release)
        self.b_play = button(f, [0.63, 0.08, 0.12, 0.05], "|| Пауза", self._toggle, hl=True)
        self.b_reset = button(f, [0.76, 0.08, 0.12, 0.05], "↺ Заново", lambda e: self.reset())

        self.rt = MonoText(MONO, 8.0, C["text"], C["main"], C["panel"], f.dpi)
        self.s_txt = ""
        # области: графики сверху и панель текста слева внизу (ползунки не трогаем)
        W = lambda: f.bbox.width
        H = lambda: f.bbox.height
        self.blit = Blitter(f, regions=[
            Region(lambda: (0, 0.37 * H(), W(), H()), A, None),
            Region(lambda: (0, 0, 0.53 * W(), 0.37 * H()), [], self._raw)])
        self.reset()
        self.timer = f.canvas.new_timer(interval=15)
        self.timer.add_callback(self._tick)
        self.timer.start()
        f.canvas.mpl_connect("close_event", lambda e: self.timer.stop())
        f.show()

    # ------------------------------------------------------------------
    def reset(self):
        self._dirty = False
        self.sw = sw = SingleWave(n_p=self.n_p, alpha=self.alpha, vb=self.vb, n=2048,
                                  dvb=self.dvf * self.vb, dt_wp=0.05)
        g, k = sw.gamma_th, sw.k
        self.E_trap = C_TRAP * g * g * M_E * sw.gamma_b ** 3 / (E_CHARGE * k)      # В/м
        self.wB_sat = sw.omega_B(self.E_trap)
        E0 = abs(sw.E)
        T = (np.log(self.E_trap / E0) / g + 6 / g)
        if self.dvf > 0:
            T *= 2.5
        self.T = T
        self.sc_t = Scale(T, "с")
        self.sc_v = Scale(self.vb, "м/с")
        self.sc_w = Scale(abs(sw.domega_th) * 4, "с⁻¹")
        vph0 = (sw.wp + sw.domega_th) / k
        half = 2.6 * self.wB_sat / k + 2.5 * self.dvf * self.vb
        self.ax_ph.set_ylim(vph0 - half, max(vph0 + half, (1 + 3 * self.dvf + 0.05) * self.vb))
        self.ax_ph.set_ylabel(f"скорость v, {self.sc_v.label}")
        self.ax_ph.yaxis.set_major_formatter(self.sc_v.formatter("{:.3g}"))
        self.ax_A.set_xlim(0, T)
        self.ax_A.set_ylim(E0, 3 * self.E_trap)
        self.l_trap.set_ydata([self.E_trap] * 2)
        self.l_wt.set_ydata([sw.domega_th] * 2)
        dw = abs(sw.domega_th)
        self.ax_w.set_ylim(-4 * dw, 2.5 * dw)
        self.ax_w.set_xlabel(f"время t, {self.sc_t.label}")
        self.ax_w.xaxis.set_major_formatter(self.sc_t.formatter())
        self.ax_w.set_ylabel(f"δω, {self.sc_w.label}")
        self.ax_w.yaxis.set_major_formatter(self.sc_w.formatter())
        self.edges = np.linspace(*self.ax_ph.get_ylim(), 120)
        self.ax_fv.set_xlim(0, 12 / self.vb)
        self.gm = None
        self.amax = None
        self._update()
        self.fig.canvas.draw_idle()

    def _tick(self):
        if not plt.fignum_exists(self.fig.number):
            self.timer.stop()
            return
        if self._dirty or not self.running:
            keep_drawn(self.fig)
            return
        if self.sw.t < self.T * 1.6:
            self.sw.step(int(self.s_sp.val))
        self._update()
        self.blit.update()

    def _update(self):
        sw = self.sw
        t, A, w, P = sw.series()
        k, wp = sw.k, sw.wp
        st = max(1, len(t) // 2000)
        self.l_A.set_data(t[::st], np.maximum(A[::st], 1e-300))
        self.l_w.set_data(t[2::st], w[2::st] - wp)
        g = sw.gamma_th
        # линейная стадия: от 4/γ, пока амплитуда меньше 10% насыщения
        lin = (t > 4 / g) & (A < 0.1 * self.E_trap)
        if lin.sum() > 20:
            self.gm = fit_exp(t[lin], A[lin])[0]
            i0 = np.nonzero(lin)[0][0]
            tt = np.array([0, self.T])
            self.l_At.set_data(tt, A[i0] * np.exp(np.minimum(g * (tt - t[i0]), 600)))
        # первый максимум
        if self.amax is None and len(A) > 10:
            cm = np.maximum.accumulate(A)
            d = np.nonzero((A < 0.9 * cm) & (cm > 0.3 * self.E_trap))[0]
            if d.size:
                i = int(np.argmax(A[:d[0]]))
                self.amax = (t[i], A[i])
        if self.amax:
            self.p_max.set_data([self.amax[0]], [self.amax[1]])
        else:
            self.p_max.set_data([], [])
        # фазовый портрет в системе волны: Φ' = ψ + θ + π/2 (дно ямы в 0)
        v = sw.v
        ph = (sw.psi + np.angle(sw.E) + np.pi / 2 + np.pi) % (2 * np.pi) - np.pi
        self.l_pts.set_data(ph, v)
        # система волны: частоту усредняем по периоду баунс-колебаний 2π/ω_B,
        # иначе она «дрожит» вместе с захваченными частицами
        nwin = max(20, int(2 * np.pi / self.wB_sat / sw.dt))
        wn = np.mean(w[-nwin:]) if len(w) > nwin else wp + sw.domega_th
        vph = wn / k
        x = np.linspace(-np.pi, np.pi, 300)
        # E = |Ê|cos(Φ' − π/2 … ): яма с дном в Φ' = 0 ⇔ фаза (kx + φ) = Φ' − π/2
        vu, vd = separatrix(x / k, abs(sw.E), k, -np.pi / 2, vph)
        self.l_sep.set_data(np.concatenate([x, [np.nan], x]), np.concatenate([vu, [np.nan], vd]))
        self.l_vph.set_ydata([vph, vph])
        h, _ = np.histogram(v, bins=self.edges, density=True)
        c = 0.5 * (self.edges[1:] + self.edges[:-1])
        self.l_fv.set_data(np.minimum(h, 11.9 / self.vb), c)

        wB = sw.omega_B()
        L = ["§УРАВНЕНИЯ (СИ; резонанс k·v_b = ω_p)",
             " dÊ/dt = (e·n_b·ω_p/(ε₀k))·⟨exp(−iψ_j)⟩        — огибающая волны",
             " dψ_j/dt = k·v_j − ω_p,  dp_j/dt = −e·Re(Ê·exp(iψ_j)),  p = γmv",
             f"§ω_p = {sci(wp)} с⁻¹  k = {sci(k)} рад/м  γ_b = {sw.gamma_b:.4f}",
             f"§t = {fmt(sw.t, 'с')}   N = {sw.n} частиц, РК4, Δt = {fmt(sw.dt, 'с')}",
             f" |Ê| = {fmt(abs(sw.E), 'В/м')}  ω_B = √(ek|Ê|/mγ_b³) = {sci(wB)} с⁻¹  ω_B/γ = {wB / g:.2f}"]
        if self.gm is not None:
            L.append(f" γ_изм = {sci(self.gm)} с⁻¹  теория (√3/2)(n_b/2n_p)^⅓ω_p/γ_b = {sci(g)} "
                     f"({(self.gm / g - 1) * 100:+.1f}%)")
        else:
            L.append(f" γ теория (√3/2)(n_b/2n_p)^⅓ω_p/γ_b = {sci(g)} с⁻¹ — измерение после t = 4/γ")
        L.append(f" ω − ω_p сейчас = {sci(wn - wp)} с⁻¹   линейная теория = {sci(sw.domega_th)} с⁻¹")
        if self.amax:
            ts, Es = self.amax
            wBs = sw.omega_B(Es)
            L.append(f"§НАСЫЩЕНИЕ при t = {fmt(ts, 'с')}: |Ê|max = {fmt(Es, 'В/м')}")
            L.append(f" (ω_B/γ)² = {(wBs / g) ** 2:.3f}   ω_B/γ = {wBs / g:.3f}"
                     "   (при v_b << c одинаково для любого пучка!)")
        else:
            L.append(f"§ожидаемое насыщение: |Ê| ≈ 3.12·γ²mγ_b³/(ek) = {fmt(self.E_trap, 'В/м')}")
        L.append(f"§ПРОВЕРКА: P = n_b⟨p⟩ + ε₀k|Ê|²/(2ω_p) = const, ошибка "
                 f"{abs(P[-1] - P[0]) / abs(P[0]):.1e}")
        self.s_txt = "\n".join(L)

    def _raw(self, buf):
        H = buf.shape[0]
        bb = self.ax_t.bbox
        self.rt.set_dpi(self.fig.dpi)
        img = self.rt.render(self.s_txt)
        paste(buf, img[: int(bb.height) - 12, : int(bb.width) - 12], bb.x0 + 8, H - bb.y1 + 8)

    # ------------------------------------------------------------------
    def _on_param(self, _):
        self.alpha, self.vb, self.dvf = self.s_a.val, self.s_v.val, float(self.s_d.val)
        self._dirty = True

    def _on_release(self, e):
        if self._dirty:
            self.reset()

    def _toggle(self, _):
        self.running = not self.running
        self.b_play.label.set_text("|| Пауза" if self.running else "▶ Пуск")
        blit_axes(self.fig, self.b_play.ax)
