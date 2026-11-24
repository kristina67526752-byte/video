"""Дополнительные расчёты версии 3.7.

    python -m gh_integrity.revision        # ≈5 мин на одном ядре, после полного прогона run.py

Основной расчёт (run.py) не меняется: его числа воспроизводятся побайтно, а этот модуль
пишет отдельные файлы results/rev_*.csv и results/rev_summary.json.

1. Ложные решения при ошибке ручной проверки для всех вариантов абляции при одних и тех же q
   (сравнение П с вариантом без удержания при одинаковой действенности проверки).
2. Погрешность часов: допуск δf (и δo), оценённый без разметки по штатному журналу, и П без
   группы T — при случайной погрешности 30 с и постоянном смещении часов терминала до ±1 и ±2 мин.
3. Вариант формулы (2): время события по оборудованию, если его сообщение получено.
4. Разброс эффектов по сценариям устойчивости (вместо p-значений).
5. П без группы T и без R3 — полный набор показателей (табл. 4).
6. Подвиды для Б3 с допусками П (рис. 2) и минимальная задержка тревоги.
7. Перечень зависимостей и норм модели с основаниями (results/rules_table.csv).
"""
from __future__ import annotations

import csv
import gzip
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from .detectors import METHODS
from .evaluate import estimate_clock_tol, run_methods, wilson
from .model import (CROSS_EVENTS, END, OPERATIONS, TYPICAL, Params, precedence)
from .run import (BY_CONSTRUCTION, OUT_OF_REACH, V2_TRUST, _write_csv, group_of, integrity,
                  paired)
from .simulate import generate_dataset

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
KV = ("К", "В")


def _f(v):
    return None if v in ("", None) else float(v)


def _load_per_case() -> list[dict]:
    with gzip.open(RES / "per_case.csv.gz", "rt", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for x in rows:
        x["label"] = int(x["label"])
        for k in ("detect_time", "latency", "true_d1", "true_d2", "true_ofb", "d1_cond", "d2_cond",
                  "first_alarm", "inj_time", "d1_delay", "d2_delay"):
            x[k] = _f(x[k])
        x["n_alarms"] = int(x["n_alarms"])
        x["seed"] = int(x["seed"])
    return rows


def _params() -> dict[str, Params]:
    s = json.loads((RES / "summary.json").read_text(encoding="utf-8"))
    cal = {m: {k: v for k, v in c.items() if not k.startswith("_")}
           for m, c in s["calibrated"].items()}
    base = Params()
    return {"P": replace(base, **cal["P"]), "B3": replace(base, **cal["B3"]),
            "B2": replace(base, **V2_TRUST, **cal["B2"])}


def method_stats(rows: list[dict], m: str) -> dict:
    """Показатели строки табл. 4 для метода m."""
    rm = [x for x in integrity(rows) if x["method"] == m]
    neg = [x for x in rm if x["label"] == 0]
    pos = [x for x in rm if x["label"] == 1]
    sub = [x for x in pos if group_of(x) == "subst"]
    allpos = [x for x in rows if x["method"] == m and x["label"] == 1]
    lat = [x["latency"] for x in pos if x["latency"] is not None]
    k_fp = sum(x["n_alarms"] > 0 for x in neg)
    k_sb = sum(x["detect_time"] is not None for x in sub)
    k_all = sum(x["detect_time"] is not None for x in pos)
    k_d1 = sum(1 for x in pos if x["detect_time"] is not None and x["detect_time"] <= x["true_d1"])
    out = {"method": m, "n_neg": len(neg), "fpr": k_fp / len(neg),
           "fpr_lo": wilson(k_fp, len(neg))[0], "fpr_hi": wilson(k_fp, len(neg))[1],
           "n_subst": len(sub), "subst": k_sb / len(sub) if sub else float("nan"),
           "subst_lo": wilson(k_sb, len(sub))[0], "subst_hi": wilson(k_sb, len(sub))[1],
           "integrity": k_all / len(pos) if pos else float("nan"),
           "before_d1": k_d1 / len(pos) if pos else float("nan"),
           "lat_min": min(lat) if lat else float("nan"),
           "lat_median": float(np.median(lat)) if lat else float("nan"),
           "lat_p90": float(np.percentile(lat, 90)) if lat else float("nan"),
           "false_decisions_KV": sum(x["severity"] in KV for x in allpos)}
    return out


def check_error(rows: list[dict]) -> list[dict]:
    """С вероятностью q проверяющий подтверждает данные, не найдя нарушения; тогда решение,
    задержанное тревогой, принимается по данным и становится ложным, если условие по данным
    выполнилось раньше фактической готовности (как в run.py)."""
    out = []
    for m in ["B2", "B3", "B3-Ptol", "P-nohold", "P"]:
        r = [x for x in rows if x["method"] == m and x["label"] == 1]
        kv = sum(x["severity"] in KV for x in r)
        extra = sum(1 for x in r if x["severity"] not in KV and any(
            x[f"{d}_outcome"] == "manual" and x[f"{d}_cond"] is not None
            and x[f"{d}_cond"] < x[f"true_{d}"] - 1e-9 for d in ("d1", "d2")))
        for q in (0.0, 0.25, 0.5, 1.0):
            out.append({"method": m, "q_miss": q, "false_decisions_KV": kv + q * extra,
                        "n": len(r), "held_then_checked": extra})
    return out


def _row(rr: list[dict], m: str, scen: str, cfg: str, tol: float) -> dict:
    rm = [x for x in integrity(rr) if x["method"] == m]
    neg = [x for x in rm if x["label"] == 0]
    sub = [x for x in rm if x["label"] == 1 and group_of(x) == "subst"]
    return {"scenario": scen, "config": cfg, "method": m, "clock_tol": round(tol, 3),
            "fpr": sum(x["n_alarms"] > 0 for x in neg) / len(neg),
            "subst": sum(x["detect_time"] is not None for x in sub) / len(sub),
            "kv": sum(x["severity"] in KV for x in rr if x["method"] == m and x["label"] == 1),
            "n_neg": len(neg), "n_subst": len(sub)}


def clock(pp: dict[str, Params], n_seeds: int = 3) -> list[dict]:
    """Погрешность часов: как в табл. устойчивости (выборки 901–903), три настройки допуска."""
    base = Params()
    scen = [("base", {}), ("skew_sd_30s", {"clock_skew_sd": 0.5}),
            ("offset_1min", {"clock_offset_max": 1.0}),
            ("offset_2min", {"clock_offset_max": 2.0})]
    out = []
    for name, kw in scen:
        gen = replace(base, **kw)
        # калибровочный штатный журнал того же режима (без нарушений, без разметки)
        tol = estimate_clock_tol(generate_dataset(950, 600, 0, gen))
        cs = [c for s in range(1, n_seeds + 1) for c in generate_dataset(900 + s, 600, 100, gen)]
        for cfg, t in (("fixed_0.5", None), ("estimated", tol)):
            ex = {} if t is None else {"future_tol": t, "order_tol": t}
            rr = (run_methods(cs, replace(pp["P"], **kw, **ex),
                              {"P": METHODS["P"], "P-T": METHODS["P-T"],
                               "B3-Ptol": METHODS["B3-Ptol"]})
                  + run_methods(cs, replace(pp["B3"], **kw, **ex), {"B3": METHODS["B3"]})
                  + run_methods(cs, replace(pp["B2"], **kw, **ex), {"B2": METHODS["B2"]}))
            for m in ("P", "P-T", "B3", "B3-Ptol", "B2"):
                if cfg == "estimated" and m == "P-T":
                    continue                       # без группы T допуск δf не используется
                out.append(_row(rr, m, name, cfg, 0.5 if t is None else t))
        print("clock", name, round(tol, 2))
    return out


def time_rule(pp: dict[str, Params], n_seeds: int = 10) -> list[dict]:
    """Формула (2): самое раннее время по всем источникам (основной расчёт) и время по
    оборудованию, если его сообщение получено; П и Б3 с допусками П на тех же 14 000 оборотах."""
    rows = []
    for s in range(1, n_seeds + 1):
        cs = generate_dataset(s, 600, 100, Params())
        for rule in ("min", "auto_first"):
            rr = run_methods(cs, replace(pp["P"], time_rule=rule),
                             {"P": METHODS["P"], "B3-Ptol": METHODS["B3-Ptol"]})
            rows += [dict(x, method=f"{x['method']}|{rule}", seed=s) for x in rr]
    out = [method_stats(rows, m) for m in ("P|min", "P|auto_first", "B3-Ptol|min",
                                          "B3-Ptol|auto_first")]
    pr = paired(rows, "P|auto_first", "P|min")
    out[1].update({"subst_only_auto": pr["subst_a_only"], "subst_only_min": pr["subst_b_only"]})
    return out


def spread() -> list[dict]:
    """Разброс эффектов по 14 вариантам допущений (robustness.csv, без перекалибровки)."""
    with open(RES / "robustness.csv", encoding="utf-8") as f:
        rob = list(csv.DictReader(f))
    out = []
    for incl_clock in (False, True):
        r = [x for x in rob if x["factor"] != "base"
             and (incl_clock or not (x["factor"] == "clock_skew_sd" and x["value"] == "0.5"))]
        for name, a, b in (("P-B2", "subst_P", "subst_B2"), ("P-B3", "subst_P", "subst_B3"),
                           ("P-B3Ptol", "subst_P", "subst_B3-Ptol"), ("P", "subst_P", None),
                           ("fpr_P", "fpr_P", None)):
            v = [float(x[a]) - (float(x[b]) if b else 0.0) for x in r]
            out.append({"effect": name, "with_clock_30s": incl_clock, "n_variants": len(r),
                        "min": min(v), "max": max(v), "median": float(np.median(v))})
    return out


def by_subtype_extra(rows: list[dict]) -> list[dict]:
    out = []
    for m in ["B3-Ptol", "P-T"]:
        for st in sorted({x["subtype"] for x in rows if x["subtype"]}):
            r = [x for x in rows if x["method"] == m and x["subtype"] == st]
            det = sum(x["detect_time"] is not None for x in r)
            out.append({"method": m, "subtype": st, "n": len(r), "recall": det / len(r),
                        "ci_lo": wilson(det, len(r))[0], "ci_hi": wilson(det, len(r))[1],
                        "d1_false": sum(x["d1_outcome"] == "false" for x in r) / len(r),
                        "d2_false": sum(x["d2_outcome"] == "false" for x in r) / len(r)})
    return out


# Основания зависимостей и норм модели. Источник: [3] — модельный граф работ (9 операций,
# 12 связей); ФАП-128 — условия заправки с пассажирами на борту; «физ.» — физическая
# последовательность (оборудование не может работать до постановки ВС, двери закрываются после
# окончания работ в салоне и багажниках); «завершение» — завершающая последовательность оборота
# (двери → трап и АИЭП → буксировка); «доп.» — допущение авторов, подлежит экспертной проверке.
BASIS = {
    ("ONB", "GPU"): "физ.", ("ONB", "PBB"): "физ.", ("ONB", "UNL"): "физ.",
    ("ONB", "FUEL"): "физ.",
    ("PBB", "DEB"): "физ. (высадка через телетрап)", ("PBB", "CAT"): "[3]", ("PBB", "CLN"): "[3]",
    ("DEB", "WAT"): "[3]", ("DEB", "FUEL"): "ФАП-128 (снимается при SAF)",
    ("UNL", "LOD"): "физ. (загрузка после выгрузки)", ("CLN", "BRD"): "[3]", ("CAT", "BRD"): "[3]",
    ("WAT", "BRD"): "[3]", ("LOD", "BRD"): "[3]",
    ("FUEL", "BRD"): "ФАП-128 (снимается при SAF)",
    ("LOD", "LDS"): "доп. (ведомость по факту загрузки)",
    ("BRD", "LDS"): "доп. (ведомость по факту посадки)",
    ("LDS", "DRC"): "доп. (двери после ведомости)",
    ("DRC", "PBB"): "завершение", ("DRC", "GPU"): "завершение",
    ("PBB", "OFB"): "завершение", ("GPU", "OFB"): "завершение", ("DRC", "OFB"): "завершение",
}


def rules_table() -> list[dict]:
    out = []
    for i, c in enumerate(precedence("alt"), 1):
        key = (c.pred[0], c.succ[0])
        basis = BASIS.get(key)
        if basis is None and c.succ == ("DRC", END):
            basis = "физ. (двери после окончания работ)"
        out.append({"n": i, "pred": f"{c.pred[0]}.{c.pred[1]}", "succ": f"{c.succ[0]}.{c.succ[1]}",
                    "waiver": c.waiver or "", "basis": basis or "доп."})
    for op in ["DEB", "BRD", "FUEL", *TYPICAL]:
        norm = {"DEB": "n/25 мин (25 пасс./мин)", "BRD": "n/18 мин (18 пасс./мин)",
                "FUEL": "1 + q/1000 мин (1000 кг/мин)"}.get(op, f"0,5 × {TYPICAL.get(op, 0):g} мин")
        out.append({"n": "", "pred": f"{op}: норма R2", "succ": norm, "waiver": "",
                    "basis": "доп." if op in ("DEB", "BRD", "FUEL", "UNL")
                    else "α × типовая длительность [3]"})
    out.append({"n": "", "pred": "R4: события двух источников", "succ":
                ", ".join(f"{o}.{s}" for o, s in CROSS_EVENTS), "waiver": "", "basis":
                "оснащение стоянки (доп.)"})
    return out


def main() -> None:
    pp = _params()
    rows = _load_per_case()
    # контроль воспроизводимости: П на выборке 1 совпадает с основным расчётом
    cs = generate_dataset(1, 600, 100, Params())
    chk = run_methods(cs, pp["P"], {"P": METHODS["P"]})
    old = {x["case_id"]: x for x in rows if x["method"] == "P" and x["seed"] == 1}
    assert all((y["detect_time"] is None) == (old[y["case_id"]]["detect_time"] is None)
               and y["n_alarms"] == old[y["case_id"]]["n_alarms"] for y in chk), "не воспроизводится"
    summ: dict = {"version": "3.7"}
    tab = [method_stats(rows, m) for m in ("B1", "B2", "B3", "B3-Ptol", "P_v2", "P-beta",
                                            "P-nohold", "P-T", "P-R3", "P")]
    _write_csv(RES / "rev_table4.csv", tab)
    summ["table4"] = tab
    ce = check_error(rows)
    _write_csv(RES / "rev_check_error.csv", ce)
    summ["check_error"] = ce
    sp = spread()
    _write_csv(RES / "rev_spread.csv", sp)
    summ["spread"] = sp
    bs = by_subtype_extra(rows)
    _write_csv(RES / "rev_by_subtype.csv", bs)
    lat = sorted((x for x in integrity(rows) if x["method"] == "P" and x["label"] == 1
                  and x["latency"] is not None), key=lambda x: x["latency"])
    summ["min_latency_case"] = {k: lat[0][k] for k in ("case_id", "subtype", "latency",
                                                        "detect_key", "features", "inj_time")}
    summ["latency_below_W"] = sum(1 for x in lat if x["latency"] < 15 - 1e-6)
    _write_csv(RES / "rules_table.csv", rules_table())
    print("table4, check_error, spread done")
    tr = time_rule(pp)
    _write_csv(RES / "rev_time_rule.csv", tr)
    summ["time_rule"] = tr
    print("time rule done")
    ck = clock(pp)
    _write_csv(RES / "rev_clock.csv", ck)
    summ["clock"] = ck
    (RES / "rev_summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1,
                                                     default=str), encoding="utf-8")
    print("done")


if __name__ == "__main__":
    main()
