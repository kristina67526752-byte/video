"""Главное окно: PIC-модель пучково-плазменной неустойчивости в реальном времени.

Как устроен кадр анимации (метод tick):
  1. sim.step(n)          — n шагов PIC-кода (n задаёт ползунок «скорость»);
  2. tracker.update()     — определение стадии, измерение γ, насыщения;
  3. _update_artists()    — новые данные для линий и строки текста;
  4. blit.update()        — восстановить фон, скопировать в пиксели фазовый
                            портрет и тексты (fastdraw), дорисовать линии.
"""
from __future__ import annotations

import math
import os
import textwrap
import time

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button, RadioButtons, CheckButtons

from .. import dispersion as disp
from .. import diagnostics as diag
from ..pic import PIC, PICParams
from . import style
from .style import C, MONO
from .blit import Blitter, Region, SliderBlit, blit_axes
from .fastdraw import MonoText, ParagraphText, paste, rgb255
from . import texts

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "results")


def _pct(x):
    return f"{x * 100:+.1f}%"


class MainWindow:
    def __init__(self, params: PICParams | None = None, theme="dark", maximize=True):
        style.use(theme)
        self.theme = theme
        self.params = params or PICParams()
        self.fig = plt.figure(figsize=(16, 9))
        try:
            self.fig.canvas.manager.set_window_title(
                "И11 · Пучково-плазменная неустойчивость · PIC-модель")
        except Exception:
            pass
        self.children = []
        self.running = True
        self.autopause = False
        self.show_sep = True
        self.explain_key = None          # какой график объясняется справа
        self.status_msg = ""
        self._dirty_params = False
        self._fps = 0.0
        self._sps = 0.0
        self._t_last = None
        self._frame = 0
        self._ms_phys = 0.0
        self._ms_draw = 0.0

        dpi = self.fig.dpi
        self.rt_status = MonoText(MONO, 8.5, C["text"], C["main"], C["surface"], dpi)
        self.rt_ph = MonoText(MONO, 9, C["text"], C["main"], C["surface"], dpi)
        self.rt_E = MonoText(MONO, 8, C["text"], C["main"], C["surface"], dpi)
        self.rt_num = MonoText(MONO, 7.5, C["text"], C["main"], C["panel"], dpi)
        self.rt_exp_h = ParagraphText(9, C["text"], C["panel"], dpi, weight="bold")
        self.rt_exp = ParagraphText(8, C["text2"], C["panel"], dpi)
        self.s_status = self.s_ph = self.s_E = self.s_num = ""
        self.s_exp_h = self.s_exp = ""

        self._build_axes()
        self._build_controls()
        # две области с разной частотой обновления: слева фазовый портрет (каждый
        # кадр), справа графики и таблица чисел (через кадр)
        left_axes = (self.ax_ph, self.ax_fv, self.ax_E)
        AL = [a for a in self._animated if a.axes in left_axes]
        AR = [a for a in self._animated if a.axes not in left_axes]
        self.blit = Blitter(self.fig, regions=[
            Region(self._bbox_left, AL, self._raw_left, period=1),
            Region(self._bbox_right, AR, self._raw_right, period=2)])
        self.reset()

        self.fig.canvas.mpl_connect("key_press_event", self._on_key)
        self.fig.canvas.mpl_connect("button_press_event", self._on_click)
        self.fig.canvas.mpl_connect("button_release_event", self._on_release)
        self.fig.canvas.mpl_connect("close_event", self._on_close)
        self.timer = self.fig.canvas.new_timer(interval=10)
        self.timer.add_callback(self.tick)
        self.timer.start()
        if maximize:
            style.maximize(self.fig)

    # ================================================================ разметка
    def _build_axes(self):
        f = self.fig
        A = []                                   # подвижные элементы (перерисовываются каждый кадр)
        self._animated = A

        def anim(artist):
            A.append(artist)
            return artist

        f.text(0.04, 0.976, "Пучково-плазменная неустойчивость (вариант И11)",
               fontsize=13, fontweight="bold", color=C["text"], va="center")
        self.txt_sub = f.text(0.04, 0.951, "", fontsize=8, color=C["text2"], va="center")

        # --- фазовый портрет + f(v) сбоку + E(x) снизу
        self.ax_ph = f.add_axes([0.04, 0.455, 0.44, 0.455])
        self.ax_fv = f.add_axes([0.485, 0.455, 0.06, 0.455], sharey=self.ax_ph)
        self.ax_E = f.add_axes([0.04, 0.285, 0.44, 0.12], sharex=self.ax_ph)
        ax = self.ax_ph
        ax.set_ylabel("скорость v, ед. v₀")
        ax.tick_params(labelbottom=False)
        ax.grid(False)
        ax.set_facecolor(C["surface"])
        self.ln_sep = anim(ax.plot([], [], color=C["text"], lw=1.0, alpha=0.9)[0])
        # легенда цветов — над осями, справа (под картинкой её бы закрыло)
        y = 0.918
        f.text(0.48, y, "— сепаратриса", color=C["text"], ha="right", va="bottom", fontsize=8)
        self.lg_b = f.text(0.418, y, "■ пучок", color=C["beam_glow"], ha="right", va="bottom",
                           fontsize=8.5, fontweight="bold")
        self.lg_p = f.text(0.368, y, "■ плазма", color=C["plasma_glow"], ha="right", va="bottom",
                           fontsize=8.5, fontweight="bold")

        ax = self.ax_fv
        ax.set_title("f пучка", loc="left")
        ax.set_xscale("log")
        ax.tick_params(labelleft=False)
        ax.set_xlabel("f_b(v)")
        self.ln_fv0, = ax.plot([], [], color=C["text2"], lw=1.0, ls="--")
        self.ln_fv = anim(ax.plot([], [], color=C["beam"], lw=1.6)[0])
        self.ln_plat = anim(ax.plot([], [], color=C["main"], lw=2.0)[0])

        ax = self.ax_E
        ax.set_xlabel("координата x, ед. v₀/ω_p")
        ax.set_ylim(-1.15, 1.15)
        ax.set_yticks([-1, 0, 1])
        self.ln_E = anim(ax.plot([], [], color=C["field"], lw=1.4)[0])
        self.ln_nb = anim(ax.plot([], [], color=C["beam"], lw=1.1, alpha=0.9)[0])
        f.text(0.48, 0.41, "— E(x)/max|E|", color=C["field"], ha="right", va="bottom", fontsize=8)
        self.lg_nb = f.text(0.405, 0.41, "— δn_b(x)/max|δn_b|", color=C["beam"], ha="right",
                            va="bottom", fontsize=8)

        # --- энергия и спектрограмма (общая ось времени)
        self.ax_W = f.add_axes([0.59, 0.70, 0.185, 0.21])
        self.ax_sg = f.add_axes([0.59, 0.455, 0.185, 0.19], sharex=self.ax_W)
        ax = self.ax_W
        ax.set_title("Энергия / K_b0 (лог. шкала)", loc="left")
        ax.set_yscale("log")
        ax.set_ylim(1e-8, 3.0)
        ax.tick_params(labelbottom=False)
        self.ln_WE = anim(ax.plot([], [], color=C["field"], lw=1.6, label="поле W_E")[0])
        self.ln_Wm = anim(ax.plot([], [], color=C["main"], lw=1.6, label="главная волна")[0])
        self.ln_Kb = anim(ax.plot([], [], color=C["beam"], lw=1.6, label="−ΔK пучка")[0])
        self.ln_Kp = anim(ax.plot([], [], color=C["plasma"], lw=1.6, label="+ΔK плазмы")[0])
        self.ln_th = anim(ax.plot([], [], color=C["text2"], lw=1.2, ls="--",
                                  label="теория ∝ exp(2γt)")[0])
        self.ln_trap = ax.axhline(1e-9, color=C["text2"], lw=1.0, ls=":")
        self.txt_trap = ax.text(0.01, 1e-9, "", fontsize=7, color=C["text2"],
                                transform=ax.get_yaxis_transform(), va="bottom")
        self.pt_sat = anim(ax.plot([], [], "o", ms=8, mfc=C["main"], mec=C["surface"], mew=2)[0])
        ax.legend(loc="lower right", ncol=2, fontsize=6.6, handlelength=1.3,
                  borderpad=0.3, labelspacing=0.2, columnspacing=0.7)

        ax = self.ax_sg
        ax.set_title("Спектрограмма lg|E_k|²", loc="left")
        ax.set_xlabel("время t, ед. 1/ω_p")
        ax.set_ylabel("k / k_max")
        ax.grid(False)
        # сама картинка спектрограммы копируется в пиксели (см. _raw), а этот
        # невидимый imshow нужен только для цветовой шкалы и подписей осей
        self._sg_cmap = style.seq_cmap()
        self.im_sg = ax.imshow(np.zeros((2, 2)), origin="lower", aspect="auto",
                               cmap=self._sg_cmap, vmin=-9, vmax=0.5, alpha=0.0)
        self._sg_lut = (self._sg_cmap(np.linspace(0, 1, 256))[:, :3] * 255).astype(np.uint8)

        # --- γ(k) и спектр (общая ось k)
        self.ax_gk = f.add_axes([0.805, 0.70, 0.185, 0.21])
        self.ax_sp = f.add_axes([0.805, 0.455, 0.185, 0.19], sharex=self.ax_gk)
        ax = self.ax_gk
        ax.set_title("Инкремент γ(k)", loc="left")
        ax.set_ylabel("γ, ед. ω_p")
        ax.tick_params(labelbottom=False)
        self.ln_gk_th, = ax.plot([], [], color=C["text2"], ls="--", lw=1.3, label="теория (точно)")
        self.pt_gk_box, = ax.plot([], [], "o", ms=5, mfc="none", mec=C["text2"], mew=1.0,
                                  label="моды ящика")
        self.pt_gk_meas = anim(ax.plot([], [], "o", ms=8, mfc=C["field"], mec=C["surface"],
                                       mew=2, label="измерено (PIC)")[0])

        ax = self.ax_sp
        ax.set_title("Спектр волн |E_k|² сейчас", loc="left")
        ax.set_xlabel("k / k_max")
        ax.set_yscale("log")
        ax.set_ylim(1e-9, 30)
        ax.set_ylabel("|E_k|² / E_захв²")
        self.ln_sp = anim(ax.plot([], [], color=C["field"], lw=2.2, solid_capstyle="round")[0])
        self.ln_sp_main = anim(ax.plot([], [], color=C["main"], lw=3.2,
                                       solid_capstyle="round")[0])
        ax.text(0.99, 0.95, "▮ главная волна", color=C["main"], transform=ax.transAxes,
                ha="right", va="top", fontsize=7.5)

        # --- панель чисел и пояснений (тексты рисуются fastdraw)
        ax = self.ax_info = f.add_axes([0.59, 0.012, 0.40, 0.375])
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
        ax.set_facecolor(C["panel"])
        ax.axvline(0.565, color=C["grid"], lw=1)

        self.panel_axes = {self.ax_ph: "phase", self.ax_fv: "fv", self.ax_E: "E",
                           self.ax_W: "energy", self.ax_sg: "spectrogram",
                           self.ax_gk: "gk", self.ax_sp: "spectrum"}

    def _build_controls(self):
        f = self.fig
        p = self.params

        def sl(rect, label, vmin, vmax, vinit, step):
            ax = f.add_axes(rect)
            style.style_widget_axes(ax)
            s = Slider(ax, label, vmin, vmax, valinit=vinit, valstep=step,
                       color=C["main"], track_color=C["grid"],
                       handle_style=dict(facecolor=C["text"], edgecolor=C["surface"], size=9))
            s.label.set_color(C["text"])
            s.label.set_fontsize(8.5)
            s.valtext.set_color(C["text"])
            s.valtext.set_fontsize(8.5)
            return s

        self.s_alpha = sl([0.085, 0.215, 0.165, 0.022], "n_b/n_p", -3.0, -1.0,
                          np.log10(p.alpha), 0.05)
        self.s_vb = sl([0.35, 0.215, 0.13, 0.022], "v_b/v₀", 0.5, 2.0, p.vb, 0.05)
        self.s_dv = sl([0.085, 0.178, 0.165, 0.022], "Δv/v_b", 0.0, 0.3, p.dvb, 0.01)
        self.s_speed = sl([0.35, 0.178, 0.13, 0.022], "скорость", 1, 30, 5, 1)
        self.s_alpha.valtext.set_text(f"{p.alpha:.3g}")
        self.s_speed.valtext.set_text("5 шаг/кадр")
        self.s_alpha.on_changed(self._on_alpha)
        self.s_vb.on_changed(lambda v: self._param_changed())
        self.s_dv.on_changed(lambda v: self._param_changed())
        self.s_speed.on_changed(lambda v: self.s_speed.valtext.set_text(f"{int(v)} шаг/кадр"))
        # ползунки перерисовывают только себя (иначе каждое движение = полная перерисовка)
        self._slider_blits = [SliderBlit(f, sl_, C["surface"])
                              for sl_ in (self.s_alpha, self.s_vb, self.s_dv, self.s_speed)]

        ax = f.add_axes([0.012, 0.085, 0.13, 0.07])
        style.style_widget_axes(ax)
        ax.set_title("Сценарий", fontsize=8, loc="left", color=C["text2"], pad=2)
        self.r_scen = RadioButtons(ax, ("пучок в плазме", "встречные пучки"),
                                   active=0 if p.scenario == "beam" else 1,
                                   activecolor=C["main"])
        for t in self.r_scen.labels:
            t.set_color(C["text"])
            t.set_fontsize(8.5)
        self.r_scen.on_clicked(lambda lab: self._param_changed(restart_now=True))

        ax = f.add_axes([0.155, 0.085, 0.16, 0.07])
        style.style_widget_axes(ax)
        ax.set_title("Показ", fontsize=8, loc="left", color=C["text2"], pad=2)
        self.c_opts = CheckButtons(ax, ("сепаратриса", "пауза на стадиях"),
                                   (self.show_sep, self.autopause))
        for t in self.c_opts.labels:
            t.set_color(C["text"])
            t.set_fontsize(8.5)
        self.c_opts.on_clicked(self._on_check)

        def bt(rect, label, cb, hl=False):
            ax = f.add_axes(rect)
            b = Button(ax, label, color=C["main"] if hl else C["panel"], hovercolor=C["grid"])
            b.label.set_color(C["surface"] if hl else C["text"])
            b.label.set_fontsize(8.5)
            if hl:
                b.label.set_fontweight("bold")
            for sp in ax.spines.values():
                sp.set_color(C["grid"])
            b.on_clicked(cb)
            return b

        self.b_play = bt([0.33, 0.115, 0.075, 0.038], "|| Пауза", self._on_play, hl=True)
        self.b_reset = bt([0.41, 0.115, 0.065, 0.038], "↺ Заново", lambda e: self.reset())
        self.b_back = bt([0.33, 0.07, 0.075, 0.038], "◀ Назад", lambda e: self.back())
        self.b_step = bt([0.41, 0.07, 0.065, 0.038], "Шаг ▶", lambda e: self.single_step())
        self.b_save = bt([0.48, 0.07, 0.065, 0.083], "Сохранить\nPNG", lambda e: self.save_png())
        y = 0.018
        self.b_theory = bt([0.012, y, 0.1, 0.04], "Теория γ(k)", lambda e: self.open_theory())
        self.b_sw = bt([0.117, y, 0.125, 0.04], "Одноволновая модель", lambda e: self.open_single())
        self.b_tab = bt([0.247, y, 0.125, 0.04], "Таблица насыщения", lambda e: self.open_table())
        self.b_form = bt([0.377, y, 0.095, 0.04], "Формулы", lambda e: self.open_formulas())
        self.b_help = bt([0.477, y, 0.068, 0.04], "Справка", lambda e: self.show_help())

    # ================================================================ параметры
    def _on_alpha(self, val):
        self.s_alpha.valtext.set_text(f"{10 ** val:.3g}")
        self._param_changed()

    def _param_changed(self, restart_now=False):
        self._dirty_params = True
        if restart_now:
            self.reset()

    def _on_release(self, event):
        if self._dirty_params:          # перезапуск, когда отпустили ползунок параметров
            self.reset()

    def _current_params(self):
        scen = "two_stream" if self.r_scen.value_selected == "встречные пучки" else "beam"
        return self.params.copy(scenario=scen,
                                alpha=float(round(10 ** self.s_alpha.val, 6)),
                                vb=float(self.s_vb.val), dvb=float(self.s_dv.val))

    def _on_check(self, label):
        st = self.c_opts.get_status()
        self.show_sep, self.autopause = st[0], st[1]
        self.ln_sep.set_visible(self.show_sep)
        self.blit.update(force=True)

    # ================================================================ запуск
    def reset(self):
        self._dirty_params = False
        p = self._current_params()
        self.params = p
        self.sim = s = PIC(p)
        self.tr = diag.StageTracker(s)
        self.modes_meas = None
        self.ql = None
        self.explain_key = None
        self._last_stage = 0
        self.th_anchor = None
        self.status_msg = ""

        # оценка времени насыщения → масштаб оси времени
        A0 = 2 * abs(s.Ek[s.m_main]) / p.ng
        t_sat = np.log(max(self.tr.A_trap / max(A0 / 3, 1e-14), 10.0)) / s.gamma_ref
        self.T_view = float(np.ceil(max(2.6 * t_sat, t_sat + 60) / 50) * 50)

        # --- фазовый портрет: пределы скоростей
        if p.scenario == "two_stream":
            self.vmin, self.vmax = -1.3 * p.vb, 1.3 * p.vb
        else:
            self.vmin, self.vmax = -0.6 * p.vb, (1.75 + 2 * p.dvb) * p.vb
        self.ax_ph.set_xlim(0, s.L)
        self.ax_ph.set_ylim(self.vmin, self.vmax)
        self._c_surf = style.hex2rgb(C["surface"]) * 255
        self._c_p = style.hex2rgb(C["plasma_glow"]) * 255 - self._c_surf
        self._c_b = style.hex2rgb(C["beam_glow"]) * 255 - self._c_surf
        self._xs = np.linspace(0, s.L, 400)
        self._lut_key = None

        # --- f(v)
        self.v_edges = np.linspace(self.vmin, self.vmax, 181)
        self.v_cent = 0.5 * (self.v_edges[1:] + self.v_edges[:-1])
        f0 = s.velocity_hist(1, self.v_edges) / s.dens[1]
        self.ln_fv0.set_data(np.maximum(f0, 1e-4), self.v_cent)
        self.ax_fv.set_xlim(1e-2, 2e2)

        # --- E(x)
        self._xdec = max(1, p.ng // 512)              # на экран хватает 512 точек
        xg = np.arange(p.ng)[::self._xdec] * s.dx
        self.ln_E.set_xdata(xg)
        self.ln_nb.set_xdata(xg)

        # --- энергия: уровень насыщения по теории захвата
        self.K0 = s.K0_beam
        self.ax_W.set_xlim(0, self.T_view)
        Wtrap = s.L * self.tr.A_trap ** 2 / 4 / self.K0
        self.ln_trap.set_ydata([Wtrap, Wtrap])
        self.txt_trap.set_y(Wtrap * 1.3)
        self.txt_trap.set_text("насыщение по теории захвата")

        # --- спектрограмма
        self.NT = 300
        self.sg = np.full((s.m_store, self.NT), -12.0)
        self.sg_col = 0
        M = p.n_waves
        self.im_sg.set_extent([0, self.T_view, 0.5 / M, (s.m_store + 0.5) / M])
        self.ax_sg.set_ylim(0, min(3.0, (s.m_store + 0.5) / M))

        # --- γ(k): теория
        kk = np.linspace(1e-3, 2.6, 500) * s.k_max
        if p.dvb > 0:
            _, g = disp.kinetic_growth_curve(kk, s.species)
            g = np.maximum(g, 0)
            self.ln_gk_th.set_label("теория (кинетика)")
        else:
            cold = [(w, u, 0.0) for (w, u, _) in s.species]
            _, g = disp.fluid_growth(kk, cold)
            self.ln_gk_th.set_label("теория (точно)")
        self.ln_gk_th.set_data(kk / s.k_max, g)
        km = s.k_modes[1:s.m_store + 1] / s.k_max
        self.pt_gk_box.set_data(km, s.gamma_modes_th)
        self.ax_gk.set_xlim(0, 2.6)
        self.ax_gk.set_ylim(0, 1.2 * max(g.max(), s.gamma_ref, 1e-3))
        self.ax_gk.legend(loc="upper right", fontsize=6.6, borderpad=0.3, labelspacing=0.2)
        self.pt_gk_meas.set_data([], [])

        # подписи сортов частиц зависят от сценария
        two = p.scenario == "two_stream"
        self.lg_b.set_text("■ поток 2 (→)" if two else "■ пучок")
        self.lg_p.set_text("■ поток 1 (←)" if two else "■ плазма")
        self.lg_nb.set_text("— δn потока 2 / max" if two else "— δn_b(x)/max|δn_b|")
        self.ax_fv.set_title("f потока 2" if two else "f пучка", loc="left")
        self.ln_Kb.set_label("−ΔK потока 2" if two else "−ΔK пучка")
        self.ln_Kp.set_label("+ΔK потока 1" if two else "+ΔK плазмы")
        self.ax_W.legend(loc="lower right", ncol=2, fontsize=6.6, handlelength=1.3,
                         borderpad=0.3, labelspacing=0.2, columnspacing=0.7)
        scen = "пучок в плазме" if p.scenario == "beam" else "встречные пучки ±v_b/2"
        self.txt_sub.set_text(
            f"1D PIC: {s.N:,} + {s.N:,} макрочастиц · сетка {p.ng} узлов · Δt = {p.dt}/ω_p · "
            f"ящик L = {s.L:.1f} v₀/ω_p = {p.n_waves} длин волны · {scen} · "
            f"теория: {s.theory_kind}".replace(",", " "))
        self.ln_sep.set_visible(self.show_sep)
        self._update_artists(force=True)
        self.fig.canvas.draw_idle()

    # ================================================================ кадр
    def tick(self):
        if not plt.fignum_exists(self.fig.number):     # окно закрыто
            self.timer.stop()
            return
        if self._dirty_params:
            return
        now = time.perf_counter()
        changed = False
        if self.running:
            n = int(self.s_speed.val)
            self.sim.step(n)
            st = self.tr.update()
            t1 = time.perf_counter()
            self._ms_phys = 0.9 * self._ms_phys + 0.1 * (t1 - now) * 1e3
            changed = True
            if st != self._last_stage:
                self._last_stage = st
                self.explain_key = None
                if self.autopause:
                    self._pause("пауза: новая стадия (пробел — дальше)")
            if self.sim.t > self.T_view:          # ось времени кончилась — расширяем
                self._extend_time()
            if self._t_last is not None:
                fr = now - self._t_last
                self._fps = 0.9 * self._fps + 0.1 / max(fr, 1e-3)
                self._sps = 0.9 * self._sps + 0.1 * n / max(fr, 1e-3)
            self._t_last = now
        else:
            self._t_last = None
        if changed or self._frame % 10 == 0:
            t2 = time.perf_counter()
            self._update_artists(right=(self.blit.frame + 1) % 2 == 0 or not self.running)
            self.blit.update(force=not self.running)
            self._ms_draw = 0.9 * self._ms_draw + 0.1 * (time.perf_counter() - t2) * 1e3
        self._frame += 1

    def _extend_time(self):
        self.T_view *= 1.5
        self.ax_W.set_xlim(0, self.T_view)
        self.sg = np.full((self.sim.m_store, self.NT), -12.0)
        self.sg_col = 0
        M = self.params.n_waves
        self.im_sg.set_extent([0, self.T_view, 0.5 / M, (self.sim.m_store + 0.5) / M])
        self.fig.canvas.draw_idle()

    # ================================================================ пиксели
    def _phase_image(self, w, h):
        """Фазовый портрет в разрешении экрана: пиксель = клетка гистограммы.
        Яркость ∝ √(число частиц в пикселе), цвет: синий — плазма, оранжевый — пучок.
        Цвет пикселя берётся из готовой таблицы LUT[n_плазмы, n_пучка] — так
        картинка 700×400 собирается за ~2 мс."""
        s = self.sim
        x0, x1 = self.ax_ph.get_xlim()
        v0, v1 = self.ax_ph.get_ylim()
        hp, hb = s.phase_hist(w, h, v0, v1, x0, x1)
        # «насыщение» яркости: относительная плотность 40 (плазма) и 10 (пучок),
        # где 1 = частицы равномерно размазаны по всему окну
        unit = (w * h) / s.N
        key = (w, h)
        if getattr(self, "_lut_key", None) != key:
            cp = max(1, int(math.ceil(40.0 / unit)))
            cb = max(1, int(math.ceil(10.0 / unit)))
            ip = np.sqrt(np.minimum(np.arange(cp + 1) * unit / 40.0, 1.0))
            ib = np.sqrt(np.minimum(np.arange(cb + 1) * unit / 10.0, 1.0))
            lut = (self._c_surf + ip[:, None, None] * self._c_p
                   + ib[None, :, None] * self._c_b)
            self._lut = np.clip(lut, 0, 255).astype(np.uint8).reshape(-1, 3)
            self._lut_caps = (cp, cb)
            self._lut_key = key
        cp, cb = self._lut_caps
        idx = np.minimum(hp, cp)
        idx *= cb + 1
        idx += np.minimum(hb, cb)
        return self._lut[idx]

    def _sg_image(self, w, h):
        """Спектрограмма в разрешении экрана (ось t — [0, T_view], ось k — пределы осей)."""
        t0, t1 = self.ax_sg.get_xlim()
        y0, y1 = self.ax_sg.get_ylim()
        M = self.params.n_waves
        tc = t0 + (np.arange(w) + 0.5) * (t1 - t0) / w
        col = np.floor(tc / self.T_view * self.NT).astype(np.int64)
        yc = y1 - (np.arange(h) + 0.5) * (y1 - y0) / h          # сверху вниз
        row = np.rint(yc * M).astype(np.int64) - 1               # k/k_max = m/M
        okc = (col >= 0) & (col < self.NT)
        okr = (row >= 0) & (row < self.sim.m_store)
        v = (self.sg - (-9.0)) / 9.5
        idx = np.clip((v * 255).astype(np.int64), 0, 255)
        img = self._sg_lut[idx[np.clip(row, 0, self.sim.m_store - 1)][:, np.clip(col, 0, self.NT - 1)]]
        img[~okr, :] = self._sg_lut[0]
        img[:, ~okc] = self._sg_lut[0]
        # вертикальная линия «сейчас»
        jn = int((self.sim.t - t0) / (t1 - t0) * w)
        if 0 <= jn < w:
            img[:, jn] = (np.array(rgb255(C["text2"]))).astype(np.uint8)
        return img

    def _bbox_left(self):
        W, H = self.fig.bbox.width, self.fig.bbox.height
        return 0, 0.265 * H, 0.565 * W, 0.945 * H

    def _bbox_right(self):
        W, H = self.fig.bbox.width, self.fig.bbox.height
        return 0.565 * W, 0, W, H

    def _set_dpi(self):
        dpi = self.fig.dpi
        for rt in (self.rt_status, self.rt_ph, self.rt_E, self.rt_num):
            rt.set_dpi(dpi)
        return dpi

    def _raw_left(self, buf):
        H = buf.shape[0]
        self._set_dpi()
        # фазовый портрет внутри осей
        bb = self.ax_ph.bbox
        x0, x1 = int(math.ceil(bb.x0)) + 1, int(math.floor(bb.x1)) - 1
        yt, yb = H - int(math.floor(bb.y1)) + 1, H - int(math.ceil(bb.y0)) - 1
        if x1 - x0 > 4 and yb - yt > 4:
            paste(buf, self._phase_image(x1 - x0, yb - yt), x0, yt)
        # заголовок фазового портрета
        im = self.rt_ph.render(self.s_ph)
        paste(buf, im, bb.x0, H - bb.y1 - im.shape[0] - 3)
        # подпись поля
        bE = self.ax_E.bbox
        im = self.rt_E.render(self.s_E)
        paste(buf, im, bE.x0, H - bE.y1 - im.shape[0] - 2)

    def _raw_right(self, buf):
        H, W = buf.shape[:2]
        dpi = self._set_dpi()
        # спектрограмма: каждый пиксель берёт ближайшую клетку массива sg
        bs = self.ax_sg.bbox
        sx0, sx1 = int(math.ceil(bs.x0)) + 1, int(math.floor(bs.x1)) - 1
        syt, syb = H - int(math.floor(bs.y1)) + 1, H - int(math.ceil(bs.y0)) - 1
        if sx1 - sx0 > 4 and syb - syt > 4:
            paste(buf, self._sg_image(sx1 - sx0, syb - syt), sx0, syt)
        # строка состояния (справа вверху)
        im = self.rt_status.render(self.s_status)
        x = 0.59 * W                                  # в пределах правой области
        paste(buf, im[:, :int(0.99 * W - x)], x, 0.024 * H - im.shape[0] / 2)
        # панель чисел и пояснений
        bi = self.ax_info.bbox
        pad = int(0.006 * W)
        im = self.rt_num.render(self.s_num, max_rows=int((bi.height - 2 * pad) / self.rt_num.atlas.ch))
        paste(buf, im[:, :int(0.565 * bi.width) - 2 * pad], bi.x0 + pad, H - bi.y1 + pad)
        xe = bi.x0 + 0.565 * bi.width + pad
        we = bi.x1 - xe - pad
        hh = 9 * dpi / 72 * 1.45 * (self.s_exp_h.count("\n") + 1) + 4
        paste(buf, self.rt_exp_h.render(self.s_exp_h, we, hh, dpi), xe, H - bi.y1 + pad)
        paste(buf, self.rt_exp.render(self.s_exp, we, bi.height - 2 * pad - hh, dpi),
              xe, H - bi.y1 + pad + hh)

    # ================================================================ данные кадра
    def _update_artists(self, force=False, right=True):
        """Новые данные для всех подвижных элементов. right=False — пропустить
        правую половину окна (она в этом кадре не перерисовывается)."""
        s, p, tr = self.sim, self.params, self.tr
        n = s.h_n
        m = s.m_main
        Ek_m = s.Ek[m] / p.ng
        A = 2 * abs(Ek_m)                      # амплитуда главной волны
        km = s.k_modes[m]
        if self.show_sep:
            vph = s.omega_ref / km
            S = 2 * (A / km) * (1 - np.sin(km * self._xs + np.angle(Ek_m)))
            r = np.sqrt(np.maximum(S, 0))
            self.ln_sep.set_data(np.concatenate([self._xs, [np.nan], self._xs]),
                                 np.concatenate([vph + r, [np.nan], vph - r]))
        stage = tr.stage
        self.s_ph = f"t = {s.t:6.1f}/ω_p   стадия {stage + 1}/4"

        # --- f(v)
        fb = s.velocity_hist(1, self.v_edges) / s.dens[1]
        self.ln_fv.set_data(np.maximum(fb, 1e-4), self.v_cent)
        if stage == 3 and (self.ql is None or self._frame % 15 == 0 or force):
            self.ql = diag.ql_prediction(s.v[s.sl[1]], s.dens[1], s.L, s.K0_beam, p.vb)
        if stage == 3 and self.ql is not None:
            hq = 1.0 / max(self.ql["v2"] - self.ql["v1"], 1e-3)
            self.ln_plat.set_data([hq, hq], [self.ql["v1"], self.ql["v2"]])
        else:
            self.ln_plat.set_data([], [])

        # --- E(x) и δn_b(x)
        Emax = np.abs(s.E).max()
        self.ln_E.set_ydata(s.E[::self._xdec] / max(Emax, 1e-30))
        dnb = s.ne_s[1][::self._xdec] - s.dens[1]
        self.ln_nb.set_ydata(dnb / max(np.abs(dnb).max(), 1e-30))
        self.s_E = f"Поле: max|E| = {Emax:.2e}   главная волна E₀ = 2|E_k| = {A:.2e}"

        if not (right or force):
            return
        # --- энергия
        if n > 1:
            st = max(1, n // 700)
            t = s.h_t[:n:st]
            K0 = self.K0
            pos = lambda y: np.where(y > 0, y, np.nan)   # на лог. шкале ≤ 0 не рисуем
            self.ln_WE.set_data(t, pos(s.h_WE[:n:st] / K0))
            Wm = s.L * (2 * np.abs(s.h_Ek[:n:st, m - 1])) ** 2 / 4 / K0
            self.ln_Wm.set_data(t, pos(Wm))
            self.ln_Kb.set_data(t, pos((s.h_K[0, 1] - s.h_K[:n:st, 1]) / K0))
            self.ln_Kp.set_data(t, pos((s.h_K[:n:st, 0] - s.h_K[0, 0]) / K0))
            # теоретическая прямая: проходит через энергию главной волны в t1 = 4/γ
            t1 = 4.0 / s.gamma_ref
            if self.th_anchor is None and s.t > t1:
                j = int(round(t1 / p.dt))
                self.th_anchor = (s.h_t[j], s.L * (2 * abs(s.h_Ek[j, m - 1])) ** 2 / 4 / K0)
            if self.th_anchor is not None:
                ta, Wa = self.th_anchor
                tt = np.array([ta - 2 / s.gamma_ref, self.T_view])
                self.ln_th.set_data(tt, Wa * np.exp(2 * s.gamma_ref * (tt - ta)))
            else:
                self.ln_th.set_data([], [])
            if tr.sat is not None:
                self.pt_sat.set_data([tr.sat["t"]], [s.L * tr.sat["A"] ** 2 / 4 / K0])
            else:
                self.pt_sat.set_data([], [])
            # --- спектрограмма: дописываем новые столбцы
            col_dt = self.T_view / self.NT
            while self.sg_col < self.NT and (self.sg_col + 0.5) * col_dt <= s.t:
                j = min(int(round((self.sg_col + 0.5) * col_dt / p.dt)), n - 1)
                a2 = (2 * np.abs(s.h_Ek[j])) ** 2 / tr.A_trap ** 2
                self.sg[:, self.sg_col] = np.log10(np.maximum(a2, 1e-12))
                self.sg_col += 1
        else:
            for ln in (self.ln_WE, self.ln_Wm, self.ln_Kb, self.ln_Kp, self.ln_th, self.pt_sat):
                ln.set_data([], [])

        # --- γ(k): измеренные точки (когда закончилась линейная стадия)
        if stage >= 2 and self.modes_meas is None:
            self.modes_meas = diag.measure_modes(s, min_frac=0.6)
        if self.modes_meas:
            self.pt_gk_meas.set_data([d["k"] / s.k_max for d in self.modes_meas],
                                     [d["g"] for d in self.modes_meas])
        else:
            self.pt_gk_meas.set_data([], [])

        # --- спектр сейчас (вертикальные «палочки»)
        amp2 = (s.mode_amplitudes()[:s.m_store]) ** 2 / tr.A_trap ** 2
        kk = s.k_modes[1:s.m_store + 1] / s.k_max
        base = 1e-12
        xs = np.repeat(kk, 3)
        ys = np.empty_like(xs)
        ys[0::3] = base
        ys[1::3] = np.maximum(amp2, base)
        ys[2::3] = np.nan
        xs[2::3] = np.nan
        self.ln_sp.set_data(xs, ys)
        self.ln_sp_main.set_data([kk[m - 1], kk[m - 1]], [base, max(amp2[m - 1], base)])

        # --- тексты
        self.s_num = self._numbers_text(A)
        # абзац пояснения рисуется matplotlib'ом (это ~30 мс), поэтому обновляем
        # его не чаще двух раз в секунду или сразу при смене стадии/графика
        now = time.perf_counter()
        key = (self.explain_key, stage, self.params.scenario)
        if force or key != getattr(self, "_exp_key", None) or now > getattr(self, "_exp_next", 0):
            self.s_exp_h, self.s_exp = self._explanation()
            self._exp_key = key
            self._exp_next = now + 0.5
        run = "▶ идёт" if self.running else "|| пауза"
        msg = f"  · {self.status_msg}" if self.status_msg else ""
        self.s_status = (f"{run}  шаг {s.step_count}  {self._fps:3.0f} кадр/с  "
                         f"{self._sps:4.0f} шаг/с  (счёт {self._ms_phys:.0f} мс, "
                         f"рисование {self._ms_draw:.0f} мс){msg}")

    # ---------------------------------------------------------------- тексты
    def _numbers_text(self, A):
        s, p, tr = self.sim, self.params, self.tr
        g = s.gamma_ref
        L = []
        if p.scenario == "beam":
            a = p.alpha
            L.append(f"§ПАРАМЕТРЫ α=n_b/n_p={a:.4g} v_b={p.vb:.2f} Δv/v_b={p.dvb:.2f}")
            L.append("§ТЕОРИЯ  1 − 1/ω² − α/(ω − k·v_b)² = 0")
            L.append(f" k_max = {s.k_max:.4f} ω_p/v₀  (k·v_b/ω_p = {s.k_max * p.vb:.3f})")
            L.append(f" γ_max = {s.gamma_max:.4f} ω_p  ω_r = {s.omega_r:.4f} ω_p")
            gh, gw = disp.gamma_hint(a), disp.gamma_weak_beam(a)
            L.append(f" подсказка (√3/2)·α^⅓      {gh:.4f} {_pct(gh / s.gamma_max - 1)}")
            L.append(f" слабый пучок (√3/2)(α/2)^⅓ {gw:.4f} {_pct(gw / s.gamma_max - 1)}")
            if p.dvb > 0:
                L.append(f" тёплый пучок (кинетика): γ = {g:.4f}, мода {s.m_main}")
        else:
            L.append(f"§ПАРАМЕТРЫ потоки ±{p.vb / 2:.2f}·v₀, Δv/v_b = {p.dvb:.2f}")
            L.append("§ТЕОРИЯ  1 − 1/(ω−ku)² − 1/(ω+ku)² = 0, u=v_b/2")
            L.append(f" k_max = {s.k_max:.4f}   γ_max = {s.gamma_max:.4f} ω_p1")
            L.append(" γ_max = ω_p1/2 = ω_p,полн/(2√2);  ω_r = 0")
        L.append(f"§СЧЁТ  t = {s.t:.1f}/ω_p, главная мода m = {s.m_main}")
        if tr.gamma_meas is not None:
            fz = "" if tr.gamma_frozen else " …"
            L.append(f" γ_изм = d(ln E₀)/dt = {tr.gamma_meas:.4f} {_pct(tr.gamma_meas / g - 1)}{fz}")
        else:
            L.append(" γ_изм: ждём конца затравки (t > 4/γ)")
        kk = s.k_modes[s.m_main]
        wB = np.sqrt(kk * A)
        L.append(f" E₀ = 2|E_k| = {A:.3e}  ω_B = √(kE₀) = {wB:.3f}")
        L.append(f" ω_B/γ = {wB / g:.2f}   (захват при ω_B/γ ≈ 1.77)")
        if tr.sat is not None:
            Es = tr.sat["A"]
            L.append(f"§НАСЫЩЕНИЕ  t = {tr.sat['t']:.1f}/ω_p")
            L.append(f" E_sat = {Es:.4f}  ↔ теория 3.12γ²/k = {tr.A_trap:.4f}")
            L.append(f" ω_B/γ = {np.sqrt(kk * Es) / g:.2f}  W_E/K_b0 = "
                     f"{tr.sat['WE'] / self.K0 * 100:.1f}%")
            if tr.bounce is not None and p.scenario == "beam":
                L.append(f" период колебаний {tr.bounce:.1f} ↔ 2π/ω_B = "
                         f"{2 * np.pi / np.sqrt(kk * Es):.1f}")
        else:
            L.append(f" теория захвата: E_sat ≈ 3.12γ²/k = {tr.A_trap:.4f}")
        n = s.h_n
        if n > 0:
            K0 = self.K0
            WE = s.h_WE[n - 1]
            dKb = s.h_K[n - 1, 1] - s.h_K[0, 1]
            dKp = s.h_K[n - 1, 0] - s.h_K[0, 0]
            err = (WE - s.h_WE[0] + dKb + dKp) / K0
            L.append("§ЭНЕРГИЯ (доли K_b0 = ½·n_b·L·v_b²)")
            L.append(f" поле {WE / K0 * 100:4.1f}%  пучок {dKb / K0 * 100:+5.1f}%  "
                     f"плазма {dKp / K0 * 100:+5.1f}%")
            L.append(f" невязка ΔW_E + ΔK_b + ΔK_p = {err * 100:+.3f}%")
        if tr.stage == 3 and self.ql is not None and p.scenario == "beam":
            q = self.ql
            WEavg = s.h_WE[max(0, n - int(20 / p.dt)):n].mean()
            L.append(f"§КВАЗИЛИНЕЙНО: плато [{q['v1']:.2f}, {q['v2']:.2f}]·v₀")
            L.append(f" W_E=(K_b0−K_плато)/2 = {q['WE_ql'] / self.K0 * 100:.1f}% "
                     f"↔ счёт {WEavg / self.K0 * 100:.1f}%")
        return "\n".join(L)

    def _explanation(self):
        bi = self.ax_info.bbox
        width_px = 0.435 * bi.width - 0.012 * self.fig.bbox.width
        chars = max(30, int(width_px / (8 * self.fig.dpi / 72 * 0.56)))
        wrap = lambda t: "\n".join(textwrap.fill(par, chars) for par in t.split("\n"))
        hwrap = lambda t: textwrap.fill(t, int(chars * 0.8))
        if self.explain_key is not None:
            head, body = texts.PANELS[self.explain_key]
            body += "\n\n(Пробел — продолжить; нажмите на другой график, чтобы прочитать о нём.)"
            return hwrap(head), wrap(body)
        s, p, tr = self.sim, self.params, self.tr
        stages = texts.STAGES_BEAM if p.scenario == "beam" else texts.STAGES_TWO
        head, body = stages[tr.stage]
        km = s.k_modes[s.m_main]
        A = 2 * abs(s.Ek[s.m_main]) / p.ng
        sat = tr.sat or {}
        Tb = "≈ 2π/ω_B"
        if tr.bounce is not None and sat:
            Tb = f"{tr.bounce:.1f}/ω_p (2π/ω_B = {2 * np.pi / np.sqrt(km * sat['A']):.1f})"
        gm = f"{tr.gamma_meas:.4f}" if tr.gamma_meas is not None else "(ещё измеряется)"
        body = body.format(g=s.gamma_ref, t1=4 / s.gamma_ref, vb=p.vb,
                           vph=s.omega_ref / km, gm=gm, wB=np.sqrt(km * A),
                           Es=sat.get("A", 0), ts=sat.get("t", 0), Et=tr.A_trap, Tb=Tb)
        return hwrap(head), wrap(body) + "\n\n" + wrap(texts.HELP_HINT)

    # ================================================================ действия
    def _set_play_label(self):
        self.b_play.label.set_text("|| Пауза" if self.running else "▶ Пуск")
        blit_axes(self.fig, self.b_play.ax)

    def _on_play(self, event=None):
        self.running = not self.running
        self.status_msg = ""
        if self.running:
            self.explain_key = None
        self._set_play_label()
        self._update_artists(force=True)
        self.blit.update(force=True)

    def _pause(self, msg=""):
        self.running = False
        self.status_msg = msg
        self._set_play_label()

    def single_step(self):
        self._pause("шаг")
        self.sim.step(int(self.s_speed.val))
        self.tr.update()
        self._last_stage = self.tr.stage
        self._update_artists(force=True)
        self.blit.update(force=True)

    def back(self):
        s = self.sim
        s.rewind(1)
        self.tr.rewind_to(s.t)
        self._last_stage = self.tr.stage
        if self.tr.stage < 2:
            self.modes_meas = None
        if self.th_anchor is not None and s.t < self.th_anchor[0]:
            self.th_anchor = None
        col_dt = self.T_view / self.NT
        self.sg_col = min(self.sg_col, int(s.t / col_dt))
        self.sg[:, self.sg_col:] = -12.0
        self._pause(f"перемотано на t = {s.t:.1f}")
        self._update_artists(force=True)
        self.blit.update(force=True)

    def save_png(self):
        os.makedirs(RESULTS_DIR, exist_ok=True)
        name = time.strftime("снимок_%Y%m%d_%H%M%S.png")
        self.fig.canvas.draw()                    # полный кадр в буфере
        from PIL import Image  # pillow ставится вместе с matplotlib
        buf = np.asarray(self.fig.canvas.get_renderer().buffer_rgba())
        Image.fromarray(buf[..., :3].copy()).save(os.path.join(RESULTS_DIR, name))
        self.status_msg = f"сохранено: results/{name}"
        self._update_artists()
        self.blit.update(force=True)

    def show_help(self):
        self.explain_key = None
        self._pause("справка — в правой нижней панели")
        self._update_artists(force=True)
        self.blit.update(force=True)

    def open_theory(self):
        from .theory_window import TheoryWindow
        p = self.params
        self.children.append(TheoryWindow(alpha=p.alpha, vb=p.vb, dvb=p.dvb))

    def open_single(self):
        from .single_wave_window import SingleWaveWindow
        p = self.params
        self.children.append(SingleWaveWindow(alpha=p.alpha, dvb=p.dvb))

    def open_formulas(self):
        from .formulas_window import FormulasWindow
        self.children.append(FormulasWindow())

    def open_table(self):
        from .table_window import TableWindow
        self.children.append(TableWindow(base=self.params))

    # ================================================================ события
    def _on_key(self, event):
        k = event.key
        if k == " ":
            self._on_play()
        elif k == "right":
            self.single_step()
        elif k == "left":
            self.back()
        elif k == "r":
            self.reset()
        elif k == "h":
            self.open_formulas()

    def _on_click(self, event):
        tb = getattr(self.fig.canvas, "toolbar", None)
        if tb is not None and str(getattr(tb, "mode", "")) not in ("", "None"):
            return                                   # идёт масштабирование/сдвиг
        key = self.panel_axes.get(event.inaxes)
        if key is not None:
            self.explain_key = key
            self._update_artists()
            self.blit.update(force=True)

    def _on_close(self, event):
        try:
            self.timer.stop()
        except Exception:
            pass
