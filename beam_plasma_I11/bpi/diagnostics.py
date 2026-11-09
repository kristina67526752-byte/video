"""
Обработка результатов счёта: инкремент, насыщение, баунс-частота,
квазилинейный баланс, автоматическое определение стадий процесса.

Все формулы этого файла — в docs/ОБЪЯСНЕНИЕ.md, разделы 5–7.
"""
from __future__ import annotations

import numpy as np

# Константа насыщения холодного пучка, посчитанная одноволновой моделью
# (bpi.single_wave.saturation_constant): в первом максимуме амплитуды
#     k·E_sat / γ² = (ω_B/γ)² = 3.1235,   ω_B/γ = 1.7673.
# В этой модели α убирается масштабированием, поэтому число универсально.
C_TRAP = 3.1235
OMEGA_B_OVER_GAMMA = np.sqrt(C_TRAP)


def trapping_amplitude(gamma, k):
    """Теория захвата: рост волны останавливается, когда электроны пучка
    успевают сделать примерно один оборот в яме волны, т.е. ω_B ≈ 1.77γ,
    где ω_B = √(k E₀) — баунс-частота.  Отсюда E_sat = C·γ²/k."""
    return C_TRAP * gamma ** 2 / k


def ql_full_plateau_fraction():
    """Квазилинейная теория, полная релаксация холодного пучка в плато [0, v_b]:
    кинетическая энергия пучка α v_b²/2 → α v_b²/6, т.е. пучок отдаёт 2/3 энергии.
    Половина энергии ленгмюровской волны — электрическое поле, половина —
    колебания электронов плазмы. Поэтому W_E = K_b0/3."""
    return 1.0 / 3.0


def plateau_energy(v1, v2):
    """⟨v²⟩/2 для плоского распределения на [v1, v2]:  (v1² + v1 v2 + v2²)/6."""
    return (v1 * v1 + v1 * v2 + v2 * v2) / 6.0


def plateau_edges(v, level=0.5, bins=200):
    """Края плато функции распределения: где f(v) падает до level·(высота плато).
    Высота плато — медиана f по центральной части распределения."""
    lo, hi = np.percentile(v, [0.5, 99.5])
    h, e = np.histogram(v, bins=bins, range=(lo - 0.05, hi + 0.05))
    c = 0.5 * (e[1:] + e[:-1])
    nz = np.nonzero(h > 0)[0]
    core = h[nz[0]:nz[-1] + 1]
    top = np.median(core[core > np.percentile(core, 30)])
    above = np.nonzero(h >= level * top)[0]
    return c[above[0]], c[above[-1]]


def ql_prediction(v_beam, alpha, L, K_b0, vb=1.0):
    """Квазилинейный баланс энергии по измеренным краям плато.
    Пучок с плоским распределением на [v1, v2] имеет энергию
        K_pl = α L (v1² + v1v2 + v2²)/6.
    Отданная энергия K_b0 − K_pl уходит в ленгмюровские волны, из неё
    половина — энергия поля:  W_E^QL = (K_b0 − K_pl)/2."""
    v1, v2 = plateau_edges(v_beam)
    K_pl = alpha * L * plateau_energy(v1, v2)
    return dict(v1=v1, v2=v2, K_pl=K_pl, WE_ql=0.5 * (K_b0 - K_pl))


def fit_exp(t, a):
    """МНК-прямая по ln a(t): возвращает наклон (инкремент) и R²."""
    y = np.log(a)
    A = np.vstack([t, np.ones_like(t)]).T
    coef, res, *_ = np.linalg.lstsq(A, y, rcond=None)
    ss = ((y - y.mean()) ** 2).sum()
    r2 = 1 - (res[0] / ss if res.size and ss > 0 else 0.0)
    return coef[0], r2


def linear_window(sim):
    """Окно линейной стадии [t1, t2]:
    t1 = 4/γ — к этому времени затухают «лишние» корни дисперсионного уравнения
    (начальное возмущение возбуждает все 4 корня, растёт только один);
    t2 — момент, когда главная волна дорастает до 5 % от уровня насыщения
    (дальше начинают сказываться нелинейные эффекты)."""
    h = sim.hist
    t = h["t"]
    A = 2 * np.abs(h["Ek"][:, sim.m_main - 1])
    t1 = 4.0 / sim.gamma_ref
    A_lim = 0.05 * trapping_amplitude(sim.gamma_ref, sim.k_modes[sim.m_main])
    over = np.nonzero(A > A_lim)[0]
    t2 = t[over[0]] if over.size else t[-1] if t.size else 0.0
    return t1, t2


def measure_modes(sim, min_frac=0.5):
    """Инкремент γ и частота ω каждой моды ящика из истории E_k(t).
    γ — наклон ln|E_k|,  ω = −d(arg E_k)/dt  (волна E ∝ cos(kx − ωt))."""
    h = sim.hist
    t = h["t"]
    t1, t2 = linear_window(sim)
    sel = (t >= t1) & (t <= t2)
    out = []
    if sel.sum() < 20:
        return out
    for m in range(1, sim.m_store + 1):
        gth = sim.gamma_modes_th[m - 1]
        if gth < min_frac * sim.gamma_ref:
            continue
        ek = h["Ek"][sel, m - 1]
        g, r2 = fit_exp(t[sel], np.abs(ek))
        ph = np.unwrap(np.angle(ek))
        w = -np.polyfit(t[sel], ph, 1)[0]
        out.append(dict(m=m, k=sim.k_modes[m], g_th=gth, g=g, r2=r2,
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


def bounce_period(t, A, i_sat, smooth=1.0):
    """Период колебаний амплитуды после насыщения: захваченные электроны
    вращаются в яме волны и то отбирают у неё энергию, то отдают обратно.
    Берём время от первого максимума до второго по сглаженной кривой
    (скользящее среднее по окну smooth, чтобы убрать мелкую рябь)."""
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
    """
    NAMES = ("Затравка", "Линейный рост", "Захват", "Перемешивание и турбулентность")

    def __init__(self, sim):
        self.sim = sim
        self.stage = 0
        self.t_stage = [0.0, None, None, None]
        self.gamma_meas = None
        self.gamma_frozen = False
        self.sat = None          # dict(t, A, WE) в первом максимуме
        self.bounce = None       # измеренный период баунс-колебаний
        self.A_trap = trapping_amplitude(sim.gamma_ref, sim.k_modes[sim.m_main])

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
        return self.stage

    def _go(self, st, t):
        self.stage = st
        self.t_stage[st] = t

    def rewind_to(self, t_now):
        """После перемотки назад «забываем» стадии, которые ещё не наступили."""
        for st in range(3, 0, -1):
            if self.t_stage[st] is not None and self.t_stage[st] > t_now:
                self.t_stage[st] = None
                if self.stage >= st:
                    self.stage = st - 1
        if self.sat is not None and self.sat["t"] > t_now:
            self.sat = None
        self.bounce = None if self.sat is None else self.bounce
        if self.stage < 2:
            self.gamma_frozen = False
