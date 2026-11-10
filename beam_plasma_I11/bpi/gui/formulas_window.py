"""Окно «Формулы»: все уравнения модели в СИ по страницам (рендер формул — mathtext)."""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Button

from . import style
from .style import C


def _sci(x):
    """5.64e+09 → 5.64·10^{9} для mathtext."""
    m, e = f"{x:.2e}".split("e")
    return rf"{m}\cdot10^{{{int(e)}}}"


def passport(p):
    """Числа для страницы «Паспорт плазмы»: все величины в СИ для текущих параметров."""
    from ..pic import PICParams
    from ..constants import (plasma_frequency, debye_length, thermal_velocity, lorentz_gamma,
                             kinetic_energy, collision_frequency_ei, M_E, E_CHARGE)
    from ..dispersion import most_unstable, beam_plasma_species
    from ..diagnostics import trapping_amplitude
    p = p or PICParams()
    wp = float(plasma_frequency(p.n_p))
    k, g, w = most_unstable(beam_plasma_species(p.n_p, p.alpha, p.vb))
    gph = float(lorentz_gamma(w / k))
    return dict(p=p, wp=wp, fp=wp / 2 / np.pi, lD=float(debye_length(p.n_p, p.T_e)),
                vte=float(thermal_velocity(p.T_e)), gb=float(lorentz_gamma(p.vb)),
                Wb=float(kinetic_energy(p.vb)), nu=float(collision_frequency_ei(p.n_p, p.T_e)),
                k=k, g=g, lam=2 * np.pi / k, Esat=trapping_amplitude(g, k, gph),
                Eunit=M_E * wp * p.vb / E_CHARGE)


def pages(params=None):
    P = []
    P.append(("1. Модель: уравнения в СИ", [
        (r"$\dfrac{dx_j}{dt}=v_j,\qquad \dfrac{dp_j}{dt}=q_sE(x_j),\qquad "
         r"p=\gamma m_s v,\quad \gamma=\dfrac{1}{\sqrt{1-v^2/c^2}}$",
         "движение каждой частицы (q = −e у электронов, +e у ионов); при v ≪ c это m·dv/dt = qE"),
        (r"$\dfrac{\partial E}{\partial x}=\dfrac{\rho}{\varepsilon_0},\qquad "
         r"\rho=e\,(n_i-n_e)$",
         "теорема Гаусса в 1D (уравнение Пуассона): поле создают сами частицы"),
        (r"$\omega_p=\sqrt{\dfrac{n_p e^2}{\varepsilon_0 m}},\qquad \lambda_D=\sqrt{\dfrac{\varepsilon_0 k_BT_e}{n_p e^2}}"
         r"=\dfrac{v_{Te}}{\omega_p},\qquad v_{Te}=\sqrt{\dfrac{k_BT_e}{m}}$",
         "плазменная частота [рад/с], дебаевский радиус [м], тепловая скорость [м/с]"),
        (r"$W_E=\dfrac{\varepsilon_0\langle E^2\rangle}{2},\qquad K_s=n_s\langle(\gamma-1)m_sc^2\rangle,"
         r"\qquad W_E+\sum_s K_s=\mathrm{const}$",
         "плотности энергии [Дж/м³] и закон сохранения — главная проверка счёта"),
        (r"$e=1.602\cdot10^{-19}\ \mathrm{Кл},\ \ m=9.109\cdot10^{-31}\ \mathrm{кг},\ \ "
         r"\varepsilon_0=8.854\cdot10^{-12}\ \mathrm{Ф/м},\ \ k_B=1.381\cdot10^{-23}\ \mathrm{Дж/К}$",
         "постоянные CODATA-2018 (файл bpi/constants.py); c = 299 792 458 м/с"),
    ]))
    P.append(("2. Линейная теория: инкремент γ(k)", [
        (r"$1-\dfrac{\omega_p^2}{\omega^2}-\dfrac{\omega_b^2}{(\omega-k v_b)^2}=0,\qquad"
         r"\omega_b^2=\dfrac{n_b e^2}{\varepsilon_0 m\,\gamma_b^3}$",
         "дисперсионное уравнение из задания; γ_b³ — релятивистская продольная масса (1 при v_b ≪ c)"),
        (r"$\omega^4-2kv_b\,\omega^3+(k^2v_b^2-\omega_p^2-\omega_b^2)\,\omega^2+2kv_b\omega_p^2\,\omega-k^2v_b^2\omega_p^2=0$",
         "то же после умножения на ω²(ω−kv_b)²: многочлен 4-й степени, решается точно"),
        (r"$\omega=\omega_r+i\gamma,\qquad E\propto e^{\gamma t}\cos(kx-\omega_r t)$",
         "корень с γ > 0 — растущая волна; γ [с⁻¹] — инкремент"),
        (r"$\gamma_{max}\approx\dfrac{\sqrt{3}}{2}\left(\dfrac{n_b}{2n_p}\right)^{1/3}\dfrac{\omega_p}{\gamma_b},\qquad"
         r"\omega_r\approx\omega_p\left[1-\dfrac{1}{2\gamma_b}\left(\dfrac{n_b}{2n_p}\right)^{1/3}\right],\quad k\approx\dfrac{\omega_p}{v_b}$",
         "верная асимптотика слабого пучка. В подсказке пропущен множитель 2^(−1/3) = 0.794"),
        (r"$1-\dfrac{\omega_{p1}^2}{(\omega-ku)^2}-\dfrac{\omega_{p1}^2}{(\omega+ku)^2}=0"
         r"\ \Rightarrow\ \gamma_{max}=\dfrac{\omega_{p1}}{2}\ \ \mathrm{при}\ \ ku=\dfrac{\sqrt{3}}{2}\omega_{p1}$",
         "встречные пучки ±u: то же уравнение в системе центра масс"),
        (r"$\varepsilon=1+\sum_s\dfrac{\omega_s^2}{k^2v_{Ts}^2}\left[1+\zeta_sZ(\zeta_s)\right],"
         r"\quad \zeta_s=\dfrac{\omega-ku_s}{\sqrt{2}\,k v_{Ts}}$",
         "реальные температуры: кинетическая теория, Z — функция дисперсии плазмы"),
    ]))
    P.append(("3. Метод частиц в ячейках (PIC)", [
        (r"$i=\lfloor x_j/\Delta x\rfloor,\quad f=x_j/\Delta x-i:\quad"
         r"n_i\leftarrow n_i+\dfrac{w}{\Delta x}(1-f),\ \ n_{i+1}\leftarrow n_{i+1}+\dfrac{w}{\Delta x}f$",
         "1) взвешивание CIC: частица делится между двумя узлами; w = n_s L/N — вес [м⁻²]"),
        (r"$\rho_g=\sum_s q_s n_{s,g},\qquad E_k=F(k)\,\dfrac{\rho_k}{ik\,\varepsilon_0},\qquad F=\cos^4\dfrac{k\Delta x}{2}$",
         "2) поле через БПФ; F — двойное сглаживание (1,2,1)/4 против шума сетки"),
        (r"$E(x_j)=(1-f)\,E_i+f\,E_{i+1}$",
         "3) интерполяция поля в точку частицы теми же весами"),
        (r"$u^{n+1/2}=u^{n-1/2}+\dfrac{q_s}{m_s}E^n\Delta t,\quad v=\dfrac{u}{\sqrt{1+u^2/c^2}},\quad x^{n+1}=x^n+v^{n+1/2}\Delta t$",
         "4) «чехарда» (leapfrog) для u = γv: 2-й порядок, сохраняет фазовый объём"),
        (r"$\omega_p\Delta t<2,\qquad \dfrac{\delta\omega}{\omega}\approx\dfrac{(\omega_p\Delta t)^2}{24}"
         r"=4\cdot10^{-4}$",
         "устойчивость и ошибка частоты при Δt = 0.1/ω_p"),
        (r"$\gamma_{изм}=\dfrac{d\,\ln A_m}{dt},\qquad \omega_{изм}=-\dfrac{d\,\arg E_{k_m}}{dt},\qquad"
         r"A_m=2|E_{k_m}|,\ k_m=\dfrac{2\pi m}{L}$",
         "измерение по истории счёта (МНК на отрезке линейной стадии)"),
    ]))
    P.append(("4. Нелинейная стадия: захват, насыщение, плато", [
        (r"$\dfrac{d\hat E}{dt}=\dfrac{e\,n_b\,\omega_p}{\varepsilon_0 k}\langle e^{-i\psi_j}\rangle,\quad"
         r"\dfrac{d\psi_j}{dt}=kv_j-\omega_p,\quad \dfrac{dp_j}{dt}=-e\,\mathrm{Re}\,(\hat E e^{i\psi_j})$",
         "одноволновая модель (уравнение огибающей), решается методом Рунге–Кутты 4"),
        (r"$\omega_B=\sqrt{\dfrac{e\,k\,E_0}{m\gamma_\phi^3}},\qquad (v-v_\phi)^2=\dfrac{2eE_0}{mk}\,(1-\sin(kx+\varphi))$",
         "баунс-частота захваченного электрона и сепаратриса (граница ямы; здесь — при v ≪ c)"),
        (r"$\omega_B\approx1.77\,\gamma\ \Rightarrow\ E_{sat}=3.12\,\dfrac{\gamma^2 m\gamma_\phi^3}{e\,k}\propto"
         r"\left(\dfrac{n_b}{n_p}\right)^{2/3}v_b\sqrt{n_p}$",
         "теория захвата [В/м]: константа 1.77 получена одноволновой моделью"),
        (r"$K_{плато}=n_b m\,\dfrac{v_1^2+v_1v_2+v_2^2}{6},\qquad W_E^{КЛ}=\dfrac{K_{b0}-K_{плато}}{2}$",
         "квазилинейный баланс [Дж/м³]: плато f = const на [v₁, v₂]; половина энергии волны — поле"),
        (r"$v_1=0,\ v_2=v_b:\qquad W_E^{КЛ}=\dfrac{K_{b0}}{3}=\dfrac{n_b m v_b^2}{6}$",
         "полная квазилинейная релаксация холодного пучка (верхняя оценка)"),
    ]))
    P.append(("5. Ионы, каверны и солитоны (уравнения Захарова)", [
        (r"$i\dfrac{\partial\tilde E}{\partial t}+\dfrac{3v_{Te}^2}{2\omega_p}\dfrac{\partial^2\tilde E}{\partial x^2}"
         r"=\dfrac{\omega_p}{2}\,\dfrac{\delta n}{n}\,\tilde E,\qquad E=\mathrm{Re}\,[\tilde E\,e^{-i\omega_pt}]$",
         "огибающая ленгмюровской волны; справа — нелинейный сдвиг частоты δω = ω_p·δn/2n"),
        (r"$\dfrac{\partial^2}{\partial t^2}\dfrac{\delta n}{n}-c_s^2\dfrac{\partial^2}{\partial x^2}\dfrac{\delta n}{n}"
         r"=\dfrac{\varepsilon_0}{4n\,m_i}\dfrac{\partial^2|\tilde E|^2}{\partial x^2},\qquad c_s=\sqrt{\dfrac{k_B(T_e+3T_i)}{m_i}}$",
         "ионный звук под действием высокочастотного давления (пондеромоторной силы)"),
        (r"$W=\dfrac{\varepsilon_0|\tilde E|^2}{4n\,k_BT_e}:\qquad \tilde E=E_m\,\mathrm{sech}\dfrac{x}{\Delta},\quad"
         r"\dfrac{\delta n}{n}=-\dfrac{W_m}{\tau}\,\mathrm{sech}^2\dfrac{x}{\Delta},\quad \Delta=\lambda_D\sqrt{\dfrac{6\tau}{W_m}}$",
         "ленгмюровский солитон (каверна): яма концентрации удерживает поле; τ = 1 + 3T_i/T_e"),
        (r"$(\Omega^2-c_s^2q^2)\,[(\Omega-qV_g)^2-\delta^2]=W_0\dfrac{k_BT_e}{m_i}q^2\omega_p\delta,\qquad"
         r"\delta=\dfrac{3q^2v_{Te}^2}{2\omega_p},\ V_g=\dfrac{3v_{Te}^2k_0}{\omega_p}$",
         "модуляционная неустойчивость однородной волны: γ_мод = max Im Ω (многочлен 4-й степени)"),
        (r"$\gamma_L=\sqrt{\dfrac{\pi}{8}}\,\dfrac{\omega_p}{(k\lambda_D)^3}\exp\left(-\dfrac{1}{2k^2\lambda_D^2}-\dfrac{3}{2}\right)$",
         "затухание Ландау: каверна сжимается до нескольких λ_D, и волны поглощаются электронами"),
    ]))
    ex = passport(params)
    p = ex["p"]
    P.append(("6. Паспорт плазмы: числа в СИ для текущих параметров", [
        (rf"$n_p={_sci(p.n_p)}\ \mathrm{{м^{{-3}}}},\ T_e={_sci(p.T_e)}\ \mathrm{{К}}:\quad"
         rf"\omega_p={_sci(ex['wp'])}\ \mathrm{{с^{{-1}}}},\quad f_p={_sci(ex['fp'])}\ \mathrm{{Гц}}$",
         f"плазменная частота; период колебаний 1/f_p = {1 / ex['fp']:.3g} с"),
        (rf"$\lambda_D={_sci(ex['lD'])}\ \mathrm{{м}},\qquad v_{{Te}}={_sci(ex['vte'])}\ \mathrm{{м/с}},\qquad"
         rf"\nu_{{ei}}={_sci(ex['nu'])}\ \mathrm{{с^{{-1}}}}$",
         "дебаевский радиус, тепловая скорость, частота столкновений (ν_ei ≪ γ: плазма бесстолкновительная)"),
        (rf"$v_b={_sci(p.vb)}\ \mathrm{{м/с}}:\quad \gamma_b={ex['gb']:.4f},\quad "
         rf"(\gamma_b-1)mc^2={_sci(ex['Wb'])}\ \mathrm{{Дж}}$",
         "скорость, лоренц-фактор и кинетическая энергия одного электрона пучка"),
        (rf"$\lambda=\dfrac{{2\pi}}{{k_{{max}}}}={_sci(ex['lam'])}\ \mathrm{{м}},\qquad "
         rf"\gamma_{{max}}={_sci(ex['g'])}\ \mathrm{{с^{{-1}}}},\qquad 1/\gamma_{{max}}={_sci(1 / ex['g'])}\ \mathrm{{с}}$",
         f"самая неустойчивая волна при n_b/n_p = {p.alpha:g}"),
        (rf"$E_{{sat}}\approx3.12\,\dfrac{{\gamma^2m\gamma_\phi^3}}{{ek}}={_sci(ex['Esat'])}\ \mathrm{{В/м}},\qquad"
         rf"\dfrac{{m\omega_pv_b}}{{e}}={_sci(ex['Eunit'])}\ \mathrm{{В/м}}$",
         "поле насыщения и характерный масштаб поля"),
        (r"$\gamma\propto\sqrt{n_p}\,/\gamma_b;\qquad k_{max}\propto \sqrt{n_p}/v_b;\qquad E_{sat}\propto \sqrt{n_p}\,v_b$",
         "как всё меняется с концентрацией плазмы и скоростью пучка (v_b ≪ c)"),
    ]))
    return P


class FormulasWindow:
    def __init__(self, page=0, params=None):
        style.use(style.current_theme())
        self.pages = pages(params)
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
            f.text(0.05, y, formula, fontsize=14, color=C["text"], va="center")
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
