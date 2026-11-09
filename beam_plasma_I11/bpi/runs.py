"""Один «эксперимент»: PIC-счёт до насыщения и чуть дальше + все измерения.

Используется окном «Таблица насыщения» и скриптом experiments/run_experiments.py.
Счёт можно продвигать порциями (advance), чтобы интерфейс не замирал.
"""
from __future__ import annotations

import time

import numpy as np

from .pic import PIC, PICParams
from . import diagnostics as diag


class SatRun:
    def __init__(self, p: PICParams, t_end_factor=2.0, t_max=None):
        self.p = p
        self.sim = PIC(p)
        self.tr = diag.StageTracker(self.sim)
        self.t_end = None
        self.t_end_factor = t_end_factor
        g = self.sim.gamma_ref
        self.t_max = t_max or (30.0 / g + 100.0)
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
        A = 2 * abs(s.Ek[s.m_main]) / s.p.ng
        a0 = 2 * abs(s.h_Ek[0, s.m_main - 1]) if s.h_n else A
        lo, hi = np.log(max(a0, 1e-14)), np.log(self.tr.A_trap)
        return 0.6 * float(np.clip((np.log(max(A, 1e-14)) - lo) / (hi - lo), 0, 1))

    def result(self):
        s, tr, p = self.sim, self.tr, self.p
        k = s.k_modes[s.m_main]
        r = dict(scenario=p.scenario, alpha=p.alpha, vb=p.vb, dvb=p.dvb, vtp=p.vtp,
                 npart=p.npart, ng=p.ng, dt=p.dt, n_waves=p.n_waves, seed=p.rng_seed,
                 k_main=k, gamma_th=s.gamma_ref, omega_th=s.omega_ref,
                 gamma_meas=tr.gamma_meas if tr.gamma_meas is not None else np.nan,
                 E_trap=tr.A_trap)
        if tr.sat is not None:
            Es = tr.sat["A"]
            r.update(t_sat=tr.sat["t"], E_sat=Es, wB_over_g=np.sqrt(k * Es) / s.gamma_ref,
                     WE_sat_frac=tr.sat["WE"] / s.K0_beam,
                     bounce_T=tr.bounce if tr.bounce is not None else np.nan)
        else:
            r.update(t_sat=np.nan, E_sat=np.nan, wB_over_g=np.nan, WE_sat_frac=np.nan,
                     bounce_T=np.nan)
        h = s.hist
        n = s.h_n
        tot = h["WE"] + h["K"].sum(1)
        r["energy_err"] = float(np.abs(tot - tot[0]).max() / s.K0_beam)
        r["t_end"] = s.t
        nav = max(1, int(50 / p.dt))          # среднее по последним 50/ω_p
        r["WE_end_frac"] = float(h["WE"][n - nav:].mean() / s.K0_beam)
        if p.scenario == "beam":
            q = diag.ql_prediction(s.v[s.sl[1]], s.dens[1], s.L, s.K0_beam, p.vb)
            r.update(plateau_v1=q["v1"], plateau_v2=q["v2"],
                     WE_ql_frac=q["WE_ql"] / s.K0_beam)
        else:
            r.update(plateau_v1=np.nan, plateau_v2=np.nan, WE_ql_frac=np.nan)
        r["wall_s"] = self.wall
        return r


def run_to_end(p: PICParams, **kw):
    sr = SatRun(p, **kw)
    while not sr.advance(200):
        pass
    return sr
