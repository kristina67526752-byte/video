"""Нарушитель, знающий допуски (версия 3.6).

Исполнитель операции (уровень А1) ставит единственную отметку окончания раньше фактического
окончания и не отправляет подлинную; сообщения оборудования он подавить не может. Для каждого
штатного оборота и каждой операции обслуживания бинарным поиском находится самая ранняя отметка,
при которой метод не выдаёт тревоги, отсутствующей у того же оборота без подлога. Выигрыш —
насколько раньше фактического окончания можно незаметно отметить операцию: в минутах и в долях
её фактической длительности; дополнительно — ложное решение о готовности к посадке (D1) и его
опережение.
"""
from __future__ import annotations

import numpy as np

from .detectors import METHODS, MODE, alarm_keys, derive, evaluate_case
from .evaluate import true_readiness
from .model import END, MANUAL, SERVICE_OPS, START

N_ITER = 12          # шагов бинарного поиска: точность — длительность операции / 4096


def _attacked(msgs: list[dict], op: str, t_f: float) -> list[dict] | None:
    genuine = [m for m in msgs if m["op"] == op and m["status"] == END and m["kind"] == MANUAL
               and m["corr_of"] is None]
    if not genuine:
        return None
    g = genuine[0]
    out = [m for m in msgs if m["msg_id"] != g["msg_id"] and m.get("corr_of") != g["msg_id"]]
    out.append(dict(g, event_time=t_f, recv_time=t_f + 0.1))
    return out


def _outcome(case, msgs, p, method, twin_keys, d1, d2):
    groups, mode = METHODS[method], MODE.get(method, "P")
    steps = evaluate_case(case.meta(), msgs, p)
    return derive(steps, groups, p.grace, p.missing_horizon, 0.0, d1, d2, twin_keys, mode,
                  p.check_time)


def gain_for_case(case, p, method: str) -> list[dict]:
    """Максимальный незаметный выигрыш по каждой операции обслуживания оборота."""
    groups, mode = METHODS[method], MODE.get(method, "P")
    d1, d2 = true_readiness(case)
    twin_steps = evaluate_case(case.meta(), case.messages, p)
    tk = alarm_keys(twin_steps, groups, p.grace, p.missing_horizon, mode)
    out = []
    for op in SERVICE_OPS:
        s_true, e_true = case.truth[(op, START)], case.truth[(op, END)]
        dur = e_true - s_true
        man_start = [m["event_time"] for m in case.messages if m["op"] == op
                     and m["status"] == START and m["kind"] == MANUAL]
        if dur < 1.0 or not man_start or _attacked(case.messages, op, e_true) is None:
            continue
        lo = max(s_true, min(man_start)) + 0.01
        hi = e_true

        def undetected(t):
            o = _outcome(case, _attacked(case.messages, op, t), p, method, tk, d1, d2)
            return o["detect_time"] is None, o

        ok_hi, _ = undetected(hi)
        if not ok_hi:                       # тревога и при отметке вовремя (шум оборота)
            continue
        ok_lo, o_lo = undetected(lo)
        if ok_lo:
            best, o_best = lo, o_lo
        else:
            a, b = lo, hi                   # a — обнаруживается, b — нет
            o_best = None
            for _ in range(N_ITER):
                mid = (a + b) / 2
                ok, o = undetected(mid)
                if ok:
                    b, o_best = mid, o
                else:
                    a = mid
            best = b
            if o_best is None:
                o_best = undetected(b)[1]
        adv = (d1 - o_best["d1_time"]) if o_best["d1_outcome"] == "false" else 0.0
        out.append({"method": method, "case_id": case.case_id, "op": op, "duration": dur,
                    "gain_min": e_true - best, "gain_frac": (e_true - best) / dur,
                    "d1_false": o_best["d1_outcome"] == "false", "d1_advance": adv})
    return out


def summarize(rows: list[dict]) -> list[dict]:
    res = []
    for method in sorted({r["method"] for r in rows}):
        for op in SERVICE_OPS + ["ALL"]:
            r = [x for x in rows if x["method"] == method and (op == "ALL" or x["op"] == op)]
            if not r:
                continue
            g = np.array([x["gain_frac"] for x in r])
            m = np.array([x["gain_min"] for x in r])
            adv = [x["d1_advance"] for x in r if x["d1_false"]]
            res.append({"method": method, "op": op, "n": len(r),
                        "gain_frac_median": float(np.median(g)),
                        "gain_frac_p10": float(np.percentile(g, 10)),
                        "gain_frac_p90": float(np.percentile(g, 90)),
                        "gain_min_median": float(np.median(m)),
                        "gain_min_p90": float(np.percentile(m, 90)),
                        "share_over_half": float(np.mean(g >= 0.5)),
                        "d1_false_share": float(np.mean([x["d1_false"] for x in r])),
                        "d1_advance_median": float(np.median(adv)) if adv else 0.0})
    return res
