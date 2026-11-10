"""
Одномерный электростатический PIC-код (Particle-In-Cell, «частицы в ячейках»).
Все величины — в единицах СИ.

Что моделируется
----------------
Электроны плазмы (сорт 0), электроны пучка (сорт 1) и — если включены —
ионы (сорт 2) в периодическом ящике длины L [м].  Если ионы «неподвижны»,
они заменяются однородным положительным фоном.

Уравнения (СИ)
--------------
    dx_j/dt = v_j                              (1)  движение частицы
    dp_j/dt = q_s E(x_j),   p = γ m_s v        (2)  второй закон Ньютона (релятивистский)
    ∂E/∂x   = ρ/ε₀,   ρ = Σ_s q_s n_s(x)       (3)  теорема Гаусса (уравнение Пуассона) в 1D

q = −e для электронов, +e для ионов.  γ = 1/√(1 − v²/c²) = √(1 + u²/c²), где
u = γv = p/m — «импульс на единицу массы» [м/с]; именно u хранится для каждой
частицы.  При v ≪ c уравнение (2) переходит в m dv/dt = qE.

Магнитного поля в задаче нет: всё зависит только от x, ток продольный, и в
одномерной геометрии (∇×B)_x = 0, поэтому продольное поле чисто потенциальное.
Средний ток пучка замыкается через внешнюю цепь установки (среднее поле ⟨E⟩ = 0).

Один шаг по времени Δt (схема «чехарда», leapfrog, 2-й порядок точности)
------------------------------------------------------------------------
  1. Взвешивание (CIC — «облако в ячейке»): частица в точке x между узлами
     i и i+1 отдаёт в узел i долю (1−f), в узел i+1 — долю f, где f = x/Δx − i.
     Так получаем концентрацию n_s [м⁻³] каждого сорта в узлах сетки.
  2. Поле: ρ = Σ q_s n_s [Кл/м³], затем E из теоремы Гаусса через быстрое
     преобразование Фурье:  i k E_k = ρ_k/ε₀  ⇒  E_k = ρ_k/(i k ε₀)   (E_0 = 0).
     Перед этим ρ_k умножается на фильтр F(k) = cos⁴(kΔx/2) — двойное
     сглаживание (1,2,1)/4, которое убирает шум сетки.
  3. Интерполяция поля в точки частиц теми же весами (1−f, f).
  4. Импульсы:   u^{n+½} = u^{n−½} + (q_s/m_s)·E(x^n)·Δt.
  5. Скорости:   v = u/√(1 + u²/c²);  координаты: x^{n+1} = x^n + v^{n+½}·Δt,
     затем x приводится в [0, L).

Импульсы хранятся в полуцелые моменты времени, координаты — в целые.
Схема устойчива при ω_p Δt < 2; ошибка частоты ≈ (ω_p Δt)²/24 (0.04 % при ω_pΔt = 0.1).

Энергия (плотность, усреднённая по ящику, Дж/м³)
------------------------------------------------
    W_E = ε₀⟨E²⟩/2                         — энергия электрического поля
    K_s = n_s ⟨(γ − 1) m_s c²⟩             — кинетическая энергия сорта s
Сумма W_E + Σ K_s должна сохраняться — это главная проверка счёта.
«Вес» макрочастицы w_s = n_s L/N [м⁻²] — сколько реальных частиц (на 1 м²
сечения пучка) она представляет.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace

import numpy as np

from . import dispersion as disp
from .constants import (E_CHARGE, M_E, EPS0, K_B, C_LIGHT, IONS, plasma_frequency,
                        thermal_velocity, debye_length, lorentz_gamma, kinetic_energy,
                        ion_sound_speed, coulomb_logarithm, collision_frequency_ei,
                        landau_damping_rate)


@dataclass
class PICParams:
    scenario: str = "beam"     # "beam" — пучок в плазме; "two_stream" — встречные пучки
    n_p: float = 1.0e16        # концентрация электронов плазмы n_p, м⁻³
    T_e: float = 3.0e4         # температура электронов плазмы T_e, К
    alpha: float = 0.01        # отношение концентраций n_b / n_p (безразмерное)
    vb: float = 1.0e7          # скорость пучка v_b, м/с (для two_stream — относительная скорость потоков)
    dvb: float = 0.0           # тепловой разброс скоростей пучка Δv_b (σ), м/с
    ion: str = "none"          # ионы: "none" — неподвижный фон; "H+", "D+", "He+", "Ar+", "O+"
    T_i: float = 3.0e3         # температура ионов T_i, К
    n_waves: int = 8           # сколько длин самой неустойчивой волны укладывается в ящик
    ng: int = 1024             # число узлов сетки
    npart: int = 65536         # макрочастиц каждого сорта
    dt_wp: float = 0.1         # шаг по времени в долях 1/ω_pe:  Δt = dt_wp/ω_pe  [с]
    seed_amp: float = 1e-4     # затравка: δn_b/n_b главной моды
    seed_other: float = 0.1    # амплитуда затравки остальных мод относительно главной
    rng_seed: int = 1          # зерно генератора случайных фаз затравки
    snap_every: int = 200      # как часто запоминать состояние (для перемотки назад)
    max_snaps: int = 24        # сколько снимков хранить (старые прореживаются)
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
    g_j = Φ⁻¹(q_j), где Φ⁻¹ — обратная функция нормального распределения."""
    from scipy.special import ndtri
    return ndtri(_bit_reversed_quantiles(n))


class PIC:
    """Состояние и шаг PIC-модели. Всё хранится в numpy-массивах,
    один шаг — около 25 векторных операций над всеми частицами."""

    def __init__(self, p: PICParams | None = None):
        self.p = p = p or PICParams()
        if not 0 < abs(p.vb) < C_LIGHT:
            raise ValueError("скорость пучка должна быть меньше скорости света")
        two = p.scenario == "two_stream"
        self.m_i = IONS.get(p.ion)                 # масса иона, кг (None — ионы неподвижны)
        self.wpe = float(plasma_frequency(p.n_p))  # плазменная частота электронов плазмы, рад/с
        self.dt = p.dt_wp / self.wpe               # шаг по времени, с
        self.vte = float(thermal_velocity(p.T_e))  # тепловая скорость электронов плазмы, м/с
        self.lambda_D = self.vte / self.wpe        # дебаевский радиус, м

        # ---- сорта частиц: заряд q [Кл], масса m [кг], концентрация n [м⁻³],
        #      скорость потока u0 [м/с], тепловой разброс vt [м/с]
        if two:
            u = 0.5 * p.vb
            sp = [dict(name="поток 1 (←)", q=-E_CHARGE, m=M_E, n=p.n_p, u0=-u, vt=p.dvb),
                  dict(name="поток 2 (→)", q=-E_CHARGE, m=M_E, n=p.n_p, u0=+u, vt=p.dvb)]
            self.theory_species = disp.two_stream_species(p.n_p, p.vb, p.dvb, self.m_i, p.T_i)
        else:
            sp = [dict(name="электроны плазмы", q=-E_CHARGE, m=M_E, n=p.n_p, u0=0.0, vt=self.vte),
                  dict(name="электроны пучка", q=-E_CHARGE, m=M_E, n=p.alpha * p.n_p, u0=p.vb,
                       vt=p.dvb)]
            self.theory_species = disp.beam_plasma_species(p.n_p, p.alpha, p.vb, p.T_e, p.dvb,
                                                           self.m_i, p.T_i)
        n_e_tot = sum(s["n"] for s in sp)
        if self.m_i:
            sp.append(dict(name="ионы", q=+E_CHARGE, m=self.m_i, n=n_e_tot, u0=0.0,
                           vt=float(thermal_velocity(p.T_i, self.m_i))))
        self.sp = sp
        self.ns = len(sp)
        self.names = tuple(s["name"] for s in sp)
        self.dens = np.array([s["n"] for s in sp])                # n_s, м⁻³
        self.q = np.array([s["q"] for s in sp])                   # Кл
        self.m = np.array([s["m"] for s in sp])                   # кг
        # неподвижный фон ионов нейтрализует электроны: ρ_фон = e·Σn_e, Кл/м³
        self.rho_bg = 0.0 if self.m_i else E_CHARGE * n_e_tot

        # ---- линейная теория: самая неустойчивая волна (холодное уравнение из задания)
        cold = disp.cold(self.theory_species)
        self.k_max, self.gamma_max, self.omega_r = disp.most_unstable(cold)
        # ящик подбирается так, чтобы в нём укладывалось ровно n_waves длин этой волны
        self.L = 2 * np.pi * p.n_waves / self.k_max               # м
        self.dx = self.L / p.ng                                   # м
        self.k_modes = 2 * np.pi * np.arange(p.ng // 2 + 1) / self.L   # рад/м
        k_safe = self.k_modes.copy()
        k_safe[0] = 1.0
        self._inv_ik = 1.0 / (1j * k_safe * EPS0)                 # 1/(i k ε₀) для решения Пуассона
        self._inv_ik[0] = 0.0
        # сглаживающий фильтр (1,2,1)/4, применённый n_filter раз: F(k) = cos^{2n}(kΔx/2).
        # Подавляет коротковолновый шум сетки (численный нагрев); на рабочие волны
        # почти не влияет: для главной волны kΔx ≈ 0.05 и F ≈ 0.999.
        self._filt = np.cos(0.5 * self.k_modes * self.dx) ** (2 * p.n_filter)
        # более сильное сглаживание (8 раз, ширина ≈ 2 ячейки ≈ 1.5 λ_D) — только для ВЫВОДА
        # концентрации ионов: убирает дробовой шум макрочастиц на масштабе ячейки,
        # каверны (шириной ≳ 10 λ_D) не искажает. На счёт не влияет.
        self._filt_diag = np.cos(0.5 * self.k_modes * self.dx) ** 16
        # инкремент каждой моды ящика по теории
        self.m_store = min(6 * p.n_waves, p.ng // 2)              # сколько мод записывать в историю
        km = self.k_modes[1:self.m_store + 1]
        self.omega_modes_cold, self.gamma_modes_cold = disp.fluid_growth(km, cold)
        if any(vt > 0 for (_, _, vt) in self.theory_species):
            # реальные температуры: точная кинетическая теория (функция Z) — учитывает
            # поправку Бома–Гросса, затухание Ландау и тёплый пучок
            wr, gk = disp.kinetic_growth_curve(km, self.theory_species)
            self.omega_modes_th, self.gamma_modes_th = wr, np.maximum(gk, 0.0)
            self.theory_kind = "кинетическая теория (функция дисперсии плазмы Z)"
        else:
            self.omega_modes_th, self.gamma_modes_th = self.omega_modes_cold, self.gamma_modes_cold
            self.theory_kind = "холодная гидродинамика (уравнение 4-й степени)"
        # главная (самая быстрая) мода ящика и её инкремент
        self.m_main = int(np.argmax(self.gamma_modes_th)) + 1
        self.gamma_ref = float(self.gamma_modes_th[self.m_main - 1])   # рад/с
        self.omega_ref = float(self.omega_modes_th[self.m_main - 1])   # рад/с
        self.v_phase = self.omega_ref / self.k_modes[self.m_main]      # фазовая скорость, м/с

        # ---- частицы ---------------------------------------------------------
        N = p.npart
        self.N = N
        self.w = self.dens * self.L / N                           # вес макрочастицы, м⁻²
        rng = np.random.default_rng(p.rng_seed)
        x0 = (np.arange(N) + 0.5) * self.L / N                    # равномерная решётка (тихий старт)
        g = _quiet_gaussian(N)
        xs, vs = [], []
        vlim = 0.9995 * C_LIGHT
        for s, d in enumerate(sp):
            x = x0.copy()
            v = d["u0"] + d["vt"] * g if d["vt"] > 0 else np.full(N, d["u0"], dtype=float)
            np.clip(v, -vlim, vlim, out=v)
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
        self.x = np.concatenate(xs)                               # координаты, м
        self.v = np.concatenate(vs)                               # скорости, м/с
        self.u = self.v * lorentz_gamma(self.v)                   # u = γv, м/с
        self.sl = tuple(slice(s * N, (s + 1) * N) for s in range(self.ns))
        self._qmdt = np.concatenate([np.full(N, d["q"] / d["m"] * self.dt) for d in sp])
        self._gam = np.empty_like(self.u)
        self._tmp = np.empty_like(self.u)
        self._ic2 = 1.0 / C_LIGHT ** 2
        self._kfac = self.w * self.m / self.L                     # множитель плотности энергии сорта

        self.t = 0.0
        self.step_count = 0
        self.E2avg = np.zeros(p.ng)                               # ⟨E²⟩ за плазменный период, (В/м)²
        self._avg_rate = p.dt_wp / (2 * np.pi)                    # Δt/T_p для скользящего среднего
        # начальное поле и «полшага назад» для импульсов (запуск чехарды)
        self._deposit_and_solve()
        self.u -= self._gather() * (0.5 * self._qmdt)             # u^{-1/2} = u^0 − (q/m)E·Δt/2
        self._update_velocity()
        self._K_old, self._P_old = self._moments()

        # начальная плотность кинетической энергии пучка (точно, по начальным скоростям), Дж/м³
        self.K0_beam = float(self.dens[1] * np.mean(kinetic_energy(vs[1])))
        self._init_history()
        self.snapshots = []
        self._save_snapshot()

    # ------------------------------------------------------------------ шаги
    def _deposit_and_solve(self):
        """Шаги 1–2: концентрации методом CIC и поле из теоремы Гаусса (БПФ)."""
        ng = self.p.ng
        xi = self.x * (1.0 / self.dx)
        i = xi.astype(np.int64)
        np.minimum(i, ng - 1, out=i)          # страховка от x == L из-за округления
        f = xi - i
        self._i, self._f = i, f
        self.dens_grid = []
        rho = np.full(ng, self.rho_bg)
        for s, sl in enumerate(self.sl):
            c = np.bincount(i[sl], weights=1.0 - f[sl], minlength=ng + 1)
            c += np.bincount(i[sl] + 1, weights=f[sl], minlength=ng + 1)
            c[0] += c[ng]                     # узел ng — это тот же узел 0 (периодичность)
            n_s = c[:ng] * (self.w[s] / self.dx)                   # концентрация сорта s, м⁻³
            self.dens_grid.append(n_s)
            rho += self.q[s] * n_s            # плотность заряда, Кл/м³
        self.rho = rho
        rho_k = np.fft.rfft(rho)
        self.Ek = rho_k * self._inv_ik * self._filt   # E_k = F(k)·ρ_k / (i k ε₀)
        self.E = np.fft.irfft(self.Ek, ng)            # напряжённость поля в узлах, В/м
        self._Eext = np.append(self.E, self.E[0])     # E в узлах 0..N_g (узел N_g = узел 0)
        self._dE = np.diff(self._Eext)                # E_{i+1} − E_i
        # среднее ⟨E²⟩ за плазменный период (для огибающей поля и каверн)
        self.E2avg += (self.E * self.E - self.E2avg) * self._avg_rate

    def _gather(self):
        """Шаг 3: поле в точке частицы  E_p = E_i (1−f) + E_{i+1} f,  В/м."""
        i, f = self._i, self._f
        return np.take(self._Eext, i) + f * np.take(self._dE, i)

    def _update_velocity(self):
        """γ = √(1 + u²/c²),  v = u/γ."""
        np.multiply(self.u, self.u, out=self._tmp)
        self._tmp *= self._ic2
        self._tmp += 1.0
        np.sqrt(self._tmp, out=self._gam)
        np.divide(self.u, self._gam, out=self.v)

    def _moments(self):
        """Плотность кинетической энергии [Дж/м³] и импульса [кг·м/с на м³] каждого сорта.
        (γ − 1)mc² = m u²/(γ + 1) — без потери точности при v ≪ c."""
        np.multiply(self.u, self.u, out=self._tmp)
        self._tmp /= (self._gam + 1.0)
        K = np.array([self._tmp[sl].sum() for sl in self.sl]) * self._kfac
        P = np.array([self.u[sl].sum() for sl in self.sl]) * self._kfac
        return K, P

    def step(self, n=1):
        """Сделать n шагов по времени."""
        dt, L = self.dt, self.L
        for _ in range(n):
            # поле в момент t^n уже посчитано (в конце предыдущего шага)
            self._record()
            Ep = self._gather()
            Ep *= self._qmdt
            self.u += Ep                                     # (2): u^{n+1/2}
            self._update_velocity()
            K_new, P_new = self._moments()
            # кинетическая энергия и импульс в момент t^n — среднее по соседним полушагам
            self._finish_record(0.5 * (self._K_old + K_new), 0.5 * (self._P_old + P_new))
            self._K_old, self._P_old = K_new, P_new
            np.multiply(self.v, dt, out=self._tmp)
            self.x += self._tmp                              # (1): x^{n+1}
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
        self.h_K = np.zeros((cap, self.ns))
        self.h_P = np.zeros((cap, self.ns))
        self.h_Ek = np.zeros((cap, self.m_store), dtype=complex)
        self.h_dni = np.zeros(cap)

    def _grow(self):
        cap = self.h_t.size * 2
        for name in ("h_t", "h_WE", "h_K", "h_P", "h_Ek", "h_dni"):
            a = getattr(self, name)
            b = np.zeros((cap,) + a.shape[1:], dtype=a.dtype)
            b[:a.shape[0]] = a
            setattr(self, name, b)

    def _record(self):
        if self.h_n >= self.h_t.size:
            self._grow()
        j = self.h_n
        self.h_t[j] = self.t
        self.h_WE[j] = 0.5 * EPS0 * np.dot(self.E, self.E) / self.p.ng     # ε₀⟨E²⟩/2, Дж/м³
        # комплексная амплитуда моды m: E(x) = Σ_m 2|E_m| cos(k_m x + arg E_m), В/м
        self.h_Ek[j] = self.Ek[1:self.m_store + 1] / self.p.ng
        if self.m_i:
            d = self.ion_perturbation()
            self.h_dni[j] = np.sqrt(np.mean(d * d))

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
                    P=self.h_P[:n], Ek=self.h_Ek[:n], dni=self.h_dni[:n])

    def ion_perturbation(self):
        """Относительное возмущение концентрации ионов δn_i/n_i в узлах сетки
        (сглаженное: без дробового шума макрочастиц). Без подвижных ионов — нули."""
        if not self.m_i:
            return np.zeros(self.p.ng)
        nk = np.fft.rfft(self.dens_grid[-1] / self.dens[-1] - 1.0)
        return np.fft.irfft(nk * self._filt_diag, self.p.ng)

    def mode_amplitudes(self):
        """Амплитуды мод сейчас, В/м: E(x) = Σ A_m cos(k_m x + φ_m), A_m = 2|E_k|/N_g."""
        return 2.0 * np.abs(self.Ek[1:]) / self.p.ng

    def main_amplitude(self):
        """Амплитуда главной волны E₀ = 2|E_k|/N_g, В/м."""
        return 2.0 * abs(self.Ek[self.m_main]) / self.p.ng

    # ------------------------------------------------------- перемотка
    def _save_snapshot(self):
        self.snapshots.append(dict(
            step=self.step_count, t=self.t, x=self.x.copy(), u=self.u.copy(),
            K=self._K_old.copy(), P=self._P_old.copy(), E2=self.E2avg.copy(), h_n=self.h_n))
        if len(self.snapshots) > self.p.max_snaps:
            # прореживаем старую половину (начальный снимок остаётся всегда)
            half = len(self.snapshots) // 2
            self.snapshots = self.snapshots[:1] + self.snapshots[1:half:2] + self.snapshots[half:]

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
        self.u[:] = s["u"]
        self._update_velocity()
        self._K_old = s["K"].copy()
        self._P_old = s["P"].copy()
        self.t = s["t"]
        self.step_count = s["step"]
        self.h_n = s["h_n"]
        self.E2avg[:] = s["E2"]
        keep = self.E2avg.copy()
        self._deposit_and_solve()
        self.E2avg[:] = keep                 # снимок уже содержит среднее на этот момент

    # ------------------------------------------------------- для рисования
    def phase_hist(self, nx, nv, vmin, vmax, xmin=0.0, xmax=None, species=(0, 1)):
        """Двумерные гистограммы (v, x) для сортов species — фазовый портрет как картинка.
        Строка 0 соответствует vmax (как пиксели экрана: сверху вниз)."""
        xmax = self.L if xmax is None else xmax
        out = []
        sx = nx / (xmax - xmin)
        sv = nv / (vmax - vmin)
        for s in species:
            sl = self.sl[s]
            ix = np.floor((self.x[sl] - xmin) * sx).astype(np.int64)
            iv = np.floor((vmax - self.v[sl]) * sv).astype(np.int64)
            ok = (iv >= 0) & (iv < nv) & (ix >= 0) & (ix < nx)
            h = np.bincount(iv[ok] * nx + ix[ok], minlength=nx * nv).reshape(nv, nx)
            out.append(h)
        return out

    def velocity_hist(self, s, edges):
        """Функция распределения сорта s по скоростям f(v) [с/м⁴]: ∫ f dv = n_s."""
        h, _ = np.histogram(self.v[self.sl[s]], bins=edges)
        width = edges[1] - edges[0]
        return h * (self.dens[s] / (self.N * width))

    # ------------------------------------------------------- паспорт плазмы (СИ)
    def info(self):
        """Производные параметры плазмы и пучка в СИ и проверка допущений модели."""
        p = self.p
        k = self.k_modes[self.m_main]
        gb = float(lorentz_gamma(p.vb if p.scenario == "beam" else 0.5 * p.vb))
        nu = float(collision_frequency_ei(p.n_p, p.T_e))
        d = dict(
            wpe=self.wpe, fpe=self.wpe / (2 * np.pi), Tpe=2 * np.pi / self.wpe,
            vte=self.vte, lambda_D=self.lambda_D,
            N_D=p.n_p * self.lambda_D ** 3,                    # электронов в дебаевском кубе
            lnL=coulomb_logarithm(p.n_p, p.T_e), nu_ei=nu,
            gamma_b=gb, beta_b=p.vb / C_LIGHT,
            W_b=float(kinetic_energy(p.vb)),                   # энергия электрона пучка, Дж
            lam=2 * np.pi / k, k_lD=k * self.lambda_D,
            landau=float(landau_damping_rate(k, p.n_p, p.T_e)),
            dx_over_lD=self.dx / self.lambda_D if self.lambda_D > 0 else np.inf,
            real_per_macro=self.w[0],                          # электронов на 1 м² в макрочастице
            # параметр Тоде–Судана: при S ≪ 1 захват в системе пучка нерелятивистский
            S=(p.vb / C_LIGHT) ** 2 * gb * np.cbrt(p.alpha / 2.0),
        )
        if self.m_i:
            d.update(mass_ratio=self.m_i / M_E, wpi=float(plasma_frequency(self.dens[-1], self.m_i)),
                     cs=float(ion_sound_speed(p.T_e, p.T_i, self.m_i)))
        return d
