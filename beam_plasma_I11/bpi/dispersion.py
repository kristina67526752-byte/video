"""
Линейная теория: дисперсионное уравнение «пучок + плазма» и инкремент γ(k).

Все величины — в СИ:  k в рад/м,  ω и γ в рад/с (с⁻¹),  скорости в м/с,
концентрации в м⁻³, температуры в К.

Дисперсионное уравнение из задания (холодные потоки):

        1 − ω_p1²/ω² − ω_p2²/(ω − k v_b)² = 0 ,

где ω_p1² = n_p e²/(ε₀ m) — плазменная частота электронов плазмы,
ω_p2² = n_b e²/(ε₀ m γ_b³) — плазменная частота пучка.  Множитель γ_b³
(γ_b = 1/√(1 − v_b²/c²)) — релятивистская «продольная масса» m γ_b³: при
v_b ≪ c он равен 1, и уравнение совпадает с записанным в задании.

Каждый поток s (концентрация n_s, скорость u_s, заряд q_s, масса m_s) даёт
слагаемое ω_s²/(ω − k u_s)², ω_s² = n_s q_s²/(ε₀ m_s γ_s³).  Умножив уравнение на
произведение знаменателей, получаем многочлен по ω (для плазмы и пучка — 4-й
степени); его корни находятся ТОЧНО как собственные числа сопровождающей
матрицы.  Корень ω = ω_r + iγ с γ > 0 — растущая волна E ∝ e^{γt} cos(kx − ω_r t).

Тепловой разброс учитывается двумя способами:
  * гидродинамически (поправка Бома–Гросса): (ω − ku)² → (ω − ku)² − 3k²v_T²;
  * кинетически — через функцию дисперсии плазмы Z(ζ): точная теория для
    максвелловских распределений (затухание Ландау, тёплый пучок).

Замечание о численном методе.  Частоты ~10¹⁰ рад/с в 4-й степени дают числа
~10⁴⁰, поэтому внутри функций корни ищутся для отношений ω/ω₀ и k v₀/ω₀
(ω₀ — наибольшая плазменная частота, v₀ — наибольшая скорость потока), а
результат возвращается в рад/с.  Это масштабирование — приём вычислений,
на вход и на выход идут величины в СИ.
"""
from __future__ import annotations

import numpy as np

from .constants import (E_CHARGE, M_E, EPS0, K_B, C_LIGHT, plasma_frequency,
                        thermal_velocity, lorentz_gamma)

try:  # scipy нужен только для кинетической (тёплой) теории
    from scipy.special import wofz as _wofz
except Exception:  # pragma: no cover
    _wofz = None


# --------------------------------------------------------------------------
# Наборы потоков. Поток = (ω_s², u_s, v_Ts):
#   ω_s² — квадрат плазменной частоты потока с учётом γ_s³, рад²/с²;
#   u_s  — скорость потока, м/с;   v_Ts — тепловой разброс (σ), м/с.
# --------------------------------------------------------------------------
def beam_plasma_species(n_p, alpha, vb, T_e=0.0, dvb=0.0, m_i=None, T_i=0.0):
    """Плазма (покоится, концентрация n_p, температура T_e) + пучок (n_b = α·n_p,
    скорость v_b, разброс скоростей Δv_b) + ионы (если задана масса m_i)."""
    wp2 = n_p * E_CHARGE ** 2 / (EPS0 * M_E)
    gb = float(lorentz_gamma(vb))
    sp = [(wp2, 0.0, float(thermal_velocity(T_e)) if T_e > 0 else 0.0),
          (alpha * wp2 / gb ** 3, float(vb), float(dvb))]
    if m_i:
        sp.append(((1.0 + alpha) * n_p * E_CHARGE ** 2 / (EPS0 * m_i), 0.0,
                   float(thermal_velocity(T_i, m_i)) if T_i > 0 else 0.0))
    return sp


def two_stream_species(n_p, vb, dv=0.0, m_i=None, T_i=0.0):
    """Два одинаковых встречных потока электронов ±v_b/2 (система центра масс),
    концентрация каждого n_p, т.е. ω_p1 = ω_p2."""
    u = 0.5 * vb
    g = float(lorentz_gamma(u))
    wp2 = n_p * E_CHARGE ** 2 / (EPS0 * M_E) / g ** 3
    sp = [(wp2, -u, float(dv)), (wp2, +u, float(dv))]
    if m_i:
        sp.append((2.0 * n_p * E_CHARGE ** 2 / (EPS0 * m_i), 0.0,
                   float(thermal_velocity(T_i, m_i)) if T_i > 0 else 0.0))
    return sp


def cold(species):
    """Те же потоки без теплового разброса (уравнение из задания)."""
    return [(w, u, 0.0) for (w, u, _) in species]


def _scales(species):
    """Масштабы ω₀ (рад/с) и v₀ (м/с) для внутреннего решения."""
    w0 = float(np.sqrt(max(w for (w, _, _) in species)))
    v0 = max(abs(u) for (_, u, _) in species)
    if v0 == 0:
        v0 = max(vt for (_, _, vt) in species) or 1.0
    return w0, float(v0)


def _normalized(species):
    w0, v0 = _scales(species)
    return [(w / w0 ** 2, u / v0, vt / v0) for (w, u, vt) in species], w0, v0


def _merge(species):
    """Потоки с одинаковыми скоростью и разбросом складываются (ω² суммируются):
    так покоящиеся ионы и электроны плазмы дают одно слагаемое (ω_pe² + ω_pi²)/ω²."""
    out = {}
    for (w, u, vt) in species:
        out[(u, vt)] = out.get((u, vt), 0.0) + w
    return [(w, u, vt) for (u, vt), w in out.items()]


# --------------------------------------------------------------------------
# Точное решение «гидродинамического» уравнения (многочлен по ω)
# --------------------------------------------------------------------------
def _pmul(a, b):
    """Произведение многочленов, записанных по возрастанию степеней,
    сразу для массива значений k (ось 0 — разные k)."""
    out = np.zeros((a.shape[0], a.shape[1] + b.shape[1] - 1), dtype=complex)
    for i in range(a.shape[1]):
        out[:, i:i + b.shape[1]] += a[:, i:i + 1] * b
    return out


def _fluid_roots_norm(k, species):
    k = np.atleast_1d(np.asarray(k, dtype=float))
    nk = k.size
    species = _merge(species)
    Q = []
    for (wp2, u, vt) in species:
        q = np.zeros((nk, 3), dtype=complex)  # коэффициенты при ω^0, ω^1, ω^2
        q[:, 0] = k ** 2 * (u ** 2 - 3.0 * vt ** 2)
        q[:, 1] = -2.0 * k * u
        q[:, 2] = 1.0
        Q.append(q)

    def prod(polys):
        p = np.ones((nk, 1), dtype=complex)
        for q in polys:
            p = _pmul(p, q)
        return p

    P = prod(Q)
    for s, (wp2, _, _) in enumerate(species):
        rest = prod([Q[r] for r in range(len(species)) if r != s])
        P[:, :rest.shape[1]] -= wp2 * rest

    # Корни = собственные числа сопровождающей матрицы (старший коэффициент = 1)
    n = P.shape[1] - 1
    C = np.zeros((nk, n, n), dtype=complex)
    C[:, 0, :] = -P[:, n - 1::-1] / P[:, n:n + 1]
    if n > 1:
        C[:, np.arange(1, n), np.arange(0, n - 1)] = 1.0
    return np.linalg.eigvals(C)


def fluid_roots(k, species):
    """Все корни ω(k), рад/с, уравнения  1 − Σ_s ω_s² / [(ω − k u_s)² − 3k²v_Ts²] = 0.

    Обозначим Q_s(ω) = (ω − k u_s)² − 3k²v_Ts².  Умножаем уравнение на Π Q_s:
        Π_s Q_s  −  Σ_s ω_s² Π_{r≠s} Q_r  = 0      — многочлен степени 2N.
    k — волновое число, рад/м (число или массив).  Возвращает массив формы
    (len(k), 2N) комплексных корней.
    """
    sp, w0, v0 = _normalized(species)
    k = np.atleast_1d(np.asarray(k, dtype=float))
    return _fluid_roots_norm(k * v0 / w0, sp) * w0


def fluid_growth(k, species):
    """Растущий корень: возвращает (ω_r(k), γ(k)) в рад/с — корень с max Im ω."""
    r = fluid_roots(k, species)
    idx = np.argmax(r.imag, axis=1)
    w = r[np.arange(r.shape[0]), idx]
    return w.real, np.maximum(w.imag, 0.0)


def most_unstable(species, n=4000, kappa_max=3.0):
    """Максимум инкремента: (k_max [рад/м], γ_max [рад/с], ω_r при k_max [рад/с]).
    Сначала грубая сетка по k·v₀/ω₀ ∈ (0, 3], затем уточнение золотым сечением."""
    sp, w0, v0 = _normalized(species)

    def growth(kk):
        r = _fluid_roots_norm(np.atleast_1d(kk), sp)
        idx = np.argmax(r.imag, axis=1)
        return r[np.arange(r.shape[0]), idx]

    ks = np.linspace(1e-3, kappa_max, n)
    g = np.maximum(growth(ks).imag, 0.0)
    i = int(np.argmax(g))
    a, b = ks[max(i - 1, 0)], ks[min(i + 1, n - 1)]
    f = lambda kk: growth(kk)[0].imag
    gr = (np.sqrt(5) - 1) / 2
    c, d = b - gr * (b - a), a + gr * (b - a)
    for _ in range(60):
        if f(c) > f(d):
            b = d
        else:
            a = c
        c, d = b - gr * (b - a), a + gr * (b - a)
    k0 = 0.5 * (a + b)
    w = growth(k0)[0]
    return k0 * w0 / v0, max(w.imag, 0.0) * w0, w.real * w0


# --------------------------------------------------------------------------
# Асимптотики для слабого холодного пучка (α = n_b/n_p ≪ 1)
# --------------------------------------------------------------------------
def gamma_hint(alpha, wp):
    """Формула из подсказки задания: γ ≈ (√3/2)·(n_b/n_p)^(1/3)·ω_p, рад/с."""
    return np.sqrt(3) / 2 * np.cbrt(alpha) * wp


def gamma_weak_beam(alpha, wp, gamma_b=1.0):
    """Правильная асимптотика: γ ≈ (√3/2)·(n_b/2n_p)^(1/3)·ω_p/γ_b, рад/с.
    Вывод: при k v_b = ω_p положим ω = ω_p + δ, |δ| ≪ ω_p. Тогда
    1 − ω_p²/ω² ≈ 2δ/ω_p,  ω_b²/(ω − k v_b)² = α ω_p²/(γ_b³ δ²)
    ⇒ 2δ³ = α ω_p³/γ_b³ ⇒ δ = ω_p (α/2)^(1/3) e^{2πi/3}/γ_b (корень с Im δ > 0):
    Im δ = (√3/2)(α/2)^(1/3) ω_p/γ_b,  Re δ = −½(α/2)^(1/3) ω_p/γ_b."""
    return np.sqrt(3) / 2 * np.cbrt(alpha / 2.0) * wp / gamma_b


def omega_weak_beam(alpha, wp, gamma_b=1.0):
    """Действительная частота растущей волны: ω_r ≈ ω_p·[1 − ½(α/2)^(1/3)/γ_b], рад/с."""
    return wp * (1.0 - 0.5 * np.cbrt(alpha / 2.0) / gamma_b)


def bohm_gross(k, n_p, T_e):
    """Ленгмюровская волна в тёплой плазме: ω² = ω_p² + 3k²v_Te², рад/с."""
    return np.sqrt(plasma_frequency(n_p) ** 2 + 3.0 * (np.asarray(k) * thermal_velocity(T_e)) ** 2)


# --------------------------------------------------------------------------
# Кинетическая теория (максвелловские потоки) — функция плазменной дисперсии
# --------------------------------------------------------------------------
def Zfun(zeta):
    """Функция плазменной дисперсии Z(ζ) = i√π·w(ζ), w — функция Фаддеевой.
    Это аналитическое продолжение по Ландау, верное при любом Im ζ."""
    if _wofz is None:
        raise ImportError("Для кинетической теории нужен scipy (scipy.special.wofz)")
    return 1j * np.sqrt(np.pi) * _wofz(zeta)


def _resp(z):
    """R(ζ) = 1 + ζZ(ζ) и dR/dζ = Z − 2ζR.  При |ζ| > 30 — асимптотический ряд
    R ≈ −1/(2ζ²) − 3/(4ζ⁴) − 15/(8ζ⁶) (прямое вычитание 1 + ζZ теряло бы точность)."""
    z = np.asarray(z, dtype=complex)
    R = np.empty_like(z)
    dR = np.empty_like(z)
    big = np.abs(z) > 30.0
    if np.any(~big):
        zz = z[~big]
        Z = Zfun(zz)
        R[~big] = 1.0 + zz * Z
        dR[~big] = Z - 2.0 * zz * R[~big]
    if np.any(big):
        zz = z[big]
        i2 = 1.0 / (zz * zz)
        R[big] = -0.5 * i2 - 0.75 * i2 ** 2 - 1.875 * i2 ** 3
        dR[big] = (i2 + 3.0 * i2 ** 2 + 11.25 * i2 ** 3) / zz
    return R, dR


def _kinetic_D_norm(w, k, species):
    """Диэлектрическая проницаемость ε(ω,k) = 1 + Σ χ_s и её производная по ω
    (в нормированных переменных)."""
    D = np.ones_like(w, dtype=complex)
    dD = np.zeros_like(w, dtype=complex)
    for (wp2, u, vt) in species:
        if vt <= 0:
            x = w - k * u
            D -= wp2 / x ** 2
            dD += 2 * wp2 / x ** 3
        else:
            s = np.sqrt(2.0) * k * vt
            R, dR = _resp((w - k * u) / s)
            D += wp2 / (k * vt) ** 2 * R
            dD += wp2 / (k * vt) ** 2 * dR / s
    return D, dD


def kinetic_D(w, k, species):
    """ε(ω,k) кинетической теории:  ε = 1 + Σ_s ω_s²/(k²v_Ts²)·[1 + ζ_s Z(ζ_s)],
    ζ_s = (ω − k u_s)/(√2 k v_Ts).  ω в рад/с, k в рад/м.  Возвращает (ε, ∂ε/∂ω)."""
    sp, w0, v0 = _normalized(species)
    D, dD = _kinetic_D_norm(np.asarray(w, dtype=complex) / w0, np.asarray(k) * v0 / w0, sp)
    return D, dD / w0


def _kinetic_growth_norm(k, species, n_cont=12, iters=40):
    k = np.atleast_1d(np.asarray(k, dtype=float))
    cold_sp = [(wp2, u, 0.0) for (wp2, u, _) in species]
    r = _fluid_roots_norm(k, cold_sp)
    w = r[np.arange(k.size), np.argmax(r.imag, axis=1)].astype(complex)
    # для устойчивых k у холодного корня Im ω = 0 — сдвинем его чуть вверх
    w = w + 1e-3j
    for j in range(1, n_cont + 1):
        sp = [(wp2, u, vt * j / n_cont) for (wp2, u, vt) in species]
        for _ in range(iters):
            D, dD = _kinetic_D_norm(w, k, sp)
            step = D / dD
            step = np.where(np.isfinite(step), step, 0)
            # ограничиваем шаг, чтобы не «перепрыгнуть» на другую ветвь
            big = np.abs(step) > 0.2
            step[big] *= 0.2 / np.abs(step[big])
            w = w - step
            if np.all(np.abs(step) < 1e-12):
                break
    return w


def kinetic_growth(k, species):
    """Растущий корень кинетического уравнения ε(ω,k) = 0 методом Ньютона.
    Начальное приближение — холодный корень; тепловые скорости увеличиваются
    от 0 до заданных за 12 шагов (метод продолжения).  Возвращает (ω_r, γ), рад/с."""
    sp, w0, v0 = _normalized(species)
    w = _kinetic_growth_norm(np.atleast_1d(k) * v0 / w0, sp) * w0
    return w.real, w.imag


def kinetic_growth_curve(k, species, iters=60):
    """γ(k) кинетической теории вдоль массива k (по возрастанию, рад/м) методом
    продолжения по k: в точке максимума холодного инкремента корень находится
    продолжением по температуре, а дальше вправо и влево — методом Ньютона с
    начальным приближением из соседней точки. Так корень не «перескакивает» на
    другие (затухающие) ветви.  Возвращает (ω_r, γ) в рад/с."""
    sp, w0, v0 = _normalized(species)
    k = np.asarray(k, dtype=float) * v0 / w0
    cold_sp = [(wp2, u, 0.0) for (wp2, u, _) in sp]
    r = _fluid_roots_norm(k, cold_sp)
    g0 = r.imag.max(axis=1)
    i0 = int(np.argmax(g0))
    w = np.empty(k.size, dtype=complex)
    w[i0] = _kinetic_growth_norm(k[i0:i0 + 1], sp)[0]

    def newton(kk, guess):
        z = complex(guess)
        for _ in range(iters):
            D, dD = _kinetic_D_norm(np.array([z]), kk, sp)
            st = D[0] / dD[0]
            if not np.isfinite(st):
                break
            if abs(st) > 0.05:
                st *= 0.05 / abs(st)
            z -= st
            if abs(st) < 1e-12:
                break
        return z

    for i in range(i0 + 1, k.size):
        w[i] = newton(k[i], w[i - 1])
    for i in range(i0 - 1, -1, -1):
        w[i] = newton(k[i], w[i + 1])
    w = w * w0
    return w.real, w.imag


def kinetic_most_unstable(species, k_cold, span=0.35, n=81):
    """Максимум кинетического инкремента вблизи холодного k_max:
    возвращает (k_max, γ_max, ω_r) в СИ."""
    k = np.linspace((1 - span) * k_cold, (1 + span) * k_cold, n)
    wr, g = kinetic_growth_curve(k, species)
    i = int(np.argmax(g))
    if 0 < i < n - 1:                        # парабола через три точки
        y0, y1, y2 = g[i - 1], g[i], g[i + 1]
        d = 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2)
        kk = k[i] + d * (k[1] - k[0])
        gg = y1 - 0.25 * (y0 - y2) * d
        ww = wr[i] + d * 0.5 * (wr[i + 1] - wr[i - 1])
        return float(kk), float(gg), float(ww)
    return float(k[i]), float(g[i]), float(wr[i])
