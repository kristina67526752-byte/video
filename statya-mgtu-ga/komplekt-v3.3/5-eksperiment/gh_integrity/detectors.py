"""Методы контроля достоверности журнала событий наземного обслуживания.

Работают в потоковом режиме: сообщения обрабатываются в порядке получения, после каждого
сообщения вычисляется множество несоответствий. Несоответствие становится тревогой, если
не устранено за время ожидания: W — для противоречий (успевает прийти исправление),
H — для неполноты (успевает прийти задержанное сообщение). Пока есть хотя бы одно
несоответствие, решения о готовности ВС по данным не принимаются автоматически.

Группы правил:
  F  — проверка полей отдельного сообщения (базовый метод Б1);
  T  — проверка временных меток (вместе с F — базовый метод Б2);
  R1 — технологическая последовательность и полнота;
  R2 — минимальная технологическая длительность;
  R3 — согласованность статусов: повторы, «завершение без начала», события после буксировки;
  R4 — согласованность независимых источников (ручная отметка, оборудование, DCS).

Версия 3 (модель доверия). Поля, ослабляющие контроль, не берутся у проверяемого источника:
исключение при заправке с пассажирами снимает зависимости только при подтверждении мер
безопасности с другого рабочего места (SAF), нормы длительности рассчитываются по
справочным значениям рейса, а количества в отметках сверяются с этими значениями.
Параметры safety_trust="manual", trusted_norms=False воспроизводят версию 2.

Метод Б3 — монитор декларативных ограничений с семантикой RV-LTL (как в мониторинге
Declare/MP-Declare): те же ограничения R1–R4 и проверка полей F; нарушение сообщается, если
сохраняется β мин (аналог буфера переупорядочивания для запоздавших событий); решение не
принимается при нарушении, но ожидаемые (ещё не выполненные) обязательства, например
подтверждение оборудованием, его не задерживают; модель доверия не применяется.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .model import (AUTO, CROSS_EVENTS, D2_EVENTS, END, INTERVAL_OPS, MANUAL, OPERATIONS,
                    SERVICE_OPS, START, Params, d1_preds, min_duration, precedence)

GROUPS = ("F", "T", "R1", "R2", "R3", "R4")
METHODS: dict[str, frozenset[str]] = {
    "B1": frozenset({"F"}),
    "B2": frozenset({"F", "T"}),
    "P": frozenset(GROUPS),
    "P-T": frozenset(GROUPS) - {"T"},
    "P-R1": frozenset(GROUPS) - {"R1"},
    "P-R2": frozenset(GROUPS) - {"R2"},
    "P-R3": frozenset(GROUPS) - {"R3"},
    "P-R4": frozenset(GROUPS) - {"R4"},
    "B3": frozenset({"F", "T", "R1", "R2", "R3", "R4"}),
}
MODE = {"B3": "RV"}                       # остальные методы — режим "P"
INCOMPLETE = {("R1", "miss"), ("R3", "nostart"), ("R4", "missing")}
PENDING_RV = {("R4", "missing")}          # в RV-LTL — «текущее» нарушение (обязательство не
                                          # выполнено), постоянным становится в конце оборота


@dataclass(frozen=True)
class Step:
    time: float
    keys: frozenset
    d1: bool
    d2: bool


def _inconsistencies(meta: dict, msgs: dict, eff: dict, bad_corr: set, p: Params):
    keys: set = set(bad_corr)
    seats = meta["seats"]
    lo, hi = meta["sched_in"] - p.window_before, meta["std"] + p.window_after
    ev: dict = defaultdict(list)
    for mid, m in msgs.items():
        t = eff[mid]
        bad = False
        if not (lo <= t <= hi):
            keys.add(("F", "window", mid)); bad = True
        if m["pax"] is not None and not (0 <= m["pax"] <= seats):
            keys.add(("F", "range", mid)); bad = True
        if m["fuel_kg"] is not None and not (0 <= m["fuel_kg"] <= p.fuel_capacity_kg):
            keys.add(("F", "range", mid)); bad = True
        if bad:
            continue                       # сообщение не принимается в состояние оборота
        if t > m["recv_time"] + p.future_tol:
            keys.add(("T", "future", mid))
        if m["recv_time"] - t > p.stale_max:
            keys.add(("T", "stale", mid))
        ev[(m["op"], m["status"])].append((t, m["kind"], m))
    first = {e: min(x[0] for x in lst) for e, lst in ev.items()}
    claimed = any(m["safety"] for _, k, m in ev.get(("FUEL", START), []) if k == MANUAL)
    confirmed = ("SAF", END) in first
    if p.safety_trust == "confirmed":
        in_time = confirmed and (("FUEL", START) not in first
                                 or first[("SAF", END)] <= first[("FUEL", START)] + p.prec_tol)
        safety = claimed and in_time
        if claimed and not confirmed and ("FUEL", START) in first:
            # подтверждения нет: противоречие (ожидание W — подтверждение может запоздать)
            keys.add(("R1", "unconfirmed", ("SAF", END), ("FUEL", START)))
        elif claimed and confirmed and not in_time:
            # с версии 3.3: подтверждение позже начала заправки исключения не даёт
            keys.add(("R1", "order", ("SAF", END), ("FUEL", START)))
    else:                                 # версия 2: доверие признаку в отметке заправщика
        safety = claimed

    for op in INTERVAL_OPS:                                    # T: END не раньше START
        s, e = first.get((op, START)), first.get((op, END))
        if s is not None and e is not None and e < s - p.order_tol:
            keys.add(("T", "order", op))

    for c in precedence(p.ctrl_model):                         # R1
        if c.succ not in first or (c.waiver == "safety" and safety):
            continue
        if c.pred not in first:
            keys.add(("R1", "miss", c.pred, c.succ))
        elif first[c.pred] > first[c.succ] + p.prec_tol:
            keys.add(("R1", "order", c.pred, c.succ))

    refs = meta.get("refs", {})
    for op in SERVICE_OPS:                                     # R2
        s, e = first.get((op, START)), first.get((op, END))
        if s is None or e is None:
            continue
        pax = next((m["pax"] for _, _, m in ev[(op, END)] if m["pax"] is not None), None)
        fuel = next((m["fuel_kg"] for _, _, m in ev[(op, END)] if m["fuel_kg"] is not None), None)
        if p.trusted_norms and refs:          # норма — по справочным значениям, а не по отметке
            pax = refs["pax_in"] if op == "DEB" else refs["pax_out"] if op == "BRD" else pax
            fuel = 0.95 * refs["fuel"] if op == "FUEL" else fuel
        if e - s < min_duration(op, pax, fuel, seats, p.min_dur_share) - p.dur_tol:
            keys.add(("R2", "short", op))

    per_kind: dict = defaultdict(set)                          # R3
    for (op, status), lst in ev.items():
        for _, kind, m in lst:
            per_kind[(op, status, kind)].add(m["msg_id"])
    for (op, status, kind), ids in per_kind.items():
        if len(ids) > 1:
            keys.add(("R3", "dup", op, status, kind))
    for op in INTERVAL_OPS:
        if (op, END) in first and (op, START) not in first:
            keys.add(("R3", "nostart", op))
    if ("OFB", END) in first:
        t_ofb = first[("OFB", END)]
        for (op, status), lst in ev.items():
            if (op, status) == ("OFB", END):
                continue
            for t, _, m in lst:
                if t > t_ofb + p.prec_tol:
                    keys.add(("R3", "after", m["msg_id"]))

    for e in CROSS_EVENTS:                                     # R4
        if not meta["auto_avail"].get(OPERATIONS[e[0]].auto_source, False):
            continue
        man = [t for t, k, _ in ev.get(e, []) if k == MANUAL]
        aut = [t for t, k, _ in ev.get(e, []) if k == AUTO]
        if man and aut:
            if abs(min(man) - min(aut)) > p.cross_tol:
                keys.add(("R4", "time", *e))
        elif man or aut:
            keys.add(("R4", "missing", *e))
    fe = ev.get(("FUEL", END), [])
    fm = [m["fuel_kg"] for _, k, m in fe if k == MANUAL and m["fuel_kg"] is not None]
    fa = [m["fuel_kg"] for _, k, m in fe if k == AUTO and m["fuel_kg"] is not None]
    if fm and fa and abs(fm[0] - fa[0]) > p.fuel_rel_tol * fa[0]:
        keys.add(("R4", "qty", "FUEL"))
    bp = [m["pax"] for _, _, m in ev.get(("BRD", END), []) if m["pax"] is not None]
    lp = [m["pax"] for _, _, m in ev.get(("LDS", END), []) if m["pax"] is not None]
    if bp and lp and bp[0] != lp[0]:
        keys.add(("R4", "pax", "BRD-LDS"))
    if p.trusted_norms and refs:          # количества в отметках — со справочными значениями
        dp = [m["pax"] for _, k, m in ev.get(("DEB", END), []) if k == MANUAL and m["pax"] is not None]
        if dp and dp[0] != refs["pax_in"]:
            keys.add(("R4", "ref", "DEB"))
        if bp and bp[0] > refs["pax_out"]:
            keys.add(("R4", "ref", "BRD"))
        if fm and abs(fm[0] - refs["fuel"]) > 0.05 * refs["fuel"]:
            keys.add(("R4", "ref", "FUEL"))

    d1 = all((op, END) in first or (waived and safety) for op, waived in d1_preds(p.ctrl_model))
    d2 = all(e in first for e in D2_EVENTS)
    return frozenset(keys), d1, d2


def evaluate_case(meta: dict, messages: list[dict], p: Params) -> list[Step]:
    """Последовательность состояний контроля после каждого нового сообщения."""
    msgs: dict = {}
    eff: dict = {}
    pending_corr: dict = {}
    bad_corr: set = set()
    seen: set = set()
    steps: list[Step] = []

    def apply(orig: dict, corr: dict) -> None:
        same = (orig["op"], orig["status"], orig["source"]) == (corr["op"], corr["status"],
                                                                 corr["source"])
        if same:
            eff[orig["msg_id"]] = corr["event_time"]
        else:
            bad_corr.add(("R3", "badcorr", corr["msg_id"]))

    for m in sorted(messages, key=lambda x: (x["recv_time"], x["msg_id"])):
        if m["msg_id"] in seen:            # повторная доставка того же сообщения
            continue
        seen.add(m["msg_id"])
        if m["corr_of"] is not None:
            if m["corr_of"] in msgs:
                apply(msgs[m["corr_of"]], m)
            else:
                pending_corr[m["corr_of"]] = m
        else:
            msgs[m["msg_id"]] = m
            eff[m["msg_id"]] = m["event_time"]
            if m["msg_id"] in pending_corr:
                apply(m, pending_corr.pop(m["msg_id"]))
        keys, d1, d2 = _inconsistencies(meta, msgs, eff, bad_corr, p)
        steps.append(Step(m["recv_time"], keys, d1, d2))
    return steps


def _grace(key, W: float, H: float, mode: str = "P") -> float:
    """Время ожидания до тревоги. В режиме RV (Б3) W = H = β — буфер переупорядочивания,
    а ожидаемые обязательства становятся нарушением только в конце оборота (inf)."""
    if mode == "RV":
        return float("inf") if key[:2] in PENDING_RV else W
    return H if key[:2] in INCOMPLETE else W


def alarm_keys(steps: list[Step], groups: frozenset, W: float, H: float,
               mode: str = "P") -> set:
    """Ключи несоответствий, ставших тревогами (для «двойника» оборота)."""
    return {k for _, k in _alarms(steps, groups, W, H, mode)[0]}


def _alarms(steps: list[Step], groups: frozenset, W: float, H: float, mode: str = "P"):
    times = [s.time for s in steps] + [float("inf")]
    t_end = steps[-1].time if steps else 0.0
    filt = [frozenset(k for k in s.keys if k[0] in groups) for s in steps]
    alarms: list[tuple[float, tuple]] = []
    active: dict = {}
    for i, ks in enumerate(filt):
        for k in ks:
            active.setdefault(k, times[i])
        for k in [k for k in active if k not in ks]:
            start = active.pop(k)
            g = _grace(k, W, H, mode)
            if times[i] - start > g or g == 0:
                alarms.append((start + g, k))
    for k, start in active.items():                     # не устранено до конца наблюдения
        g = _grace(k, W, H, mode)
        alarms.append((start + g if g != float("inf") else max(t_end, start), k))
    alarms.sort()
    return alarms, filt


def derive(steps: list[Step], groups: frozenset, W: float, H: float,
           inj_time: float | None, true_d1: float, true_d2: float,
           twin_keys: set | frozenset = frozenset(), mode: str = "P",
           check_time: float = 3.0) -> dict:
    """Тревоги и решения о готовности для заданного метода (набора групп правил).

    Обнаружением нарушения считается тревога, выданная не раньше момента его внесения
    и отсутствующая у «двойника» — того же оборота без нарушения (twin_keys).

    Решение D принимается автоматически в момент T_D, когда выполнено условие D и нет
    несоответствий (режим P) или нет нарушений, кроме ожидаемых обязательств (режим RV).
    Если до этого момента выдана тревога, решение принимается после ручной проверки:
    проверяющий подтверждает фактическое состояние, поэтому T_D = max(тревога, факт) + check_time.
    Возвращаются исход, момент решения и задержка относительно фактической готовности."""
    alarms, filt = _alarms(steps, groups, W, H, mode)
    first_alarm = alarms[0][0] if alarms else None
    attributable = [a for a in alarms if inj_time is not None and a[0] >= inj_time - 1e-9
                    and a[1] not in twin_keys]
    out = {"n_alarms": len(alarms), "first_alarm": first_alarm,
           "first_key": alarms[0][1] if alarms else None,
           "detect_time": attributable[0][0] if attributable else None,
           "detect_key": attributable[0][1] if attributable else None}
    if mode == "RV":
        blocking = [frozenset(k for k in ks if k[:2] not in PENDING_RV) for ks in filt]
    else:
        blocking = filt
    for name, cond_attr, true_t in (("d1", "d1", true_d1), ("d2", "d2", true_d2)):
        t_cond = next((s.time for s in steps if getattr(s, cond_attr)), None)
        t_auto = next((steps[i].time for i in range(len(steps))
                       if getattr(steps[i], cond_attr) and not blocking[i]), None)
        if first_alarm is not None and (t_auto is None or first_alarm <= t_auto):
            outcome = "manual"         # решение после ручной проверки по тревоге
            t_dec = max(first_alarm, true_t) + check_time
        elif t_auto is None:
            outcome, t_dec = "none", None   # данных для решения так и не стало
        elif t_auto < true_t - 1e-9:
            outcome, t_dec = "false", t_auto   # готовность объявлена раньше фактической
        else:
            outcome, t_dec = "ok", t_auto
        out[f"{name}_outcome"] = outcome
        out[f"{name}_cond"] = t_cond               # когда условие выполнено по данным
        out[f"{name}_time"] = t_dec
        out[f"{name}_delay"] = (t_dec - true_t) if t_dec is not None else None
        out[f"{name}_hold"] = (t_auto - t_cond) if (t_auto is not None and t_cond is not None
                                                   and outcome == "ok") else None
    return out
