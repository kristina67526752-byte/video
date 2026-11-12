"""Автоматические проверки физики и численной схемы (все величины в СИ).

    python -m pytest tests          (если установлен pytest)
    python tests/run_all.py         (без pytest)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bpi import dispersion as disp           # noqa: E402
from bpi import diagnostics as diag          # noqa: E402
from bpi import constants as cst             # noqa: E402
from bpi import units                        # noqa: E402
from bpi.pic import PIC, PICParams           # noqa: E402
from bpi.single_wave import SingleWave, saturation_constant  # noqa: E402
from bpi.zakharov import Zakharov, modulational_growth       # noqa: E402

N_P, VB = 1.0e16, 1.0e7
WP = float(cst.plasma_frequency(N_P))


# ----------------------------------------------------------------- единицы и постоянные
def test_si_plasma_parameters():
    """Известные числа: f_p = 8.98·√n Гц, λ_D = 69·√(T/n) м, ν_ei по формуле NRL."""
    assert abs(WP / (2 * np.pi) / (8.9787 * np.sqrt(N_P)) - 1) < 1e-3
    assert abs(cst.debye_length(N_P, 3e4) / (69.01 * np.sqrt(3e4 / N_P)) - 1) < 1e-3
    T_eV = 3e4 * cst.K_B / cst.E_CHARGE
    nrl = 2.91e-12 * N_P * cst.coulomb_logarithm(N_P, 3e4) / T_eV ** 1.5
    assert abs(cst.collision_frequency_ei(N_P, 3e4) / nrl - 1) < 5e-3
    assert abs(cst.kinetic_energy(1e3) / (0.5 * cst.M_E * 1e6) - 1) < 1e-9      # v ≪ c
    assert units.fmt(8.98e8, "Гц") == "898 МГц" and units.fmt(1.2e-4, "м") == "120 мкм"


# ----------------------------------------------------------------- линейная теория
def test_roots_satisfy_dispersion_relation():
    """Каждый из 4 корней действительно обращает D(ω,k) в ноль (в т.ч. релятивистский пучок)."""
    for vb in (1e7, 2.5e8):
        a = 0.01
        sp = disp.beam_plasma_species(N_P, a, vb)
        k = np.linspace(0.1, 2.0, 50) * WP / vb
        r = disp.fluid_roots(k, sp)
        D = 1 - sp[0][0] / r ** 2 - sp[1][0] / (r - k[:, None] * vb) ** 2
        assert np.abs(D).max() < 1e-8


def test_weak_beam_asymptotics():
    """При n_b/n_p → 0 точный γ_max → (√3/2)(n_b/2n_p)^(1/3)ω_p (а не формула подсказки)."""
    a = 1e-6
    _, g, w = disp.most_unstable(disp.beam_plasma_species(N_P, a, 1e6))
    assert abs(g / disp.gamma_weak_beam(a, WP) - 1) < 0.01
    assert abs(g / disp.gamma_hint(a, WP) - 2 ** (-1 / 3)) < 0.01
    assert abs(w / disp.omega_weak_beam(a, WP) - 1) < 1e-3


def test_known_value_alpha_001():
    k, g, w = disp.most_unstable(disp.beam_plasma_species(N_P, 0.01, 1e5))   # v_b ≪ c
    assert abs(g / WP - 0.13647) < 2e-4 and abs(k * 1e5 / WP - 1.0414) < 2e-3


def test_relativistic_growth_scales_as_inverse_gamma():
    """Релятивистский пучок: ω_b² → ω_b²/γ_b³, поэтому γ_max ≈ γ_max(нерел.)/γ_b."""
    g0 = disp.most_unstable(disp.beam_plasma_species(N_P, 1e-4, 1e6))[1]
    for vb in (1.5e8, 2.7e8):
        g = disp.most_unstable(disp.beam_plasma_species(N_P, 1e-4, vb))[1]
        assert abs(g * cst.lorentz_gamma(vb) / g0 - 1) < 0.02


def test_two_stream_textbook():
    """Встречные пучки ±u с ω_p1 каждый: γ_max = ω_p1/2 при ku = (√3/2)ω_p1."""
    k, g, w = disp.most_unstable(disp.two_stream_species(N_P, 2e5))
    assert abs(g / WP - 0.5) < 1e-5
    assert abs(k * 1e5 / WP - np.sqrt(3) / 2) < 1e-4
    assert abs(w / WP) < 1e-8


def test_kinetic_tends_to_fluid_for_cold_beam():
    k = np.linspace(0.8, 1.2, 9) * WP / VB
    _, gf = disp.fluid_growth(k, disp.beam_plasma_species(N_P, 0.01, VB))
    _, gk = disp.kinetic_growth_curve(k, disp.beam_plasma_species(N_P, 0.01, VB, 10.0, 1e-3 * VB))
    assert np.abs(gk - gf).max() / WP < 2e-3


def test_kinetic_curve_has_no_branch_jumps():
    """Кинетический γ(k) при холодном пучке и тёплой плазме (v_Te ≪ v_b) совпадает с
    гидродинамикой Бома–Гросса на ВСЁМ диапазоне k — в том числе при малых k, где
    раньше корень перескакивал на плазменную ветвь и давал γ = 0."""
    sp = disp.beam_plasma_species(N_P, 0.01, VB, 3e4)
    k0 = disp.most_unstable(disp.cold(sp))[0]
    k = np.linspace(1e-3, 2.6, 400) * k0
    _, gbg = disp.fluid_growth(k, sp)
    _, gk = disp.kinetic_growth_curve(k, sp)
    inside = gbg > 0.05 * gbg.max()               # вдали от крутого края у границы
    assert np.abs(gk[inside] - gbg[inside]).max() < 0.01 * gbg.max()
    assert abs(np.maximum(gk, 0).max() / gbg.max() - 1) < 0.01


# ----------------------------------------------------------------- PIC
def test_deposit_conserves_charge():
    for ion in ("none", "H+"):
        s = PIC(PICParams(npart=8192, ion=ion))
        assert abs(s.rho.sum()) * s.dx < 1e-9 * cst.E_CHARGE * N_P * s.L     # нейтральность
        ne = (s.dens_grid[0] + s.dens_grid[1]).sum() * s.dx
        assert abs(ne / ((s.dens[0] + s.dens[1]) * s.L) - 1) < 1e-12


def test_pic_growth_rate_and_conservation():
    """Инкремент главной моды — в пределах 2 % от теории; импульс сохраняется
    точно (схема CIC + чехарда), энергия — лучше 1 % энергии пучка."""
    s = PIC(PICParams(npart=16384))
    tr = diag.StageTracker(s)
    while s.t * s.wpe < 130:
        s.step(20)
        tr.update()
    assert tr.gamma_meas is not None
    assert abs(tr.gamma_meas / s.gamma_ref - 1) < 0.02
    h = s.hist
    P = h["P"].sum(1)
    assert np.abs(P - P[0]).max() < 1e-9 * abs(h["P"][0, 1])
    tot = h["WE"] + h["K"].sum(1)
    assert np.abs(tot - tot[0]).max() / s.K0_beam < 0.01
    assert tr.sat is not None                     # насыщение найдено
    assert 0.9 < tr.sat["A"] / tr.A_trap < 1.3    # и близко к теории захвата
    assert 1e4 < tr.sat["A"] < 3e4                # ≈ 19 кВ/м при n_p = 10¹⁶ м⁻³, v_b = 10⁷ м/с


def test_main_mode_measured_reliably():
    """При рабочем числе частиц (65 536) γ главной волны по двум половинам линейной
    стадии совпадает (разброс < 1 %) и отличается от теории меньше чем на 2 %."""
    s = PIC(PICParams())
    tr = diag.StageTracker(s)
    while tr.stage < 2:
        s.step(20)
        tr.update()
    main = [d for d in diag.measure_modes(s, 0.6) if d["m"] == s.m_main][0]
    assert main["g_err"] < 0.01 * main["g_th"]
    assert abs(main["g"] / main["g_th"] - 1) < 0.02


def test_pic_relativistic_beam():
    """v_b = 0.67c: инкремент совпадает с теорией (с γ_b³), скорости не превышают c."""
    s = PIC(PICParams(npart=16384, vb=2.0e8))
    tr = diag.StageTracker(s)
    while s.t * s.wpe < 170:
        s.step(20)
        tr.update()
    assert abs(tr.gamma_meas / s.gamma_ref - 1) < 0.03
    assert np.abs(s.v).max() < cst.C_LIGHT
    assert tr.sat is not None and 0.9 < tr.sat["A"] / tr.A_trap < 1.3


def test_rewind_is_deterministic():
    s = PIC(PICParams(npart=4096, snap_every=50, ion="H+"))
    s.step(150)
    x1 = s.x.copy()
    s.rewind(1)                                    # назад на снимок шага 100
    assert s.step_count == 100
    s.step(50)
    assert np.array_equal(s.x, x1)


def test_separatrix_limits():
    """Сепаратриса: при v ≪ c совпадает с (v − v_ф)² = 2eE₀(1 − sin)/(mk); всегда |v| < c."""
    x = np.linspace(0, 0.02, 50)
    k, E0, vph = 600.0, 2e4, 9e6
    vu, vd = diag.separatrix(x, E0, k, 0.3, vph)
    ref = np.sqrt(2 * cst.E_CHARGE * E0 / (cst.M_E * k) * (1 - np.sin(k * x + 0.3)))
    assert np.abs(vu - vph - ref).max() < 2e-3 * ref.max()
    vu, vd = diag.separatrix(x, 5e7, 2.0, 0.3, 2.8e8)
    assert vu.max() < cst.C_LIGHT and vd.min() > -cst.C_LIGHT


# ----------------------------------------------------------------- одноволновая модель
def test_single_wave_linear_and_momentum():
    sw = SingleWave(alpha=0.01, n=1024, dt_wp=0.05)
    sw.step(1200)                                  # t = 60/ω_p, ещё линейная стадия
    t, A, w, P = sw.series()
    sel = (t * sw.wp > 25) & (t * sw.wp < 55)
    g = diag.fit_exp(t[sel], A[sel])[0]
    assert abs(g / sw.gamma_th - 1) < 0.01
    assert abs(np.median(w[sel]) - (sw.wp + sw.domega_th)) < 2e-3 * sw.wp
    assert np.abs(P - P[0]).max() < 1e-9 * abs(P[0])


def test_saturation_constant_is_universal():
    """(ω_B/γ)² в первом максимуме не зависит ни от n_b/n_p, ни от n_p, ни от v_b (v_b ≪ c)."""
    c1 = saturation_constant(0.001, n=2048)[0]
    c2 = saturation_constant(0.05, vb=3e6, n_p=1e11, n=2048)[0]
    assert abs(c1 - diag.C_TRAP) < 0.02 and abs(c2 - diag.C_TRAP) < 0.02


# ----------------------------------------------------------------- уравнения Захарова
def test_zakharov_exact_soliton():
    """Точный солитон сохраняет форму и движется со скоростью V; число плазмонов постоянно."""
    z = Zakharov(damping=False)
    z.add_soliton(0.05, 0.3 * z.L, mach=0.5)
    f0, N0 = z.fit_soliton(), z.plasmons()
    z.step(3000)
    f1 = z.fit_soliton()
    assert abs(f1["W_m"] / f0["W_m"] - 1) < 2e-3
    assert abs(f1["delta"] / f0["delta"] - 1) < 5e-3
    assert abs((f1["x_m"] - f0["x_m"]) - 0.5 * z.cs * z.t) < 1.5 * z.dx      # V = 0.5·c_s
    assert abs(z.plasmons() / N0 - 1) < 1e-9
    # ширина покоящегося солитона: Δ = λ_D√(6τ/W_m)
    z = Zakharov(damping=False)
    z.add_soliton(0.02, 0.5 * z.L)
    f = z.fit_soliton()
    assert abs(f["delta"] / f["delta_th"] - 1) < 5e-3


def test_zakharov_modulational_growth():
    """Рост возмущения концентрации совпадает с корнем многочлена 4-й степени."""
    W0 = 0.02
    z = Zakharov(damping=False)
    z.set_pump(W0, 0.07 / z.lambda_D, noise=1e-10)
    q = 2 * np.pi * np.arange(1, 60) / z.L
    gth = modulational_growth(q, W0, z.k0, z.n_p, z.T_e, z.T_i)
    j = int(np.argmax(gth))
    ts, amps = [], []
    while z.t * gth[j] < 11:
        z.step(20)
        ts.append(z.t)
        amps.append(abs(z.nk[j + 1]) + abs(z.nk[-(j + 1)]))
    ts, amps = np.array(ts), np.array(amps)
    sel = ts * gth[j] > 6
    g = diag.fit_exp(ts[sel], amps[sel])[0]
    assert abs(g / gth[j] - 1) < 0.02
