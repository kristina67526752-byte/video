"""
Уравнения огибающей ленгмюровской волны с нелинейным сдвигом частоты
(уравнения Захарова) и ленгмюровские солитоны.  Всё в СИ.

Это второе прочтение подсказки задания: «используйте уравнения для огибающей
волны с нелинейным сдвигом частоты».  Высокочастотное поле записывается как

    E(x,t) = Re[ Ẽ(x,t)·exp(−iω_p t) ],                       [Ẽ] = В/м,

Ẽ(x,t) — медленная комплексная огибающая.  Плазма квазинейтральна, её медленное
возмущение концентрации ν(x,t) = δn/n₀ (безразмерная доля).

Уравнения
---------
    i ∂Ẽ/∂t + (3v_Te²/2ω_p)·∂²Ẽ/∂x² = (ω_p/2)·ν·Ẽ                         (1)
    ∂²ν/∂t² − c_s² ∂²ν/∂x² = (ε₀/(4 n₀ m_i))·∂²|Ẽ|²/∂x²                    (2)

(1): ленгмюровская волна в плазме с локальной концентрацией n₀(1 + ν) имеет
     частоту ω_p(1 + ν/2) — это и есть НЕЛИНЕЙНЫЙ СДВИГ ЧАСТОТЫ: волна сама
     меняет ν.  Слагаемое с v_Te² — дисперсия Бома–Гросса ω ≈ ω_p + 3k²v_Te²/2ω_p.
(2): ионный звук (скорость c_s = √(k_B(T_e + 3T_i)/m_i)), который возбуждается
     силой высокочастотного давления (пондеромоторной силой): поле выталкивает
     плазму из областей, где оно сильнее.
Добавлены реальные потери: затухание Ландау ленгмюровских волн γ_L(k) и
ионного звука (в пространстве Фурье).

Статический предел (медленные возмущения): из (2) ν = −ε₀|Ẽ|²/(4n₀m_ic_s²), и (1)
становится нелинейным уравнением Шрёдингера с кубической нелинейностью:
сдвиг частоты δω = −ω_p·ε₀|Ẽ|²/(8 n₀ m_i c_s²) ∝ −|Ẽ|².

Солитон (точное решение, движется со скоростью V < c_s)
-------------------------------------------------------
    Ẽ = E_m·sech((x − Vt)/Δ)·exp(i(κx − Ωt)),     ν = −ν_m·sech²((x − Vt)/Δ),
    W_m = ε₀E_m²/(4 n₀ k_B T_e),  τ = 1 + 3T_i/T_e,  M = V/c_s,
    ν_m = W_m/(τ(1 − M²)),     Δ = λ_D·√(6τ(1 − M²)/W_m),
    κ = V ω_p/(3 v_Te²),       Ω = (3v_Te²/2ω_p)(κ² − 1/Δ²).
Яма концентрации удерживает поле, а поле своим давлением удерживает яму.

Численный метод
---------------
Псевдоспектральный метод расщепления (split-step Fourier), 2-й порядок:
линейная часть (1) интегрируется точно в пространстве Фурье, нелинейная —
точно в координатном; уравнение (2) для каждой гармоники — осциллятор с
вынуждающей силой, шаг которого делается по точной формуле.
Инвариант (без затухания): N = ∫|Ẽ|² dx — «число плазмонов».
"""
from __future__ import annotations

import numpy as np

from .constants import (E_CHARGE, M_E, EPS0, K_B, IONS, plasma_frequency, thermal_velocity,
                        debye_length, ion_sound_speed, landau_damping_rate)


class Zakharov:
    def __init__(self, n_p=1.0e16, T_e=3.0e4, T_i=3.0e3, ion="H+", L=0.0856, ng=1024,
                 dt_wp=0.5, damping=True):
        self.n_p, self.T_e, self.T_i, self.ion = n_p, T_e, T_i, ion
        self.m_i = IONS[ion]
        self.wp = float(plasma_frequency(n_p))                 # рад/с
        self.vte = float(thermal_velocity(T_e))                # м/с
        self.lambda_D = float(debye_length(n_p, T_e))          # м
        self.cs = float(ion_sound_speed(T_e, T_i, self.m_i))   # м/с
        self.tau = 1.0 + 3.0 * T_i / T_e
        self.nT = n_p * K_B * T_e                              # n₀k_BT_e, Дж/м³
        self.L, self.ng = L, ng
        self.dx = L / ng
        self.x = np.arange(ng) * self.dx
        self.k = 2 * np.pi * np.fft.fftfreq(ng, d=self.dx)     # рад/м
        self.dt = dt_wp / self.wp
        self.t = 0.0
        self.P = 1.5 * self.vte ** 2 / self.wp                 # коэффициент дисперсии, м²/с
        self.damping = damping
        if damping:
            self.nu_L = landau_damping_rate(self.k, n_p, T_e)  # с⁻¹
            dlt = np.sqrt(np.pi / 8) * (np.sqrt(M_E / self.m_i)
                                        + (T_e / T_i) ** 1.5 * np.exp(-T_e / (2 * T_i) - 1.5)
                                        if T_i > 0 else np.sqrt(M_E / self.m_i))
            self.nu_s = dlt * np.abs(self.k) * self.cs         # затухание ионного звука, с⁻¹
        else:
            self.nu_L = np.zeros(ng)
            self.nu_s = np.zeros(ng)
        self.E = np.zeros(ng, dtype=complex)                   # огибающая Ẽ, В/м
        self.nk = np.zeros(ng, dtype=complex)                  # ν_k
        self.dnk = np.zeros(ng, dtype=complex)                 # dν_k/dt
        self._setup()
        self.hist_t, self.hist_N, self.hist_Wmax, self.hist_numin = [], [], [], []

    # ------------------------------------------------------------------
    def _setup(self):
        dt = self.dt
        k = self.k
        # (1): линейный полушаг в пространстве Фурье
        self._lin_half = np.exp((-1j * self.P * k * k - self.nu_L) * dt / 2)
        # Гармоники с kλ_D > 1 отбрасываются: ленгмюровских волн с такими k в плазме нет
        # (затухают за период), а в счёте они дают ложный резонанс метода расщепления
        # (нужно 3(kλ_D)²·ω_pΔt/2 < π).
        self._mask = (np.abs(k) * self.lambda_D <= 1.0)
        self._lin_half = self._lin_half * self._mask
        # (2): точный полушаг затухающего осциллятора ν̈ + 2ν_s ν̇ + c_s²k²ν = F
        w2 = (self.cs * k) ** 2
        Om = np.sqrt(np.maximum(w2 - self.nu_s ** 2, 1e-300))
        h = dt / 2
        self._c, self._s = np.cos(Om * h), np.sin(Om * h)
        self._e = np.exp(-self.nu_s * h)
        self._Om = Om
        # равновесное ν при постоянной силе: ν_eq = −ε₀(|Ẽ|²)_k/(4 n₀ m_i c_s²)
        self._feq = -EPS0 / (4.0 * self.n_p * self.m_i * self.cs ** 2)

    def _ion_half(self):
        I = np.fft.fft(np.abs(self.E) ** 2)
        neq = self._feq * I
        neq[0] = 0.0
        a = self.nk - neq
        b = (self.dnk + self.nu_s * a) / self._Om
        a_new = self._e * (a * self._c + b * self._s)
        da_new = self._e * (-a * self._Om * self._s + b * self._Om * self._c) - self.nu_s * a_new
        self.nk = (a_new + neq) * self._mask
        self.dnk = da_new * self._mask
        self.nk[0] = 0.0
        self.dnk[0] = 0.0

    def step(self, nsteps=1):
        for _ in range(nsteps):
            self._ion_half()
            E = np.fft.ifft(np.fft.fft(self.E) * self._lin_half)
            nu = np.fft.ifft(self.nk).real
            E *= np.exp(-0.5j * self.wp * nu * self.dt)          # нелинейный сдвиг частоты
            self.E = np.fft.ifft(np.fft.fft(E) * self._lin_half)
            self._ion_half()
            self.t += self.dt
        self._record()

    def _record(self):
        self.hist_t.append(self.t)
        self.hist_N.append(self.plasmons())
        self.hist_Wmax.append(float(self.W().max()))
        self.hist_numin.append(float(self.nu().min()))

    # ------------------------------------------------------------------ величины
    def nu(self):
        """Возмущение концентрации δn/n₀ (доля)."""
        return np.fft.ifft(self.nk).real

    def W(self):
        """Локальный уровень поля W(x) = ε₀|Ẽ|²/(4 n₀ k_B T_e)."""
        return EPS0 * np.abs(self.E) ** 2 / (4.0 * self.nT)

    def plasmons(self):
        """Инвариант N = ∫|Ẽ|² dx, В²/м."""
        return float(np.sum(np.abs(self.E) ** 2) * self.dx)

    def field_from_W(self, W):
        """Амплитуда огибающей [В/м] по уровню W:  E = √(4 n₀ k_B T_e W/ε₀)."""
        return np.sqrt(4.0 * self.nT * W / EPS0)

    # ------------------------------------------------------------------ начальные условия
    def soliton_params(self, W_m, mach=0.0):
        """Параметры точного солитона: (E_m [В/м], Δ [м], ν_m, κ [рад/м], V [м/с])."""
        f = self.tau * (1.0 - mach ** 2)
        return (float(self.field_from_W(W_m)), self.lambda_D * np.sqrt(6.0 * f / W_m),
                W_m / f, mach * self.cs * self.wp / (3.0 * self.vte ** 2), mach * self.cs)

    def add_soliton(self, W_m, x0, mach=0.0, phase=0.0):
        """Добавить точный солитон с уровнем поля W_m в точке x0, скорость V = mach·c_s."""
        Em, D, num, kap, V = self.soliton_params(W_m, mach)
        xi = (self.x - x0 + 0.5 * self.L) % self.L - 0.5 * self.L       # периодическая координата
        s = 1.0 / np.cosh(xi / D)
        self.E = self.E + Em * s * np.exp(1j * (kap * xi + phase))
        nu = -num * s * s
        self.nk = self.nk + np.fft.fft(nu - nu.mean())
        # ν(x − Vt): dν/dt = −V ∂ν/∂x
        self.dnk = self.dnk + (-V) * 1j * self.k * np.fft.fft(nu)
        self.hist_t, self.hist_N, self.hist_Wmax, self.hist_numin = [], [], [], []
        self._record()

    def set_pump(self, W0, k0, noise=1e-4, seed=1):
        """Однородная волна накачки Ẽ = E₀·exp(ik₀x) (насыщенная пучковая волна) и
        слабый шум концентрации с амплитудой noise (тепловые флуктуации)."""
        m0 = int(round(k0 * self.L / (2 * np.pi)))
        self.k0 = 2 * np.pi * m0 / self.L
        self.E = self.field_from_W(W0) * np.exp(1j * self.k0 * self.x)
        rng = np.random.default_rng(seed)
        nu = noise * rng.standard_normal(self.ng)
        nk = np.fft.fft(nu - nu.mean())
        nk[np.abs(self.k) * self.lambda_D > 0.5] = 0.0        # шум только в длинных волнах
        self.nk = nk
        self.dnk = np.zeros(self.ng, dtype=complex)
        self.hist_t, self.hist_N, self.hist_Wmax, self.hist_numin = [], [], [], []
        self._record()

    # ------------------------------------------------------------------ анализ
    def fit_soliton(self):
        """Параметры самого сильного пика огибающей: уровень W_m, положение x_m,
        измеренная ширина Δ_изм (по ширине на полувысоте |Ẽ|²: FWHM = 1.763·Δ для sech²)
        и теоретическая ширина Δ_теор = λ_D√(6τ/W_m) для покоящегося солитона."""
        W = self.W()
        i = int(np.argmax(W))
        Wm = float(W[i])
        half = 0.5 * Wm
        n = self.ng

        def edge(step):
            j = i
            for c in range(n // 2):
                jn = (j + step) % n
                if W[jn] < half:
                    fr = (W[j] - half) / max(W[j] - W[jn], 1e-300)
                    return c + fr
                j = jn
            return np.nan
        fwhm = (edge(+1) + edge(-1)) * self.dx
        d_meas = fwhm / (2 * np.arccosh(np.sqrt(2.0)))
        d_th = self.lambda_D * np.sqrt(6.0 * self.tau / max(Wm, 1e-300))
        return dict(W_m=Wm, x_m=float(self.x[i]), E_m=float(np.abs(self.E[i])),
                    delta=float(d_meas), delta_th=float(d_th), nu_min=float(self.nu()[i]),
                    nu_th=-Wm / self.tau)


def modulational_growth(q, W0, k0, n_p, T_e, T_i, ion="H+"):
    """Инкремент модуляционной (распадной) неустойчивости однородной накачки
    Ẽ = E₀e^{ik₀x} по линейной теории уравнений Захарова, с⁻¹.

    Возмущение концентрации ∝ e^{i(qx − Ωt)} связывает накачку с сателлитами
    k₀ ± q.  Дисперсионное уравнение — многочлен 4-й степени по Ω:
        (Ω² − c_s²q²)·[(Ω − qV_g)² − δ²] = W₀·(k_BT_e/m_i)·q²·ω_p·δ ,
    где V_g = 3v_Te²k₀/ω_p — групповая скорость накачки, δ = 3q²v_Te²/(2ω_p),
    W₀ = ε₀E₀²/(4n₀k_BT_e).  Решается точно (корни многочлена), как и уравнение
    пучка.  Возвращает max Im Ω для каждого q."""
    q = np.atleast_1d(np.asarray(q, dtype=float))
    m_i = IONS[ion]
    wp = float(plasma_frequency(n_p))
    vte = float(thermal_velocity(T_e))
    cs = float(ion_sound_speed(T_e, T_i, m_i))
    Vg = 3.0 * vte ** 2 * k0 / wp
    out = np.zeros(q.size)
    for j, qq in enumerate(q):
        if qq == 0:
            continue
        # нормировка частоты на ω₀ = c_s|q| + δ + |qV_g| — для устойчивости поиска корней
        d = 1.5 * qq * qq * vte ** 2 / wp
        w0 = cs * abs(qq) + d + abs(qq * Vg)
        a, b, dd = (cs * qq / w0) ** 2, qq * Vg / w0, d / w0
        rhs = W0 * (K_B * T_e / m_i) * qq * qq * wp * d / w0 ** 4
        # (Ω² − a)((Ω − b)² − dd²) − rhs = 0
        p1 = np.array([1.0, 0.0, -a])
        p2 = np.array([1.0, -2.0 * b, b * b - dd * dd])
        poly = np.polymul(p1, p2)
        poly[-1] -= rhs
        out[j] = max(np.roots(poly).imag.max(), 0.0) * w0
    return out
