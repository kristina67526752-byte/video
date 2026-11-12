"""
Обработка результатов счёта: инкремент, насыщение, баунс-частота, сепаратриса,
квазилинейный баланс, автоматическое определение стадий процесса.
Все величины — в СИ.

Все формулы этого файла — в docs/ОБЪЯСНЕНИЕ.md, разделы 6–8.
"""
from __future__ import annotations

import numpy as np

from .constants import E_CHARGE, M_E, EPS0, K_B, C_LIGHT, lorentz_gamma

# Константа насыщения холодного пучка, посчитанная одноволновой моделью
# (bpi.single_wave.saturation_constant): в первом максимуме амплитуды
#     (ω_B/γ)² = e·k·E_sat/(m γ_ф³ γ²) = 3.1235,   ω_B/γ = 1.7673.
# В этой модели n_b/n_p убирается масштабированием, поэтому число универсально.
C_TRAP = 3.1235
OMEGA_B_OVER_GAMMA = np.sqrt(C_TRAP)


def bounce_frequency(E0, k, gamma_ph=1.0):
    """Баунс-частота электрона на дне потенциальной ямы волны, рад/с:
        ω_B = √(e k E₀/(m γ_ф³)),
    E₀ — амплитуда волны [В/м], k [рад/м], γ_ф — лоренц-фактор при фазовой скорости
    (m γ_ф³ — релятивистская продольная масса; при v ≪ c γ_ф = 1)."""
    return np.sqrt(E_CHARGE * k * np.abs(E0) / (M_E * gamma_ph ** 3))


def trapping_amplitude(gamma, k, gamma_ph=1.0):
    """Теория захвата: рост волны останавливается, когда электроны пучка
    успевают сделать примерно пол-оборота в яме волны, т.е. ω_B ≈ 1.77γ.
    Отсюда амплитуда насыщения, В/м:
        E_sat = C·γ²·m γ_ф³/(e k),   C = 3.12."""
    return C_TRAP * gamma ** 2 * M_E * gamma_ph ** 3 / (E_CHARGE * k)


def separatrix(x, E0, k, phase, v_ph):
    """Сепаратриса — граница потенциальной ямы волны E = E₀cos(kx + φ) на
    фазовой плоскости (x, v).  Возвращает (v_верх(x), v_низ(x)), м/с.

    Потенциальная энергия электрона U(x) = (eE₀/k)·sin(kx + φ).  В системе,
    движущейся с фазовой скоростью v_ф, сохраняется
        h = γ m c² − v_ф p + U(x).
    Сепаратриса проходит через вершину потенциала (U = eE₀/k, v = v_ф):
        γ m c² − v_ф p = m c²/γ_ф + ΔU(x) ≡ R(x),   ΔU = (eE₀/k)(1 − sin(kx + φ)).
    Решение квадратного уравнения для импульса:
        p = γ_ф² [R β_ф ± √(R² − (m c²/γ_ф)²)]/c.
    При v ≪ c это обычное (v − v_ф)² = 2ΔU/m: полуширина ямы 2√(eE₀/(mk))."""
    c = C_LIGHT
    bph = v_ph / c
    gph = 1.0 / np.sqrt(1.0 - bph * bph)
    mc2 = M_E * c * c
    dU = (E_CHARGE * abs(E0) / k) * (1.0 - np.sin(k * np.asarray(x) + phase))
    R = mc2 / gph + dU
    root = np.sqrt(np.maximum(dU * (2.0 * mc2 / gph + dU), 0.0))
    out = []
    for sgn in (+1.0, -1.0):
        u = gph ** 2 * (R * bph + sgn * root) / (M_E * c)        # u = p/m
        out.append(u / np.sqrt(1.0 + (u / c) ** 2))
    return out[0], out[1]


# --------------------------------------------------------------------------
# Квазилинейная теория: плато на функции распределения
# --------------------------------------------------------------------------
def ql_full_plateau_fraction():
    """Квазилинейная теория, полная релаксация холодного нерелятивистского пучка
    в плато [0, v_b]: плотность энергии пучка n_b m v_b²/2 → n_b m v_b²/6, т.е.
    пучок отдаёт 2/3 энергии.  Половина энергии ленгмюровской волны — электрическое
    поле, половина — колебания электронов плазмы.  Поэтому W_E = K_b0/3."""
    return 1.0 / 3.0


def plateau_energy(n_b, u1, u2):
    """Плотность кинетической энергии [Дж/м³] пучка с плоским распределением
    по импульсу на [u1, u2] (u = γv = p/m):
        K_пл = n_b m c² (⟨γ⟩ − 1),  ⟨γ⟩ = [F(u2) − F(u1)]/(u2 − u1),
        F(u) = ½[u√(1 + u²/c²) + c·arsh(u/c)].
    При v ≪ c:  K_пл = n_b m (v1² + v1v2 + v2²)/6."""
    c = C_LIGHT
    if abs(u2 - u1) < 1e-9 * (abs(u1) + abs(u2) + 1.0):
        return n_b * M_E * u1 * u1 / (np.sqrt(1 + (u1 / c) ** 2) + 1.0)
    if max(abs(u1), abs(u2)) < 0.02 * c:           # нерелятивистский предел без потери точности
        corr = 1.0 - 0.15 * (u1 ** 4 + u1 ** 3 * u2 + u1 ** 2 * u2 ** 2 + u1 * u2 ** 3 + u2 ** 4) \
            / (c * c * (u1 * u1 + u1 * u2 + u2 * u2))
        return n_b * M_E * (u1 * u1 + u1 * u2 + u2 * u2) / 6.0 * corr
    F = lambda u: 0.5 * (u * np.sqrt(1.0 + (u / c) ** 2) + c * np.arcsinh(u / c))
    return n_b * M_E * c * c * ((F(u2) - F(u1)) / (u2 - u1) - 1.0)


def plateau_edges(u, level=0.5, bins=200):
    """Края плато функции распределения: где f падает до level·(высота плато).
    Высота плато — медиана f по центральной части распределения."""
    lo, hi = np.percentile(u, [0.5, 99.5])
    pad = 0.05 * max(hi - lo, 1e-6 * (abs(hi) + abs(lo) + 1.0))
    h, e = np.histogram(u, bins=bins, range=(lo - pad, hi + pad))
    c = 0.5 * (e[1:] + e[:-1])
    nz = np.nonzero(h > 0)[0]
    core = h[nz[0]:nz[-1] + 1]
    top = np.median(core[core > np.percentile(core, 30)])
    above = np.nonzero(h >= level * top)[0]
    return c[above[0]], c[above[-1]]


def ql_prediction(sim):
    """Квазилинейный баланс энергии по измеренным краям плато.
    Пучок с плоским распределением на [v1, v2] имеет плотность энергии K_пл.
    Отданная энергия K_b0 − K_пл уходит в ленгмюровские волны, из неё
    половина — энергия поля:  W_E^КЛ = (K_b0 − K_пл)/2  [Дж/м³]."""
    u1, u2 = plateau_edges(sim.u[sim.sl[1]])
    K_pl = plateau_energy(sim.dens[1], u1, u2)
    to_v = lambda u: u / np.sqrt(1.0 + (u / C_LIGHT) ** 2)
    return dict(v1=float(to_v(u1)), v2=float(to_v(u2)), K_pl=float(K_pl),
                WE_ql=float(0.5 * (sim.K0_beam - K_pl)))


# --------------------------------------------------------------------------
# Измерения по истории счёта
# --------------------------------------------------------------------------
def fit_exp(t, a):
    """МНК-прямая по ln a(t): возвращает наклон (инкремент, с⁻¹) и R²."""
    y = np.log(a)
    t0 = t[0]
    T = max(t[-1] - t0, 1e-300)
    A = np.vstack([(t - t0) / T, np.ones_like(t)]).T       # время в долях окна — для устойчивости МНК
    coef, res, *_ = np.linalg.lstsq(A, y, rcond=None)
    ss = ((y - y.mean()) ** 2).sum()
    r2 = 1 - (res[0] / ss if res.size and ss > 0 else 0.0)
    return coef[0] / T, r2


def trap_level(sim):
    """Уровень насыщения главной волны по теории захвата, В/м."""
    return trapping_amplitude(sim.gamma_ref, sim.k_modes[sim.m_main],
                              float(lorentz_gamma(sim.v_phase)))


def linear_window(sim):
    """Окно линейной стадии [t1, t2], с:
    t1 = 4/γ — к этому времени затухают «лишние» корни дисперсионного уравнения
    (начальное возмущение возбуждает все 4 корня, растёт только один);
    t2 — момент, когда главная волна дорастает до 5 % от уровня насыщения
    (дальше начинают сказываться нелинейные эффекты)."""
    h = sim.hist
    t = h["t"]
    A = 2 * np.abs(h["Ek"][:, sim.m_main - 1])
    t1 = 4.0 / sim.gamma_ref
    A_lim = 0.05 * trap_level(sim)
    over = np.nonzero(A > A_lim)[0]
    t2 = t[over[0]] if over.size else t[-1] if t.size else 0.0
    return t1, t2


def measure_modes(sim, min_frac=0.5):
    """Инкремент γ и частота ω каждой моды ящика из истории E_k(t), рад/с.
    γ — наклон ln|E_k|,  ω = −d(arg E_k)/dt  (волна E ∝ cos(kx − ωt)).

    Оценка погрешности g_err: окно делится пополам, γ измеряется отдельно по каждой
    половине, g_err = |γ₁ − γ₂|/2. Если рост мода чисто экспоненциальный, половины
    дают одно и то же; если мода ещё не выделилась из шума или её искажают соседние
    корни, половины расходятся — и это видно в g_err."""
    h = sim.hist
    t = h["t"]
    t1, t2 = linear_window(sim)
    sel = (t >= t1) & (t <= t2)
    out = []
    if sel.sum() < 20:
        return out
    ts = t[sel]
    T = ts[-1] - ts[0]
    for m in range(1, sim.m_store + 1):
        gth = sim.gamma_modes_th[m - 1]
        if gth < min_frac * sim.gamma_ref:
            continue
        ek = h["Ek"][sel, m - 1]
        g, r2 = fit_exp(ts, np.abs(ek))
        nh = ts.size // 2
        g1 = fit_exp(ts[:nh], np.abs(ek[:nh]))[0]
        g2 = fit_exp(ts[nh:], np.abs(ek[nh:]))[0]
        ph = np.unwrap(np.angle(ek))
        w = -np.polyfit((ts - ts[0]) / T, ph, 1)[0] / T
        out.append(dict(m=m, k=sim.k_modes[m], g_th=gth, g=g, g_err=0.5 * abs(g1 - g2), r2=r2,
                        w_th=sim.omega_modes_th[m - 1], w=w))
    return out


def first_maximum(t, A, A_min):
    """Первый максимум амплитуды (момент насыщения). Рассматриваем только время
    после того, как амплитуда превысила A_min (≈ 0.3 от оценки насыщения), ищем
    первый момент, когда она упала ниже 85 % от достигнутого максимума,
    и берём максимум до него."""
    if A.size < 3:
        return None
    cm = np.maximum.accumulate(A)
    drop = np.nonzero((A < 0.85 * cm) & (cm > A_min))[0]
    if not drop.size:
        return None
    i = int(np.argmax(A[:drop[0]]))
    return i


def bounce_period(t, A, i_sat, smooth):
    """Период колебаний амплитуды после насыщения, с: захваченные электроны
    вращаются в яме волны и то отбирают у неё энергию, то отдают обратно.
    Берём время от первого максимума до второго по сглаженной кривой
    (скользящее среднее по окну smooth [с], чтобы убрать мелкую рябь)."""
    if i_sat is None or A.size - i_sat < 10:
        return None
    dt = t[1] - t[0]
    w = max(1, int(round(smooth / dt)))
    As = np.convolve(A, np.ones(w) / w, mode="same")
    n = As.size - w // 2 - 1          # не доверяем правому краю сглаживания
    j = i_sat
    while j + 1 < n and As[j + 1] <= As[j]:
        j += 1
    i_min = j
    while j + 1 < n and As[j + 1] >= As[j]:
        j += 1
    if j + 1 >= n or As[i_min] > 0.95 * As[i_sat]:
        return None
    return t[j] - t[i_sat], i_min, j


def wave_level(sim, E2=None):
    """Безразмерный уровень ленгмюровской турбулентности
        W = ε₀⟨E²⟩/(2 n_p k_B T_e)
    — отношение плотности энергии поля к тепловой энергии электронов.  От него
    зависят модуляционная неустойчивость и глубина каверн (δn/n ≈ −W)."""
    E2 = sim.E2avg if E2 is None else E2
    return EPS0 * E2 / (2.0 * sim.p.n_p * K_B * sim.p.T_e)


def omega_k_spectrum(sim, nwin=2048):
    """Спектр поля на плоскости (k, ω) — «дисперсионная диаграмма из счёта».

    Берётся история комплексных амплитуд мод E_k(t) за последние nwin шагов,
    умножается на окно Ханна и раскладывается в ряд Фурье по времени.  Волна
    E ∝ cos(kx − ωt) даёт E_k(t) ∝ e^{−iωt}, поэтому ω > 0 — волна бежит вправо
    (по пучку), ω < 0 — влево.  Возвращает (ω [рад/с], k [рад/м], P[ω, k] в (В/м)²)
    или None, если шагов ещё мало."""
    n = sim.h_n
    nw = int(min(n, nwin))
    if nw < 128:
        return None
    Ek = sim.h_Ek[n - nw:n]
    win = np.hanning(nw)[:, None]
    F = np.fft.fftshift(np.fft.fft(Ek * win, axis=0), axes=0) / (0.5 * nw)
    f = np.fft.fftshift(np.fft.fftfreq(nw, d=sim.dt))            # Гц
    omega = (-2 * np.pi * f)[::-1]                               # по возрастанию
    P = (np.abs(F) ** 2)[::-1]
    return omega, sim.k_modes[1:sim.m_store + 1], P


class StageTracker:
    """Автоматическое определение стадий процесса по самому счёту.

    0  Затравка        — начальное возмущение возбуждает все корни дисперсионного
                         уравнения; растёт только один, остальные осциллируют.
    1  Линейный рост   — амплитуда растёт как exp(γt); пучок группируется в сгустки.
    2  Захват          — волна стала такой сильной, что электроны пучка попадают в
                         её потенциальные ямы и начинают в них вращаться.
    3  Перемешивание   — первый максимум пройден; амплитуда колеблется с баунс-
                         частотой, вихри сливаются, спектр уширяется, функция
                         распределения пучка расплывается в плато.
    4  Каверны         — (только с подвижными ионами) давление ленгмюровских волн
                         выталкивает плазму: в концентрации ионов появляются ямы,
                         в которых запирается поле, — каверны и солитоны.
    """
    NAMES = ("Затравка", "Линейный рост", "Захват", "Перемешивание и турбулентность",
             "Каверны и солитоны")
    DNI_LEVEL = 0.02          # порог стадии 4: среднеквадратичное δn_i/n_i

    def __init__(self, sim):
        self.sim = sim
        self.stage = 0
        self.t_stage = [0.0, None, None, None, None]
        self.gamma_meas = None
        self.gamma_frozen = False
        self.sat = None          # dict(t, A, WE) в первом максимуме
        self.bounce = None       # измеренный период баунс-колебаний, с
        self.A_trap = trap_level(sim)
        self.n_stages = 5 if sim.m_i else 4

    def update(self):
        s = self.sim
        n = s.h_n
        if n < 5:
            return self.stage
        t = s.h_t[:n]
        A = 2 * np.abs(s.h_Ek[:n, s.m_main - 1])
        g = s.gamma_ref
        t1 = 4.0 / g
        # --- живое измерение инкремента по главной моде
        if not self.gamma_frozen and t[-1] > t1 + 1.5 / g:
            sel = t >= t1
            gm, _ = fit_exp(t[sel], A[sel])
            self.gamma_meas = gm
            if A[-1] > 0.05 * self.A_trap:
                self.gamma_frozen = True
        # --- переходы между стадиями
        if self.stage == 0 and t[-1] >= t1:
            self._go(1, t[-1])
        if self.stage == 1 and A[-1] > 0.3 * self.A_trap:
            self._go(2, t[-1])
        if self.stage == 2:
            i = first_maximum(t, A, 0.3 * self.A_trap)
            if i is not None:
                self.sat = dict(t=t[i], A=A[i], WE=s.h_WE[i], i=i)
                self._go(3, t[-1])
        if self.stage == 3 and self.bounce is None and self.sat is not None:
            b = bounce_period(t, A, self.sat["i"], smooth=0.5 / s.gamma_ref)
            if b is not None:
                self.bounce = b[0]
        if self.stage == 3 and s.m_i and s.h_dni[n - 1] > self.DNI_LEVEL:
            self._go(4, t[-1])
        return self.stage

    def _go(self, st, t):
        self.stage = st
        self.t_stage[st] = t

    def rewind_to(self, t_now):
        """После перемотки назад «забываем» стадии, которые ещё не наступили."""
        for st in range(4, 0, -1):
            if self.t_stage[st] is not None and self.t_stage[st] > t_now:
                self.t_stage[st] = None
                if self.stage >= st:
                    self.stage = st - 1
        if self.sat is not None and self.sat["t"] > t_now:
            self.sat = None
        self.bounce = None if self.sat is None else self.bounce
        if self.stage < 2:
            self.gamma_frozen = False
