"""
Одномерный электростатический PIC-код (Particle-In-Cell, «частицы в ячейках»).

Что моделируется
----------------
Электроны плазмы (сорт 0) и электроны пучка (сорт 1) в периодическом ящике
длины L.  Ионы тяжёлые — неподвижный однородный положительный фон.
Все величины безразмерные (см. dispersion.py): t·ω_p, x·ω_p/v_0, v/v_0,
E·e/(m ω_p v_0), n/n_p.

Уравнения
---------
    dx_j/dt = v_j                       (1)  движение частицы
    dv_j/dt = −E(x_j)                   (2)  второй закон Ньютона для электрона (заряд −e)
    dE/dx   = ρ = n_i − n_e(x)          (3)  уравнение Пуассона (теорема Гаусса в 1D)

В размерном виде (2) — это m dv/dt = −eE, а (3) — dE/dx = e(n_i − n_e)/ε₀.
Переход к безразмерным: ω_p² = n_p e²/(ε₀ m) «съедает» все константы.

Один шаг по времени (схема «чехарда», leapfrog, 2-й порядок точности)
---------------------------------------------------------------------
  1. Взвешивание (CIC — «облако в ячейке»): частица в точке x между узлами
     i и i+1 отдаёт в узел i долю (1−f), в узел i+1 — долю f, где f = x/Δx − i.
     Так получаем плотность электронов n_e в узлах сетки.
  2. Поле: ρ = n_i − n_e, затем E из уравнения Пуассона через быстрое
     преобразование Фурье:  i k E_k = ρ_k  ⇒  E_k = −i ρ_k / k   (E_0 = 0).
     Перед этим ρ_k умножается на фильтр F(k) = cos⁴(kΔx/2) — двойное
     сглаживание (1,2,1)/4, которое убирает шум сетки.
  3. Интерполяция поля в точки частиц теми же весами (1−f, f).
  4. Скорости:  v^{n+½} = v^{n−½} − E(x^n)·Δt.
  5. Координаты: x^{n+1} = x^n + v^{n+½}·Δt, затем x приводится в [0, L).

Скорости хранятся в полуцелые моменты времени, координаты — в целые.
Схема устойчива при ω_p Δt < 2; ошибка частоты ≈ (ω_p Δt)²/24 (0.04 % при Δt=0.1).

Энергия (на всю длину ящика, в единицах n_p m v_0² · (v_0/ω_p))
---------------------------------------------------------------
    W_E = ½ Σ_g E_g² Δx                — энергия электрического поля
    K_s = ½ w_s Σ_j v_j²               — кинетическая энергия сорта s,
w_s = n_s L / N_s — «вес» макрочастицы (сколько реальной плотности·длины она несёт).
Сумма W_E + K_0 + K_1 должна сохраняться — это главная проверка счёта.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, replace

import numpy as np

from . import dispersion as disp


@dataclass
class PICParams:
    scenario: str = "beam"     # "beam" — пучок в плазме; "two_stream" — встречные пучки
    alpha: float = 0.01        # n_b / n_p
    vb: float = 1.0            # скорость пучка, в единицах v_0 (для two_stream — относительная скорость потоков)
    dvb: float = 0.0           # тепловой разброс скоростей пучка Δv/v_b (σ максвелловского распределения)
    vtp: float = 0.02          # тепловой разброс электронов плазмы v_Tp/v_b. Небольшая температура
                               # нужна, чтобы подавить численный нагрев холодной плазмы на сетке
                               # (нужно Δx ≲ 5λ_D, λ_D = v_Tp/ω_p); на неустойчивость она не влияет:
                               # поправка Бома–Гросса к частоте 3k²v_Tp²/2 ≈ 0.06 %
    n_waves: int = 8           # сколько длин самой неустойчивой волны укладывается в ящик
    ng: int = 1024             # число узлов сетки
    npart: int = 65536         # макрочастиц каждого сорта
    dt: float = 0.1            # шаг по времени, 1/ω_p
    seed_amp: float = 1e-4     # затравка: δn_b/n_b главной моды
    seed_other: float = 0.1    # амплитуда затравки остальных мод относительно главной
    rng_seed: int = 1          # зерно генератора случайных фаз затравки
    snap_every: int = 200      # как часто запоминать состояние (для перемотки назад)
    n_filter: int = 2          # сколько раз применять сглаживание (1,2,1)/4 к плотности заряда

    def copy(self, **kw):
        return replace(self, **kw)

    def as_dict(self):
        return asdict(self)


def _bit_reversed_quantiles(n):
    """Квантили (j+½)/n, переставленные в бит-реверсном порядке (последовательность
    ван дер Корпута). Даёт «тихий старт»: распределение по скоростям точное,
    и при этом не коррелирует с равномерно расставленными координатами."""
    bits = int(np.ceil(np.log2(n)))
    j = np.arange(n)
    r = np.zeros(n, dtype=np.int64)
    jj = j.copy()
    for _ in range(bits):
        r = (r << 1) | (jj & 1)
        jj >>= 1
    q = (r + 0.5) / (1 << bits)
    return q


def _quiet_gaussian(n):
    """n значений с точным нормальным распределением N(0,1) (тихий старт):
    v_j = Φ⁻¹(q_j), где Φ⁻¹ — обратная функция нормального распределения."""
    from scipy.special import ndtri
    return ndtri(_bit_reversed_quantiles(n))


class PIC:
    """Состояние и шаг PIC-модели. Всё хранится в numpy-массивах,
    один шаг — около 15 векторных операций над всеми частицами."""

    def __init__(self, p: PICParams | None = None):
        self.p = p = p or PICParams()

        # ---- потоки: (ω_s², u_s, v_Ts) -------------------------------------
        if p.scenario == "two_stream":
            self.species = disp.two_stream_species(p.vb, p.dvb * p.vb)
            self.names = ("поток 1 (←)", "поток 2 (→)")
        else:
            self.species = disp.beam_plasma_species(p.alpha, p.vb, p.vtp * p.vb, p.dvb * p.vb)
            self.names = ("электроны плазмы", "электроны пучка")
        self.dens = np.array([s[0] for s in self.species])   # n_s (= ω_s²)
        self.n_ion = self.dens.sum()                          # нейтрализующий фон ионов

        # ---- линейная теория: самая неустойчивая волна -----------------------
        cold = [(w, u, 0.0) for (w, u, _) in self.species]
        self.k_max, self.gamma_max, self.omega_r = disp.most_unstable(cold)
        # ящик подбирается так, чтобы в нём укладывалось ровно n_waves длин этой волны
        self.L = 2 * np.pi * p.n_waves / self.k_max
        self.dx = self.L / p.ng
        self.k_modes = 2 * np.pi * np.arange(p.ng // 2 + 1) / self.L
        k_safe = self.k_modes.copy()
        k_safe[0] = 1.0
        self._inv_ik = 1.0 / (1j * k_safe)                    # 1/(ik) для решения Пуассона
        self._inv_ik[0] = 0.0
        # сглаживающий фильтр (1,2,1)/4, применённый n_filter раз: F(k) = cos^{2n}(kΔx/2).
        # Подавляет коротковолновый шум сетки (численный нагрев); на рабочие волны
        # почти не влияет: для главной волны kΔx ≈ 0.05 и F ≈ 0.999.
        self._filt = np.cos(0.5 * self.k_modes * self.dx) ** (2 * p.n_filter)
        # инкремент каждой моды ящика по теории
        self.m_store = min(4 * p.n_waves, p.ng // 2)          # сколько мод записывать в историю
        km = self.k_modes[1:self.m_store + 1]
        self.omega_modes_th, self.gamma_modes_th = disp.fluid_growth(km, cold)
        self.theory_kind = "холодная гидродинамика (уравнение 4-й степени)"
        if p.dvb > 0:
            # тёплый пучок: точная кинетическая теория (функция Z), учитывает и
            # затухание Ландау, и переход к кинетической неустойчивости
            wr, gk = disp.kinetic_growth_curve(km, self.species)
            self.omega_modes_th, self.gamma_modes_th = wr, np.maximum(gk, 0.0)
            self.theory_kind = "кинетическая теория (функция дисперсии плазмы Z)"
        # главная (самая быстрая) мода ящика и её инкремент
        self.m_main = int(np.argmax(self.gamma_modes_th)) + 1
        self.gamma_ref = float(self.gamma_modes_th[self.m_main - 1])
        self.omega_ref = float(self.omega_modes_th[self.m_main - 1])

        # ---- частицы ---------------------------------------------------------
        N = p.npart
        self.N = N
        self.w = self.dens * self.L / N                       # вес макрочастицы сорта s
        rng = np.random.default_rng(p.rng_seed)
        x0 = (np.arange(N) + 0.5) * self.L / N                # равномерная решётка (тихий старт)
        g = _quiet_gaussian(N)
        xs, vs = [], []
        for s, (wp2, u, vt) in enumerate(self.species):
            x = x0.copy()
            v = u + vt * g if vt > 0 else np.full(N, u, dtype=float)
            if s == 1:
                # затравка: смещение ξ(x) = Σ (ε_m/k_m) cos(k_m x + φ_m)
                # даёт возмущение плотности пучка δn_b/n_b = Σ ε_m sin(k_m x + φ_m)
                for m in range(1, self.m_store + 1):
                    eps = p.seed_amp * (1.0 if m == self.m_main else p.seed_other)
                    phi = rng.uniform(0, 2 * np.pi)
                    km_ = self.k_modes[m]
                    x += eps / km_ * np.cos(km_ * x0 + phi)
                x %= self.L
            xs.append(x)
            vs.append(v)
        self.x = np.concatenate(xs)
        self.v = np.concatenate(vs)
        self.sl = (slice(0, N), slice(N, 2 * N))              # срезы сортов в общих массивах

        self.t = 0.0
        self.step_count = 0
        # начальное поле и «полшага назад» для скоростей (запуск чехарды)
        self._deposit_and_solve()
        self.v += self._gather() * (0.5 * p.dt)               # v^{-1/2} = v^0 + E·Δt/2
        self._vv_old = np.array([np.dot(self.v[s], self.v[s]) for s in self.sl])
        self._vs_old = np.array([self.v[s].sum() for s in self.sl])

        self.K0_beam = 0.5 * self.w[1] * np.sum(vs[1] ** 2)  # начальная энергия пучка
        self._init_history()
        self.snapshots = []
        self._save_snapshot()

    # ------------------------------------------------------------------ шаги
    def _deposit_and_solve(self):
        """Шаги 1–2: плотность методом CIC и поле из уравнения Пуассона (БПФ)."""
        ng = self.p.ng
        xi = self.x * (1.0 / self.dx)
        i = xi.astype(np.int64)
        np.minimum(i, ng - 1, out=i)          # страховка от x == L из-за округления
        f = xi - i
        self._i, self._f = i, f
        self.ne_s = []
        for s, sl in enumerate(self.sl):
            c = np.bincount(i[sl], weights=1.0 - f[sl], minlength=ng + 1)
            c += np.bincount(i[sl] + 1, weights=f[sl], minlength=ng + 1)
            c[0] += c[ng]                     # узел ng — это тот же узел 0 (периодичность)
            self.ne_s.append(c[:ng] * (self.w[s] / self.dx))   # плотность сорта s в узлах
        self.ne = self.ne_s[0] + self.ne_s[1]  # плотность всех электронов
        rho = self.n_ion - self.ne            # плотность заряда (в единицах e·n_p)
        rho_k = np.fft.rfft(rho)
        self.Ek = rho_k * self._inv_ik * self._filt   # E_k = F(k)·ρ_k / (ik)
        self.E = np.fft.irfft(self.Ek, ng)
        self._Eext = np.append(self.E, self.E[0])    # E в узлах 0..N_g (узел N_g = узел 0)
        self._dE = np.diff(self._Eext)               # E_{i+1} − E_i

    def _gather(self):
        """Шаг 3: поле в точке частицы  E_p = E_i (1−f) + E_{i+1} f."""
        i, f = self._i, self._f
        return np.take(self._Eext, i) + f * np.take(self._dE, i)

    def step(self, n=1):
        """Сделать n шагов по времени."""
        dt, L = self.p.dt, self.L
        for _ in range(n):
            # поле в момент t^n уже посчитано (в конце предыдущего шага)
            self._record()
            Ep = self._gather()
            self.v -= Ep * dt                                # (2): v^{n+1/2}
            vv_new = np.array([np.dot(self.v[s], self.v[s]) for s in self.sl])
            vs_new = np.array([self.v[s].sum() for s in self.sl])
            # кинетическая энергия в момент t^n — среднее по соседним полушагам
            k_now = 0.25 * self.w * (self._vv_old + vv_new)
            p_now = 0.5 * self.w * (self._vs_old + vs_new)
            self._finish_record(k_now, p_now)
            self._vv_old, self._vs_old = vv_new, vs_new
            self.x += self.v * dt                            # (1): x^{n+1}
            # периодичность: вышедшие за край возвращаем с другой стороны
            # (за шаг частица смещается меньше чем на L, так что хватает ±L)
            np.subtract(self.x, L, out=self.x, where=self.x >= L)
            np.add(self.x, L, out=self.x, where=self.x < 0)
            self.t += dt
            self.step_count += 1
            self._deposit_and_solve()                        # (3): поле в t^{n+1}
            if self.step_count % self.p.snap_every == 0:
                self._save_snapshot()

    # ------------------------------------------------------- диагностика
    def _init_history(self, cap=4096):
        self.h_n = 0
        self.h_t = np.zeros(cap)
        self.h_WE = np.zeros(cap)
        self.h_K = np.zeros((cap, 2))
        self.h_P = np.zeros((cap, 2))
        self.h_Ek = np.zeros((cap, self.m_store), dtype=complex)

    def _grow(self):
        cap = self.h_t.size * 2
        for name in ("h_t", "h_WE", "h_K", "h_P", "h_Ek"):
            a = getattr(self, name)
            b = np.zeros((cap,) + a.shape[1:], dtype=a.dtype)
            b[:a.shape[0]] = a
            setattr(self, name, b)

    def _record(self):
        if self.h_n >= self.h_t.size:
            self._grow()
        j = self.h_n
        self.h_t[j] = self.t
        self.h_WE[j] = 0.5 * np.dot(self.E, self.E) * self.dx
        # комплексная амплитуда моды m: E(x) = Σ_m 2|E_m| cos(k_m x + arg E_m)
        self.h_Ek[j] = self.Ek[1:self.m_store + 1] / self.p.ng

    def _finish_record(self, k_now, p_now):
        j = self.h_n
        self.h_K[j] = k_now
        self.h_P[j] = p_now
        self.h_n += 1

    # удобные срезы истории
    @property
    def hist(self):
        n = self.h_n
        return dict(t=self.h_t[:n], WE=self.h_WE[:n], K=self.h_K[:n],
                    P=self.h_P[:n], Ek=self.h_Ek[:n])

    def mode_amplitudes(self):
        """Амплитуды мод сейчас: E(x) = Σ A_m cos(k_m x + φ_m), A_m = 2|E_k|/N_g."""
        return 2.0 * np.abs(self.Ek[1:]) / self.p.ng

    # ------------------------------------------------------- перемотка
    def _save_snapshot(self):
        self.snapshots.append(dict(
            step=self.step_count, t=self.t, x=self.x.copy(), v=self.v.copy(),
            vv=self._vv_old.copy(), vs=self._vs_old.copy(), h_n=self.h_n))

    def rewind(self, n_snap_back=1):
        """Вернуться на n снимков назад. Счёт детерминирован: повторный проход
        вперёд даёт в точности те же числа."""
        cur = self.step_count
        # последний снимок не позже текущего шага; если стоим ровно на нём — шагнём ещё назад
        idx = [j for j, s in enumerate(self.snapshots) if s["step"] <= cur]
        if not idx:
            return
        j = idx[-1]
        if self.snapshots[j]["step"] == cur:
            j -= 1
        j = max(0, j - (n_snap_back - 1))
        s = self.snapshots[j]
        self.snapshots = self.snapshots[:j + 1]
        self.x[:] = s["x"]
        self.v[:] = s["v"]
        self._vv_old = s["vv"].copy()
        self._vs_old = s["vs"].copy()
        self.t = s["t"]
        self.step_count = s["step"]
        self.h_n = s["h_n"]
        self._deposit_and_solve()

    # ------------------------------------------------------- для рисования
    def phase_hist(self, nx, nv, vmin, vmax, xmin=0.0, xmax=None):
        """Двумерные гистограммы (v, x) для обоих сортов — фазовый портрет как картинка.
        Строка 0 соответствует vmax (как пиксели экрана: сверху вниз)."""
        xmax = self.L if xmax is None else xmax
        out = []
        sx = nx / (xmax - xmin)
        sv = nv / (vmax - vmin)
        for sl in self.sl:
            ix = np.floor((self.x[sl] - xmin) * sx).astype(np.int64)
            iv = np.floor((vmax - self.v[sl]) * sv).astype(np.int64)
            ok = (iv >= 0) & (iv < nv) & (ix >= 0) & (ix < nx)
            h = np.bincount(iv[ok] * nx + ix[ok], minlength=nx * nv).reshape(nv, nx)
            out.append(h)
        return out

    def velocity_hist(self, s, edges):
        h, _ = np.histogram(self.v[self.sl[s]], bins=edges)
        width = edges[1] - edges[0]
        # нормировка: ∫ f dv = n_s
        return h * (self.dens[s] / (self.N * width))
