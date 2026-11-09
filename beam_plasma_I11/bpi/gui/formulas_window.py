"""Окно «Формулы»: все уравнения модели по страницам (рендер формул — mathtext)."""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Button

from . import style
from .style import C


def _phys_example(n_cm3=1e10, E_keV=1.0, alpha=0.01):
    """Перевод безразмерных чисел в физические единицы для примера."""
    e, me, eps0, c = 1.602176634e-19, 9.1093837e-31, 8.8541878128e-12, 2.99792458e8
    n = n_cm3 * 1e6
    wp = np.sqrt(n * e * e / (eps0 * me))
    gam = 1 + E_keV * 1e3 * e / (me * c * c)
    vb = c * np.sqrt(1 - 1 / gam ** 2)
    Eunit = me * wp * vb / e
    from ..dispersion import most_unstable, beam_plasma_species
    from ..diagnostics import C_TRAP
    k, g, _ = most_unstable(beam_plasma_species(alpha))
    return dict(wp=wp, fp=wp / 2 / np.pi, vb=vb, lam=2 * np.pi / k * vb / wp,
                Eunit=Eunit, g=g, tg=1 / (g * wp), Esat=C_TRAP * g * g / k * Eunit,
                n=n_cm3, EkeV=E_keV, alpha=alpha)


def _sci(x):
    """5.64e+09 → 5.64·10^{9} для mathtext."""
    m, e = f"{x:.2e}".split("e")
    return rf"{m}\cdot10^{{{int(e)}}}"


def pages():
    P = []
    P.append(("1. Модель и безразмерные единицы", [
        (r"$\omega_p^2=\dfrac{n_p e^2}{\varepsilon_0 m}$",
         "плазменная частота электронов плазмы — естественная единица времени"),
        (r"$t\to t\,\omega_p,\quad x\to\dfrac{x\,\omega_p}{v_0},\quad v\to\dfrac{v}{v_0},"
         r"\quad E\to\dfrac{eE}{m\,\omega_p v_0},\quad n\to\dfrac{n}{n_p}$",
         "безразмерные переменные; v₀ — опорная скорость (по умолчанию v_b = v₀)"),
        (r"$\alpha=\dfrac{n_b}{n_p}=\dfrac{\omega_b^2}{\omega_p^2}$",
         "единственный параметр холодной задачи «пучок + плазма»"),
        (r"$\dfrac{dx_j}{dt}=v_j,\qquad \dfrac{dv_j}{dt}=-E(x_j)$",
         "движение каждого электрона (заряд −e): закон Ньютона"),
        (r"$\dfrac{\partial E}{\partial x}=n_i-n_e(x),\qquad n_i=1+\alpha$",
         "уравнение Пуассона (теорема Гаусса в 1D); ионы — неподвижный фон"),
        (r"$W_E=\dfrac{1}{2}\int_0^L E^2\,dx,\qquad K_s=\dfrac{1}{2}\sum_j w_s v_j^2,"
         r"\qquad w_s=\dfrac{n_s L}{N_s}$",
         "энергия поля и кинетическая энергия; w — «вес» макрочастицы"),
        (r"$W_E+K_{плазмы}+K_{пучка}=\mathrm{const}$",
         "закон сохранения энергии — главная проверка правильности счёта"),
    ]))
    P.append(("2. Линейная теория: инкремент γ(k)", [
        (r"$1-\dfrac{\omega_p^2}{\omega^2}-\dfrac{\omega_b^2}{(\omega-k v_b)^2}=0$",
         "дисперсионное уравнение из задания (холодные плазма и пучок)"),
        (r"$\omega^4-2kv_b\,\omega^3+(k^2v_b^2-1-\alpha)\,\omega^2+2kv_b\,\omega-k^2v_b^2=0$",
         "то же после умножения на ω²(ω−kv_b)²: многочлен 4-й степени, решается точно"),
        (r"$\omega=\omega_r+i\gamma,\qquad E\propto e^{\gamma t}\cos(kx-\omega_r t)$",
         "корень с γ > 0 — растущая волна; γ — инкремент"),
        (r"$kv_b=\omega_p,\ \ \omega=\omega_p+\delta:\quad 2\delta^3=\alpha\,\omega_p^3$",
         "слабый пучок: разложение вблизи резонанса (1 − 1/ω² ≈ 2δ)"),
        (r"$\gamma_{max}\approx\dfrac{\sqrt{3}}{2}\left(\dfrac{\alpha}{2}\right)^{1/3}\omega_p,\qquad"
         r"\omega_r\approx\omega_p\left[1-\dfrac{1}{2}\left(\dfrac{\alpha}{2}\right)^{1/3}\right]$",
         "верная асимптотика. В подсказке пропущен множитель 2^(−1/3) = 0.794"),
        (r"$1-\dfrac{\omega_b^2}{(\omega-ku)^2}-\dfrac{\omega_b^2}{(\omega+ku)^2}=0"
         r"\ \Rightarrow\ \gamma_{max}=\dfrac{\omega_b}{2}\ \ \mathrm{при}\ \ ku=\dfrac{\sqrt{3}}{2}\omega_b$",
         "встречные пучки ±u: то же уравнение в системе центра масс"),
        (r"$\varepsilon=1+\sum_s\dfrac{\omega_s^2}{k^2v_{Ts}^2}\left[1+\zeta_sZ(\zeta_s)\right],"
         r"\quad \zeta_s=\dfrac{\omega-ku_s}{\sqrt{2}\,k v_{Ts}}$",
         "тёплый пучок: кинетическая теория, Z — функция дисперсии плазмы"),
    ]))
    P.append(("3. Метод частиц в ячейках (PIC)", [
        (r"$i=\lfloor x_j/\Delta x\rfloor,\quad f=x_j/\Delta x-i:\quad"
         r"n_i\leftarrow n_i+w(1-f),\ \ n_{i+1}\leftarrow n_{i+1}+wf$",
         "1) взвешивание CIC: заряд частицы делится между двумя узлами"),
        (r"$\rho_g=n_i-n_{e,g},\qquad E_k=F(k)\,\dfrac{\rho_k}{ik},\qquad F=\cos^4\dfrac{k\Delta x}{2}$",
         "2) поле через БПФ; F — двойное сглаживание (1,2,1)/4 против шума сетки"),
        (r"$E(x_j)=(1-f)\,E_i+f\,E_{i+1}$",
         "3) интерполяция поля в точку частицы теми же весами"),
        (r"$v^{n+1/2}=v^{n-1/2}-E^n(x^n)\,\Delta t,\qquad x^{n+1}=x^n+v^{n+1/2}\Delta t$",
         "4) «чехарда» (leapfrog): 2-й порядок, сохраняет фазовый объём"),
        (r"$\omega_p\Delta t<2,\qquad \dfrac{\delta\omega}{\omega}\approx\dfrac{(\omega_p\Delta t)^2}{24}"
         r"=4\cdot10^{-4}$",
         "устойчивость и ошибка частоты при Δt = 0.1/ω_p"),
        (r"$E(x)=\sum_m A_m\cos(k_m x+\varphi_m),\quad A_m=2|E_{k_m}|,\quad k_m=\dfrac{2\pi m}{L}$",
         "моды ящика; L = 8·(2π/k_max), поэтому мода m = 8 — самая неустойчивая"),
        (r"$\gamma_{изм}=\dfrac{d\,\ln A_m}{dt},\qquad \omega_{изм}=-\dfrac{d\,\arg E_{k_m}}{dt}$",
         "измерение по истории счёта (МНК на отрезке линейной стадии)"),
    ]))
    P.append(("4. Нелинейная стадия: захват, насыщение, плато", [
        (r"$\dfrac{d\hat E}{dt}=\dfrac{\alpha}{k}\langle e^{-i\psi_j}\rangle,\quad"
         r"\dfrac{d\psi_j}{dt}=kv_j-\omega_p,\quad \dfrac{dv_j}{dt}=-\mathrm{Re}\,(\hat E e^{i\psi_j})$",
         "одноволновая модель (уравнение огибающей), решается методом Рунге–Кутты 4"),
        (r"$\omega(t)=\omega_p-\dfrac{d\theta}{dt},\qquad \theta=\arg\hat E$",
         "нелинейный сдвиг частоты"),
        (r"$\omega_B=\sqrt{\dfrac{e\,k\,E_0}{m}},\qquad (v-v_\phi)^2=\dfrac{2eE_0}{mk}\,(1-\sin\Phi)$",
         "баунс-частота захваченного электрона и сепаратриса (граница ямы)"),
        (r"$\omega_B\approx1.77\,\gamma\ \Rightarrow\ E_{sat}=3.12\,\dfrac{\gamma^2}{k}\propto"
         r"\alpha^{2/3}v_b$",
         "теория захвата: константа 1.77 получена одноволновой моделью"),
        (r"$\dfrac{W_{E,sat}}{K_{b0}}\propto\alpha^{1/3},\qquad K_{b0}=\dfrac{1}{2} n_b L v_b^2$",
         "доля энергии пучка, переданная волне к моменту насыщения"),
        (r"$K_{плато}=n_bL\,\dfrac{v_1^2+v_1v_2+v_2^2}{6},\qquad W_E^{КЛ}=\dfrac{K_{b0}-K_{плато}}{2}$",
         "квазилинейный баланс: плато f = const на [v₁, v₂]; половина энергии волны — поле"),
        (r"$v_1=0,\ v_2=v_b:\qquad W_E^{КЛ}=\dfrac{K_{b0}}{3},\qquad E_{rms}=v_b\sqrt{\alpha/3}$",
         "полная квазилинейная релаксация холодного пучка (верхняя оценка)"),
    ]))
    ex = _phys_example()
    P.append(("5. Перевод в физические единицы (пример)", [
        (r"$n_p=10^{10}\ \mathrm{cm^{-3}}:\quad \omega_p=5.64\cdot10^4\sqrt{n_p}="
         + _sci(ex["wp"]) + r"\ \mathrm{s^{-1}}$",
         f"f_p = ω_p/2π = {ex['fp'] / 1e9:.2f} ГГц"),
        (r"$\mathcal{E}_b=1\ \mathrm{keV}:\quad v_b=" + _sci(ex["vb"]) + r"\ \mathrm{m/s}$",
         "скорость электронов пучка с энергией 1 кэВ"),
        (rf"$\lambda=\dfrac{{2\pi}}{{k_{{max}}}}=\dfrac{{2\pi v_b}}{{1.041\,\omega_p}}={ex['lam'] * 100:.2f}\ \mathrm{{cm}}$",
         "длина самой неустойчивой волны (α = 0.01)"),
        (rf"$\dfrac{{m\omega_p v_b}}{{e}}={ex['Eunit'] / 1e5:.2f}\ \mathrm{{kV/cm}}$",
         "единица напряжённости поля в программе"),
        (rf"$1/\gamma={ex['tg'] * 1e9:.2f}\ \mathrm{{ns}},\qquad E_{{sat}}\approx"
         rf"{ex['Esat'] / 1e5:.2f}\ \mathrm{{kV/cm}}$",
         "время e-кратного роста и поле насыщения при α = 0.01"),
        (r"$\gamma\ \mathrm{не\ зависит\ от}\ v_b;\quad k_{max}\propto 1/v_b;\quad E_{sat}\propto v_b$",
         "у холодной задачи v_b — только масштаб (теория размерностей)"),
    ]))
    return P


class FormulasWindow:
    def __init__(self, page=0):
        style.use(style.current_theme())
        self.pages = pages()
        self.page = page
        self.fig = plt.figure(figsize=(13.5, 8.0))
        try:
            self.fig.canvas.manager.set_window_title("И11 · Формулы")
        except Exception:
            pass
        self._draw()
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)
        self.fig.show()

    def _draw(self):
        f = self.fig
        f.clear()
        title, rows = self.pages[self.page]
        f.text(0.04, 0.95, title, fontsize=16, fontweight="bold", color=C["text"])
        f.text(0.96, 0.95, f"страница {self.page + 1} из {len(self.pages)}", ha="right",
               fontsize=10, color=C["text2"])
        y = 0.86
        dy = 0.78 / max(len(rows), 1)
        for formula, note in rows:
            f.text(0.05, y, formula, fontsize=15, color=C["text"], va="center")
            f.text(0.05, y - 0.052, note, fontsize=10, color=C["text2"], va="center")
            y -= dy
        ax = f.add_axes([0.04, 0.02, 0.1, 0.05])
        self.b_prev = Button(ax, "◀ назад", color=C["panel"], hovercolor=C["grid"])
        ax2 = f.add_axes([0.15, 0.02, 0.1, 0.05])
        self.b_next = Button(ax2, "вперёд ▶", color=C["panel"], hovercolor=C["grid"])
        for b in (self.b_prev, self.b_next):
            b.label.set_color(C["text"])
        self.b_prev.on_clicked(lambda e: self.go(-1))
        self.b_next.on_clicked(lambda e: self.go(+1))
        f.text(0.27, 0.045, "клавиши ← → листают страницы; полный вывод формул — docs/ОБЪЯСНЕНИЕ.md",
               fontsize=9, color=C["muted"], va="center")
        f.canvas.draw()          # сразу (draw_idle может ждать, пока идёт анимация)

    def go(self, d):
        self.page = (self.page + d) % len(self.pages)
        self._draw()

    def _on_key(self, e):
        if e.key in ("right", "pagedown"):
            self.go(1)
        elif e.key in ("left", "pageup"):
            self.go(-1)
