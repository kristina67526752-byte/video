"""Полный воспроизводимый прогон эксперимента (версия 3).

    python -m gh_integrity.run            # полный прогон (≈20–30 мин)
    python -m gh_integrity.run --quick    # сокращённый прогон для проверки

Этапы:
1) калибровка допусков на выборке seed=0 (условие: доля ложных тревог ≤ FPR_MAX) для П, Б2
   и Б3; точки сетки дают кривые «ложные тревоги — полнота»;
2) проверка на независимых выборках seed=1..N с зафиксированными допусками; П версии 2
   (доверие признаку safety и полям отметки) — для сравнения с исправленной моделью доверия;
3) последствия: исходы решений, задержки с учётом ручных проверок, нагрузка на смену,
   момент выявления относительно решений, условные категории тяжести;
4) сравнение при разных бюджетах ложных тревог; анализ чувствительности; проверка на данных
   альтернативной модели процесса (граф [Головченко, Асмоловская]);
5) сутки работы аэропорта: атаки и неисправности, правило K за окно и CUSUM, блокировка;
6) таблицы results/*.csv, сводка results/summary.json, рисунки figures/*.
Все данные синтетические.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import platform
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from .detectors import METHODS, MODE, alarm_keys, derive, evaluate_case
from .evaluate import (SEVERITY, calibrate, run_methods, summarize, true_readiness, wilson)
from .model import END, MANUAL, START, Params, precedence
from .simulate import VIOLATION_NAMES, VIOLATION_TYPES, generate_dataset

VERSION = "3.3"
ROOT = Path(__file__).resolve().parents[1]
RES, FIG, DATA = ROOT / "results", ROOT / "figures", ROOT / "data"
FPR_MAX = 0.05
BUDGETS = (0.025, 0.05, 0.10)
MAIN_TYPES = ["V1", "V2", "V3", "V4", "V5"]          # калибровка и показатель версии 3.0
ALL_TYPES = VIOLATION_TYPES
# Окно ожидания W ограничено сверху: критерий калибровки (максимум полноты при ограничении на
# ложные тревоги) не учитывает задержку тревоги, и без ограничения выбирается наибольшее W.
# Компромисс «окно — полнота — задержка» на широкой сетке: results/tradeoff_W.json; 15 мин —
# рабочая точка, выбранная авторами (дальше полнота растёт медленно, а задержка — линейно).
W_MAX = 15
# С версии 3.3 сетка шире (чтобы оптимум не ложился на её край), а монитор Б3 получает те же
# правила, что и П, включая подтверждение SAF и сверку со справочными значениями: это обычные
# ограничения предшествования с условием по данным (MP-Declare).
GRID_P = {"prec_tol": [2, 4, 6, 8, 10, 12], "dur_tol": [1, 2, 3, 4, 5], "cross_tol": [5, 8, 12],
          "stale_max": [15, 30, 45], "grace": [5, 10, W_MAX],
          "missing_horizon": [20, 30, 45, 60]}
GRID_B2 = {"stale_max": [15, 30], "grace": [5, 10, 15]}
GRID_B3 = {"prec_tol": [2, 4, 6, 8, 10, 12], "dur_tol": [1, 2, 3, 4, 5], "cross_tol": [5, 8, 12],
           "stale_max": [15, 30, 45], "grace": [0, 5, 10, W_MAX]}   # grace — буфер β
# Группы подвидов по тому, зависит ли исход от метода (версия 3.3, замечание о составе выборки)
BY_CONSTRUCTION = {"V1a", "V3a", "V3b", "V4-start", "V4-end", "V7a"}   # дубль, пропуск, флаг
OUT_OF_REACH = {"V6", "V7b", "V8"}                                     # граница применимости


def group_of(x: dict) -> str:
    """'construct' — обнаружение задано построением; 'reach' — вне возможностей метода;
    'subst' — содержательные случаи, где результат зависит от допусков и правил."""
    key = x["subtype"] or x["vtype"]
    if key in BY_CONSTRUCTION:
        return "construct"
    if key in OUT_OF_REACH or x["vtype"] in OUT_OF_REACH:
        return "reach"
    return "subst"
V2_TRUST = {"safety_trust": "manual", "trusted_norms": False}
DAY = 180                                           # оборотов в сутки (для нагрузки)


def _open_text(path: Path):
    """Текстовый файл; .gz — без метки времени в заголовке (повторный запуск даёт тот же файл)."""
    if path.suffix == ".gz":
        import io
        return io.TextIOWrapper(gzip.GzipFile(path, "wb", mtime=0), encoding="utf-8", newline="")
    return open(path, "w", newline="", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with _open_text(path) as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else
                            (str(v) if isinstance(v, (tuple, list)) else v)) for k, v in r.items()})


def _best(grid_rows: list[dict], method: str, keys: list[str], fpr_max: float = FPR_MAX) -> dict:
    rows = [r for r in grid_rows if r["method"] == method]
    feas = [r for r in rows if r["fpr"] <= fpr_max]
    if feas:
        b = max(feas, key=lambda r: (r["recall"], -r["fpr"], -r["lat_median"]))
    else:                                   # условие не выполнимо: минимум ложных тревог
        b = min(rows, key=lambda r: (r["fpr"], -r["recall"]))
    return {k: b[k] for k in keys} | {"_feasible": bool(feas)}


def _cfg(c: dict) -> dict:
    return {k: v for k, v in c.items() if not k.startswith("_")}


def integrity(rows: list[dict]) -> list[dict]:
    """Нарушения целостности данных: все виды, кроме V5a (фактическое нарушение технологии
    при правдивых данных); штатные обороты сохраняются."""
    return [x for x in rows if x["subtype"] != "V5a"]


def bypass_case(quiet: Params):
    """Оборот для контрольного опыта с признаком safety: без штатных отклонений, мер
    безопасности нет, счётчик есть, а заправка заканчивается последней из операций,
    предшествующих посадке (иначе готовность всё равно ждёт другую операцию)."""
    from .model import d1_preds
    for seed in range(1, 500):
        c = generate_dataset(seed, 1, 0, quiet)[0]
        ends = sorted(c.truth[(op, END)] for op, _ in d1_preds(quiet.gen_model))
        if (not c.safety and c.auto_avail.get("METER") and
                c.truth[("FUEL", END)] == ends[-1] and ends[-1] - ends[-2] >= 3.0):
            return c
    raise RuntimeError("no suitable case")


def _p(x) -> float:
    return float(np.percentile(x, 95)) if len(x) else float("nan")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args(argv)
    n_seeds, n_norm, n_type = (2, 200, 30) if a.quick else (10, 600, 100)
    grid_p = {k: [v[0], v[-1]] for k, v in GRID_P.items()} if a.quick else GRID_P
    grid_b3 = {k: [v[0], v[-1]] for k, v in GRID_B3.items()} if a.quick else GRID_B3
    t0 = time.time()
    base = Params()
    summary: dict = {"generated_by": "gh_integrity.run", "version": VERSION, "quick": a.quick,
                     "grid_P": GRID_P, "grid_B3": GRID_B3,
                     "fpr_max": FPR_MAX, "data": "synthetic", "base_params": asdict(base),
                     "environment": {"python": platform.python_version(),
                                     "numpy": np.__version__}}
    try:
        import matplotlib
        summary["environment"]["matplotlib"] = matplotlib.__version__
    except ImportError:
        pass

    # 1. калибровка
    cal = generate_dataset(0, n_norm, n_type, base, MAIN_TYPES)
    g_p = calibrate(cal, base, grid_p, {"P": METHODS["P"]}, FPR_MAX, MAIN_TYPES)
    g_b = calibrate(cal, replace(base, **V2_TRUST), GRID_B2, {"B2": METHODS["B2"]}, FPR_MAX,
                    MAIN_TYPES)
    g_3 = calibrate(cal, replace(base, missing_horizon=0), grid_b3,
                    {"B3": METHODS["B3"]}, FPR_MAX, MAIN_TYPES)
    _write_csv(RES / "calibration_grid.csv",
               [{k: v for k, v in r.items() if not k.endswith("_ci")} for r in g_p + g_b + g_3])
    cfg_p, cfg_b, cfg_3 = (_best(g_p, "P", list(grid_p)), _best(g_b, "B2", list(GRID_B2)),
                           _best(g_3, "B3", list(grid_b3)))
    p_P = replace(base, **_cfg(cfg_p))
    p_B = replace(base, **V2_TRUST, **_cfg(cfg_b))
    p_3 = replace(base, **_cfg(cfg_3))
    p_V2 = replace(p_P, **V2_TRUST)
    summary["calibrated"] = {"P": cfg_p, "B2": cfg_b, "B3": cfg_3}
    print("calibrated", cfg_p, cfg_b, cfg_3, f"{time.time() - t0:.0f}s")

    # 2. проверка на независимых выборках
    by_method = [(p_P, {k: v for k, v in METHODS.items() if k.startswith("P")}, None),
                 (p_B, {"B1": METHODS["B1"], "B2": METHODS["B2"]}, None),
                 (p_3, {"B3": METHODS["B3"]}, None),
                 (p_V2, {"P": METHODS["P"]}, "P_v2")]
    rows, cases_all = [], []
    for s in range(1, n_seeds + 1):
        cs = generate_dataset(s, n_norm, n_type, base)
        cases_all.append(cs)
        for pm, methods, rename in by_method:
            rr = run_methods(cs, pm, methods)
            rr = [dict(x, seed=s) for x in rr]
            rows += [dict(x, method=rename) for x in rr] if rename else rr
    _write_csv(RES / "per_case.csv.gz", rows)
    print("test done", f"{time.time() - t0:.0f}s")

    order = ["B1", "B2", "B3", "P_v2", "P", "P-T", "P-R1", "P-R2", "P-R3", "P-R4"]
    main_tab = []
    for m in order:
        s15, s17, s7 = (summarize(rows, m, MAIN_TYPES), summarize(integrity(rows), m, ALL_TYPES),
                        summarize(rows, m, ["V7"]))
        s8 = summarize(rows, m, ["V8"])
        main_tab.append({"method": m, "fpr": s15["fpr"], "fpr_lo": s15["fpr_ci"][0],
                         "fpr_hi": s15["fpr_ci"][1], "precision_V1_5": s15["precision"],
                         "recall_V1_5": s15["recall"], "recall_lo": s15["recall_ci"][0],
                         "recall_hi": s15["recall_ci"][1], "f1_V1_5": s15["f1"],
                         "recall_V8": s8["recall"],
                         "recall_V1_7": s17["recall"], "recall_V1_7_lo": s17["recall_ci"][0],
                         "recall_V1_7_hi": s17["recall_ci"][1], "recall_V7": s7["recall"],
                         "precision_V1_7": s17["precision"],
                         "tp_V1_5": s15["tp"], "fn_V1_5": s15["fn"], "fp": s15["fp"],
                         "tn": s15["tn"], "tp_any_V1_5": s15["tp_any"],
                         "recall_any_V1_5": s15["recall_any"],
                         "precision_any_V1_5": s15["precision_any"],
                         "lat_median": s15["lat_median"], "lat_p90": s15["lat_p90"],
                         "n_neg": s15["n_neg"], "n_pos_V1_5": s15["n_pos"],
                         "n_pos_V1_7": s17["n_pos"]})
        # содержательные случаи, разброс между выборками, время до тревоги (версия 3.3)
        rm = [x for x in integrity(rows) if x["method"] == m]
        pos = [x for x in rm if x["label"] == 1]
        for g in ("subst", "construct", "reach"):
            gg = [x for x in pos if group_of(x) == g]
            k = sum(x["detect_time"] is not None for x in gg)
            main_tab[-1].update({f"n_{g}": len(gg), f"recall_{g}": k / len(gg),
                                 f"recall_{g}_lo": wilson(k, len(gg))[0],
                                 f"recall_{g}_hi": wilson(k, len(gg))[1]})
        per_seed = {"fpr": [], "int": [], "subst": []}
        for sd in sorted({x["seed"] for x in rm}):
            neg = [x for x in rm if x["seed"] == sd and x["label"] == 0]
            ps = [x for x in pos if x["seed"] == sd]
            sb = [x for x in ps if group_of(x) == "subst"]
            per_seed["fpr"].append(sum(x["n_alarms"] > 0 for x in neg) / len(neg))
            per_seed["int"].append(sum(x["detect_time"] is not None for x in ps) / len(ps))
            per_seed["subst"].append(sum(x["detect_time"] is not None for x in sb) / len(sb))
        for k, v in per_seed.items():
            main_tab[-1].update({f"{k}_seed_min": min(v), f"{k}_seed_max": max(v),
                                 f"{k}_seed_sd": float(np.std(v, ddof=1)) if len(v) > 1 else 0.0})
        lat = [x["latency"] for x in pos if x["latency"] is not None]
        main_tab[-1].update({"lat_int_min": min(lat) if lat else float("nan"),
                             "lat_int_median": float(np.median(lat)) if lat else float("nan"),
                             "lat_int_p90": float(np.percentile(lat, 90)) if lat else float("nan")})
        fpr_m = main_tab[-1]["fpr"]
        for prev in (0.01, 0.001):          # доля тревог, связанных с нарушением (по Байесу)
            for nm in ("recall_V1_7", "recall_subst"):
                r_ = main_tab[-1][nm]
                den = prev * r_ + (1 - prev) * fpr_m
                main_tab[-1][f"ppv_{nm[7:]}_{prev}"] = prev * r_ / den if den else float("nan")
    _write_csv(RES / "main_metrics.csv", main_tab)
    summary["main"] = main_tab

    # по видам и подвидам нарушений, исходы решений
    by_type = []
    for m in ["B1", "B2", "B3", "P_v2", "P"]:
        for vt in ["N"] + VIOLATION_TYPES:
            r = [x for x in rows if x["method"] == m and x["vtype"] == vt]
            n = len(r)
            det = sum((x["n_alarms"] > 0) if vt == "N" else (x["detect_time"] is not None)
                      for x in r)
            lat = [x["latency"] for x in r if x["latency"] is not None]
            rec = {"method": m, "vtype": vt, "n": n, "alarm_or_detect": det / n,
                   "ci_lo": wilson(det, n)[0], "ci_hi": wilson(det, n)[1],
                   "lat_median": float(np.median(lat)) if lat else float("nan")}
            for d in ("d1", "d2"):
                for oc in ("false", "manual", "none", "ok"):
                    rec[f"{d}_{oc}"] = sum(x[f"{d}_outcome"] == oc for x in r) / n
                dl = [x[f"{d}_delay"] for x in r if x[f"{d}_delay"] is not None
                      and x[f"{d}_outcome"] != "false"]
                rec[f"{d}_delay_mean"] = float(np.mean(dl)) if dl else float("nan")
                rec[f"{d}_delay_p95"] = _p(dl)
                hold = [x[f"{d}_hold"] for x in r if x[f"{d}_hold"] is not None]
                rec[f"{d}_hold_p95_auto"] = _p(hold)
            by_type.append(rec)
    _write_csv(RES / "by_type.csv", by_type)
    summary["by_type"] = by_type

    sub = []
    for m in ["B2", "B3", "P_v2", "P"]:
        for st in sorted({x["subtype"] for x in rows if x["subtype"]}):
            r = [x for x in rows if x["method"] == m and x["subtype"] == st]
            det = sum(x["detect_time"] is not None for x in r)
            sub.append({"method": m, "subtype": st, "n": len(r), "recall": det / len(r),
                        "ci_lo": wilson(det, len(r))[0], "ci_hi": wilson(det, len(r))[1],
                        "d1_false": sum(x["d1_outcome"] == "false" for x in r) / len(r),
                        "d2_false": sum(x["d2_outcome"] == "false" for x in r) / len(r)})
    _write_csv(RES / "by_subtype.csv", sub)
    summary["by_subtype"] = sub

    # нагрузка на смену и задержки решений на штатных оборотах
    work = []
    for m in ["B2", "B3", "P_v2", "P"]:
        r = [x for x in rows if x["method"] == m and x["label"] == 0]
        n = len(r)
        alarm = sum(x["n_alarms"] > 0 for x in r) / n
        man1 = sum(x["d1_outcome"] == "manual" for x in r) / n
        man2 = sum(x["d2_outcome"] == "manual" for x in r) / n
        d1 = [x["d1_delay"] for x in r if x["d1_delay"] is not None]
        d2 = [x["d2_delay"] for x in r if x["d2_delay"] is not None]
        work.append({"method": m, "n": n, "alarm_share": alarm, "d1_manual": man1,
                     "d2_manual": man2, "alarms_per_day": alarm * DAY,
                     "checks_per_day": (man1 + man2) * DAY,
                     "check_minutes_per_day": (man1 + man2) * DAY * base.check_time,
                     "d1_delay_mean": float(np.mean(d1)), "d1_delay_p95": _p(d1),
                     "d2_delay_mean": float(np.mean(d2)), "d2_delay_p95": _p(d2),
                     "d1_delay_share_gt5": float(np.mean([v > 5 for v in d1])),
                     "d1_false": sum(x["d1_outcome"] == "false" for x in r) / n,
                     "d2_false": sum(x["d2_outcome"] == "false" for x in r) / n})
    _write_csv(RES / "workload.csv", work)
    summary["workload"] = work

    # момент выявления относительно фактических решений
    timing = []
    for m in ["B2", "B3", "P"]:
        r = [x for x in integrity(rows) if x["method"] == m and x["label"] == 1]
        det = [x for x in r if x["detect_time"] is not None]
        cats = {"before_d1": 0, "before_d2": 0, "before_ofb": 0, "after_ofb": 0}
        for x in det:
            t = x["detect_time"]
            k = ("before_d1" if t <= x["true_d1"] else "before_d2" if t <= x["true_d2"]
                 else "before_ofb" if t <= x["true_ofb"] else "after_ofb")
            cats[k] += 1
        timing.append({"method": m, "n_pos": len(r), "n_detected": len(det),
                       **{k: v / len(r) for k, v in cats.items()}})
    _write_csv(RES / "timing.csv", timing)
    summary["timing"] = timing

    # ошибка ручной проверки: с вероятностью q проверяющий подтверждает данные, не обнаружив
    # нарушения (например, запрос тому же исполнителю); решение тогда принимается по данным
    check_err = []
    for m in ["B2", "B3", "P_v2", "P"]:
        r = [x for x in rows if x["method"] == m and x["label"] == 1]
        kv = sum(x["severity"] in ("К", "В") for x in r)
        extra = sum(1 for x in r if x["severity"] not in ("К", "В") and any(
            x[f"{d}_outcome"] == "manual" and x[f"{d}_cond"] is not None
            and x[f"{d}_cond"] < x[f"true_{d}"] - 1e-9 for d in ("d1", "d2")))
        for q in (0.0, 0.25, 0.5, 1.0):
            check_err.append({"method": m, "q_miss": q, "false_decisions_KV": kv + q * extra,
                              "n": len(r)})
    ct_sens = []
    for m in ["B3", "P"]:
        r = [x for x in rows if x["method"] == m and x["label"] == 0]
        for ct in (1.0, 3.0, 5.0, 10.0):
            dl = []
            for x in r:
                if x["d1_outcome"] == "manual":
                    dl.append(max(x["first_alarm"], x["true_d1"]) + ct - x["true_d1"])
                elif x["d1_delay"] is not None:
                    dl.append(x["d1_delay"])
            checks = sum((x["d1_outcome"] == "manual") + (x["d2_outcome"] == "manual") for x in r)
            ct_sens.append({"method": m, "check_time": ct,
                            "check_minutes_per_day": checks / len(r) * DAY * ct,
                            "d1_delay_mean": float(np.mean(dl)), "d1_delay_p95": _p(dl)})
    _write_csv(RES / "check_error.csv", check_err)
    _write_csv(RES / "check_time.csv", ct_sens)
    summary["check_error"], summary["check_time"] = check_err, ct_sens

    # зависимость полноты от величины нарушения (нарушитель, знающий допуски, выбирает малую)
    from .simulate import generate_case
    mag = []
    specs = [("V1", "frac", [0.1, 0.25, 0.4, 0.55, 0.7, 0.85], {"subtype": "V1b"}),
             ("V2", "shift", [1, 2, 4, 6, 8, 12, 16, 20], {}),
             ("V5", "amount", [1, 2, 3, 5, 7, 10], {})]
    n_mag = 60 if a.quick else 300
    for vt, key, values, extra in specs:
        for v in values:
            rng = np.random.default_rng([400, VIOLATION_TYPES.index(vt), int(v * 100)])
            cs = [generate_case(rng, f"M-{vt}-{i}", vt, base, force={key: v, **extra})
                  for i in range(n_mag)]
            cs = [c for c in cs if c.gt_inj_time is not None]
            for pm, meths in ((p_P, {"P": METHODS["P"]}), (p_3, {"B3": METHODS["B3"]}),
                              (p_B, {"B2": METHODS["B2"]})):
                rr = run_methods(cs, pm, meths)
                for mname in meths:
                    x = [y for y in rr if y["method"] == mname]
                    mag.append({"vtype": vt, "param": key, "value": v, "method": mname,
                                "n": len(x), "recall": sum(y["detect_time"] is not None for y in x)
                                / max(1, len(x))})
    _write_csv(RES / "magnitude.csv", mag)
    summary["magnitude"] = mag
    print("magnitude done", f"{time.time() - t0:.0f}s")

    # условные категории тяжести: абсолютные числа и парное сравнение с П
    sev = []
    by_case = {}
    for x in rows:
        if x["label"] == 1:
            by_case.setdefault(x["case_id"], {})[x["method"]] = x["severity"]
    for m in ["B1", "B2", "B3", "P_v2", "P"]:
        r = [x for x in rows if x["method"] == m and x["label"] == 1]
        cnt = {k: sum(x["severity"] == k for x in r) for k in SEVERITY}
        rec = {"method": m, "n": len(r), **{k: cnt[k] / len(r) for k in SEVERITY},
               **{f"{k}_n": cnt[k] for k in SEVERITY}}
        if m != "P":                        # обороты, где ровно один метод дал К или В
            worse = sum(1 for v in by_case.values() if v.get(m) in ("К", "В")
                        and v.get("P") not in ("К", "В"))
            better = sum(1 for v in by_case.values() if v.get("P") in ("К", "В")
                         and v.get(m) not in ("К", "В"))
            rec.update({"only_this_KV": worse, "only_P_KV": better})
            nn = worse + better
            if nn:
                from math import comb
                kmin = min(worse, better)
                rec["mcnemar_p"] = min(1.0, 2 * sum(comb(nn, i) for i in range(kmin + 1)) / 2 ** nn)
        sev.append(rec)
    _write_csv(RES / "severity.csv", sev)
    summary["severity"] = sev

    # причины ложных тревог предложенного метода
    fp_keys: dict = {}
    for x in rows:
        if x["method"] == "P" and x["label"] == 0 and x["n_alarms"] > 0:
            k = x["first_key"][0] + ":" + x["first_key"][1]
            fp_keys[k] = fp_keys.get(k, 0) + 1
    summary["fp_first_key_P"] = dict(sorted(fp_keys.items(), key=lambda kv: -kv[1]))
    fp_var = {}
    for x in rows:
        if x["method"] == "P" and x["label"] == 0:
            v = "unmodeled_variant" in x["features"]
            fp_var.setdefault(v, [0, 0])
            fp_var[v][0] += x["n_alarms"] > 0
            fp_var[v][1] += 1
    summary["fpr_P_by_unmodeled_variant"] = {str(k): v[0] / v[1] for k, v in fp_var.items()}

    # 3. бюджеты ложных тревог: точки на калибровочной выборке и проверка на трёх выборках
    flat3 = [c for cs in cases_all[:3] for c in cs]
    budget = []
    for B in BUDGETS:
        for m, grid_rows, keys, pbase in (("P", g_p, list(grid_p), base),
                                           ("B2", g_b, list(GRID_B2), replace(base, **V2_TRUST)),
                                           ("B3", g_3, list(grid_b3), base)):
            c = _best(grid_rows, m, keys, B)
            rr = run_methods(flat3, replace(pbase, **_cfg(c)), {m: METHODS[m]})
            s = summarize(rr, m, MAIN_TYPES)
            cal_pt = next(r for r in grid_rows if r["method"] == m
                          and all(r[k] == c[k] for k in keys))
            budget.append({"budget": B, "method": m, "feasible_on_calibration": c["_feasible"],
                           "fpr_calibration": cal_pt["fpr"],
                           **_cfg(c), "fpr": s["fpr"], "recall": s["recall"],
                           "recall_V1_7": summarize(integrity(rr), m, ALL_TYPES)["recall"],
                           "d1_false_V": sum(x["d1_outcome"] == "false" for x in rr if x["label"])
                           / max(1, sum(x["label"] for x in rr))})
    _write_csv(RES / "budgets.csv", budget)
    summary["budgets"] = budget
    print("budgets done", f"{time.time() - t0:.0f}s")

    # 4. чувствительность
    sens = []
    flat = [c for cs in cases_all[:3] for c in cs]

    def _cache(pp):
        return [(c, evaluate_case(c.meta(), c.messages, pp),
                 evaluate_case(c.meta(), c.twin_messages, pp) if c.twin_messages else None,
                 *true_readiness(c)) for c in flat]
    cache_P, cache_B = _cache(p_P), _cache(p_B)
    for W in [0, 2, 5, 10, 15, 20]:
        for m, cache, H in (("P", cache_P, p_P.missing_horizon), ("B2", cache_B, p_B.missing_horizon)):
            rr = []
            for c, st, tw, d1, d2 in cache:
                tk = alarm_keys(tw, METHODS[m], W, H) if tw else frozenset()
                o = derive(st, METHODS[m], W, H, c.gt_inj_time, d1, d2, tk)
                rr.append({"method": m, "label": c.label, "vtype": c.vtype or "N", **o,
                           "latency": (o["detect_time"] - c.gt_inj_time)
                           if o["detect_time"] is not None else None})
            s = summarize(rr, m, MAIN_TYPES)
            sens.append({"factor": "grace_W", "value": W, "method": m, "fpr": s["fpr"],
                         "recall": s["recall"], "lat_median": s["lat_median"]})
    for factor, values in (("late_mark_share", [0.0, 0.05, 0.15, 0.30, 0.45]),
                           ("p_unmodeled_variant", [0.0, 0.05, 0.10, 0.20]),
                           ("min_dur_share", [0.3, 0.4, 0.5, 0.6, 0.7])):
        for v in values:
            gen = replace(base, **{factor: v})
            cs = [c for s in range(1, 4) for c in generate_dataset(100 + s, n_norm, n_type, gen,
                                                                     MAIN_TYPES)]
            rr = run_methods(cs, replace(p_P, **{factor: v}), {"P": METHODS["P"]}) + \
                run_methods(cs, replace(p_B, **{factor: v}), {"B2": METHODS["B2"]})
            for m in ("P", "B2"):
                s = summarize(rr, m, MAIN_TYPES)
                v1b = [x for x in rr if x["method"] == m and x["subtype"] == "V1b"]
                sens.append({"factor": factor, "value": v, "method": m, "fpr": s["fpr"],
                             "recall": s["recall"], "lat_median": s["lat_median"],
                             "recall_V1b": sum(x["detect_time"] is not None for x in v1b)
                             / max(1, len(v1b))})
    _write_csv(RES / "sensitivity.csv", sens)
    summary["sensitivity"] = sens
    print("sensitivity done", f"{time.time() - t0:.0f}s")

    # 4а. согласованность модели процесса: генератор × правила (основная модель / граф [Г])
    cross = []
    for gm in ("base", "alt"):
        cs = [c for s in range(1, 4) for c in generate_dataset(200 + s, n_norm, n_type,
                                                                 replace(base, gen_model=gm),
                                                                 MAIN_TYPES)]
        for cm in ("base", "alt"):
            rr = run_methods(cs, replace(p_P, ctrl_model=cm), {"P": METHODS["P"]})
            s = summarize(rr, "P", MAIN_TYPES)
            fk: dict = {}
            for x in rr:
                if x["label"] == 0 and x["n_alarms"] > 0:
                    k = x["first_key"]
                    kk = f"{k[0]}:{k[1]}" + (f":{k[2][0]}.{k[2][1]}>{k[3][0]}.{k[3][1]}"
                                             if k[0] == "R1" else "")
                    fk[kk] = fk.get(kk, 0) + 1
            top = max(fk.items(), key=lambda kv: kv[1]) if fk else ("", 0)
            cross.append({"generator": gm, "rules": cm, "n_rules": len(precedence(cm)),
                          "fpr": s["fpr"], "fpr_lo": s["fpr_ci"][0], "fpr_hi": s["fpr_ci"][1],
                          "recall": s["recall"], "top_fp_key": top[0],
                          "top_fp_share": top[1] / max(1, s["fp"])})
    _write_csv(RES / "cross_model.csv", cross)
    summary["cross_model"] = cross

    # 4б. обход через признак safety (контрольный опыт рецензии) и его исправление
    quiet = replace(base, late_mark_share=0, p_offline=0, p_correction=0, retry_share=0,
                    p_operational_delay=0, p_unmodeled_variant=0, p_safety_fuelling=0)
    c = bypass_case(quiet)
    # доля штатных оборотов, где заправка — последняя операция перед посадкой (там обход значим)
    fuel_last = [x for cs in cases_all for x in cs if x.label == 0 and not x.safety
                 and x.truth[("FUEL", END)] >= true_readiness(x)[0] - 1e-9]
    n_norm_all = sum(1 for cs in cases_all for x in cs if x.label == 0)
    msgs = [dict(m) for m in c.messages]
    for m in msgs:
        if m["op"] == "FUEL" and m["status"] == START and m["kind"] == MANUAL:
            m["safety"] = True
    d1t, d2t = true_readiness(c)
    sc = {"case_id": c.case_id, "true_safety": c.safety, "meter": c.auto_avail.get("METER"),
          "true_d1": d1t, "share_fuel_last_normal": len(fuel_last) / n_norm_all}
    for name, pp in (("v2", p_V2), ("v3", p_P)):
        st = evaluate_case(c.meta(), msgs, pp)
        o = derive(st, METHODS["P"], pp.grace, pp.missing_horizon, 0.0, d1t, d2t,
                   check_time=pp.check_time)
        sc[name] = {"d1_outcome": o["d1_outcome"], "d1_time": o["d1_time"],
                    "n_alarms": o["n_alarms"], "first_alarm": o["first_alarm"],
                    "first_key": str(o["first_key"])}
    (RES / "safety_check.json").write_text(json.dumps(sc, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    summary["safety_check"] = sc

    # 5. сутки работы аэропорта
    from . import campaign as C
    n_days = 5 if a.quick else 100
    cal_days = list(range(5000, 5000 + (5 if a.quick else 50)))
    cus = C.calibrate_cusum(cal_days, base, p_P, p_B)
    camp_rows = C.run(n_days, base, p_P, p_B, cusum=cus)
    _write_csv(RES / "campaign_days.csv", camp_rows)
    camp = C.summarize(camp_rows)
    _write_csv(RES / "campaign.csv", camp)
    summary["campaign"] = {"summary": camp, "n_days": n_days, "n_turn": C.N_TURN,
                           "pools": C.POOLS, "attacks": {k: list(v) for k, v in C.ATTACKS.items()},
                           "faults": C.FAULTS, "attack_start_h": C.ATTACK_START / 60 + 6,
                           "q_forge": C.Q_FORGE, "q_quiet": C.Q_QUIET, "window_h": C.WINDOW / 60,
                           "k_values": list(C.K_VALUES), "cusum": cus,
                           "cusum_calibration_days": len(cal_days)}
    print("campaign done", f"{time.time() - t0:.0f}s")

    # 6. образец синтетического журнала и описание выборок
    DATA.mkdir(exist_ok=True)
    sample = cases_all[0]
    with _open_text(DATA / "synthetic_log_seed01.csv.gz") as f:
        keys = ["case_id", "msg_id", "op", "status", "kind", "source", "event_time", "recv_time",
                "pax", "fuel_kg", "safety", "corr_of", "gt_injected", "gt_true_time", "gt_note"]
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for c in sample:
            for m in c.messages:
                w.writerow({k: (round(m[k], 3) if isinstance(m[k], float) else m[k]) for k in keys})
    _write_csv(DATA / "synthetic_cases_seed01.csv",
               [{"case_id": c.case_id, "label": c.label, "vtype": c.vtype or "N",
                 "subtype": c.subtype or "", "target": c.gt_target or "",
                 "inj_time": c.gt_inj_time, "features": ";".join(c.features),
                 "seats": c.seats, "pax_in": c.pax_in, "pax_out": c.pax_out,
                 "fuel_kg": round(c.fuel_kg), "safety": c.safety,
                 "ref_pax_in": c.refs["pax_in"], "ref_pax_out": c.refs["pax_out"],
                 "ref_fuel": c.refs["fuel"],
                 "auto": ";".join(k for k, v in c.auto_avail.items() if v),
                 "n_messages": len(c.messages)} for c in sample])
    n_msgs = [len(c.messages) for cs in cases_all for c in cs]
    summary["dataset"] = {"seeds_test": list(range(1, n_seeds + 1)), "seed_calibration": 0,
                          "n_normal_per_seed": n_norm, "n_per_type_per_seed": n_type,
                          "n_cases_test": sum(len(cs) for cs in cases_all),
                          "messages_per_case_mean": float(np.mean(n_msgs)),
                          "violation_names": VIOLATION_NAMES, "n_rules": len(precedence())}
    summary["runtime_s"] = round(time.time() - t0, 1)
    RES.mkdir(exist_ok=True)
    (RES / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1,
                                                 default=lambda o: list(o) if isinstance(o, tuple) else str(o)),
                                      encoding="utf-8")

    from .figures import fig_campaign, make_all
    make_all(RES, FIG, cases_all[0], p_P, p_B)
    fig_campaign(RES, FIG, base, p_P, p_B)
    print("done", f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
