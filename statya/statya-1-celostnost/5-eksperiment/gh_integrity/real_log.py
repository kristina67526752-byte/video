"""Проверка правил на журнале эксплуатации без разметки нарушений (версия 3.7).

Доля ложных тревог измеряется на штатных журналах, разметка нарушений для этого не нужна:
каждый оборот, по которому выдана тревога, либо содержит недостоверные данные, либо даёт ложную
тревогу, и при редких нарушениях доля оборотов с тревогой — оценка сверху доли ложных тревог.

    python -m gh_integrity.real_log --log log.csv --turns turns.csv --codes codes.json --out out/
    python -m gh_integrity.real_log --demo --out out/     # проверка на синтетическом журнале

Формат — как в запросе данных (3-materialy/zapros-dannyh-ekspluatatsii.docx).

log.csv (одна строка — одно сообщение): msg_id, turnaround_id, operation, status, event_time,
receive_time, source_type (MANUAL | AUTO | SYSTEM), source_id, role, correction_of, pax_count,
fuel_qty, fuel_with_pax (0/1). Времена — ISO 8601 (UTC) или минуты от начала оборота.

turns.csv (одна строка — один оборот): turnaround_id, seats, sta, std, pax_in, pax_out,
fuel_order, equipped — оснащение стоянки через «;» из VDGS, PBB, GPU, METER (DCS есть всегда).

codes.json — соответствие кодов операций и статусов системы кодам модели, например
{"operation": {"Заправка": "FUEL", ...}, "status": {"Начало": "START", "Окончание": "END"}}.
Операции, которых нет в соответствии, пропускаются (и перечисляются в отчёте).

Отчёт (out/real_log_report.json, out/real_log_turns.csv): доля оборотов с тревогой для П, М и Б
с интервалом Уилсона; причины первой тревоги по правилам; оценка допуска часов δf по разности
τ − t; распределения длительностей операций и задержек доставки, доля исправлений — для сверки
с допущениями генератора (model.py).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np

from .detectors import METHODS, MODE, derive, evaluate_case
from .evaluate import estimate_clock_tol, wilson
from .model import AUTO, END, MANUAL, OPERATIONS, SERVICE_OPS, START, SYSTEM, Params

ROOT = Path(__file__).resolve().parents[1]
REPORT_METHODS = {"P": "П", "B3": "М", "B2": "Б"}


def _num(v):
    if v in ("", None):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _time(v: str) -> float:
    """Минуты: число как есть, ISO 8601 — от 1970-01-01 (далее сдвигается к началу оборота)."""
    x = _num(v)
    if x is not None:
        return x
    return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() / 60.0


def load(log_path: Path, turns_path: Path, codes: dict) -> tuple[list[dict], Counter]:
    """Обороты в виде {"meta": ..., "messages": [...]} и счётчик пропущенных кодов."""
    op_map, st_map = codes.get("operation", {}), codes.get("status", {})
    skipped: Counter = Counter()
    msgs: dict = defaultdict(list)
    with open(log_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            op = op_map.get(r["operation"], r["operation"])
            st = st_map.get(r["status"], r["status"])
            if op not in OPERATIONS or st not in (START, END):
                skipped[(r["operation"], r["status"])] += 1
                continue
            kind = r.get("source_type", MANUAL).upper()
            kind = kind if kind in (MANUAL, AUTO, SYSTEM) else MANUAL
            msgs[r["turnaround_id"]].append({
                "msg_id": r["msg_id"], "op": op, "status": st, "kind": kind,
                "source": r.get("source_id") or r.get("role") or "?",
                "event_time": _time(r["event_time"]), "recv_time": _time(r["receive_time"]),
                "corr_of": r.get("correction_of") or None,
                "pax": None if _num(r.get("pax_count")) is None else int(_num(r["pax_count"])),
                "fuel_kg": _num(r.get("fuel_qty")),
                "safety": str(r.get("fuel_with_pax", "")).strip() in ("1", "true", "True", "да")})
    turns = []
    with open(turns_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ms = msgs.get(r["turnaround_id"])
            if not ms:
                continue
            t0 = min(m["event_time"] for m in ms)
            for m in ms:
                m["event_time"] -= t0
                m["recv_time"] -= t0
            eq = {x.strip() for x in (r.get("equipped") or "").split(";") if x.strip()} | {"DCS"}
            sta = _time(r["sta"]) - t0 if r.get("sta") else 0.0
            std = _time(r["std"]) - t0 if r.get("std") else sta + 50.0
            refs = {}
            if all(_num(r.get(k)) is not None for k in ("pax_in", "pax_out", "fuel_order")):
                refs = {"pax_in": int(float(r["pax_in"])), "pax_out": int(float(r["pax_out"])),
                        "fuel": float(r["fuel_order"])}
            meta = {"case_id": r["turnaround_id"], "seats": int(float(r.get("seats") or 180)),
                    "sched_in": sta, "std": std,
                    "auto_avail": {s: (s in eq) for s in ("VDGS", "PBB", "GPU", "METER", "DCS")},
                    "refs": refs}
            turns.append({"meta": meta, "messages": ms})
    return turns, skipped


def calibrated_params() -> dict[str, Params]:
    s = json.loads((ROOT / "results" / "summary.json").read_text(encoding="utf-8"))
    cal = {m: {k: v for k, v in c.items() if not k.startswith("_")}
           for m, c in s["calibrated"].items()}
    base = Params()
    return {"P": replace(base, **cal["P"]), "B3": replace(base, **cal["B3"]),
            "B2": replace(base, safety_trust="manual", trusted_norms=False, **cal["B2"])}


def analyse(turns: list[dict], clock_tol: float | None = None) -> tuple[dict, list[dict]]:
    tol = estimate_clock_tol([m for t in turns for m in t["messages"]]) \
        if clock_tol is None else clock_tol
    pp = calibrated_params()
    per_turn, alarms, reasons = [], Counter(), {m: Counter() for m in REPORT_METHODS}
    for t in turns:
        rec = {"turnaround_id": t["meta"]["case_id"], "n_messages": len(t["messages"])}
        for m in REPORT_METHODS:
            p = replace(pp[m], future_tol=tol, order_tol=tol)
            steps = evaluate_case(t["meta"], t["messages"], p)
            o = derive(steps, METHODS[m], p.grace, p.missing_horizon, None, float("inf"),
                       float("inf"), frozenset(), MODE.get(m, "P"), p.check_time)
            rec[f"alarm_{m}"] = int(o["n_alarms"] > 0)
            rec[f"first_key_{m}"] = "" if o["first_key"] is None else \
                ":".join(str(x) for x in o["first_key"][:2])
            alarms[m] += o["n_alarms"] > 0
            if o["first_key"] is not None:
                reasons[m][f"{o['first_key'][0]}:{o['first_key'][1]}"] += 1
        per_turn.append(rec)
    n = len(turns)
    man = [m for t in turns for m in t["messages"] if m["kind"] == MANUAL and not m["corr_of"]]
    dur = defaultdict(list)
    for t in turns:
        first = {}
        for m in t["messages"]:
            k = (m["op"], m["status"])
            first[k] = min(first.get(k, np.inf), m["event_time"])
        for op in SERVICE_OPS:
            if (op, START) in first and (op, END) in first:
                dur[op].append(first[(op, END)] - first[(op, START)])
    lag = [m["recv_time"] - m["event_time"] for m in man]
    report = {
        "n_turnarounds": n, "clock_tol_min": round(tol, 3),
        "alarm_share": {REPORT_METHODS[m]: {"value": alarms[m] / n if n else None,
                                            "ci95": wilson(alarms[m], n) if n else None}
                        for m in REPORT_METHODS},
        "first_alarm_reasons": {REPORT_METHODS[m]: dict(reasons[m].most_common())
                                for m in REPORT_METHODS},
        "measured": {
            "correction_share_turns": float(np.mean([any(m["corr_of"] for m in t["messages"])
                                                     for t in turns])) if n else None,
            "delivery_lag_min_quantiles": dict(zip(("p50", "p90", "p99"),
                                                   map(float, np.percentile(lag, [50, 90, 99]))))
            if lag else {},
            "duration_min_median": {op: float(np.median(v)) for op, v in dur.items()},
            "duration_min_p05": {op: float(np.percentile(v, 5)) for op, v in dur.items()},
        },
        "note": "Доля оборотов с тревогой на журнале без разметки — оценка сверху доли ложных "
                "тревог; причины первой тревоги показывают, какие зависимости и нормы модели "
                "расходятся с технологией эксплуатанта.",
    }
    return report, per_turn


def _demo(out: Path) -> tuple[Path, Path, Path]:
    """Синтетический журнал (штатные обороты выборки 1) в формате запроса данных."""
    from .simulate import generate_dataset
    cs = generate_dataset(1, 600, 0, Params())
    out.mkdir(parents=True, exist_ok=True)
    lp, tp, cp = out / "demo_log.csv", out / "demo_turns.csv", out / "demo_codes.json"
    with open(lp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["msg_id", "turnaround_id", "operation", "status", "event_time",
                    "receive_time", "source_type", "source_id", "role", "correction_of",
                    "pax_count", "fuel_qty", "fuel_with_pax"])
        for c in cs:
            for m in c.messages:
                w.writerow([m["msg_id"], c.case_id, m["op"], m["status"], repr(m["event_time"]),
                            repr(m["recv_time"]), m["kind"], m["source"], "", m["corr_of"] or "",
                            "" if m["pax"] is None else m["pax"],
                            "" if m["fuel_kg"] is None else m["fuel_kg"], int(m["safety"])])
    with open(tp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["turnaround_id", "seats", "sta", "std", "pax_in", "pax_out", "fuel_order",
                    "equipped"])
        for c in cs:
            # время в журнале отсчитывается от первого события оборота (постановка, 0 мин)
            w.writerow([c.case_id, c.seats, c.sched_in, c.std, c.refs["pax_in"],
                        c.refs["pax_out"], c.refs["fuel"],
                        ";".join(s for s, v in c.auto_avail.items() if v and s != "DCS")])
    cp.write_text(json.dumps({"operation": {}, "status": {}}), encoding="utf-8")
    return lp, tp, cp


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log")
    ap.add_argument("--turns")
    ap.add_argument("--codes")
    ap.add_argument("--out", default="real_log_out")
    ap.add_argument("--clock-tol", type=float, default=None,
                    help="допуск часов δf, мин; по умолчанию оценивается по журналу")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if a.demo:
        lp, tp, cp = _demo(out)
    else:
        lp, tp, cp = Path(a.log), Path(a.turns), Path(a.codes)
    codes = json.loads(Path(cp).read_text(encoding="utf-8"))
    turns, skipped = load(lp, tp, codes)
    report, per_turn = analyse(turns, a.clock_tol)
    report["skipped_codes"] = {f"{k[0]}|{k[1]}": v for k, v in skipped.items()}
    out.mkdir(parents=True, exist_ok=True)
    (out / "real_log_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    with open(out / "real_log_turns.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(per_turn[0]) if per_turn else ["turnaround_id"])
        w.writeheader()
        w.writerows(per_turn)
    print(json.dumps(report["alarm_share"], ensure_ascii=False))


if __name__ == "__main__":
    main()
