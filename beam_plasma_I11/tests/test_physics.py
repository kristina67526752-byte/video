"""Автоматические проверки физики и численной схемы.

    python -m pytest tests          (если установлен pytest)
    python tests/run_all.py         (без pytest)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bpi import dispersion as disp           # noqa: E402
from bpi import diagnostics as diag          # noqa: E402
from bpi.pic import PIC, PICParams           # noqa: E402
from bpi.single_wave import SingleWave, saturation_constant  # noqa: E402


# ----------------------------------------------------------------- линейная теория
def test_roots_satisfy_dispersion_relation():
    """Каждый из 4 корней действительно обращает D(ω,k) в ноль."""
    a = 0.01
    k = np.linspace(0.1, 2.0, 50)
    r = disp.fluid_roots(k, disp.beam_plasma_species(a))
    D = 1 - 1 / r**2 - a / (r - k[:, None]) ** 2
    assert np.abs(D).max() < 1e-9


def test_weak_beam_asymptotics():
    """При α → 0 точный γ_max → (√3/2)(α/2)^(1/3) (а не формула подсказки)."""
    a = 1e-6
    _, g, w = disp.most_unstable(disp.beam_plasma_species(a))
    assert abs(g / disp.gamma_weak_beam(a) - 1) < 0.01
    assert abs(g / disp.gamma_hint(a) - 2 ** (-1 / 3)) < 0.01
    assert abs(w - disp.omega_weak_beam(a)) < 1e-3


def test_known_value_alpha_001():
    k, g, w = disp.most_unstable(disp.beam_plasma_species(0.01))
    assert abs(g - 0.13647) < 2e-4 and abs(k - 1.0414) < 2e-3


def test_two_stream_textbook():
    """Встречные пучки ±u с ω_b² = 1 каждый: γ_max = ω_b/2 при ku = (√3/2)ω_b."""
    k, g, w = disp.most_unstable(disp.two_stream_species(1.0))
    assert abs(g - 0.5) < 1e-6
    assert abs(k * 0.5 - np.sqrt(3) / 2) < 1e-4
    assert abs(w) < 1e-8


def test_kinetic_tends_to_fluid_for_cold_beam():
    k = np.linspace(0.8, 1.2, 9)
    _, gf = disp.fluid_growth(k, disp.beam_plasma_species(0.01))
    _, gk = disp.kinetic_growth_curve(k, disp.beam_plasma_species(0.01, 1.0, 0.0, 1e-3))
    assert np.abs(gk - gf).max() < 2e-3


# ----------------------------------------------------------------- PIC
def test_deposit_conserves_charge():
    s = PIC(PICParams(npart=8192))
    total = s.ne.sum() * s.dx
    assert abs(total - s.n_ion * s.L) < 1e-9 * s.L


def test_pic_growth_rate_and_conservation():
    """Инкремент главной моды — в пределах 2 % от теории; импульс сохраняется
    точно (схема CIC + чехарда), энергия — лучше 1 % энергии пучка."""
    s = PIC(PICParams(npart=16384))
    tr = diag.StageTracker(s)
    while s.t < 130:
        s.step(20)
        tr.update()
    assert tr.gamma_meas is not None
    assert abs(tr.gamma_meas / s.gamma_ref - 1) < 0.02
    h = s.hist
    P = h["P"].sum(1)
    assert np.abs(P - P[0]).max() < 1e-9
    tot = h["WE"] + h["K"].sum(1)
    assert np.abs(tot - tot[0]).max() / s.K0_beam < 0.01
    assert tr.sat is not None                     # насыщение найдено
    assert 0.9 < tr.sat["A"] / tr.A_trap < 1.3    # и близко к теории захвата


def test_rewind_is_deterministic():
    s = PIC(PICParams(npart=4096, snap_every=50))
    s.step(150)
    x1 = s.x.copy()
    s.rewind(1)                                    # назад на снимок t = 10
    assert abs(s.t - 10.0) < 1e-9
    s.step(50)
    assert np.array_equal(s.x, x1)


# ----------------------------------------------------------------- одноволновая модель
def test_single_wave_linear_and_momentum():
    sw = SingleWave(alpha=0.01, n=1024, dt=0.05)
    sw.step(1200)                                  # t = 60, ещё линейная стадия
    t, A, w, P = sw.series()
    sel = (t > 25) & (t < 55)
    g = np.polyfit(t[sel], np.log(A[sel]), 1)[0]
    assert abs(g / sw.gamma_th - 1) < 0.01
    assert abs(np.median(w[sel]) - (1 + sw.domega_th)) < 2e-3
    assert np.abs(P - P[0]).max() < 1e-9


def test_saturation_constant_is_universal():
    c1 = saturation_constant(0.001, n=2048)[0]
    c2 = saturation_constant(0.05, n=2048)[0]
    assert abs(c1 - diag.C_TRAP) < 0.02 and abs(c2 - diag.C_TRAP) < 0.02
