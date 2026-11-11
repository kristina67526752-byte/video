"""Подозрение на нарушение источника данных: сутки работы аэропорта.

Сценарии атаки (нарушитель Н2 с 12:00 контролирует один мобильный терминал):
  FUEL, CLEAN, GATE — подделывает отметку об окончании операции и подавляет подлинную (V1b);
  SAFETY — с терминала заправщика ставит ложный признак заправки с пассажирами (V7a).
Сценарии неисправностей без атаки (с 12:00):
  CLOCK — часы терминала агента выхода спешат на 8 мин;
  NET — сообщения терминала службы уборки доставляются с задержкой 20–40 мин;
  METER — счётчик топливозаправщика занижает количество на 3 % (тревоги относятся к
  терминалу заправщика этой машины — ошибочная локализация).

Уровень 1 — тревоги по отдельным оборотам (методы Б2 и П).
Уровень 2 — подозрение на нарушение источника: терминал признаётся подозрительным, если
  (а) тревоги, отнесённые к нему, возникли не менее чем в K разных оборотах за окно Tw, или
  (б) статистика CUSUM по доле его оборотов с тревогами превысила порог h.
Подозрение — не установленная компрометация: его причиной может быть и неисправность.
После подозрения терминал блокируется: его дальнейшие отметки требуют ручного подтверждения
(предотвращённые ложные решения и нагрузка), данные за окно Tw перепроверяются
(ретроспективно выявленные ложные решения). Ущерб — ложные решения о готовности, принятые
до момента подозрения, по общей шкале времени.

Для каждых суток строится «чистый» вариант с теми же случайными величинами (общие
случайные числа): так оцениваются ложные подозрения.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from .detectors import METHODS, _alarms, derive, evaluate_case
from .evaluate import true_readiness
from .model import AUTO, END, MANUAL, OPERATIONS, Params
from .simulate import generate_case

# Пулы терминалов — по числу ресурсов в модельном сценарии [Головченко, Асмоловская] при той
# же интенсивности (~10 рейсов/ч): заправщики 4, уборочные бригады 4, кейтеринг-машины 3,
# наземные бригады 5 (выход и трап), перрон 10 = 5 багажных тягачей + 2 водовоза + 3 буксира;
# руководители смены (подтверждение мер безопасности) 3 — допущение.
POOLS = {"RAMP": 10, "PBB_OP": 5, "GATE": 5, "CLEAN": 4, "CATER": 3, "FUEL": 4, "SUPV": 3}
ATTACKS = {"FUEL": ("FUEL", "V1"), "CLEAN": ("CLN", "V1"), "GATE": ("BRD", "V1"),
           "SAFETY": (None, "V7"),                      # сценарий -> (операция, вид)
           "GATE_QUIET": ("BRD", "V1")}                 # «тихий» нарушитель: Q_QUIET оборотов
ATTACK_ROLE = {"FUEL": "FUEL", "CLEAN": "CLEAN", "GATE": "GATE", "SAFETY": "FUEL",
               "GATE_QUIET": "GATE"}
Q_QUIET = 0.15             # доля оборотов, где подделывает отметку «тихий» нарушитель
FAULTS = {"CLOCK": "GATE", "NET": "CLEAN", "METER": "FUEL"}   # неисправность -> роль
SCENARIOS = {"FUEL": "FUEL", "CLEAN": "CLN", "GATE": "BRD"}   # совместимость с версией 2
N_TURN = 180               # оборотов за сутки
DAY_MIN = 18 * 60          # обороты начинаются с 06:00 до 24:00
ATTACK_START = 6 * 60      # атака или неисправность начинается в 12:00
Q_FORGE = 0.7              # доля обслуживаемых оборотов, где нарушитель подделывает отметку
WINDOW = 6 * 60            # Tw, мин
K_VALUES = (2, 3, 4, 5)
CUSUM_P1 = 0.5             # доля оборотов с тревогами, на которую настроена CUSUM
METHODS_DAY = ("P", "B2")


@dataclass
class Turn:
    k: int
    t0: float
    assign: dict
    case: object


def _remap(case, assign: dict) -> None:
    """Ручные отметки оборота — с терминалов, назначенных из пула роли."""
    for msgs in (case.messages, case.twin_messages or []):
        for m in msgs:
            if m["kind"] == MANUAL:
                role = m["source"].rsplit("-T", 1)[0]
                m["source"] = f"{role}-T{assign[role]:02d}"


def _terminal(op: str, assign: dict) -> str | None:
    role = OPERATIONS[op].manual_role
    return f"{role}-T{assign[role]:02d}" if role else None


def key_terminals(key: tuple, by_id: dict, assign: dict) -> set[str]:
    """К каким терминалам исполнителей относится несоответствие."""
    g, kind = key[0], key[1]
    ops: list[str] = []
    if kind in ("window", "range", "future", "stale", "after", "badcorr"):
        m = by_id.get(key[2])
        return {m["source"]} if m is not None and m["kind"] == MANUAL else set()
    if g == "R1" and key[2] == ("SAF", END):
        ops = [key[3][0]]                       # признак заявлен заправщиком без подтверждения
    elif g == "R1":
        ops = [key[2][0], key[3][0]]
    elif g in ("T", "R2") or kind in ("nostart", "ref"):
        ops = [key[2]]
    elif kind == "dup":
        ops = [key[2]] if key[4] == MANUAL else []
    elif kind in ("time", "missing"):
        ops = [key[2]]
    elif kind == "qty":
        ops = ["FUEL"]
    elif kind == "pax":
        ops = ["BRD"]
    return {t for t in (_terminal(o, assign) for o in ops) if t}


def _served(assign: dict) -> set[str]:
    return {f"{r}-T{i:02d}" for r, i in assign.items()}


def _evaluate(turn: Turn, params: dict) -> dict:
    c = turn.case
    by_id = {m["msg_id"]: m for m in c.messages}
    d1, d2 = true_readiness(c)
    out = {"served": _served(turn.assign), "t_end": turn.t0 + c.truth[("OFB", END)]}
    for name in METHODS_DAY:
        pp = params[name]
        steps = evaluate_case(c.meta(), c.messages, pp)
        al, _ = _alarms(steps, METHODS[name], pp.grace, pp.missing_horizon)
        o = derive(steps, METHODS[name], pp.grace, pp.missing_horizon, c.gt_inj_time, d1, d2,
                   check_time=pp.check_time)
        events = [(turn.t0 + t, term) for t, k in al for term in key_terminals(k, by_id, turn.assign)]
        false_dec = [turn.t0 + o[f"{d}_time"] for d in ("d1", "d2") if o[f"{d}_outcome"] == "false"]
        out[name] = {"events": events, "false_dec": false_dec}
    return out


def _flags_k(events: list[tuple[float, str, int]], K: int) -> dict[str, float]:
    """Момент подозрения по правилу «K оборотов за окно WINDOW»."""
    by_term: dict[str, list[tuple[float, int]]] = {}
    for t, term, k in sorted(events):
        by_term.setdefault(term, []).append((t, k))
    flags = {}
    for term, evs in by_term.items():
        for i, (t, _) in enumerate(evs):
            turns = {kk for tt, kk in evs[: i + 1] if tt >= t - WINDOW}
            if len(turns) >= K:
                flags[term] = t
                break
    return flags


def cusum_ref(p0: float, p1: float = CUSUM_P1) -> float:
    """Опорное значение бернуллиевой CUSUM для сдвига доли с p0 до p1."""
    p0 = min(max(p0, 1e-4), p1 - 1e-4)
    return math.log((1 - p0) / (1 - p1)) / math.log(p1 * (1 - p0) / (p0 * (1 - p1)))


def _observations(res: list[dict], method: str) -> dict[str, list[tuple[float, int]]]:
    """Наблюдения по терминалам: (время, 1 — в обороте есть тревога по терминалу, 0 — нет)."""
    obs: dict[str, list[tuple[float, int]]] = {}
    for k, r in enumerate(res):
        first: dict[str, float] = {}
        for t, term in r[method]["events"]:
            first[term] = min(t, first.get(term, t))
        for term in r["served"]:
            obs.setdefault(term, []).append((first[term], 1) if term in first else (r["t_end"], 0))
    return obs


def _flags_cusum(obs: dict, k_ref: dict, h: float) -> dict[str, float]:
    flags = {}
    for term, seq in obs.items():
        k = k_ref[term.rsplit("-T", 1)[0]]
        s = 0.0
        for t, x in sorted(seq):
            s = max(0.0, s + x - k)
            if s >= h:
                flags[term] = t
                break
    return flags


def _transform_fault(case, fault: str, term: str, rng: np.random.Generator) -> bool:
    """Применить неисправность к сообщениям оборота; True, если оборот затронут."""
    hit = False
    for m in case.messages:
        if fault == "CLOCK" and m["kind"] == MANUAL and m["source"] == term:
            m["event_time"] += 8.0
            hit = True
        elif fault == "NET" and m["kind"] == MANUAL and m["source"] == term:
            m["recv_time"] += float(rng.uniform(20, 40))
            hit = True
        elif fault == "METER" and m["kind"] == AUTO and m["op"] == "FUEL" and m["fuel_kg"] is not None:
            m["fuel_kg"] = round(m["fuel_kg"] * 0.97, 0)
            hit = True
    if fault == "METER" and not any(m["kind"] == MANUAL and m["source"] == term for m in case.messages):
        return False                                  # счётчик — на машине этого заправщика
    return hit


def _day(seed: int, p_gen: Params, params: dict, scenarios: tuple):
    """Результаты оценки всех оборотов суток: чистый вариант и варианты сценариев."""
    rng = np.random.default_rng([seed, 0])
    starts = np.sort(rng.uniform(0, DAY_MIN, N_TURN))
    assigns = [{r: int(rng.integers(n)) for r, n in POOLS.items()} for _ in range(N_TURN)]
    forge_u = rng.random(N_TURN)                              # решения нарушителя
    bad_idx = {r: int(rng.integers(n)) for r, n in POOLS.items()}

    def build(k: int, vtype=None, force=None) -> Turn:
        case = generate_case(np.random.default_rng([seed, 1, k]), f"D{seed:03d}-T{k:03d}",
                             vtype, p_gen, force=force)
        _remap(case, assigns[k])
        return Turn(k, float(starts[k]), assigns[k], case)

    clean_turns = [build(k) for k in range(N_TURN)]
    clean = [_evaluate(t, params) for t in clean_turns]
    variants = {"none": (clean, {}, None)}
    for scen in scenarios:
        res, forged = list(clean), {}
        if scen in ATTACKS:
            role = ATTACK_ROLE[scen]
            bad_term = f"{role}-T{bad_idx[role]:02d}"
            op, vtype = ATTACKS[scen]
            for k in range(N_TURN):
                if assigns[k][role] != bad_idx[role] or starts[k] < ATTACK_START \
                        or forge_u[k] >= (Q_QUIET if scen.endswith("_QUIET") else Q_FORGE):
                    continue
                if scen == "SAFETY" and clean_turns[k].case.safety:
                    continue                          # подделка имеет смысл без мер безопасности
                force = {"op": op, "subtype": "V1b"} if vtype == "V1" else {"subtype": "V7a"}
                turn = build(k, vtype, force)
                if turn.case.gt_inj_time is not None:
                    res[k] = _evaluate(turn, params)
                    forged[k] = starts[k] + turn.case.gt_inj_time
        else:
            role = FAULTS[scen]
            bad_term = f"{role}-T{bad_idx[role]:02d}"
            frng = np.random.default_rng([seed, 2])
            for k in range(N_TURN):
                if assigns[k][role] != bad_idx[role] or starts[k] < ATTACK_START:
                    continue
                turn = build(k)
                if _transform_fault(turn.case, scen, bad_term, frng):
                    res[k] = _evaluate(turn, params)
                    forged[k] = starts[k]             # затронутые обороты
        variants[scen] = (res, forged, bad_term)
    return variants


def _events(res: list[dict], method: str) -> list[tuple[float, str, int]]:
    return [(t, term, k) for k, r in enumerate(res) for t, term in r[method]["events"]]


def _rules(res: list[dict], method: str, cusum: dict | None) -> dict[str, dict]:
    ev = _events(res, method)
    rules = {f"K{K}": _flags_k(ev, K) for K in K_VALUES}
    if cusum is not None:
        rules["CUSUM"] = _flags_cusum(_observations(res, method), cusum["k_ref"][method],
                                      cusum["h"][method])
    return rules


def _consequences(res: list[dict], method: str, flags: dict, bad_term: str | None) -> dict:
    """Ущерб и нагрузка при блокировке терминалов в момент подозрения."""
    t_bad = flags.get(bad_term, math.inf) if bad_term else math.inf
    before = prevented = retro = total = 0
    for r in res:
        for t in r[method]["false_dec"]:
            total += 1
            if bad_term and bad_term in r["served"] and t >= t_bad:
                prevented += 1                      # решение после блокировки не принимается
            else:
                before += 1
                if bad_term and bad_term in r["served"] and t_bad - WINDOW <= t < t_bad:
                    retro += 1                      # выявлено при перепроверке данных за Tw
    manual = sum(1 for r in res for term, t_f in flags.items()
                 if term in r["served"] and r["t_end"] >= t_f)
    return {"false_ready_total": total, "false_ready_before_detect": before,
            "prevented_by_block": prevented, "retro_detected": retro,
            "manual_after_block": manual}


def simulate_day(seed: int, p_gen: Params, pP: Params, pB: Params,
                 scenarios: tuple = (*ATTACKS, *FAULTS), cusum: dict | None = None) -> list[dict]:
    rows = []
    params = {"P": pP, "B2": pB}
    for scen, (res, forged, bad_term) in _day(seed, p_gen, params, scenarios).items():
        for method in METHODS_DAY:
            for rule, flags in _rules(res, method, cusum).items():
                row = {"seed": seed, "scenario": scen, "method": method, "rule": rule,
                       "K": int(rule[1:]) if rule.startswith("K") else None,
                       "n_affected": len(forged),
                       "false_incidents": sum(1 for term in flags if term != bad_term),
                       **_consequences(res, method, flags, bad_term)}
                if bad_term:
                    t_flag = flags.get(bad_term)
                    detected = t_flag is not None and t_flag >= ATTACK_START
                    t_stop = t_flag if detected else float("inf")
                    row.update({"detected": detected,
                                "hours_to_detect": (t_flag - ATTACK_START) / 60 if detected else None,
                                "forged_before_detect": sum(1 for t in forged.values() if t < t_stop)})
                rows.append(row)
    return rows


def calibrate_cusum(seeds: list[int], p_gen: Params, pP: Params, pB: Params) -> dict:
    """Порог CUSUM подбирается на отдельных чистых сутках так, чтобы частота ложных
    подозрений совпала с правилом K = 3 на тех же сутках (сравнение при равной нагрузке)."""
    params = {"P": pP, "B2": pB}
    days = [_day(s, p_gen, params, ())["none"][0] for s in seeds]
    out = {"k_ref": {}, "h": {}, "p0": {}, "target_false_per_day": {}}
    for method in METHODS_DAY:
        cnt: dict = {}
        for res in days:
            for term, seq in _observations(res, method).items():
                role = term.rsplit("-T", 1)[0]
                a = cnt.setdefault(role, [0, 0])
                a[0] += sum(x for _, x in seq)
                a[1] += len(seq)
        p0 = {r: a[0] / a[1] for r, a in cnt.items()}
        k_ref = {r: cusum_ref(v) for r, v in p0.items()}
        target = float(np.mean([len(_flags_k(_events(res, method), 3)) for res in days]))
        obs = [_observations(res, method) for res in days]
        best = None
        for h in np.arange(0.5, 8.01, 0.05):
            fpd = float(np.mean([len(_flags_cusum(o, k_ref, h)) for o in obs]))
            if fpd <= target + 1e-9:
                best = (round(float(h), 2), fpd)
                break
        out["p0"][method], out["k_ref"][method] = p0, k_ref
        out["h"][method] = best[0] if best else 8.0
        out["target_false_per_day"][method] = {"K3": target, "CUSUM": best[1] if best else None}
    return out


def day_trace(seed: int, scenario: str, p_gen: Params, pP: Params, pB: Params) -> dict:
    """Данные для рисунка: события по терминалам одной роли за одни сутки."""
    params = {"P": pP, "B2": pB}
    res, forged, bad_term = _day(seed, p_gen, params, (scenario,))[scenario]
    role = ATTACK_ROLE.get(scenario, FAULTS.get(scenario))
    out = {"bad_term": bad_term, "forged": sorted(forged.values()), "methods": {}}
    for method in METHODS_DAY:
        ev = [(t, term, k) for t, term, k in _events(res, method) if term.startswith(role + "-T")]
        out["methods"][method] = {"events": ev, "flags": _flags_k(_events(res, method), 3)}
    return out


def run(n_days: int, p_gen: Params, pP: Params, pB: Params, first_seed: int = 1000,
        cusum: dict | None = None) -> list[dict]:
    rows = []
    for d in range(n_days):
        rows += simulate_day(first_seed + d, p_gen, pP, pB, cusum=cusum)
    return rows


def summarize(rows: list[dict]) -> list[dict]:
    out = []
    scen_all = ["none", *ATTACKS, *FAULTS]
    rules = sorted({x["rule"] for x in rows}, key=lambda r: (r == "CUSUM", r))
    for scen in scen_all:
        for method in METHODS_DAY:
            for rule in rules:
                r = [x for x in rows if x["scenario"] == scen and x["method"] == method
                     and x["rule"] == rule]
                if not r:
                    continue
                s = {"scenario": scen, "method": method, "rule": rule, "K": r[0]["K"],
                     "days": len(r),
                     "false_incidents_per_day": float(np.mean([x["false_incidents"] for x in r])),
                     "manual_after_block_mean": float(np.mean([x["manual_after_block"] for x in r]))}
                if scen != "none":
                    det = [x for x in r if x["detected"]]
                    s.update({
                        "affected_per_day": float(np.mean([x["n_affected"] for x in r])),
                        "detected_share": len(det) / len(r),
                        "hours_to_detect_median": float(np.median([x["hours_to_detect"] for x in det]))
                        if det else float("nan"),
                        "forged_before_detect_mean": float(np.mean([x["forged_before_detect"] for x in r])),
                        "false_ready_before_detect_mean": float(np.mean(
                            [x["false_ready_before_detect"] for x in r])),
                        "false_ready_total_mean": float(np.mean([x["false_ready_total"] for x in r])),
                        "prevented_by_block_mean": float(np.mean([x["prevented_by_block"] for x in r])),
                        "retro_detected_mean": float(np.mean([x["retro_detected"] for x in r]))})
                out.append(s)
    return out
