"""
Одноволновая модель (модель огибающей): одна волна + частицы пучка.

Это то, что предлагает подсказка задания: «уравнения для огибающей волны
с нелинейным сдвигом частоты».  Поле считается одной волной

    E(x,t) = Re[ Ê(t) · exp(i(kx − ω_p t)) ],

у которой медленно меняется комплексная амплитуда Ê = |Ê|·e^{iθ}
(огибающая).  Плазма описывается линейно (её отклик и даёт ω_p),
электроны пучка — точными уравнениями движения в поле волны.

Вывод уравнения для огибающей (безразмерные единицы, ω_p = 1)
------------------------------------------------------------
Смещение электронов плазмы ξ подчиняется  ξ̈ = −E,  а поле  E = ξ + E_b,
где E_b — поле, созданное возмущением плотности пучка δn_b
(из уравнения Пуассона ∂E_b/∂x = −δn_b).  Отсюда  ξ̈ + ξ = −E_b:
плазма — это осциллятор с частотой ω_p, который «раскачивает» пучок.
Для гармоники exp(i(kx − t)) с медленной амплитудой (|dÊ/dt| ≪ |Ê|):

    dÊ/dt = (α/k) · ⟨exp(−iψ_j)⟩,   ψ_j = k x_j − t          (A)

⟨…⟩ — среднее по частицам пучка.  Пока пучок однороден, ⟨e^{−iψ}⟩ = 0 и
волна не растёт; как только пучок сгруппировался в сгустки — растёт.

Частицы пучка (электроны: dv/dt = −E):

    dψ_j/dt = k v_j − 1,      dv_j/dt = −Re[ Ê · exp(iψ_j) ]     (B)

Линеаризация (A)+(B) при k v_b = 1 даёт s³ = iα/2, т.е.
    γ = (√3/2)(α/2)^{1/3},   ω = 1 − ½(α/2)^{1/3}
— это асимптотика слабого пучка (точное уравнение 4-й степени даёт чуть
меньший γ, разница ≈ 8 % при α = 0.01).

Сдвиг частоты: ω(t) = 1 − dθ/dt, θ = arg Ê.  В линейной стадии
δω = −½(α/2)^{1/3}, после захвата частота меняется — это и есть
«нелинейный сдвиг частоты».

Точный интеграл движения (проверка численного счёта):
    P = α⟨v⟩ + (k/2)|Ê|² = const        (импульс пучка + импульс волны)

Интегрирование — метод Рунге–Кутты 4-го порядка.
"""
from __future__ import annotations

import numpy as np


class SingleWave:
    def __init__(self, alpha=0.01, vb=1.0, n=2048, k=None, dvb=0.0, E0=1e-6, dt=0.05):
        self.alpha, self.vb, self.n, self.dt = alpha, vb, n, dt
        self.k = 1.0 / vb if k is None else k          # резонанс k v_b = ω_p
        # частицы равномерно по фазе на одной длине волны (тихий старт)
        self.psi = 2 * np.pi * (np.arange(n) + 0.5) / n
        if dvb > 0:
            from .pic import _quiet_gaussian
            self.v = vb + dvb * vb * _quiet_gaussian(n)
        else:
            self.v = np.full(n, float(vb))
        self.E = complex(E0)
        self.t = 0.0
        self.gamma_th = np.sqrt(3) / 2 * np.cbrt(alpha / 2)
        self.domega_th = -0.5 * np.cbrt(alpha / 2)
        self.P0 = self.momentum()
        self.hist_t, self.hist_E = [0.0], [self.E]
        self.hist_P = [self.P0]

    # правая часть системы (A)+(B)
    def rhs(self, psi, v, E):
        e = np.exp(1j * psi)
        dpsi = self.k * v - 1.0
        dv = -(E * e).real
        dE = self.alpha / self.k * np.mean(np.conj(e))
        return dpsi, dv, dE

    def step(self, nsteps=1):
        h = self.dt
        for _ in range(nsteps):
            p, v, E = self.psi, self.v, self.E
            k1 = self.rhs(p, v, E)
            k2 = self.rhs(p + 0.5*h*k1[0], v + 0.5*h*k1[1], E + 0.5*h*k1[2])
            k3 = self.rhs(p + 0.5*h*k2[0], v + 0.5*h*k2[1], E + 0.5*h*k2[2])
            k4 = self.rhs(p + h*k3[0], v + h*k3[1], E + h*k3[2])
            self.psi = p + h/6*(k1[0] + 2*k2[0] + 2*k3[0] + k4[0])
            self.v = v + h/6*(k1[1] + 2*k2[1] + 2*k3[1] + k4[1])
            self.E = E + h/6*(k1[2] + 2*k2[2] + 2*k3[2] + k4[2])
            self.t += h
            self.hist_t.append(self.t)
            self.hist_E.append(self.E)
            self.hist_P.append(self.momentum())

    def momentum(self):
        return self.alpha * np.mean(self.v) + 0.5 * self.k * abs(self.E) ** 2

    # --- удобные величины
    @property
    def amp(self):
        return abs(self.E)

    def omega_B(self):
        """Баунс-частота захваченного электрона на дне ямы: ω_B = √(k|Ê|)."""
        return np.sqrt(self.k * abs(self.E))

    def wave_frame_phase(self):
        """Фаза частицы относительно волны Φ = ψ + θ, приведённая к (−π, π]."""
        ph = self.psi + np.angle(self.E)
        return (ph + np.pi) % (2 * np.pi) - np.pi

    def series(self):
        t = np.array(self.hist_t)
        E = np.array(self.hist_E)
        th = np.unwrap(np.angle(E))
        # мгновенная частота ω = 1 − dθ/dt
        w = 1.0 - np.gradient(th, t) if len(t) > 2 else np.ones_like(t)
        return t, np.abs(E), w, np.array(self.hist_P)


def saturation_constant(alpha=0.01, n=4096, dt=0.02, tmax=None):
    """Универсальная константа насыщения холодного пучка в одноволновой модели:
    C = k·E_sat/γ² = (ω_B/γ)²  в первом максимуме амплитуды.
    В этой модели при k v_b = 1 параметр α убирается масштабированием, так что C
    не зависит от α — это число и есть «теория захвата»."""
    sw = SingleWave(alpha=alpha, n=n, dt=dt, E0=1e-7)
    g = sw.gamma_th
    tmax = tmax or 30.0 / g
    prev, rising = 0.0, True
    while sw.t < tmax:
        sw.step(10)
        a = sw.amp
        if a < prev and a > 1e-3 * alpha ** (2 / 3):
            break
        prev = a
    t, A, _, _ = sw.series()
    i = int(np.argmax(A))
    return sw.k * A[i] / g**2, np.sqrt(sw.k * A[i]) / g, t[i] * g
