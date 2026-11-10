"""
Одноволновая модель (модель огибающей): одна волна + частицы пучка.  Всё в СИ.

Это первое прочтение подсказки задания: «уравнения для огибающей волны
с нелинейным сдвигом частоты».  Поле считается одной волной

    E(x,t) = Re[ Ê(t) · exp(i(kx − ω_p t)) ],        [Ê] = В/м,

у которой медленно меняется комплексная амплитуда Ê = |Ê|·e^{iθ} (огибающая).
Плазма описывается линейно (её отклик и даёт ω_p), электроны пучка — точными
(релятивистскими) уравнениями движения в поле волны.

Вывод уравнения для огибающей
-----------------------------
Смещение электронов плазмы ξ подчиняется  m ξ̈ = −eE.  Из теоремы Гаусса
поле  E = (e n_p/ε₀)·ξ + E_b,  где E_b — поле, созданное возмущением плотности
пучка δn_b:  ε₀ ∂E_b/∂x = −e δn_b.  Отсюда

    Ë + ω_p² E = Ë_b ,        ω_p² = n_p e²/(ε₀ m):

плазма — это осциллятор с частотой ω_p, который «раскачивает» пучок.
Гармоника плотности пучка: δn_b = 2 n_b Re[⟨e^{−iψ_j}⟩ e^{i(kx − ω_p t)}], поэтому
Ê_b = (2i e n_b/(ε₀ k))·⟨e^{−iψ_j}⟩.  Для медленной амплитуды (|dÊ/dt| ≪ ω_p|Ê|)

    dÊ/dt = (e n_b ω_p/(ε₀ k)) · ⟨exp(−iψ_j)⟩,     ψ_j = k x_j − ω_p t      (A)

⟨…⟩ — среднее по частицам пучка.  Пока пучок однороден, ⟨e^{−iψ}⟩ = 0 и
волна не растёт; как только пучок сгруппировался в сгустки — растёт.

Частицы пучка (электроны, p = γ m v):

    dψ_j/dt = k v_j − ω_p,      dp_j/dt = −e·Re[ Ê · exp(iψ_j) ]            (B)

Линеаризация (A)+(B) при k v_b = ω_p даёт s³ = i n_b ω_p³/(2 n_p γ_b³), т.е.
    γ = (√3/2)(n_b/2n_p)^{1/3} ω_p/γ_b,   ω = ω_p[1 − ½(n_b/2n_p)^{1/3}/γ_b]
— это асимптотика слабого пучка (точное уравнение 4-й степени даёт чуть
меньший γ, разница ≈ 8 % при n_b/n_p = 0.01).

Сдвиг частоты: ω(t) = ω_p − dθ/dt, θ = arg Ê.  В линейной стадии
δω = −½(n_b/2n_p)^{1/3} ω_p/γ_b, после захвата частота меняется — это и есть
«нелинейный сдвиг частоты».

Точный интеграл движения (проверка численного счёта), кг·м/с на м³:
    P = n_b⟨p⟩ + ε₀ k |Ê|²/(2ω_p) = const        (импульс пучка + импульс волны)

Интегрирование — метод Рунге–Кутты 4-го порядка.
"""
from __future__ import annotations

import numpy as np

from .constants import E_CHARGE, M_E, EPS0, C_LIGHT, plasma_frequency, lorentz_gamma


class SingleWave:
    def __init__(self, n_p=1.0e16, alpha=0.01, vb=1.0e7, n=2048, k=None, dvb=0.0,
                 E0=None, dt_wp=0.05):
        self.n_p, self.alpha, self.vb, self.n = n_p, alpha, vb, n
        self.wp = float(plasma_frequency(n_p))           # рад/с
        self.dt = dt_wp / self.wp                         # с
        self.k = self.wp / vb if k is None else k         # резонанс k v_b = ω_p, рад/м
        self.gamma_b = float(lorentz_gamma(vb))
        self.E_unit = M_E * self.wp * vb / E_CHARGE       # характерное поле m ω_p v_b/e, В/м
        # частицы равномерно по фазе на одной длине волны (тихий старт)
        self.psi = 2 * np.pi * (np.arange(n) + 0.5) / n
        if dvb > 0:
            from .pic import _quiet_gaussian
            v = np.clip(vb + dvb * _quiet_gaussian(n), -0.9995 * C_LIGHT, 0.9995 * C_LIGHT)
        else:
            v = np.full(n, float(vb))
        self.u = v * lorentz_gamma(v)                     # u = γv, м/с
        self.E = complex(1e-6 * self.E_unit if E0 is None else E0)      # В/м
        self._coef = E_CHARGE * alpha * n_p * self.wp / (EPS0 * self.k)  # множитель в (A)
        self._qm = E_CHARGE / M_E
        self.t = 0.0
        self.gamma_th = np.sqrt(3) / 2 * np.cbrt(alpha / 2) * self.wp / self.gamma_b
        self.domega_th = -0.5 * np.cbrt(alpha / 2) * self.wp / self.gamma_b
        self.P0 = self.momentum()
        self.hist_t, self.hist_E = [0.0], [self.E]
        self.hist_P = [self.P0]

    @property
    def v(self):
        """Скорости частиц пучка, м/с."""
        return self.u / np.sqrt(1.0 + (self.u / C_LIGHT) ** 2)

    # правая часть системы (A)+(B)
    def rhs(self, psi, u, E):
        e = np.exp(1j * psi)
        v = u / np.sqrt(1.0 + (u / C_LIGHT) ** 2)
        dpsi = self.k * v - self.wp
        du = -self._qm * (E * e).real
        dE = self._coef * np.mean(np.conj(e))
        return dpsi, du, dE

    def step(self, nsteps=1):
        h = self.dt
        for _ in range(nsteps):
            p, u, E = self.psi, self.u, self.E
            k1 = self.rhs(p, u, E)
            k2 = self.rhs(p + 0.5*h*k1[0], u + 0.5*h*k1[1], E + 0.5*h*k1[2])
            k3 = self.rhs(p + 0.5*h*k2[0], u + 0.5*h*k2[1], E + 0.5*h*k2[2])
            k4 = self.rhs(p + h*k3[0], u + h*k3[1], E + h*k3[2])
            self.psi = p + h/6*(k1[0] + 2*k2[0] + 2*k3[0] + k4[0])
            self.u = u + h/6*(k1[1] + 2*k2[1] + 2*k3[1] + k4[1])
            self.E = E + h/6*(k1[2] + 2*k2[2] + 2*k3[2] + k4[2])
            self.t += h
            self.hist_t.append(self.t)
            self.hist_E.append(self.E)
            self.hist_P.append(self.momentum())

    def momentum(self):
        """Плотность импульса пучка + волны, кг·м/с на м³."""
        return (self.alpha * self.n_p * M_E * np.mean(self.u)
                + 0.5 * EPS0 * self.k * abs(self.E) ** 2 / self.wp)

    # --- удобные величины
    @property
    def amp(self):
        return abs(self.E)

    def omega_B(self, E=None):
        """Баунс-частота захваченного электрона на дне ямы: ω_B = √(e k|Ê|/(m γ_b³)), рад/с."""
        E = abs(self.E) if E is None else abs(E)
        return np.sqrt(E_CHARGE * self.k * E / (M_E * self.gamma_b ** 3))

    def series(self):
        t = np.array(self.hist_t)
        E = np.array(self.hist_E)
        th = np.unwrap(np.angle(E))
        # мгновенная частота ω = ω_p − dθ/dt
        w = self.wp - np.gradient(th, t) if len(t) > 2 else np.full_like(t, self.wp)
        return t, np.abs(E), w, np.array(self.hist_P)


def saturation_constant(alpha=0.01, vb=1.0e7, n_p=1.0e16, n=4096, dt_wp=0.02, tmax=None):
    """Универсальная константа насыщения холодного пучка в одноволновой модели:
        C = e k E_sat/(m γ_b³ γ²) = (ω_B/γ)²  в первом максимуме амплитуды.
    В этой модели при k v_b = ω_p и v_b ≪ c отношение n_b/n_p убирается
    масштабированием, так что C не зависит ни от плотности пучка, ни от n_p, ни
    от v_b — это число и есть «теория захвата».
    Возвращает (C, ω_B/γ, γ·t_sat)."""
    sw = SingleWave(n_p=n_p, alpha=alpha, vb=vb, n=n, dt_wp=dt_wp)
    sw.E = complex(1e-7 * sw.E_unit)
    sw.hist_E[0] = sw.E
    g = sw.gamma_th
    tmax = tmax or 30.0 / g
    prev = 0.0
    floor = 1e-3 * alpha ** (2 / 3) * sw.E_unit
    while sw.t < tmax:
        sw.step(10)
        a = sw.amp
        if a < prev and a > floor:
            break
        prev = a
    t, A, _, _ = sw.series()
    i = int(np.argmax(A))
    wB = sw.omega_B(A[i])
    return (wB / g) ** 2, wB / g, t[i] * g
