"""Генератор синтетических журналов событий оборотного обслуживания ВС.

Каждый оборот (case) строится в два слоя:
1) «истина» — фактические моменты операций (ground truth), недоступные методам контроля;
2) журнал сообщений, который видит информационная система: ручные отметки исполнителей,
   данные автоматических источников, штатные задержки, исправления и — в части оборотов —
   одно внесённое нарушение достоверности.

Поля с префиксом ``gt_`` — разметка эксперимента; методы контроля их не читают.

Версия 3: типовые длительности операций взяты по модельному сценарию [Головченко,
Асмоловская] как моды распределений; добавлены подтверждение мер безопасности (SAF),
справочные значения рейса (пассажиры по ведомостям, заказ топлива), вид нарушения V7 —
подмена поля, ослабляющего контроль, и генератор по альтернативному графу операций.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .model import (AUTO, END, INTERVAL_OPS, MANUAL, OPERATIONS, SERVICE_OPS, START, SYSTEM,
                    Params, min_duration, precedence)

# Треугольные распределения (min, мода, max), мин. Моды CLN 15, CAT 12, WAT 8, LOD 18 — по
# модельному сценарию [Головченко, Асмоловская]; выгрузки в нём нет (UNL — допущение).
TRI = {"UNL": (7, 10, 15), "CLN": (10, 15, 22), "CAT": (8, 12, 18), "WAT": (5, 8, 12),
       "LOD": (12, 18, 26)}

VIOLATION_TYPES = ["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8"]
VIOLATION_NAMES = {
    "V1": ("Ложное завершение операции", "False completion"),
    "V2": ("Изменение временной метки", "Timestamp tampering"),
    "V3": ("Повтор сообщения", "Message replay"),
    "V4": ("Пропуск сообщения", "Message omission"),
    "V5": ("Нарушение последовательности", "Sequence violation"),
    "V6": ("Согласованная подмена", "Coordinated substitution"),
    "V7": ("Подмена поля, ослабляющего контроль", "Substitution of a rule-relaxing field"),
    "V8": ("Правдоподобная ранняя отметка осведомлённого исполнителя",
           "Plausible early mark by an informed insider"),
}
EARLY_PAIRS = [("CLN", "DEB"), ("BRD", "CLN"), ("BRD", "CAT"), ("LOD", "UNL"), ("BRD", "FUEL")]
EARLY_PAIRS_ALT = [("BRD", "CLN"), ("BRD", "CAT"), ("LOD", "UNL"), ("BRD", "FUEL"), ("BRD", "LOD")]
V7_SUBTYPES = ["V7a", "V7b", "V7c"]   # признак safety; он же с подтверждением; занижение количества


@dataclass
class Case:
    case_id: str
    label: int                       # 0 — штатный оборот, 1 — оборот с нарушением
    vtype: str | None
    subtype: str | None
    features: list[str]
    seats: int
    sched_in: float
    std: float
    auto_avail: dict[str, bool]
    pax_in: int
    pax_out: int
    fuel_kg: float
    safety: bool
    truth: dict[tuple[str, str], float]
    refs: dict = field(default_factory=dict)  # справочные значения рейса из других систем
    messages: list[dict] = field(default_factory=list)
    gt_inj_time: float | None = None
    gt_target: str | None = None
    twin_messages: list[dict] | None = None   # тот же оборот без внесённого нарушения

    def meta(self) -> dict:
        """Сведения, известные системе заранее (план рейса, оснащение стоянки)."""
        return {"case_id": self.case_id, "seats": self.seats, "sched_in": self.sched_in,
                "std": self.std, "auto_avail": dict(self.auto_avail), "refs": dict(self.refs)}


class _Ids:
    def __init__(self, prefix: str):
        self.prefix, self.n = prefix, 0

    def __call__(self) -> str:
        self.n += 1
        return f"{self.prefix}-{self.n:03d}"


def _net_delay(rng: np.random.Generator, p: Params) -> float:
    return float(min(2.0, rng.lognormal(math.log(p.net_delay_median), p.net_delay_sigma)))


def _late_mark(rng: np.random.Generator, p: Params) -> float:
    if rng.random() < p.late_mark_share:
        return float(min(p.late_mark_cap, rng.exponential(p.late_mark_mean)))
    return 0.0


def schedule(rng: np.random.Generator, pax_in: int, pax_out: int, fuel_kg: float,
             mods: dict) -> dict[tuple[str, str], float]:
    """Фактические моменты операций одного оборота (минуты от постановки на стоянку)."""
    T: dict[tuple[str, str], float] = {}
    late_op, late_kind = mods.get("late_op"), mods.get("late_kind")
    early = mods.get("early")          # (succ, pred): нарушение последовательности в «истине»
    safety = mods.get("safety", False)

    def dur(op: str) -> float:
        if op == "DEB":
            d = pax_in / rng.uniform(12, 18)
        elif op == "BRD":
            d = pax_out / rng.uniform(10, 15)
        elif op == "FUEL":
            d = rng.uniform(2, 4) + fuel_kg / rng.uniform(300, 500)
        else:
            d = rng.triangular(*TRI[op])
        if late_op == op and late_kind == "slow":
            d *= rng.uniform(1.8, 3.0)
        return float(d)

    def place(op: str, start: float) -> None:
        if late_op == op and late_kind == "wait":
            start += rng.uniform(5, 20)
        if early is not None and early[0] == op:
            pred = early[1]
            start = max(T[(pred, START)] + 1.0, T[(pred, END)] - mods["early_amount"])
        T[(op, START)] = float(start)
        T[(op, END)] = float(start + dur(op))

    alt = mods.get("gen_model") == "alt"
    T[("ONB", END)] = 0.0
    T[("GPU", START)] = float(rng.uniform(1, 3))
    T[("PBB", START)] = float(rng.uniform(0.5, 2.5))
    place("DEB", T[("PBB", START)] + rng.uniform(0.3, 1.5))
    place("UNL", rng.uniform(1, 4))
    if alt and not mods.get("variant"):           # граф [Головченко]: вода после высадки
        place("WAT", T[("DEB", END)] + rng.uniform(0.5, 3))
    else:                                         # в графе — неучтённый вариант: вода раньше
        place("WAT", rng.uniform(3, 15))
    if alt or mods.get("variant"):
        # граф [Головченко]: уборка после установки трапа, т. е. может идти во время высадки;
        # в основной модели это допустимый, но не отражённый в ней вариант
        T[("CLN", START)] = float(T[("DEB", START)] + rng.uniform(2, 5))
        T[("CLN", END)] = T[("CLN", START)] + dur("CLN")
    else:
        place("CLN", T[("DEB", END)] + rng.uniform(0, 2))
    place("CAT", T[("PBB", START)] + rng.uniform(1, 6))   # после установки трапа
    if safety:
        place("FUEL", max(3.0, T[("DEB", END)] - rng.uniform(0, 5)))
        T[("SAF", END)] = float(max(0.5, T[("FUEL", START)] - rng.uniform(0.5, 3)))
    else:
        place("FUEL", T[("DEB", END)] + rng.uniform(0.5, 3))
    lod_base = T[("UNL", END)] if not alt else max(T[("UNL", END)], T[("DEB", END)])
    place("LOD", lod_base + rng.uniform(0.5, 3))
    brd_base = max(T[("CLN", END)], T[("CAT", END)])
    if alt:                                       # граф [Головченко]: посадка после воды и багажа
        brd_base = max(brd_base, T[("WAT", END)], T[("LOD", END)])
    if not safety:                                # посадка при заправке — только с мерами
        brd_base = max(brd_base, T[("FUEL", END)])  # безопасности (в графе не рассматривается)
    place("BRD", brd_base + rng.uniform(0.5, 3))
    T[("LDS", END)] = float(max(T[("LOD", END)], T[("BRD", END)]) + rng.uniform(0.5, 3))
    T[("DRC", END)] = float(max([T[("LDS", END)]] + [T[(o, END)] for o in SERVICE_OPS])
                            + rng.uniform(0.5, 2))
    T[("PBB", END)] = float(T[("DRC", END)] + rng.uniform(0.5, 2))
    T[("GPU", END)] = float(T[("DRC", END)] + rng.uniform(0.5, 3))
    T[("OFB", END)] = float(max(T[("PBB", END)], T[("GPU", END)]) + rng.uniform(1, 4))
    return T


def _fields(op: str, status: str, kind: str, case: Case) -> dict:
    f = {"pax": None, "fuel_kg": None, "safety": False}
    if status == END and op == "DEB":
        f["pax"] = case.pax_in
    if status == END and op in ("BRD", "LDS"):
        f["pax"] = case.pax_out
    if status == END and op == "FUEL":
        f["fuel_kg"] = round(case.fuel_kg, -1) if kind == MANUAL else round(case.fuel_kg, 0)
    if status == START and op == "FUEL" and kind == MANUAL:
        f["safety"] = case.safety
    return f


def emit_messages(rng: np.random.Generator, case: Case, p: Params, ids: _Ids,
                  terminals: dict[str, str]) -> list[dict]:
    msgs = []
    for (op, status), t in sorted(case.truth.items(), key=lambda kv: kv[1]):
        o = OPERATIONS[op]
        if o.manual_role:
            press = t + _late_mark(rng, p)
            msgs.append({"msg_id": ids(), "op": op, "status": status, "kind": MANUAL,
                         "source": terminals[o.manual_role],
                         "event_time": press + float(rng.normal(0, p.clock_skew_sd)),
                         "recv_time": press + _net_delay(rng, p), "corr_of": None,
                         **_fields(op, status, MANUAL, case),
                         "gt_injected": False, "gt_true_time": t, "gt_note": ""})
        if o.auto_source and case.auto_avail.get(o.auto_source, False):
            kind = SYSTEM if o.auto_source == "DCS" else AUTO
            msgs.append({"msg_id": ids(), "op": op, "status": status, "kind": kind,
                         "source": f"{o.auto_source}-S{case.case_id[-2:]}",
                         "event_time": t + float(rng.normal(0, 0.05)),
                         "recv_time": t + _net_delay(rng, p), "corr_of": None,
                         **_fields(op, status, kind, case),
                         "gt_injected": False, "gt_true_time": t, "gt_note": ""})
    return msgs


def _apply_offline(rng, msgs, case, p) -> None:
    roles = sorted({m["source"] for m in msgs if m["kind"] == MANUAL})
    src = roles[rng.integers(len(roles))]
    t_a = float(rng.uniform(0, case.truth[("OFB", END)] - 5))
    t_b = t_a + float(rng.uniform(*p.offline_range))
    for m in msgs:
        if m["source"] == src and t_a <= m["recv_time"] <= t_b:
            m["recv_time"] = t_b + float(rng.uniform(0.05, 0.5))
    case.features.append(f"offline:{src}")


def _apply_correction(rng, msgs, case, p, ids) -> None:
    cand = [m for m in msgs if m["kind"] == MANUAL and m["corr_of"] is None]
    m = cand[rng.integers(len(cand))]
    correct = m["event_time"]
    err = float(rng.uniform(*p.corr_error_range)) * (1 if rng.random() < 0.5 else -1)
    m["event_time"] = correct + err
    m["gt_note"] = "corrected"
    msgs.append({**m, "msg_id": ids(), "event_time": correct,
                 "recv_time": m["recv_time"] + float(rng.uniform(*p.corr_delay_range)),
                 "corr_of": m["msg_id"], "gt_note": "correction"})
    case.features.append(f"correction:{m['op']}.{m['status']}")


def _eligible(msgs, pred) -> list[dict]:
    return [m for m in msgs if m["corr_of"] is None and m["gt_note"] == "" and pred(m)]


def _forge(m_like: dict, ids: _Ids, event_time: float, recv_time: float, note: str) -> dict:
    return {**m_like, "msg_id": ids(), "event_time": event_time, "recv_time": recv_time,
            "corr_of": None, "gt_injected": True, "gt_true_time": None, "gt_note": note}


def inject(rng, vtype: str, case: Case, msgs: list[dict], p: Params, ids: _Ids,
           terminals: dict[str, str], force: dict | None = None) -> list[dict]:
    """Внести одно нарушение достоверности; вернуть изменённый журнал.

    force — для моделирования компрометации конкретного источника: {"op": операция,
    "subtype": "V1a"|"V1b"} или {"subtype": "V7a"}. Без force выбор случаен (основной
    эксперимент)."""
    T = case.truth

    def manual_msg(op, status):
        c = [m for m in msgs if m["op"] == op and m["status"] == status and m["kind"] == MANUAL
             and m["corr_of"] is None]
        return c[0] if c else None

    if vtype == "V1":                                     # ложное завершение
        cand = [op for op in SERVICE_OPS if T[(op, END)] - T[(op, START)] >= 4.0]
        if force and "op" in force:
            if force["op"] not in cand:                   # подделать нечего: операция слишком коротка
                return msgs
            op = force["op"]
        else:
            op = cand[rng.integers(len(cand))]
        d = T[(op, END)] - T[(op, START)]
        frac = float(rng.uniform(0.25, 0.75))
        if force and "frac" in force:                     # анализ величины нарушения
            frac = force["frac"]
        t_f = min(T[(op, START)] + frac * d, T[(op, END)] - 1.0)
        genuine = manual_msg(op, END)
        forged = _forge(genuine, ids, t_f, t_f + _net_delay(rng, p), "forged_end")
        case.subtype = force["subtype"] if force else ("V1a" if rng.random() < 0.5 else "V1b")
        if case.subtype == "V1b":                         # подлинная отметка подавлена
            msgs = [m for m in msgs if m["msg_id"] != genuine["msg_id"]
                    and m.get("corr_of") != genuine["msg_id"]]
        msgs.append(forged)
        case.gt_target, case.gt_inj_time = op, forged["recv_time"]

    elif vtype == "V2":                                   # изменение временной метки
        cand = _eligible(msgs, lambda m: m["op"] in INTERVAL_OPS)
        m = cand[rng.integers(len(cand))]
        shift = float(rng.uniform(3, 20))
        if force and "shift" in force:
            shift = force["shift"]
        new_t = m["event_time"] + (-shift if m["status"] == END else shift)
        for x in msgs:
            if x["msg_id"] == m["msg_id"]:
                x["event_time"] = new_t
                x["gt_injected"] = True
                x["gt_note"] = f"tampered:{'-' if m['status'] == END else '+'}{shift:.1f}"
        case.subtype = "V2-end" if m["status"] == END else "V2-start"
        case.gt_target, case.gt_inj_time = f"{m['op']}.{m['status']}", m["recv_time"]

    elif vtype == "V3":                                   # повтор сообщения
        t_ofb = T[("OFB", END)]
        cand = _eligible(msgs, lambda m: m["recv_time"] < t_ofb - 2 and m["op"] != "LDS")
        m = cand[rng.integers(len(cand))]
        r = m["recv_time"] + float(rng.uniform(2, 30))
        case.subtype = "V3a" if rng.random() < 0.5 else "V3b"
        et = m["event_time"] if case.subtype == "V3a" else r + float(rng.normal(0, p.clock_skew_sd))
        msgs.append(_forge(m, ids, et, r, "replay"))
        case.gt_target, case.gt_inj_time = f"{m['op']}.{m['status']}", r

    elif vtype == "V4":                                   # пропуск сообщения
        cand = _eligible(msgs, lambda m: m["kind"] == MANUAL and (m["op"] in INTERVAL_OPS
                                                                   or m["op"] == "DRC"))
        m = cand[rng.integers(len(cand))]
        msgs = [x for x in msgs if x["msg_id"] != m["msg_id"]]
        case.subtype = "V4-end" if m["status"] == END else "V4-start"
        case.gt_target, case.gt_inj_time = f"{m['op']}.{m['status']}", m["recv_time"]

    elif vtype == "V5":                                   # нарушение последовательности
        succ, pred = case.gt_target.split("<")
        starts = [m for m in msgs if m["op"] == succ and m["status"] == START]
        if case.subtype == "V5b":                         # порядок искажён в данных
            # величина нарушения — опережение самого позднего из предшествующих событий
            preds = [c.pred for c in precedence(p.gen_model) if c.succ == (succ, START)
                     and not (c.waiver == "safety" and case.safety) and c.pred in T]
            t_ref = max([T[(pred, END)]] + [T[x] for x in preds])
            amount = float(rng.uniform(3, 10)) if not (force and "amount" in force) \
                else force["amount"]
            t_new = max(T[(pred, START)] + 1.0, t_ref - amount)
            for m in starts:
                m["event_time"] = t_new + float(rng.normal(0, 0.05))
                m["gt_injected"], m["gt_note"] = True, "reordered"
        case.gt_inj_time = min(m["recv_time"] for m in starts)

    elif vtype in ("V6", "V8"):
        # V6 — согласованная подмена ручной отметки и счётчика (Н3); V8 — осведомлённый
        # исполнитель: ранняя отметка единственного источника операции, рассчитанная так, чтобы
        # не нарушить известные ему нормы и допуски (подлинной отметки нет)
        if vtype == "V6":
            ops = ["FUEL"]
        else:
            ops = [o for o in SERVICE_OPS if not (o == "FUEL" and case.auto_avail.get("METER"))]
        refs = case.refs
        cand = []
        for op in ops:
            ms = manual_msg(op, START)
            if ms is None:
                continue
            dmin = min_duration(op, refs["pax_in"] if op == "DEB" else refs["pax_out"],
                                refs["fuel"], case.seats, p.min_dur_share)
            t_f = max(ms["event_time"], T[(op, START)]) + dmin + p.dur_tol + 2.0
            if t_f < T[(op, END)] - 1.0:
                cand.append((op, t_f))
        if not cand:                                      # запасной вариант: поздняя подмена
            op = max(ops, key=lambda o: T[(o, END)] - T[(o, START)])
            cand = [(op, T[(op, END)] - 1.0)]
        op, t_f = cand[rng.integers(len(cand))]
        t_f += float(rng.uniform(0.0, 0.5))
        genuine = list({m["msg_id"]: m for m in msgs if m["op"] == op and m["status"] == END
                        and m["corr_of"] is None}.values())
        drop = {m["msg_id"] for m in genuine}
        msgs = [m for m in msgs if m["msg_id"] not in drop and m.get("corr_of") not in drop]
        recv = t_f + _net_delay(rng, p)
        for g in genuine:                                 # подделываются все источники события
            msgs.append(_forge(g, ids, t_f + float(rng.normal(0, 0.05)),
                               recv + float(rng.uniform(0, 0.2)), "forged_consistent"))
        case.subtype = vtype
        case.gt_target, case.gt_inj_time = op, recv

    elif vtype == "V7":                                   # подмена поля, ослабляющего контроль
        if case.subtype in ("V7a", "V7b"):                # ложный признак заправки с пассажирами
            ms = manual_msg("FUEL", START)
            if ms is None:
                return msgs
            for x in msgs:
                if x["op"] == "FUEL" and x["status"] == START and x["kind"] == MANUAL:
                    x["safety"], x["gt_injected"], x["gt_note"] = True, True, "forged_safety_flag"
            case.gt_target, case.gt_inj_time = "FUEL.safety", ms["recv_time"]
            if case.subtype == "V7b":                     # и подложное подтверждение с другого места
                t_c = max(0.5, ms["event_time"] - float(rng.uniform(0.5, 3)))
                tmpl = {"op": "SAF", "status": END, "kind": MANUAL,
                        "source": terminals["SUPV"], "pax": None, "fuel_kg": None,
                        "safety": False, "case_id": case.case_id}
                f = _forge(tmpl, ids, t_c, ms["recv_time"] + float(rng.uniform(0, 0.3)),
                           "forged_confirmation")
                msgs.append(f)
        else:                                             # V7c: занижено количество в отметке
            cand = [op for op in ("DEB", "BRD", "FUEL") if T[(op, END)] - T[(op, START)] >= 4.0
                    and manual_msg(op, START) is not None and manual_msg(op, END) is not None]
            if not cand:
                return msgs
            op = cand[rng.integers(len(cand))]
            d = T[(op, END)] - T[(op, START)]
            t_f = min(T[(op, START)] + float(rng.uniform(0.25, 0.6)) * d, T[(op, END)] - 2.0)
            s_obs = manual_msg(op, START)["event_time"]
            genuine = manual_msg(op, END)
            forged = _forge(genuine, ids, t_f, t_f + _net_delay(rng, p), "forged_end_low_qty")
            span = max(0.0, t_f - s_obs - 0.5)          # нарушитель знает норму и подгоняет поле
            if op == "FUEL":
                forged["fuel_kg"] = float(max(0.0, round((span - 1.0) * 1000.0, -1)))
            else:
                rate = 25.0 if op == "DEB" else 18.0
                forged["pax"] = int(max(1, min(genuine["pax"], math.floor(span * rate))))
            msgs = [m for m in msgs if m["msg_id"] != genuine["msg_id"]
                    and m.get("corr_of") != genuine["msg_id"]]
            msgs.append(forged)
            case.gt_target, case.gt_inj_time = op, forged["recv_time"]
    return msgs


def _apply_retries(rng, msgs, p) -> list[dict]:
    extra = [{**m, "recv_time": m["recv_time"] + float(rng.uniform(0.1, 2.0)), "gt_note":
              (m["gt_note"] + " retry").strip()}
             for m in msgs if not m["gt_injected"] and rng.random() < p.retry_share]
    return msgs + extra


def _build(rng: np.random.Generator, case_id: str, vtype: str | None, p: Params,
           violate: bool, force: dict | None = None) -> Case:
    """Построить оборот. При violate=False нарушение не вносится, а все случайные
    величины берутся в том же порядке — так получается «двойник» оборота."""
    seats = int(rng.choice(p.seats))
    pax_in = int(rng.binomial(seats, rng.uniform(0.6, 0.98)))
    pax_out = int(rng.binomial(seats, rng.uniform(0.6, 0.98)))
    fuel_kg = float(rng.uniform(2500, 8000))
    refs = {"pax_in": pax_in,                                  # ведомость прилетевшего рейса
            "pax_out": min(seats, pax_out + int(rng.integers(0, 3))),   # зарегистрировано (DCS)
            "fuel": float(round(fuel_kg * rng.uniform(0.97, 1.03), -2))}  # заказ на заправку
    features: list[str] = []
    safety = bool(rng.random() < p.p_safety_fuelling)
    subtype = target = None
    u7 = int(rng.integers(len(V7_SUBTYPES)))            # тянется всегда: общие случайные числа
    if vtype == "V7":
        subtype = force["subtype"] if force and "subtype" in force else V7_SUBTYPES[u7]
        if subtype in ("V7a", "V7b"):                  # в действительности мер безопасности нет
            safety = False
    if safety:
        features.append("safety_fuelling")
    mods: dict = {"safety": safety, "gen_model": p.gen_model}
    if rng.random() < p.p_operational_delay:
        mods["late_op"] = str(rng.choice(["CAT", "CLN", "FUEL", "LOD", "BRD", "UNL"]))
        mods["late_kind"] = str(rng.choice(["slow", "wait"]))
        features.append(f"op_delay:{mods['late_op']}:{mods['late_kind']}")
    if rng.random() < p.p_unmodeled_variant:
        mods["variant"] = True
        features.append("unmodeled_variant:" + ("WAT_before_DEB_end" if p.gen_model == "alt"
                                                 else "CLN_during_DEB"))
    if vtype == "V5":
        pairs = [pr for pr in (EARLY_PAIRS if p.gen_model != "alt" else EARLY_PAIRS_ALT)
                 if not (safety and pr == ("BRD", "FUEL"))]
        pair = pairs[rng.integers(len(pairs))]
        target = f"{pair[0]}<{pair[1]}"
        subtype = "V5a" if rng.random() < 0.5 else "V5b"
        mods["early_amount"] = float(rng.uniform(3, 10))
        if force and "amount" in force:
            subtype, mods["early_amount"] = "V5b", force["amount"]
        if subtype == "V5a" and violate:                  # фактическое нарушение технологии
            mods["early"] = pair
    truth = schedule(rng, pax_in, pax_out, fuel_kg, mods)
    sched_in = float(-rng.normal(5, 10))
    auto_avail = {o.auto_source: bool(rng.random() < o.auto_availability)
                  for o in OPERATIONS.values() if o.auto_source}
    if vtype == "V6":                       # согласованная подмена — при наличии счётчика
        auto_avail["METER"] = True
    case = Case(case_id, int(vtype is not None), vtype, subtype, features, seats, sched_in,
                sched_in + p.planned_turnaround, auto_avail, pax_in, pax_out, fuel_kg, safety,
                truth, refs=refs, gt_target=target)
    ids = _Ids(case_id)
    terminals = {r: f"{r}-T{int(rng.integers(1, 40)):02d}"
                 for r in sorted({o.manual_role for o in OPERATIONS.values() if o.manual_role})}
    msgs = emit_messages(rng, case, p, ids, terminals)
    if rng.random() < p.p_offline:
        _apply_offline(rng, msgs, case, p)
    if rng.random() < p.p_correction:
        _apply_correction(rng, msgs, case, p, ids)
    msgs = _apply_retries(rng, msgs, p)
    if vtype is not None and violate:
        msgs = inject(rng, vtype, case, msgs, p, ids, terminals, force)
    msgs.sort(key=lambda m: (m["recv_time"], m["msg_id"]))
    for m in msgs:
        m["case_id"] = case_id
    case.messages = msgs
    return case


def generate_case(rng: np.random.Generator, case_id: str, vtype: str | None,
                  p: Params, force: dict | None = None) -> Case:
    state = rng.bit_generator.state
    case = _build(rng, case_id, vtype, p, violate=True, force=force)
    if vtype is not None:
        twin_rng = np.random.default_rng()
        twin_rng.bit_generator.state = state
        case.twin_messages = _build(twin_rng, case_id, vtype, p, violate=False,
                                    force=force).messages
    return case


def generate_dataset(seed: int, n_normal: int, n_per_type: int, p: Params,
                     types: list[str] = VIOLATION_TYPES) -> list[Case]:
    rng = np.random.default_rng(seed)
    plan = [None] * n_normal + [t for t in types for _ in range(n_per_type)]
    return [generate_case(rng, f"S{seed:02d}-C{i:05d}", vt, p) for i, vt in enumerate(plan)]
