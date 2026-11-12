"""Прогон методов контроля по набору оборотов и расчёт метрик."""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from .detectors import METHODS, MODE, alarm_keys, derive, evaluate_case
from .model import D2_EVENTS, END, SERVICE_OPS, Params, d1_preds
from .simulate import Case


def true_readiness(case: Case) -> tuple[float, float]:
    T = case.truth
    d1 = max(T[(op, END)] for op, waived in d1_preds(case.gen_model)
             if not (waived and case.safety))
    d2 = max(T[e] for e in D2_EVENTS)
    return d1, d2


def incomplete_ops(case: Case, decision: str, t: float) -> list[str]:
    """Операции, фактически не завершённые к моменту решения (по разметке эксперимента)."""
    T = case.truth
    ops = ([op for op, waived in d1_preds(case.gen_model) if not (waived and case.safety)]
           if decision == "d1" else SERVICE_OPS)
    return [op for op in ops if T[(op, END)] > t + 1e-9]


SEVERITY = {
    "К": ("критический", "critical"),
    "В": ("высокий", "high"),
    "С": ("средний", "medium"),
    "Н": ("низкий", "low"),
}
SAFETY_CRITICAL_OPS = ("FUEL", "LOD")   # пожарная безопасность; центровка и закрытие люков


def severity(case: Case, o: dict) -> tuple[str, str]:
    """Условная категория исхода нарушения для метода (шкала задана до эксперимента;
    это не оценка авиационного риска). Категория определяется реконструкцией состояния
    на момент ложного решения: какие операции фактически не были завершены.

    К — ложное решение, когда не завершены заправка или загрузка;
    В — ложное решение, когда не завершены другие операции;
    С — ложного решения нет, но нарушение не обнаружено: искажены учётные данные;
    Н — нарушение обнаружено, ложного решения нет.
    Возвращает категорию и перечень незавершённых операций."""
    worst, ops_all = None, []
    for d in ("d1", "d2"):
        if o[f"{d}_outcome"] == "false":
            ops = incomplete_ops(case, d, o[f"{d}_time"])
            ops_all += ops
            cat = "К" if any(op in SAFETY_CRITICAL_OPS for op in ops) else "В"
            worst = cat if worst is None or cat == "К" else worst
    if worst:
        return worst, ",".join(sorted(set(ops_all)))
    return ("С" if o["detect_time"] is None else "Н"), ""


def run_methods(cases: list[Case], p: Params, methods: dict = METHODS,
                W: float | None = None, H: float | None = None) -> list[dict]:
    """Одна запись на пару (оборот, метод)."""
    W = p.grace if W is None else W
    H = p.missing_horizon if H is None else H
    rows = []
    for c in cases:
        steps = evaluate_case(c.meta(), c.messages, p)
        twin = evaluate_case(c.meta(), c.twin_messages, p) if c.twin_messages else None
        d1, d2 = true_readiness(c)
        t_ofb = c.truth[("OFB", END)]
        for name, groups in methods.items():
            mode = MODE.get(name, "P")
            tk = alarm_keys(twin, groups, W, H, mode) if twin else frozenset()
            o = derive(steps, groups, W, H, c.gt_inj_time, d1, d2, tk, mode, p.check_time)
            sev, sev_ops = severity(c, o) if c.label else ("", "")
            rows.append({"case_id": c.case_id, "method": name, "label": c.label,
                         "vtype": c.vtype or "N", "subtype": c.subtype or "",
                         "features": ";".join(c.features), "target": c.gt_target or "",
                         "inj_time": c.gt_inj_time, "true_d1": d1, "true_d2": d2,
                         "true_ofb": t_ofb, **o, "severity": sev, "sev_ops": sev_ops,
                         "latency": (o["detect_time"] - c.gt_inj_time)
                         if o["detect_time"] is not None else None})
    return rows


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def summarize(rows: list[dict], method: str, types: list[str]) -> dict:
    """Метрики уровня оборота.

    Сопоставление с «двойником»: тревога в штатном обороте — ложная; оборот с нарушением
    обнаружен, если тревога выдана не раньше внесения нарушения и её нет у «двойника».
    Обычная матрица ошибок: оборот с нарушением засчитывается при любой тревоге."""
    r = [x for x in rows if x["method"] == method]
    neg = [x for x in r if x["label"] == 0]
    pos = [x for x in r if x["label"] == 1 and x["vtype"] in types]
    fp = sum(x["n_alarms"] > 0 for x in neg)
    tp = sum(x["detect_time"] is not None for x in pos)
    tp_any = sum(x["n_alarms"] > 0 for x in pos)
    lat = [x["latency"] for x in pos if x["latency"] is not None]
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / len(pos) if pos else float("nan")
    return {"method": method, "n_neg": len(neg), "n_pos": len(pos), "tp": tp, "fp": fp,
            "fn": len(pos) - tp, "tn": len(neg) - fp, "tp_any": tp_any,
            "recall_any": tp_any / len(pos) if pos else float("nan"),
            "precision_any": tp_any / (tp_any + fp) if tp_any + fp else float("nan"),
            "precision": prec, "recall": rec, "recall_ci": wilson(tp, len(pos)),
            "f1": 2 * prec * rec / (prec + rec) if prec + rec else float("nan"),
            "fpr": fp / len(neg) if neg else float("nan"), "fpr_ci": wilson(fp, len(neg)),
            "lat_median": float(np.median(lat)) if lat else float("nan"),
            "lat_p90": float(np.percentile(lat, 90)) if lat else float("nan")}


def calibrate(cases: list[Case], base: Params, grid: dict, methods: dict, fpr_max: float,
              types: list[str]) -> list[dict]:
    """Перебор допусков на калибровочной выборке. Возвращает все точки сетки."""
    import itertools
    keys = list(grid)
    out = []
    step_keys = [k for k in keys if k not in ("grace", "missing_horizon")]
    derive_keys = [k for k in keys if k in ("grace", "missing_horizon")]
    for combo in itertools.product(*[grid[k] for k in step_keys]):
        p = replace(base, **dict(zip(step_keys, combo)))
        cache = [(c, evaluate_case(c.meta(), c.messages, p),
                  evaluate_case(c.meta(), c.twin_messages, p) if c.twin_messages else None,
                  *true_readiness(c)) for c in cases]
        for dcombo in itertools.product(*[grid[k] for k in derive_keys]):
            pd = replace(p, **dict(zip(derive_keys, dcombo)))
            for name, groups in methods.items():
                mode = MODE.get(name, "P")
                rows = []
                for c, steps, twin, d1, d2 in cache:
                    tk = (alarm_keys(twin, groups, pd.grace, pd.missing_horizon, mode)
                          if twin else frozenset())
                    o = derive(steps, groups, pd.grace, pd.missing_horizon, c.gt_inj_time, d1, d2,
                               tk, mode, pd.check_time)
                    rows.append({"method": name, "label": c.label, "vtype": c.vtype or "N",
                                 **o, "latency": (o["detect_time"] - c.gt_inj_time)
                                 if o["detect_time"] is not None else None})
                s = summarize(rows, name, types)
                out.append({**dict(zip(step_keys, combo)), **dict(zip(derive_keys, dcombo)),
                            **s, "feasible": s["fpr"] <= fpr_max})
    return out
