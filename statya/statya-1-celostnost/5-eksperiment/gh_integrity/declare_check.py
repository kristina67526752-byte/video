"""Независимое сравнение с реализацией Declare из библиотеки pm4py (версия 3.6).

    python -m gh_integrity.declare_check      # после gh_integrity.run; нужен pm4py

pm4py не входит в requirements.txt (лицензия AGPL v3) и ставится отдельно; результаты получены
с pm4py 2.7.23 и numpy 2.5.3. Проверка conformance_declare в pm4py работает по готовой трассе и
поддерживает только ограничения порядка: условий по данным, допусков на время и учёта
времени поступления сообщений в ней нет. Поэтому сравнение двухчастное:

1) сверка реализации: ограничения предшествования R1 нашего кода при нулевом допуске (без двух
   зависимостей, снимаемых при заправке с пассажирами: условие по данным pm4py не выражает) и
   шаблон precedence из pm4py на тех же итоговых трассах — совпадение по каждой паре
   «оборот × ограничение»;
2) монитор Б4 — проверка итоговой трассы оборота в pm4py по 27 ограничениям предшествования
   модели и 11 ограничениям «начало раньше окончания»: доля ложных тревог на штатных оборотах
   и доля выявленных нарушений (нарушение выявлено, если есть отклонение, которого нет у того
   же оборота без нарушения), парное сравнение с П по содержательным случаям.

Итоговая трасса — принятые сообщения после исправлений, упорядоченные по времени события τ.
"""
from __future__ import annotations

import csv
import gzip
import json
from dataclasses import replace
from math import comb
from pathlib import Path

import numpy as np
import pm4py
from pm4py.algo.conformance.declare.variants import classic as pm_declare
from pm4py.algo.discovery.declare.templates import PRECEDENCE as PM_PRECEDENCE

from .detectors import _inconsistencies
from .evaluate import wilson
from .model import END, INTERVAL_OPS, START, Params, precedence
from .run import BY_CONSTRUCTION, OUT_OF_REACH, RES, _write_csv
from .simulate import generate_dataset


def final_state(meta: dict, messages: list[dict], p: Params):
    """Итоговое состояние оборота так же, как его строит evaluate_case: повторная доставка
    отсеивается, исправление от источника исходного сообщения заменяет его время."""
    msgs, eff, pending, bad, seen = {}, {}, {}, set(), set()

    def apply(orig, corr):
        if (orig["op"], orig["status"], orig["source"]) == (corr["op"], corr["status"],
                                                            corr["source"]):
            eff[orig["msg_id"]] = corr["event_time"]
        else:
            bad.add(("R3", "badcorr", corr["msg_id"]))

    for m in sorted(messages, key=lambda x: (x["recv_time"], x["msg_id"])):
        if m["msg_id"] in seen:
            continue
        seen.add(m["msg_id"])
        if m["corr_of"] is not None:
            if m["corr_of"] in msgs:
                apply(msgs[m["corr_of"]], m)
            else:
                pending[m["corr_of"]] = m
        else:
            msgs[m["msg_id"]] = m
            eff[m["msg_id"]] = m["event_time"]
            if m["msg_id"] in pending:
                apply(m, pending.pop(m["msg_id"]))
    keys, _, _ = _inconsistencies(meta, msgs, eff, bad, p)
    rejected = {k[2] for k in keys if k[0] == "F" and len(k) == 3}
    trace = sorted((eff[i], f"{m['op']}.{m['status']}") for i, m in msgs.items()
                   if i not in rejected)
    return [a for _, a in trace], keys


def declare_model(ctrl_model: str):
    cons = [(f"{c.pred[0]}.{c.pred[1]}", f"{c.succ[0]}.{c.succ[1]}")
            for c in precedence(ctrl_model) if c.waiver is None]
    cons += [(f"{op}.{START}", f"{op}.{END}") for op in INTERVAL_OPS]
    return {PM_PRECEDENCE: {c: {"support": 1.0, "confidence": 1.0} for c in cons}}, cons


def group_of(subtype: str, vtype: str) -> str:
    key = subtype or vtype
    if key in BY_CONSTRUCTION:
        return "construct"
    if key in OUT_OF_REACH or vtype in OUT_OF_REACH:
        return "reach"
    return "subst"


def main() -> None:
    summ = json.loads((RES / "summary.json").read_text(encoding="utf-8"))
    cfg = {k: v for k, v in summ["calibrated"]["P"].items() if not k.startswith("_")}
    base = Params()
    p_P = replace(base, **cfg)
    p0 = replace(p_P, prec_tol=0.0, order_tol=0.0)
    model, cons = declare_model(base.ctrl_model)
    cons_set = set(cons)
    d = summ["dataset"]
    seeds = d["seeds_test"]

    det_P = {}
    with gzip.open(RES / "per_case.csv.gz", "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["method"] == "P":
                det_P[r["case_id"]] = r["detect_time"] != ""

    agree = mism = 0
    rows = []
    for s in seeds:
        cases = generate_dataset(s, d["n_normal_per_seed"], d["n_per_type_per_seed"], base)
        traces, ours = [], []
        for c in cases:
            tr, keys = final_state(c.meta(), c.messages, p0)
            traces.append(tr)
            ours.append({(k[2], k[3]) for k in keys if k[0] == "R1" and k[1] in ("order", "miss")})
            if c.twin_messages:
                traces.append(final_state(c.meta(), c.twin_messages, p0)[0])
            else:
                traces.append(None)
        res = pm_declare.apply_list([t for t in traces if t is not None], model)
        it = iter(res)
        dev = [({tuple(x[1]) for x in next(it)["deviations"]} if t is not None else None)
               for t in traces]
        for i, c in enumerate(cases):
            dv, dtw = dev[2 * i], dev[2 * i + 1]
            ours_i = {(f"{a[0]}.{a[1]}", f"{b[0]}.{b[1]}") for a, b in ours[i]} & cons_set
            pm_r1 = {x for x in dv if x in cons_set and x[0].split(".")[0] != x[1].split(".")[0]}
            for con in cons:
                if con[0].split(".")[0] == con[1].split(".")[0]:
                    continue                      # «начало раньше окончания» — не R1
                same = (con in ours_i) == (con in pm_r1)
                agree += same
                mism += not same
            new = dv - (dtw or set())
            rows.append({"case_id": c.case_id, "label": c.label, "vtype": c.vtype or "N",
                         "subtype": c.subtype or "", "alarm": bool(dv),
                         "detected": bool(new) if c.label else False,
                         "P_detected": det_P.get(c.case_id, False)})

    out = [{"metric": "R1_agreement_pairs", "value": agree, "n": agree + mism,
            "share": agree / (agree + mism), "lo": "", "hi": ""}]
    neg = [r for r in rows if r["label"] == 0]
    k = sum(r["alarm"] for r in neg)
    lo, hi = wilson(k, len(neg))
    out.append({"metric": "B4_fpr", "value": k, "n": len(neg), "share": k / len(neg),
                "lo": lo, "hi": hi})
    integ = [r for r in rows if r["label"] == 1 and r["subtype"] != "V5a"]
    for g in ("subst", "construct", "reach", "all"):
        gg = [r for r in integ if g == "all" or group_of(r["subtype"], r["vtype"]) == g]
        k = sum(r["detected"] for r in gg)
        lo, hi = wilson(k, len(gg))
        out.append({"metric": f"B4_recall_{g}", "value": k, "n": len(gg), "share": k / len(gg),
                    "lo": lo, "hi": hi})
    sub = [r for r in integ if group_of(r["subtype"], r["vtype"]) == "subst"]
    a_only = sum(r["P_detected"] and not r["detected"] for r in sub)
    b_only = sum(r["detected"] and not r["P_detected"] for r in sub)
    n = a_only + b_only
    pval = min(1.0, 2 * sum(comb(n, i) for i in range(min(a_only, b_only) + 1)) / 2 ** n) if n else 1.0
    out.append({"metric": "P_vs_B4_subst_P_only", "value": a_only, "n": len(sub), "share": "",
                "lo": "", "hi": ""})
    out.append({"metric": "P_vs_B4_subst_B4_only", "value": b_only, "n": len(sub), "share": "",
                "lo": "", "hi": ""})
    out.append({"metric": "P_vs_B4_mcnemar_p", "value": pval, "n": n, "share": "", "lo": "",
                "hi": ""})
    by_sub = {}
    for r in integ:
        by_sub.setdefault(r["subtype"] or r["vtype"], []).append(r["detected"])
    for st, v in sorted(by_sub.items()):
        out.append({"metric": f"B4_recall_{st}", "value": sum(v), "n": len(v),
                    "share": sum(v) / len(v), "lo": "", "hi": ""})
    out.append({"metric": "n_constraints", "value": len(cons), "n": "", "share": "", "lo": "",
                "hi": ""})
    out.append({"metric": "pm4py_version", "value": pm4py.__version__, "n": "", "share": "",
                "lo": "", "hi": ""})
    out.append({"metric": "numpy_version", "value": np.__version__, "n": "", "share": "",
                "lo": "", "hi": ""})
    _write_csv(RES / "declare_pm4py.csv", out)
    for r in out[:12]:
        print(r)


if __name__ == "__main__":
    main()
