"""Главное окно: PIC-модель пучково-плазменной неустойчивости в реальном времени.
Все величины на экране — в единицах СИ (с десятичными приставками).

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
import warnings

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button, RadioButtons, CheckButtons

from .. import dispersion as disp
from .. import diagnostics as diag
from ..constants import (C_LIGHT, K_B, EPS0, M_E, ION_LABEL, lorentz_gamma, thermal_velocity)
from ..pic import PIC, PICParams
from ..units import Scale, fmt, sci
from . import style
from .style import C, MONO
from .blit import Blitter, Region, SliderBlit, blit_axes
from .fastdraw import MonoText, ParagraphText, paste, rgb255
from .widgets import ListSlider, plain_slider, button, fmt_velocity, ALPHAS, VELOCITIES
from . import texts

# 14.4×8.1 дюйма = 1440×810 точек: окно помещается на экран 13-дюймового ноутбука
# (MacBook 1440×900); на большом экране его можно развернуть — всё масштабируется.
FIGSIZE = (14.4, 8.1)
SPLIT = 0.55         # доля панели внизу справа под таблицу чисел (остальное — пояснение)
XT_NX = 256          # точек по x в картах x–t (окно «Анализ»)

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "results")


def _pct(x):
    return f"{x * 100:+.1f}%"


class MainWindow:
    def __init__(self, params: PICParams | None = None, theme="dark", maximize=True,
                 ion="H+", T_i=None):
        style.use(theme)
        self.theme = theme
        self.params = params or PICParams()
        # сорт и температура ионов, которые включает галочка «ионы подвижны»
        self.ion_species = self.params.ion if self.params.ion != "none" else ion
        self.T_i = self.params.T_i if T_i is None else T_i
        self.fig = plt.figure(figsize=FIGSIZE)
        try:
            self.fig.canvas.manager.set_window_title(
                "И11 · Пучково-плазменная неустойчивость · PIC-модель в СИ")
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
        self.rt_num = MonoText(MONO, 7.8, C["text"], C["main"], C["panel"], dpi)
        self.rt_exp_h = ParagraphText(8.5, C["text"], C["panel"], dpi, weight="bold")
        self.rt_exp = ParagraphText(7.6, C["text2"], C["panel"], dpi)
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

        f.text(0.04, 0.976, "Пучково-плазменная неустойчивость (вариант И11) · все величины в СИ",
               fontsize=13, fontweight="bold", color=C["text"], va="center")
        self.txt_sub = f.text(0.04, 0.951, "", fontsize=7.6, color=C["text2"], va="center")

        # --- фазовый портрет + f(v) сбоку + E(x) снизу
        self.ax_ph = f.add_axes([0.04, 0.47, 0.44, 0.44])
        self.ax_fv = f.add_axes([0.485, 0.47, 0.06, 0.44], sharey=self.ax_ph)
        self.ax_E = f.add_axes([0.04, 0.305, 0.44, 0.115], sharex=self.ax_ph)
        ax = self.ax_ph
        ax.tick_params(labelbottom=False)
        ax.grid(False)
        ax.set_facecolor(C["surface"])
        self.ln_sep = anim(ax.plot([], [], color=C["text"], lw=1.0, alpha=0.9)[0])
        # подсветка каверны (всплеск поля в яме концентрации ионов)
        from matplotlib.patches import Rectangle
        self.band_ph = anim(ax.add_patch(Rectangle((0, 0), 0, 1, transform=ax.get_xaxis_transform(),
                                                   fc=C["ion"], ec="none", alpha=0.22)))
        # легенда цветов — над осями, справа (под картинкой её бы закрыло)
        y = 0.918
        f.text(0.474, y, "— сепаратриса", color=C["text"], ha="right", va="bottom", fontsize=8)
        self.lg_b = f.text(0.41, y, "■ пучок", color=C["beam_glow"], ha="right", va="bottom",
                           fontsize=8.5, fontweight="bold")
        self.lg_p = f.text(0.358, y, "■ плазма", color=C["plasma_glow"], ha="right", va="bottom",
                           fontsize=8.5, fontweight="bold")

        ax = self.ax_fv
        ax.set_title("f пучка", loc="left")
        ax.set_xscale("log")
        ax.tick_params(labelleft=False)
        ax.set_xlabel("f_b(v), с/м")
        self.ln_fv0, = ax.plot([], [], color=C["text2"], lw=1.0, ls="--")
        self.ln_fv = anim(ax.plot([], [], color=C["beam"], lw=1.6)[0])
        self.ln_plat = anim(ax.plot([], [], color=C["main"], lw=2.0)[0])

        ax = self.ax_E
        ax.set_ylim(-1.15, 1.15)
        ax.set_yticks([-1, 0, 1])
        self.ln_E = anim(ax.plot([], [], color=C["field"], lw=1.4)[0])
        self.ln_nb = anim(ax.plot([], [], color=C["beam"], lw=1.0, alpha=0.9)[0])
        self.ln_ni = anim(ax.plot([], [], color=C["ion"], lw=1.5)[0])
        self.band_E = anim(ax.add_patch(Rectangle((0, 0), 0, 1, transform=ax.get_xaxis_transform(),
                                                  fc=C["ion"], ec=C["ion"], alpha=0.25)))
        # подписи линий (все три нормированы на свой максимум; сами максимумы — в строке слева)
        f.text(0.48, 0.425, "— E(x)", color=C["field"], ha="right", va="bottom", fontsize=8)
        self.lg_nb = f.text(0.446, 0.425, "— δn_b", color=C["beam"], ha="right",
                            va="bottom", fontsize=8)
        self.lg_ni = f.text(0.412, 0.425, "", color=C["ion"], ha="right", va="bottom", fontsize=8)

        # --- энергия и спектрограмма (общая ось времени)
        self.ax_W = f.add_axes([0.59, 0.70, 0.185, 0.21])
        self.ax_sg = f.add_axes([0.59, 0.455, 0.185, 0.19], sharex=self.ax_W)
        ax = self.ax_W
        ax.set_title("Плотность энергии, Дж/м³ (лог. шкала)", loc="left")
        ax.set_yscale("log")
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

        ax = self.ax_sg
        ax.set_title("Спектрограмма lg|E_k|²", loc="left")
        ax.grid(False)
        # сама картинка спектрограммы копируется в пиксели (см. _raw), а этот
        # невидимый imshow нужен только для цветовой шкалы и подписей осей
        self._sg_cmap = style.seq_cmap()
        with warnings.catch_warnings():          # пустая заготовка: пределы осей зададим в reset()
            warnings.simplefilter("ignore")
            self.im_sg = ax.imshow(np.zeros((2, 2)), origin="lower", aspect="auto", extent=[0, 1, 0, 1],
                                   cmap=self._sg_cmap, vmin=-9, vmax=0.5, alpha=0.0)
        self._sg_lut = (self._sg_cmap(np.linspace(0, 1, 256))[:, :3] * 255).astype(np.uint8)

        # --- γ(k) и спектр (общая ось k)
        self.ax_gk = f.add_axes([0.805, 0.70, 0.185, 0.21])
        self.ax_sp = f.add_axes([0.805, 0.455, 0.185, 0.19], sharex=self.ax_gk)
        ax = self.ax_gk
        ax.set_title("Инкремент γ(k)", loc="left")
        ax.tick_params(labelbottom=False)
        self.ln_gk_cold, = ax.plot([], [], color=C["text2"], ls="--", lw=1.3,
                                   label="уравнение из задания")
        self.ln_gk_th, = ax.plot([], [], color=C["main"], lw=1.3, label="с температурой")
        self.pt_gk_box, = ax.plot([], [], "o", ms=5, mfc="none", mec=C["text2"], mew=1.0,
                                  label="моды ящика")
        self.pt_gk_meas = anim(ax.plot([], [], "o", ms=8, mfc=C["field"], mec=C["surface"],
                                       mew=2, label="измерено (PIC)")[0])

        ax = self.ax_sp
        ax.set_title("Спектр волн A_k² сейчас", loc="left")
        ax.set_yscale("log")
        ax.set_ylabel("A_k², (В/м)²")
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
        ax.axvline(SPLIT, color=C["grid"], lw=1)

        self.panel_axes = {self.ax_ph: "phase", self.ax_fv: "fv", self.ax_E: "E",
                           self.ax_W: "energy", self.ax_sg: "spectrogram",
                           self.ax_gk: "gk", self.ax_sp: "spectrum"}

    def _build_controls(self):
        f = self.fig
        p = self.params

        # ползунки: параметры пучка из задания (n_b/n_p, v_b) + разброс скоростей + скорость счёта
        y1, y2, h = 0.218, 0.182, 0.02
        xl, wl, xr, wr = 0.075, 0.115, 0.345, 0.105
        self.s_alpha = ListSlider(f, [xl, y1, wl, h], "n_b/n_p", ALPHAS, p.alpha,
                                  lambda v: f"{v:.3g}")
        self.s_vb = ListSlider(f, [xr, y1, wr, h], "v_b", VELOCITIES, p.vb, fmt_velocity)
        self.s_dv = plain_slider(f, [xl, y2, wl, h], "Δv_b/v_b", 0.0, 0.3, p.dvb / p.vb, 0.01)
        self.s_speed = plain_slider(f, [xr, y2, wr, h], "скорость", 1, 40, 5, 1)
        self._sync_valtexts()
        self.s_speed.valtext.set_text("5 шаг/кадр")
        for s_ in (self.s_alpha, self.s_vb):
            s_.on_changed(self._on_slider)
        self.s_dv.on_changed(self._on_slider)
        self.s_speed.on_changed(lambda v: self.s_speed.valtext.set_text(f"{int(v)} шаг/кадр"))
        # ползунки перерисовывают только себя (иначе каждое движение = полная перерисовка)
        self._slider_blits = [SliderBlit(f, sl_, C["surface"])
                              for sl_ in (self.s_alpha.slider, self.s_vb.slider, self.s_dv,
                                          self.s_speed)]

        ax = f.add_axes([0.012, 0.06, 0.118, 0.075])
        style.style_widget_axes(ax)
        ax.set_title("Сценарий", fontsize=8, loc="left", color=C["text2"], pad=2)
        self.r_scen = RadioButtons(ax, ("пучок в плазме", "встречные пучки"),
                                   active=0 if p.scenario == "beam" else 1,
                                   activecolor=C["main"])
        for t in self.r_scen.labels:
            t.set_color(C["text"])
            t.set_fontsize(8.3)
        self.r_scen.on_clicked(lambda lab: self._param_changed(restart_now=True))

        ax = f.add_axes([0.136, 0.05, 0.132, 0.085])
        style.style_widget_axes(ax)
        ax.set_title("Показ и физика", fontsize=8, loc="left", color=C["text2"], pad=2)
        self.c_opts = CheckButtons(ax, ("сепаратриса", "пауза на стадиях", "ионы подвижны"),
                                   (self.show_sep, self.autopause, p.ion != "none"))
        for t in self.c_opts.labels:
            t.set_color(C["text"])
            t.set_fontsize(8.3)
        self.c_opts.on_clicked(self._on_check)

        bt = lambda rect, label, cb, hl=False, fs=8.5: button(f, rect, label, cb, hl, fs)

        self.b_play = bt([0.278, 0.10, 0.085, 0.045], "|| Пауза", self._on_play, hl=True)
        self.b_reset = bt([0.368, 0.10, 0.085, 0.045], "↺ Заново", lambda e: self.reset())
        self.b_save = bt([0.458, 0.10, 0.087, 0.045], "Сохранить PNG", lambda e: self.save_png())
        self.b_back = bt([0.278, 0.05, 0.085, 0.045], "◀ Назад", lambda e: self.back())
        self.b_step = bt([0.368, 0.05, 0.085, 0.045], "Шаг ▶", lambda e: self.single_step())
        self.b_an = bt([0.458, 0.05, 0.087, 0.045], "Анализ ω–k, x–t", lambda e: self.open_analysis(),
                       fs=8)

    # ================================================================ параметры
    def _slider_values(self):
        """Значения параметров пучка (СИ) по положениям ползунков."""
        vb = self.s_vb.val
        return dict(alpha=self.s_alpha.val, vb=vb, dvb=float(self.s_dv.val) * vb)

    def _sync_valtexts(self):
        v = self._slider_values()
        self.s_dv.valtext.set_text(f"{self.s_dv.val:.2f} → {sci(v['dvb'], 2)} м/с"
                                   if v["dvb"] > 0 else "0 (холодный)")

    def _on_slider(self, val):
        self._sync_valtexts()
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
        ions_on = self.c_opts.get_status()[2]
        return self.params.copy(scenario=scen, ion=self.ion_species if ions_on else "none",
                                T_i=self.T_i, **self._slider_values())

    def _on_check(self, label):
        st = self.c_opts.get_status()
        ions_changed = (st[2] != (self.params.ion != "none"))
        self.show_sep, self.autopause = st[0], st[1]
        self.ln_sep.set_visible(self.show_sep)
        if ions_changed:
            self.reset()
        else:
            self.blit.update(force=True)

    # ================================================================ запуск
    def reset(self):
        self._dirty_params = False
        p = self._current_params()
        self.params = p
        self.sim = s = PIC(p)
        self.tr = diag.StageTracker(s)
        self.info = s.info()
        self.modes_meas = None
        self.ql = None
        self.explain_key = None
        self._last_stage = 0
        self.th_anchor = None
        self.status_msg = ""
        two = p.scenario == "two_stream"
        if not two and p.vb < 4 * s.vte:
            self.status_msg = "v_b < 4·v_Te: пучок в тепловом «хвосте» плазмы — рост слабый"

        # оценка времени насыщения → масштаб оси времени (с)
        A0 = s.main_amplitude()
        t_sat = np.log(max(self.tr.A_trap / max(A0 / 3, 1e-14 * self.tr.A_trap), 10.0)) / s.gamma_ref
        Tp = 1.0 / s.wpe
        T_view = max(2.6 * t_sat, t_sat + 60 * Tp)
        T_view = min(T_view, 4000 * Tp)
        self.T_view = self._nice_time(T_view)

        # --- масштабы осей (данные всегда в СИ, подписи — с приставками)
        self.sc_x = Scale(s.L, "м")
        self.sc_v = Scale(p.vb, "м/с")
        self.sc_t = Scale(self.T_view, "с")
        self.sc_k = Scale(2.5 * s.k_max, "рад/м")
        self.sc_g = Scale(s.gamma_max, "с⁻¹")
        self.ax_ph.set_ylabel(f"скорость v, {self.sc_v.label}")
        self.ax_ph.yaxis.set_major_formatter(self.sc_v.formatter())
        self.ax_E.set_xlabel(f"координата x, {self.sc_x.label}", labelpad=1)
        self.ax_E.xaxis.set_major_formatter(self.sc_x.formatter())
        self.ax_sg.set_xlabel(f"время t, {self.sc_t.label}", labelpad=1)
        self.ax_sg.xaxis.set_major_formatter(self.sc_t.formatter())
        self.ax_sg.set_ylabel(f"k, {self.sc_k.label}")
        self.ax_sg.yaxis.set_major_formatter(self.sc_k.formatter())
        self.ax_sp.set_xlabel(f"волновое число k, {self.sc_k.label}", labelpad=1)
        self.ax_sp.xaxis.set_major_formatter(self.sc_k.formatter())
        self.ax_gk.set_ylabel(f"γ, {self.sc_g.label}")
        self.ax_gk.yaxis.set_major_formatter(self.sc_g.formatter())

        # --- фазовый портрет: пределы скоростей (м/с)
        dvf = p.dvb / p.vb
        if two:
            self.vmin, self.vmax = -1.3 * p.vb, 1.3 * p.vb
        else:
            self.vmin, self.vmax = -0.6 * p.vb, (1.75 + 2 * dvf) * p.vb
        self.vmax = min(self.vmax, 1.02 * C_LIGHT)
        self.vmin = max(self.vmin, -1.02 * C_LIGHT)
        self.ax_ph.set_xlim(0, s.L)
        self.ax_ph.set_ylim(self.vmin, self.vmax)
        self._c_surf = style.hex2rgb(C["surface"]) * 255
        self._c_p = style.hex2rgb(C["plasma_glow"]) * 255 - self._c_surf
        self._c_b = style.hex2rgb(C["beam_glow"]) * 255 - self._c_surf
        self._xs = np.linspace(0, s.L, 400)
        self._lut_key = None

        # --- f(v), с/м
        self.v_edges = np.linspace(self.vmin, self.vmax, 181)
        self.v_cent = 0.5 * (self.v_edges[1:] + self.v_edges[:-1])
        self._f_floor = 1e-4 / p.vb
        f0 = s.velocity_hist(1, self.v_edges) / s.dens[1]
        self.ln_fv0.set_data(np.maximum(f0, self._f_floor), self.v_cent)
        self.ax_fv.set_xlim(1e-2 / p.vb, 2e2 / p.vb)

        # --- E(x)
        self._xdec = max(1, p.ng // 512)              # на экран хватает 512 точек
        xg = np.arange(p.ng)[::self._xdec] * s.dx
        self.ln_E.set_xdata(xg)
        self.ln_nb.set_xdata(xg)
        self.ln_ni.set_xdata(xg)
        self.ln_ni.set_visible(bool(s.m_i))
        if not s.m_i:
            self.ln_ni.set_ydata(np.full(xg.size, np.nan))

        # --- энергия: уровень насыщения по теории захвата, Дж/м³
        self.K0 = s.K0_beam
        self.ax_W.set_xlim(0, self.T_view)
        self.ax_W.set_ylim(1e-8 * self.K0, 3.0 * self.K0)
        Wtrap = EPS0 * self.tr.A_trap ** 2 / 4
        self.ln_trap.set_ydata([Wtrap, Wtrap])
        self.txt_trap.set_y(Wtrap * 1.3)
        self.txt_trap.set_text("насыщение по теории захвата")

        # --- спектрограмма
        self.NT = 300
        self.sg = np.full((s.m_store, self.NT), -12.0)
        self.sg_col = 0
        dk = 2 * np.pi / s.L
        self.im_sg.set_extent([0, self.T_view, 0.5 * dk, (s.m_store + 0.5) * dk])
        self.ax_sg.set_ylim(0, min(3.0 * s.k_max, (s.m_store + 0.5) * dk))

        # --- γ(k): теория (уравнение из задания и кинетика с реальными температурами)
        kk = np.linspace(1e-3, 2.6, 400) * s.k_max
        cold = disp.cold(s.theory_species)
        _, g = disp.fluid_growth(kk, cold)
        self.ln_gk_cold.set_data(kk, g)
        gtop = g.max()
        if any(vt > 0 for (_, _, vt) in s.theory_species):
            _, gk = disp.kinetic_growth_curve(kk, s.theory_species)
            gk = np.maximum(gk, 0)
            self.ln_gk_th.set_data(kk, gk)
            self.ln_gk_th.set_label("с температурой (кинетика)")
            gtop = max(gtop, gk.max())
        else:
            self.ln_gk_th.set_data([], [])
            self.ln_gk_th.set_label("_нет")
        km = s.k_modes[1:s.m_store + 1]
        self.pt_gk_box.set_data(km, s.gamma_modes_th)
        self.ax_gk.set_xlim(0, 2.6 * s.k_max)
        self.ax_gk.set_ylim(0, 1.25 * max(gtop, s.gamma_ref, 1e-6 * s.wpe))
        self.ax_gk.legend(loc="center right", fontsize=6.3, borderpad=0.3, labelspacing=0.2,
                          handlelength=1.4)
        self.pt_gk_meas.set_data([], [])
        self.ax_sp.set_ylim(1e-9 * self.tr.A_trap ** 2, 30 * self.tr.A_trap ** 2)

        # --- карты x–t для окна «Анализ» (уровень поля W и концентрация ионов)
        self.xt_t, self.xt_W, self.xt_ni = [], [], []
        self.xt_dt = 2.0 / s.wpe
        self._xt_dec = max(1, p.ng // XT_NX)

        # подписи сортов частиц зависят от сценария
        self.lg_b.set_text("■ поток 2 (→)" if two else "■ пучок")
        self.lg_p.set_text("■ поток 1 (←)" if two else "■ плазма")
        self.lg_nb.set_text("— δn₂" if two else "— δn_b")
        self.lg_ni.set_text(f"— δn_i ({ION_LABEL[p.ion]})" if s.m_i else "")
        self.ax_fv.set_title("f потока 2" if two else "f пучка", loc="left")
        self.ln_Kb.set_label("−ΔK потока 2" if two else "−ΔK пучка")
        self.ln_Kp.set_label("+ΔK потока 1" if two else "+ΔK плазмы")
        self.ax_W.legend(loc="lower right", ncol=2, fontsize=6.3, handlelength=1.3,
                         borderpad=0.3, labelspacing=0.2, columnspacing=0.7)
        scen = "пучок в плазме" if not two else "встречные пучки ±v_b/2"
        ions = f"ионы {ION_LABEL[p.ion]} подвижны" if s.m_i else "ионы неподвижны"
        I = self.info
        self.txt_sub.set_text(
            f"n_p = {sci(p.n_p, 2)} м⁻³ · T_e = {sci(p.T_e, 2)} К · 1D PIC: {s.ns}×{s.N:,} макрочастиц · сетка {p.ng} узлов · Δt = {fmt(s.dt, 'с')} · "
            f"L = {fmt(s.L, 'м')} = {p.n_waves} длин волны · f_p = {fmt(I['fpe'], 'Гц')} · "
            f"λ_D = {fmt(I['lambda_D'], 'м')} · {scen} · {ions}"
            .replace(",", " "))
        self.ln_sep.set_visible(self.show_sep)
        self._update_artists(force=True)
        self.fig.canvas.draw_idle()

    @staticmethod
    def _nice_time(T):
        """Округление длины оси времени вверх до 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8 ×10ⁿ с."""
        e = 10.0 ** math.floor(math.log10(T))
        for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
            if m * e >= T:
                return m * e
        return 10 * e

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
            self._record_xt()
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

    def _record_xt(self):
        """Строка карт x–t каждые 2/ω_p: уровень поля W(x) и δn_i/n_i(x)."""
        s = self.sim
        if self.xt_t and s.t < self.xt_t[-1] + self.xt_dt:
            return
        d = self._xt_dec
        self.xt_t.append(s.t)
        self.xt_W.append(diag.wave_level(s)[::d].astype(np.float32))
        if s.m_i:
            self.xt_ni.append(s.ion_perturbation()[::d].astype(np.float32))

    def _extend_time(self):
        self.T_view = self._nice_time(self.T_view * 1.5)
        self.sc_t = Scale(self.T_view, "с")
        self.ax_sg.set_xlabel(f"время t, {self.sc_t.label}", labelpad=1)
        self.ax_sg.xaxis.set_major_formatter(self.sc_t.formatter())
        self.ax_W.set_xlim(0, self.T_view)
        self.sg = np.full((self.sim.m_store, self.NT), -12.0)
        self.sg_col = 0
        dk = 2 * np.pi / self.sim.L
        self.im_sg.set_extent([0, self.T_view, 0.5 * dk, (self.sim.m_store + 0.5) * dk])
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
        tc = t0 + (np.arange(w) + 0.5) * (t1 - t0) / w
        col = np.floor(tc / self.T_view * self.NT).astype(np.int64)
        yc = y1 - (np.arange(h) + 0.5) * (y1 - y0) / h          # сверху вниз
        row = np.rint(yc * self.sim.L / (2 * np.pi)).astype(np.int64) - 1   # k = 2πm/L
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
        return 0, 0.29 * H, 0.565 * W, 0.945 * H

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
            # на Retina/4K (2 физических пикселя на точку) считаем картинку вдвое
            # меньше и растягиваем — на глаз то же, а работы в 4 раза меньше
            r = 2 if getattr(self.fig.canvas, "device_pixel_ratio", 1) >= 1.75 else 1
            img = self._phase_image((x1 - x0) // r, (yb - yt) // r)
            if r > 1:
                img = img.repeat(r, axis=0).repeat(r, axis=1)
            paste(buf, img, x0, yt)
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
        paste(buf, im[:, :int(SPLIT * bi.width) - 2 * pad], bi.x0 + pad, H - bi.y1 + pad)
        xe = bi.x0 + SPLIT * bi.width + pad
        we = bi.x1 - xe - pad
        # текст разбивается на строки по измеренной ширине и обрезается по высоте панели
        head = self.rt_exp_h.fit(self.s_exp_h, we, 0.3 * bi.height, dpi)
        hh = 8.5 * dpi / 72 * 1.6 * (head.count("\n") + 1) + 4
        hb = bi.height - 2 * pad - hh
        paste(buf, self.rt_exp_h.render(head, we, hh, dpi), xe, H - bi.y1 + pad)
        paste(buf, self.rt_exp.render(self.rt_exp.fit(self.s_exp, we, hb, dpi), we, hb, dpi),
              xe, H - bi.y1 + pad + hh)

    # ================================================================ данные кадра
    def _update_artists(self, force=False, right=True):
        """Новые данные для всех подвижных элементов. right=False — пропустить
        правую половину окна (она в этом кадре не перерисовывается)."""
        s, p, tr = self.sim, self.params, self.tr
        n = s.h_n
        m = s.m_main
        Ek_m = s.Ek[m] / p.ng
        A = 2 * abs(Ek_m)                      # амплитуда главной волны, В/м
        km = s.k_modes[m]
        if self.show_sep:
            vu, vd = diag.separatrix(self._xs, A, km, np.angle(Ek_m), s.v_phase)
            self.ln_sep.set_data(np.concatenate([self._xs, [np.nan], self._xs]),
                                 np.concatenate([vu, [np.nan], vd]))
        stage = tr.stage
        self.s_ph = f"t = {fmt(s.t, 'с')}   стадия {stage + 1}/{tr.n_stages}"

        # --- f(v)
        fb = s.velocity_hist(1, self.v_edges) / s.dens[1]
        self.ln_fv.set_data(np.maximum(fb, self._f_floor), self.v_cent)
        if stage >= 3 and (self.ql is None or self._frame % 15 == 0 or force):
            self.ql = diag.ql_prediction(s)
        if stage >= 3 and self.ql is not None:
            hq = 1.0 / max(self.ql["v2"] - self.ql["v1"], 1e-3 * p.vb)
            self.ln_plat.set_data([hq, hq], [self.ql["v1"], self.ql["v2"]])
        else:
            self.ln_plat.set_data([], [])

        # --- E(x), δn_b(x) и δn_i(x)
        Emax = np.abs(s.E).max()
        self.ln_E.set_ydata(s.E[::self._xdec] / max(Emax, 1e-300))
        dnb = s.dens_grid[1][::self._xdec] - s.dens[1]
        self.ln_nb.set_ydata(dnb / max(np.abs(dnb).max(), 1e-300))
        self.s_E = f"max|E| = {fmt(Emax, 'В/м')}  E₀ = {fmt(A, 'В/м')}"
        if s.m_i:
            dni = s.ion_perturbation()[::self._xdec]
            nmax = np.abs(dni).max()
            self.ln_ni.set_ydata(dni / max(nmax, 1e-300))
            self.s_E += f"  max|δn_i|/n_i = {nmax * 100:.1f}%"
        cav = self._find_cavern() if s.m_i else None
        if cav is not None:
            x0, half, Wm, dn = cav
            for b in (self.band_ph, self.band_E):
                b.set_x(x0 - half)
                b.set_width(2 * half)
            self.s_E = (f"КАВЕРНА x = {fmt(x0, 'м')}: поле {fmt(float(np.abs(s.E).max()), 'В/м')} "
                        f"(W = {Wm:.2f}), δn_i = {dn * 100:+.0f}%")
        else:
            for b in (self.band_ph, self.band_E):
                b.set_width(0)

        if not (right or force):
            return
        # --- энергия, Дж/м³
        if n > 1:
            st = max(1, n // 700)
            t = s.h_t[:n:st]
            pos = lambda y: np.where(y > 0, y, np.nan)   # на лог. шкале ≤ 0 не рисуем
            self.ln_WE.set_data(t, pos(s.h_WE[:n:st]))
            Wm = EPS0 * (2 * np.abs(s.h_Ek[:n:st, m - 1])) ** 2 / 4
            self.ln_Wm.set_data(t, pos(Wm))
            self.ln_Kb.set_data(t, pos(s.h_K[0, 1] - s.h_K[:n:st, 1]))
            self.ln_Kp.set_data(t, pos(s.h_K[:n:st, 0] - s.h_K[0, 0]))
            # теоретическая прямая: проходит через энергию главной волны в t1 = 4/γ
            t1 = 4.0 / s.gamma_ref
            if self.th_anchor is None and s.t > t1:
                j = min(int(round(t1 / s.dt)), n - 1)
                self.th_anchor = (s.h_t[j], EPS0 * (2 * abs(s.h_Ek[j, m - 1])) ** 2 / 4)
            if self.th_anchor is not None:
                ta, Wa = self.th_anchor
                tt = np.array([ta - 2 / s.gamma_ref, self.T_view])
                with np.errstate(over="ignore"):
                    self.ln_th.set_data(tt, Wa * np.exp(np.minimum(2 * s.gamma_ref * (tt - ta), 600.0)))
            else:
                self.ln_th.set_data([], [])
            if tr.sat is not None:
                self.pt_sat.set_data([tr.sat["t"]], [EPS0 * tr.sat["A"] ** 2 / 4])
            else:
                self.pt_sat.set_data([], [])
            # --- спектрограмма: дописываем новые столбцы
            col_dt = self.T_view / self.NT
            while self.sg_col < self.NT and (self.sg_col + 0.5) * col_dt <= s.t:
                j = min(int(round((self.sg_col + 0.5) * col_dt / s.dt)), n - 1)
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
            self.pt_gk_meas.set_data([d["k"] for d in self.modes_meas],
                                     [d["g"] for d in self.modes_meas])
        else:
            self.pt_gk_meas.set_data([], [])

        # --- спектр сейчас (вертикальные «палочки»), (В/м)²
        amp2 = (s.mode_amplitudes()[:s.m_store]) ** 2
        kk = s.k_modes[1:s.m_store + 1]
        base = 1e-12 * tr.A_trap ** 2
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

    def _find_cavern(self):
        """Каверна — место, где максимум усреднённого поля совпал с ямой концентрации
        ионов. Условная граница: W = ε₀⟨E²⟩/(2n k_BT_e) > 0.3 и δn_i/n_i < −5 % в той же точке.
        Возвращает (x, полуширина, W, δn_i/n_i) или None."""
        s = self.sim
        W = diag.wave_level(s)
        i = int(np.argmax(W))
        dn = s.ion_perturbation()
        j0, j1 = max(i - 8, 0), min(i + 9, W.size)
        dmin = float(dn[j0:j1].min())
        if W[i] < 0.3 or dmin > -0.05:
            return None
        half = max(8 * s.lambda_D, 4 * s.dx)
        return float(i * s.dx), half, float(W[i]), dmin

    # ---------------------------------------------------------------- тексты
    def _numbers_text(self, A):
        """Короткая таблица главных чисел (все в СИ). Строки с «§» — заголовки."""
        s, p, tr, I = self.sim, self.params, self.tr, self.info
        g, wp = s.gamma_ref, s.wpe
        gph = float(lorentz_gamma(s.v_phase))
        kk = s.k_modes[s.m_main]
        L = [f"§ПЛАЗМА  f_p = {fmt(I['fpe'], 'Гц')}   λ_D = {fmt(I['lambda_D'], 'м')}",
             f" ω_p = {sci(wp)} с⁻¹   ν_ei/γ = {I['nu_ei'] / g:.0e}"]
        if p.scenario == "beam":
            gh = disp.gamma_hint(p.alpha, wp)
            L += [f"§ТЕОРИЯ  λ = {fmt(2 * np.pi / s.k_max, 'м')}   γ_b = {I['gamma_b']:.4f}",
                  f" γ = {sci(g)} с⁻¹ = {g / wp:.4f}·ω_p",
                  f" подсказка задания: {sci(gh)} с⁻¹ ({_pct(gh / g - 1)})"]
        else:
            L += [f"§ТЕОРИЯ  λ = {fmt(2 * np.pi / s.k_max, 'м')}",
                  f" γ = {sci(g)} с⁻¹ = {g / wp:.4f}·ω_p1"]
        L.append(f"§СЧЁТ  t = {fmt(s.t, 'с')} = {s.t * wp:.0f}/ω_p")
        if tr.gamma_meas is not None:
            L.append(f" γ_изм = {sci(tr.gamma_meas)} с⁻¹ ({_pct(tr.gamma_meas / g - 1)})"
                     + ("" if tr.gamma_frozen else " …"))
        else:
            L.append(" γ_изм: ждём конца затравки")
        wB = float(diag.bounce_frequency(A, kk, gph))
        L.append(f" E₀ = {fmt(A, 'В/м')}   ω_B/γ = {wB / g:.2f}")
        if tr.sat is not None:
            Es = tr.sat["A"]
            wBs = float(diag.bounce_frequency(Es, kk, gph))
            L += [f"§НАСЫЩЕНИЕ  t = {fmt(tr.sat['t'], 'с')}",
                  f" E_sat = {fmt(Es, 'В/м')}   ω_B/γ = {wBs / g:.2f}",
                  f" теория захвата: {fmt(tr.A_trap, 'В/м')}"]
        else:
            L.append(f" теория захвата: E_sat ≈ {fmt(tr.A_trap, 'В/м')}")
        n = s.h_n
        if n > 0:
            K0 = self.K0
            WE = s.h_WE[n - 1]
            dK = s.h_K[n - 1] - s.h_K[0]
            err = (WE - s.h_WE[0] + dK.sum()) / K0
            L += [f"§ЭНЕРГИЯ  K_b0 = {fmt(K0, 'Дж/м³')}",
                  f" поле {WE / K0 * 100:.1f}%  пучок {dK[1] / K0 * 100:+.1f}%  плазма {dK[0] / K0 * 100:+.1f}%",
                  f" невязка {err * 100:+.3f}% K_b0"]
        if tr.stage >= 3 and self.ql is not None and p.scenario == "beam":
            q = self.ql
            WEavg = s.h_WE[max(0, n - int(20 / p.dt_wp)):n].mean()
            L.append(f"§БАЛАНС ПЛАТО  {q['WE_ql'] / self.K0 * 100:.1f}% ↔ счёт {WEavg / self.K0 * 100:.1f}%")
        if s.m_i:
            dni = s.ion_perturbation()
            L.append(f"§ИОНЫ {ION_LABEL[p.ion]}  W max {diag.wave_level(s).max():.2f}  "
                     f"δn_i min {dni.min() * 100:+.1f}%")
        return "\n".join(L)

    def _explanation(self):
        """Заголовок и текст пояснения (переносы строк делает _raw_right по ширине панели)."""
        if self.explain_key is not None:
            head, body = texts.PANELS[self.explain_key]
            return head, body + "\n(Пробел — продолжить.)"
        s, p, tr = self.sim, self.params, self.tr
        stages = texts.STAGES_BEAM if p.scenario == "beam" else texts.STAGES_TWO
        head, body = stages[tr.stage]
        km = s.k_modes[s.m_main]
        gph = float(lorentz_gamma(s.v_phase))
        A = s.main_amplitude()
        sat = tr.sat or {}
        Tb = "≈ 2π/ω_B"
        if tr.bounce is not None and sat:
            wBs = float(diag.bounce_frequency(sat["A"], km, gph))
            Tb = f"{fmt(tr.bounce, 'с')} (2π/ω_B = {fmt(2 * np.pi / wBs, 'с')})"
        gm = f"{sci(tr.gamma_meas)} с⁻¹" if tr.gamma_meas is not None else "(ещё измеряется)"
        kw = dict(N=tr.n_stages, g=f"{sci(s.gamma_ref)} с⁻¹", t1=fmt(4 / s.gamma_ref, "с"),
                  vb=f"{sci(p.vb)} м/с", vph=f"{sci(s.v_phase)} м/с", gm=gm,
                  wB=f"{sci(float(diag.bounce_frequency(A, km, gph)))} с⁻¹",
                  Es=fmt(sat.get("A", 0.0), "В/м"), ts=fmt(sat.get("t", 0.0), "с"),
                  Et=fmt(tr.A_trap, "В/м"), Tb=Tb, ion=ION_LABEL[p.ion],
                  ions_hint=texts.IONS_HINT if s.m_i else "", dni="", dnmin="", Wmax="")
        if s.m_i:
            dni = s.ion_perturbation()
            kw.update(dni=f"{np.sqrt(np.mean(dni ** 2)) * 100:.1f}%", dnmin=f"{dni.min() * 100:+.0f}%",
                      Wmax=f"{diag.wave_level(s).max():.2f}")
        return head.format(N=tr.n_stages), body.format(**kw)

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
        self._record_xt()
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
        keep = sum(1 for t in self.xt_t if t <= s.t)
        del self.xt_t[keep:], self.xt_W[keep:], self.xt_ni[keep:]
        self._pause(f"перемотано на t = {fmt(s.t, 'с')}")
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

    def open_analysis(self):
        from .analysis_window import AnalysisWindow
        self.children.append(AnalysisWindow(self))

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
