"""
Линейная теория: дисперсионное уравнение пучок + плазма и инкремент γ(k).

Безразмерные единицы (во всём проекте одни и те же):
    время      t   в единицах 1/ω_p      (ω_p — плазменная частота электронов плазмы)
    скорость   v   в единицах v_0        (опорная скорость; по умолчанию v_b = 1·v_0)
    длина      x   в единицах v_0/ω_p
    волновое число k в единицах ω_p/v_0
    частота    ω   в единицах ω_p
    плотность  n   в единицах n_p        (поэтому α = n_b/n_p — это просто n_b)

Дисперсионное уравнение из задания (холодные потоки):

    1 − ω_p1²/ω² − ω_p2²/(ω − k v_b)² = 0
    (в безразмерном виде:  1 − 1/ω² − α/(ω − k v_b)² = 0)

Каждый поток s (плотность n_s, скорость u_s) даёт слагаемое ω_s²/(ω − k u_s)²,
где ω_s² = n_s (в наших единицах).  Умножив уравнение на произведение
знаменателей, получаем многочлен по ω.  Для двух потоков это многочлен
4-й степени; его 4 корня находятся ТОЧНО (как собственные числа
сопровождающей матрицы).  Комплексный корень ω = ω_r + iγ с γ > 0 — это
растущая волна: E ∝ exp(γt)·cos(kx − ω_r t).

Тепловой разброс скоростей учитывается двумя способами:
  * гидродинамически (поправка Бома–Гросса):  (ω − k u)² → (ω − k u)² − 3k²v_T²;
  * кинетически — через функцию плазменной дисперсии Z(ζ) (точная теория
    для максвелловского распределения, функция kinetic_*).
"""
from __future__ import annotations

import numpy as np

try:  # scipy нужен только для кинетической (тёплой) теории
    from scipy.special import wofz as _wofz
except Exception:  # pragma: no cover
    _wofz = None


# --------------------------------------------------------------------------
# Наборы потоков. Поток = (ω_s², u_s, v_Ts): квадрат плазменной частоты потока,
# его скорость и тепловой разброс скоростей (среднеквадратичный).
# --------------------------------------------------------------------------
def beam_plasma_species(alpha, vb=1.0, vtp=0.0, vtb=0.0):
    """Плазма (покоится, n=1) + пучок (n=α, скорость v_b)."""
    return [(1.0, 0.0, vtp), (alpha, vb, vtb)]


def two_stream_species(vb=1.0, vt=0.0):
    """Два одинаковых встречных пучка ±v_b/2 (система центра масс).
    Каждый поток имеет плотность 1, т.е. ω_p1 = ω_p2 = 1."""
    return [(1.0, -0.5 * vb, vt), (1.0, 0.5 * vb, vt)]


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


def fluid_roots(k, species):
    """Все корни ω(k) уравнения  1 − Σ_s ω_s² / [(ω − k u_s)² − 3k²v_Ts²] = 0.

    Обозначим Q_s(ω) = (ω − k u_s)² − 3k²v_Ts² = ω² − 2k u_s ω + k²(u_s² − 3v_Ts²).
    Умножаем уравнение на Π Q_s:
        Π_s Q_s  −  Σ_s ω_s² Π_{r≠s} Q_r  = 0      — многочлен степени 2N.
    Возвращает массив формы (len(k), 2N) комплексных корней.
    """
    k = np.atleast_1d(np.asarray(k, dtype=float))
    nk = k.size
    Q = []
    for (wp2, u, vt) in species:
        q = np.zeros((nk, 3), dtype=complex)  # коэффициенты при ω^0, ω^1, ω^2
        q[:, 0] = k**2 * (u**2 - 3.0 * vt**2)
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


def fluid_growth(k, species):
    """Растущий корень: возвращает (ω_r(k), γ(k)) — корень с max Im ω."""
    r = fluid_roots(k, species)
    idx = np.argmax(r.imag, axis=1)
    w = r[np.arange(r.shape[0]), idx]
    return w.real, np.maximum(w.imag, 0.0)


def most_unstable(species, kmin=1e-3, kmax=None, n=4000):
    """Максимум инкремента: (k_max, γ_max, ω_r при k_max).
    Сначала грубая сетка, затем уточнение золотым сечением."""
    if kmax is None:
        umax = max(abs(u) for (_, u, _) in species) or 1.0
        kmax = 3.0 / umax
    ks = np.linspace(kmin, kmax, n)
    _, g = fluid_growth(ks, species)
    i = int(np.argmax(g))
    a, b = ks[max(i - 1, 0)], ks[min(i + 1, n - 1)]
    f = lambda kk: fluid_growth(np.array([kk]), species)[1][0]
    gr = (np.sqrt(5) - 1) / 2
    c, d = b - gr * (b - a), a + gr * (b - a)
    for _ in range(60):
        if f(c) > f(d):
            b = d
        else:
            a = c
        c, d = b - gr * (b - a), a + gr * (b - a)
    k0 = 0.5 * (a + b)
    wr, g0 = fluid_growth(np.array([k0]), species)
    return k0, g0[0], wr[0]


# --------------------------------------------------------------------------
# Асимптотики для слабого холодного пучка (α ≪ 1)
# --------------------------------------------------------------------------
def gamma_hint(alpha):
    """Формула из подсказки задания: γ ≈ (√3/2)·α^(1/3)·ω_p."""
    return np.sqrt(3) / 2 * np.cbrt(alpha)


def gamma_weak_beam(alpha):
    """Правильная асимптотика: γ ≈ (√3/2)·(α/2)^(1/3)·ω_p.
    Вывод: при k v_b = ω_p положим ω = ω_p + δ, |δ| ≪ ω_p. Тогда
    1 − 1/ω² ≈ 2δ,  α/(ω − k v_b)² = α/δ²  ⇒  2δ³ = α  ⇒  δ = (α/2)^(1/3)·e^{2πi/3}
    (берём корень с Im δ > 0):  Im δ = (√3/2)(α/2)^(1/3),  Re δ = −½(α/2)^(1/3)."""
    return np.sqrt(3) / 2 * np.cbrt(alpha / 2.0)


def omega_weak_beam(alpha):
    """Действительная частота растущей волны: ω_r ≈ ω_p·[1 − ½(α/2)^(1/3)]."""
    return 1.0 - 0.5 * np.cbrt(alpha / 2.0)


# --------------------------------------------------------------------------
# Кинетическая теория (максвелловские потоки) — функция плазменной дисперсии
# --------------------------------------------------------------------------
def Zfun(zeta):
    """Функция плазменной дисперсии Z(ζ) = i√π·w(ζ), w — функция Фаддеевой.
    Это аналитическое продолжение по Ландау, верное при любом Im ζ."""
    if _wofz is None:
        raise ImportError("Для кинетической теории нужен scipy (scipy.special.wofz)")
    return 1j * np.sqrt(np.pi) * _wofz(zeta)


def kinetic_D(w, k, species):
    """Диэлектрическая проницаемость ε(ω,k) = 1 + Σ χ_s и её производная по ω."""
    D = np.ones_like(w, dtype=complex)
    dD = np.zeros_like(w, dtype=complex)
    for (wp2, u, vt) in species:
        if vt <= 0:
            x = w - k * u
            D -= wp2 / x**2
            dD += 2 * wp2 / x**3
        else:
            s = np.sqrt(2.0) * k * vt
            z = (w - k * u) / s
            Z = Zfun(z)
            D += wp2 / (k * vt) ** 2 * (1 + z * Z)
            dD += wp2 / (k * vt) ** 2 * (Z - 2 * z * (1 + z * Z)) / s
    return D, dD


def kinetic_growth(k, species, n_cont=12, iters=40):
    """Растущий корень кинетического уравнения ε(ω,k) = 0 методом Ньютона.
    Начальное приближение — холодный корень; тепловые скорости
    увеличиваются от 0 до заданных за n_cont шагов (метод продолжения)."""
    k = np.atleast_1d(np.asarray(k, dtype=float))
    cold = [(wp2, u, 0.0) for (wp2, u, _) in species]
    r = fluid_roots(k, cold)
    w = r[np.arange(k.size), np.argmax(r.imag, axis=1)].astype(complex)
    # для устойчивых k у холодного корня Im ω = 0 — сдвинем его чуть вверх
    w = w + 1e-3j
    for j in range(1, n_cont + 1):
        sp = [(wp2, u, vt * j / n_cont) for (wp2, u, vt) in species]
        for _ in range(iters):
            D, dD = kinetic_D(w, k, sp)
            step = D / dD
            step = np.where(np.isfinite(step), step, 0)
            # ограничиваем шаг, чтобы не «перепрыгнуть» на другую ветвь
            big = np.abs(step) > 0.2
            step[big] *= 0.2 / np.abs(step[big])
            w = w - step
            if np.all(np.abs(step) < 1e-12):
                break
    return w.real, w.imag


def kinetic_growth_curve(k, species, iters=60):
    """γ(k) кинетической теории вдоль массива k (по возрастанию) методом
    продолжения по k: в точке максимума холодного инкремента корень находится
    продолжением по температуре (kinetic_growth), а дальше вправо и влево —
    методом Ньютона с начальным приближением из соседней точки. Так корень
    не «перескакивает» на другие (затухающие) ветви."""
    k = np.asarray(k, dtype=float)
    cold = [(wp2, u, 0.0) for (wp2, u, _) in species]
    _, g0 = fluid_growth(k, cold)
    i0 = int(np.argmax(g0))
    wr0, gi0 = kinetic_growth(k[i0:i0 + 1], species)
    w = np.empty(k.size, dtype=complex)
    w[i0] = wr0[0] + 1j * gi0[0]

    def newton(kk, guess):
        z = complex(guess)
        for _ in range(iters):
            D, dD = kinetic_D(np.array([z]), kk, species)
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
    return w.real, w.imag
