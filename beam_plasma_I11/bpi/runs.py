"""Один «эксперимент»: PIC-счёт до насыщения и чуть дальше + все измерения (в СИ).

Используется окном «Таблица насыщения» и скриптом experiments/run_experiments.py.
Счёт можно продвигать порциями (advance), чтобы интерфейс не замирал.
"""
from __future__ import annotations

import time

import numpy as np

from .pic import PIC, PICParams
from . import diagnostics as diag
from .constants import lorentz_gamma


class SatRun:
    def __init__(self, p: PICParams, t_end_factor=2.0, t_max=None):
        self.p = p
        self.sim = PIC(p)
        self.tr = diag.StageTracker(self.sim)
        self.t_end = None
        self.t_end_factor = t_end_factor
        g = self.sim.gamma_ref
        self.t_max = t_max or (30.0 / g + 100.0 / self.sim.wpe)       # с
        self.done = False
        self.wall = 0.0

    def advance(self, nsteps=50):
        if self.done:
            return True
        t0 = time.perf_counter()
        s, tr = self.sim, self.tr
        for _ in range(max(1, nsteps // 10)):
            s.step(10)
            tr.update()
            if self.t_end is None and tr.sat is not None:
                ts = tr.sat["t"]
                Tb = 2 * np.pi / (diag.OMEGA_B_OVER_GAMMA * s.gamma_ref)
                self.t_end = max(ts + 2 * Tb, self.t_end_factor * ts)
            if (self.t_end is not None and s.t >= self.t_end) or s.t >= self.t_max:
                self.done = True
                break
        self.wall += time.perf_counter() - t0
        return self.done

    def progress(self):
        if self.t_end is not None:
            return min(1.0, self.sim.t / self.t_end)
        # до насыщения: оценка по амплитуде главной волны (лог. шкала)
        s = self.sim
        A = s.main_amplitude()
        a0 = 2 * abs(s.h_Ek[0, s.m_main - 1]) if s.h_n else A
        tiny = 1e-14 * self.tr.A_trap
        lo, hi = np.log(max(a0, tiny)), np.log(self.tr.A_trap)
        return 0.6 * float(np.clip((np.log(max(A, tiny)) - lo) / (hi - lo), 0, 1))

    def result(self):
        """Строка журнала: все параметры и результаты счёта в СИ."""
        s, tr, p = self.sim, self.tr, self.p
        k = s.k_modes[s.m_main]
        gph = float(lorentz_gamma(s.v_phase))
        r = dict(scenario=p.scenario, n_p=p.n_p, T_e=p.T_e, alpha=p.alpha, vb=p.vb, dvb=p.dvb,
                 ion=p.ion, T_i=p.T_i, npart=p.npart, ng=p.ng, dt=s.dt, dt_wp=p.dt_wp,
                 n_waves=p.n_waves, seed=p.rng_seed, wpe=s.wpe, L=s.L,
                 k_main=k, gamma_th=s.gamma_ref, gamma_cold=s.gamma_max, omega_th=s.omega_ref,
                 gamma_meas=tr.gamma_meas if tr.gamma_meas is not None else np.nan,
                 E_trap=tr.A_trap, K_b0=s.K0_beam)
        if tr.sat is not None:
            Es = tr.sat["A"]
            r.update(t_sat=tr.sat["t"], E_sat=Es,
                     wB_over_g=float(diag.bounce_frequency(Es, k, gph)) / s.gamma_ref,
                     WE_sat=tr.sat["WE"], WE_sat_frac=tr.sat["WE"] / s.K0_beam,
                     bounce_T=tr.bounce if tr.bounce is not None else np.nan)
        else:
            r.update(t_sat=np.nan, E_sat=np.nan, wB_over_g=np.nan, WE_sat=np.nan,
                     WE_sat_frac=np.nan, bounce_T=np.nan)
        h = s.hist
        n = s.h_n
        tot = h["WE"] + h["K"].sum(1)
        r["energy_err"] = float(np.abs(tot - tot[0]).max() / s.K0_beam)
        r["t_end"] = s.t
        nav = max(1, int(50 / p.dt_wp))          # среднее по последним 50/ω_p
        r["WE_end"] = float(h["WE"][n - nav:].mean())
        r["WE_end_frac"] = r["WE_end"] / s.K0_beam
        if p.scenario == "beam":
            q = diag.ql_prediction(s)
            r.update(plateau_v1=q["v1"], plateau_v2=q["v2"], WE_ql_frac=q["WE_ql"] / s.K0_beam)
        else:
            r.update(plateau_v1=np.nan, plateau_v2=np.nan, WE_ql_frac=np.nan)
        r["wall_s"] = self.wall
        return r


def run_to_end(p: PICParams, **kw):
    sr = SatRun(p, **kw)
    while not sr.advance(200):
        pass
    return sr
