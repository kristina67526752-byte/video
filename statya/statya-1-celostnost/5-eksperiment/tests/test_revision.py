"""Тесты дополнений версии 3.7: допуск часов без разметки, вариант формулы (2),
смещение часов терминала, инструмент для журналов эксплуатации."""
from dataclasses import replace

from gh_integrity.detectors import METHODS
from gh_integrity.evaluate import estimate_clock_tol, run_methods
from gh_integrity.model import Params
from gh_integrity.simulate import generate_dataset

P = replace(Params(), prec_tol=8, dur_tol=4, cross_tol=8, stale_max=30, grace=15,
            missing_horizon=45)


def test_default_generator_unchanged_by_offset_option():
    a = generate_dataset(3, 5, 1, Params())
    b = generate_dataset(3, 5, 1, replace(Params(), clock_offset_max=0.0))
    assert [m["event_time"] for c in a for m in c.messages] == \
        [m["event_time"] for c in b for m in c.messages]


def test_clock_tol_robust_to_entry_errors_and_scales_with_offset():
    base = estimate_clock_tol(generate_dataset(950, 200, 0, Params()))
    off = estimate_clock_tol(generate_dataset(950, 200, 0, replace(Params(), clock_offset_max=2.0)))
    assert 0.5 <= base < 1.0            # ошибки ввода на 5–30 мин не завышают оценку
    assert off > 2.0                    # смещение до ±2 мин покрывается допуском


def test_estimated_clock_tol_restores_false_alarm_rate():
    gen = replace(Params(), clock_offset_max=2.0)
    cs = generate_dataset(951, 200, 0, gen)
    tol = estimate_clock_tol(generate_dataset(952, 200, 0, gen))
    fixed = run_methods(cs, replace(P, clock_offset_max=2.0), {"P": METHODS["P"]})
    est = run_methods(cs, replace(P, clock_offset_max=2.0, future_tol=tol, order_tol=tol),
                      {"P": METHODS["P"]})
    fpr = lambda rr: sum(x["n_alarms"] > 0 for x in rr) / len(rr)  # noqa: E731
    assert fpr(fixed) > 0.5 and fpr(est) < 0.1


def test_time_rule_auto_first_runs_and_keeps_alarm_rate():
    cs = generate_dataset(5, 100, 0, Params())
    a = run_methods(cs, P, {"P": METHODS["P"]})
    b = run_methods(cs, replace(P, time_rule="auto_first"), {"P": METHODS["P"]})
    assert abs(sum(x["n_alarms"] > 0 for x in a) - sum(x["n_alarms"] > 0 for x in b)) <= 3


def test_real_log_demo_matches_direct_run(tmp_path):
    import json
    from gh_integrity import real_log as RL
    lp, tp, cp = RL._demo(tmp_path)
    turns, skipped = RL.load(lp, tp, json.loads(cp.read_text()))
    assert not skipped and len(turns) == 600
    rep, _ = RL.analyse(turns[:150], clock_tol=0.5)
    cs = generate_dataset(1, 600, 0, Params())[:150]
    direct = run_methods(cs, RL.calibrated_params()["P"], {"P": METHODS["P"]})
    assert rep["alarm_share"]["П"]["value"] == sum(x["n_alarms"] > 0 for x in direct) / 150
