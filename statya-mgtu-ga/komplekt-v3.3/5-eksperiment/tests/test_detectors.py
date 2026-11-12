import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gh_integrity.detectors import METHODS, alarm_keys, derive, evaluate_case  # noqa: E402
from gh_integrity.evaluate import true_readiness  # noqa: E402
from gh_integrity.model import END, Params  # noqa: E402
from gh_integrity.simulate import generate_case, generate_dataset  # noqa: E402

QUIET = replace(Params(), late_mark_share=0.0, p_offline=0.0, p_correction=0.0, retry_share=0.0,
                p_operational_delay=0.0, p_safety_fuelling=0.0, p_unmodeled_variant=0.0)


def _run(case, p, method="P"):
    from gh_integrity.detectors import MODE
    mode = MODE.get(method, "P")
    steps = evaluate_case(case.meta(), case.messages, p)
    twin = evaluate_case(case.meta(), case.twin_messages, p) if case.twin_messages else None
    tk = (alarm_keys(twin, METHODS[method], p.grace, p.missing_horizon, mode) if twin
          else frozenset())
    return derive(steps, METHODS[method], p.grace, p.missing_horizon, case.gt_inj_time,
                  *true_readiness(case), tk, mode)


def test_clean_cases_raise_no_alarms():
    rng = np.random.default_rng(7)
    for i in range(50):
        c = generate_case(rng, f"T-{i}", None, QUIET)
        assert _run(c, QUIET)["n_alarms"] == 0


def test_false_completion_with_late_genuine_mark_is_detected_by_P_only():
    rng = np.random.default_rng(11)
    found = 0
    for i in range(40):
        c = generate_case(rng, f"T-{i}", "V1", QUIET)
        if c.subtype != "V1a":
            continue
        found += 1
        assert _run(c, QUIET)["detect_time"] is not None
        assert _run(c, QUIET, "B1")["detect_time"] is None
    assert found > 5


def test_coordinated_substitution_is_not_detected():
    rng = np.random.default_rng(13)
    for i in range(30):
        c = generate_case(rng, f"T-{i}", "V6", QUIET)
        assert _run(c, QUIET)["detect_time"] is None


def test_correction_within_grace_window_is_not_an_alarm():
    rng = np.random.default_rng(3)
    c = generate_case(rng, "T-0", None, QUIET)
    msgs = [dict(m) for m in c.messages]
    m = next(x for x in msgs if x["op"] == "CLN" and x["status"] == END)
    correct = m["event_time"]
    m["event_time"] = correct + 20.0                       # ошибка ввода «в будущее»
    msgs.append({**m, "msg_id": "fix-1", "corr_of": m["msg_id"], "event_time": correct,
                 "recv_time": m["recv_time"] + 2.0})
    steps = evaluate_case(c.meta(), msgs, QUIET)
    o = derive(steps, METHODS["P"], 5.0, 15.0, None, *true_readiness(c))
    assert o["n_alarms"] == 0
    o0 = derive(steps, METHODS["P"], 0.0, 15.0, None, *true_readiness(c))
    assert o0["n_alarms"] > 0                              # без окна ожидания — тревога


def test_generation_is_deterministic():
    a = generate_dataset(5, 20, 3, Params())
    b = generate_dataset(5, 20, 3, Params())
    assert [m for c in a for m in c.messages] == [m for c in b for m in c.messages]


def test_twin_differs_only_by_injected_messages():
    rng = np.random.default_rng(17)
    c = generate_case(rng, "T-0", "V4", Params())
    ids = {m["msg_id"] for m in c.messages}
    twin_ids = {m["msg_id"] for m in c.twin_messages}
    assert ids < twin_ids                                   # пропуск: одно сообщение удалено
    assert len({m["msg_id"] for m in c.twin_messages if m["msg_id"] not in ids}) == 1


def test_compromised_terminal_campaign_runs_and_attributes_alarms():
    from gh_integrity import campaign as C
    from gh_integrity.model import MANUAL
    p = Params()
    pB = replace(p, safety_trust="manual", trusted_norms=False)
    rows = C.simulate_day(7, p, p, pB)
    scen = {r["scenario"] for r in rows}
    assert scen == {"none", "FUEL", "CLEAN", "GATE", "SAFETY", "GATE_QUIET", "CLOCK", "NET", "METER"}
    fuel = [r for r in rows if r["scenario"] == "FUEL" and r["method"] == "P" and r["rule"] == "K3"][0]
    assert fuel["n_affected"] > 0
    for r in rows:                              # ущерб до подозрения не больше общего
        assert r["false_ready_before_detect"] + r["prevented_by_block"] == r["false_ready_total"]
    msg = {"msg_id": "x", "kind": MANUAL, "source": "FUEL-T03"}
    assign = {r: 1 for r in C.POOLS}
    assert C.key_terminals(("R2", "short", "FUEL"), {}, assign) == {"FUEL-T01"}
    assert C.key_terminals(("T", "stale", "x"), {"x": msg}, assign) == {"FUEL-T03"}
    # неподтверждённый признак safety относится к заправщику, а не к подтверждающему
    assert C.key_terminals(("R1", "unconfirmed", ("SAF", END), ("FUEL", "START")), {}, assign) == {"FUEL-T01"}


def _bypass_case():
    """Контрольный опыт рецензии 08.11.2026: оборот без штатных отклонений, мер безопасности
    нет, в отметке начала заправки изменён только признак safety; счётчик не подменён."""
    from gh_integrity.model import MANUAL, START
    from gh_integrity.run import bypass_case
    c = bypass_case(QUIET)
    msgs = [dict(m) for m in c.messages]
    for m in msgs:
        if m["op"] == "FUEL" and m["status"] == START and m["kind"] == MANUAL:
            m["safety"] = True
    return c, msgs


def test_safety_flag_bypass_reproduced_in_v2_and_closed_in_v3():
    c, msgs = _bypass_case()
    assert not c.safety and c.auto_avail["METER"]
    d1, d2 = true_readiness(c)
    p2 = replace(QUIET, safety_trust="manual", trusted_norms=False)
    o2 = derive(evaluate_case(c.meta(), msgs, p2), METHODS["P"], 5, 15, 0.0, d1, d2)
    assert o2["d1_outcome"] == "false" and o2["n_alarms"] == 0          # обход версии 2
    o3 = derive(evaluate_case(c.meta(), msgs, QUIET), METHODS["P"], 5, 15, 0.0, d1, d2)
    assert o3["d1_outcome"] != "false" and o3["n_alarms"] > 0           # исправлено
    assert o3["first_key"][:3] == ("R1", "unconfirmed", ("SAF", END))
    assert o3["d1_delay"] <= QUIET.check_time + 1e-9     # решение — после проверки, без простоя


def test_quantity_understatement_is_caught_only_with_trusted_norms():
    rng = np.random.default_rng(21)
    p2 = replace(QUIET, safety_trust="manual", trusted_norms=False)
    n = det2 = det3 = 0
    for i in range(80):
        c = generate_case(rng, f"T-{i}", "V7", QUIET)
        if c.subtype != "V7c" or c.gt_target != "DEB":
            continue
        n += 1
        det2 += _run(c, p2)["detect_time"] is not None
        det3 += _run(c, QUIET)["detect_time"] is not None
    assert n >= 3 and det3 == n and det2 < n


def test_rv_monitor_does_not_hold_decision_for_pending_confirmation():
    from gh_integrity.detectors import PENDING_RV
    assert ("R4", "missing") in PENDING_RV
    rng = np.random.default_rng(5)
    for i in range(30):
        c = generate_case(rng, f"T-{i}", None, QUIET)
        o = _run(c, QUIET, "B3")
        assert o["n_alarms"] == 0 or o["first_key"][:2] == ("R4", "missing")


def test_d1_follows_process_model():
    """Версия 3.3: готовность к посадке — после всех операций, предшествующих посадке по модели."""
    from gh_integrity.model import d1_preds
    assert {op for op, _ in d1_preds("alt")} == {"CLN", "CAT", "FUEL", "WAT", "LOD"}
    assert {op for op, _ in d1_preds("base")} == {"CLN", "CAT", "FUEL"}
    for c in generate_dataset(3, 50, 0, QUIET):
        d1, _ = true_readiness(c)
        assert d1 >= max(c.truth[("LOD", END)], c.truth[("WAT", END)]) - 1e-9
        assert d1 <= c.truth[("BRD", "START")] + 1e-9      # посадка не раньше готовности


def test_late_safety_confirmation_gives_alarm():
    """Подтверждение SAF, пришедшее после начала заправки, исключения не даёт."""
    from gh_integrity.model import START
    p = replace(QUIET, p_safety_fuelling=1.0)
    c = generate_dataset(5, 1, 0, p)[0]
    assert c.safety
    msgs = [dict(m) for m in c.messages]
    t_start = c.truth[("FUEL", START)]
    for m in msgs:
        if m["op"] == "SAF":
            m["event_time"] = t_start + 4.0
            m["recv_time"] = t_start + 4.1
    d1, d2 = true_readiness(c)
    o = derive(evaluate_case(c.meta(), sorted(msgs, key=lambda m: m["recv_time"]), p),
               METHODS["P"], 5, 15, None, d1, d2)
    assert o["n_alarms"] > 0


def test_subtype_groups_partition_and_by_construction_detected():
    """Группы «по построению / содержательные / вне возможностей» покрывают все подвиды, а
    обнаружение по построению у П действительно полное (на малой выборке без отклонений)."""
    from gh_integrity.run import BY_CONSTRUCTION, OUT_OF_REACH, group_of
    from gh_integrity.simulate import VIOLATION_TYPES
    assert not BY_CONSTRUCTION & OUT_OF_REACH
    cs = generate_dataset(11, 0, 15, QUIET, VIOLATION_TYPES)
    seen = set()
    for c in cs:
        if c.gt_inj_time is None or c.subtype == "V5a":
            continue
        x = {"subtype": c.subtype or "", "vtype": c.vtype}
        seen.add(group_of(x))
        if group_of(x) == "construct":
            steps = evaluate_case(c.meta(), c.messages, QUIET)
            twin = evaluate_case(c.meta(), c.twin_messages, QUIET)
            tk = alarm_keys(twin, METHODS["P"], 5, 15)
            o = derive(steps, METHODS["P"], 5, 15, c.gt_inj_time, *true_readiness(c), tk)
            assert o["detect_time"] is not None, c.subtype
    assert seen == {"construct", "subst", "reach"}
