"""Рисунки статьи: оттенки серого, подписи на русском и английском языках.

Каждый рисунок сохраняется отдельно в PDF (вектор), PNG и TIFF (600 dpi, оттенки серого).
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402
from PIL import Image  # noqa: E402

from .detectors import METHODS, derive, evaluate_case  # noqa: E402
from .evaluate import true_readiness  # noqa: E402
from .model import AUTO, END, OPERATIONS, START, Params, precedence  # noqa: E402

PRECEDENCE = precedence(Params().ctrl_model)   # основная модель процесса

plt.rcParams.update({"font.family": "serif",
                     "font.serif": ["Liberation Serif", "Times New Roman", "DejaVu Serif"],
                     "font.size": 8, "axes.linewidth": 0.6, "pdf.fonttype": 42,
                     "savefig.dpi": 600})
CM = 1 / 2.54
GREYS = {"B1": "0.80", "B2": "0.80", "B3": "0.55", "P": "0.15"}
HATCH = {"B1": "///", "B2": "///", "B3": "..", "P": ""}
LABEL = {"B1": "Б1 — поля / B1 — fields", "B2": "Б2 — поля и время / B2 — fields and time",
         "B3": "Б3 — монитор ограничений / B3 — constraint monitor",
         "P": "П — предложенный / P — proposed"}


def _save(fig, out: Path, name: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.pdf", bbox_inches="tight", metadata={"CreationDate": None})
    fig.savefig(out / f"{name}.png", bbox_inches="tight", dpi=300)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=600)
    buf.seek(0)
    Image.open(buf).convert("L").save(out / f"{name}.tif", compression="tiff_lzw", dpi=(600, 600))
    plt.close(fig)


NODES = {  # узел: (столбец, строка, подпись)
    "ONB": (0, 2, "ONB\nПостановка\nIn-block"),
    "GPU+": (1, 0, "GPU+\nАИЭП подкл.\nGPU on"),
    "PBB+": (1, 1, "PBB+\nТрап подан\nBridge on"),
    "UNL": (1, 3, "UNL\nВыгрузка\nUnloading"),
    "WAT": (1, 4, "WAT\nВода, санузлы\nWater, toilets"),
    "SAF": (2, 0, "SAF\nПодтв. мер\nбезоп. / Safety"),
    "DEB": (2, 1, "DEB\nВысадка\nDeboarding"),
    "CLN": (3, 0, "CLN\nУборка\nCleaning"),
    "CAT": (3, 1, "CAT\nБортпитание\nCatering"),
    "FUEL": (3, 2, "FUEL\nЗаправка\nRefuelling"),
    "LOD": (3, 3, "LOD\nЗагрузка\nLoading"),
    "BRD": (4, 1, "BRD\nПосадка\nBoarding"),
    "LDS": (5, 2, "LDS\nВедомость\nLoadsheet"),
    "DRC": (6, 2, "DRC\nДвери закр.\nDoors closed"),
    "PBB-": (7, 1, "PBB−\nТрап убран\nBridge off"),
    "GPU-": (7, 3, "GPU−\nАИЭП откл.\nGPU off"),
    "OFB": (8, 2, "OFB\nБуксировка\nPushback"),
}
AUTO_NODES = {"ONB", "GPU+", "GPU-", "PBB+", "PBB-", "FUEL", "LDS", "OFB"}
ROUTES = {("FUEL", "DRC"): [(3.3, 2.383), (3.3, 2.5), (5.8, 2.5), (5.8, 2.383)],   # под LDS
          ("WAT", "DRC"): "angle",
          ("PBB+", "CAT"): [(1.25, 0.617), (1.25, 0.5), (2.85, 0.5), (2.85, 0.617)],
          ("PBB+", "CLN"): [(1.15, 0.617), (1.15, 0.5), (3.2, 0.5), (3.2, 0.383)],
          ("DEB", "WAT"): [(2.0, 1.383), (2.0, 4.0), (1.43, 4.0)],
          ("WAT", "BRD"): [(1.43, 4.2), (3.5, 4.2), (3.5, 1.2), (3.57, 1.2)]}


def _node(op: str, status: str) -> str:
    if op in ("GPU", "PBB"):
        return op + ("+" if status == START else "-")
    return op


def _reduced_edges() -> set:
    """Непосредственные зависимости (транзитивные опущены); снимаемые — отдельно."""
    hard = {(_node(*c.pred), _node(*c.succ)) for c in PRECEDENCE if c.waiver is None}
    soft = {(_node(*c.pred), _node(*c.succ)) for c in PRECEDENCE if c.waiver is not None}
    hard = {e for e in hard if e[0] != e[1]}

    def reach(a, b, edges, skip):
        stack, seen = [a], set()
        while stack:
            x = stack.pop()
            for (u, v) in edges:
                if u == x and (u, v) != skip and v not in seen:
                    if v == b:
                        return True
                    seen.add(v)
                    stack.append(v)
        return False

    red = {e for e in hard if not reach(e[0], e[1], hard, e)}
    return ({(a, b, False) for a, b in red} | {(a, b, True) for a, b in soft}
            | {("SAF", "FUEL", "conf")})


def fig_process(out: Path) -> None:
    fig, ax = plt.subplots(figsize=(17 * CM, 7.6 * CM))
    w, h, dx, dy = 1.72, 0.92, 2.0, 1.2
    pos = {k: (c * dx, -r * dy) for k, (c, r, _) in NODES.items()}
    for k, (x, y) in pos.items():
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02",
                                    fc="white", ec="black", lw=0.7))
        if k in AUTO_NODES:
            ax.add_patch(FancyBboxPatch((x - w / 2 + 0.07, y - h / 2 + 0.07), w - 0.14,
                                        h - 0.14, boxstyle="round,pad=0.02", fc="none",
                                        ec="black", lw=0.4))
        code, *rest = NODES[k][2].split("\n")
        ax.text(x, y + 0.2, code, ha="center", va="center", fontsize=6, fontweight="bold")
        ax.text(x, y - 0.12, "\n".join(rest), ha="center", va="center", fontsize=5.4,
                linespacing=1.0)
    for a, b, waived in sorted(_reduced_edges(), key=lambda e: (e[0], e[1], str(e[2]))):
        (x1, y1), (x2, y2) = pos[a], pos[b]
        style = ROUTES.get((a, b), "arc3,rad=0.0")
        if isinstance(style, list):                 # ломаная по точкам (столбец, строка)
            pts = [(c * dx, -r * dy) for c, r in style]   # точки (столбец, строка) как есть
            ax.plot([q[0] for q in pts[:-1]], [q[1] for q in pts[:-1]], color="0.2", lw=0.5)
            ax.annotate("", xy=pts[-1], xytext=pts[-2],
                        arrowprops=dict(arrowstyle="-|>", lw=0.5, color="0.2", shrinkA=0,
                                        shrinkB=0, mutation_scale=6))
            continue
        start, end = (x1 + w / 2, y1), (x2 - w / 2, y2)
        if style == "angle":
            end = (x2, y2 - h / 2)
            style = "angle,angleA=0,angleB=90,rad=0"
        ls = (0, (1, 1.5)) if waived == "conf" else (0, (3, 2)) if waived else "-"
        ax.annotate("", xy=end, xytext=start,
                    arrowprops=dict(arrowstyle="-|>", lw=0.5, color="0.2", shrinkA=0, shrinkB=0,
                                    mutation_scale=6, linestyle=ls, connectionstyle=style))
    ax.set_xlim(-0.95, 8 * dx + 0.95)
    ax.set_ylim(-4 * dy - 1.45, 0.6)
    ax.axis("off")
    ax.text(-0.9, -4 * dy - 0.65,
            "Двойная рамка — событие подтверждается автоматическим источником (при оснащении "
            "стоянки); штриховая стрелка — зависимость снимается\nпри заправке с пассажирами на "
            "борту только после подтверждения мер безопасности SAF с отдельного рабочего места "
            "(пунктир);\nпоказаны непосредственные зависимости, транзитивные опущены.\n"
            "Double frame — event confirmed by an automatic source (if the stand is equipped); "
            "dashed arrow — dependency waived for refuelling\nwith passengers on board only after "
            "safety measures are confirmed (SAF) from a separate workstation (dotted); direct\n"
            "dependencies shown, transitive ones omitted.",
            fontsize=5.6, va="top", linespacing=1.15)
    _save(fig, out, "fig1_process_model")


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fig_by_type(res: Path, out: Path) -> None:
    rows = [r for r in _read(res / "by_type.csv")]
    types = ["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8"]
    names = {"V1": "V1\nложное\nзавершение\nfalse\ncompletion",
             "V2": "V2\nизменение\nметки\ntimestamp\ntampering",
             "V3": "V3\nповтор\nreplay", "V4": "V4\nпропуск\nomission",
             "V5": "V5\nнарушение\nпоследоват.\nsequence\nviolation",
             "V6": "V6\nсогласованная\nподмена\ncoordinated\nsubstitution",
             "V7": "V7\nподмена поля,\nослабл. контроль\nrule-relaxing\nfield",
             "V8": "V8\nосведомлённый\nисполнитель\ninformed\ninsider"}
    fig, ax = plt.subplots(figsize=(17 * CM, 6.0 * CM))
    bw = 0.26
    for i, m in enumerate(["B2", "B3", "P"]):
        vals, lo, hi = [], [], []
        for t in types:
            r = next(x for x in rows if x["method"] == m and x["vtype"] == t)
            v = float(r["alarm_or_detect"])
            vals.append(v)
            lo.append(v - float(r["ci_lo"]))
            hi.append(float(r["ci_hi"]) - v)
        xs = [j + (i - 1) * bw for j in range(len(types))]
        ax.bar(xs, vals, bw, color=GREYS[m], hatch=HATCH[m], edgecolor="black", lw=0.5,
               label=LABEL[m], yerr=[lo, hi], error_kw=dict(lw=0.6, capsize=1.5))
    ax.set_xticks(range(len(types)))
    ax.set_xticklabels([names[t] for t in types], fontsize=6.5)
    ax.set_ylabel("Доля обнаруженных нарушений\nShare of violations detected")
    ax.set_ylim(0, 1.05)
    from matplotlib.ticker import FuncFormatter
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}".replace(".", ",")))
    ax.legend(fontsize=6.5, frameon=False, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.13))
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, out, "fig3_detection_by_type")


def fig_sensitivity(res: Path, out: Path) -> None:
    rows = _read(res / "sensitivity.csv")
    panels = [("grace_W", "Окно ожидания W, мин\nGrace window W, min", "а / a"),
              ("late_mark_share", "Доля запаздывающих отметок\nShare of late manual marks", "б / b"),
              ("p_unmodeled_variant", "Доля неучтённых вариантов\nShare of unmodelled variants",
               "в / c")]
    fig, axs = plt.subplots(1, 3, figsize=(17 * CM, 6.0 * CM), sharey=True)
    for ax, (fac, xl, tag) in zip(axs, panels):
        for m, mk in (("P", "o"), ("B2", "s")):
            r = [x for x in rows if x["factor"] == fac and x["method"] == m]
            xs = [float(x["value"]) for x in r]
            ax.plot(xs, [float(x["recall"]) for x in r], marker=mk, color="black", lw=0.8, ms=3,
                    label=f"{'П' if m == 'P' else 'Б2'}: полнота / {m}: recall")
            ax.plot(xs, [float(x["fpr"]) for x in r], marker=mk, color="0.5", lw=0.8, ms=3,
                    ls="--", mfc="white",
                    label=f"{'П' if m == 'P' else 'Б2'}: ложные тревоги / {m}: FPR")
        ax.set_xlabel(xl, fontsize=7)
        ax.set_title(tag, fontsize=8, loc="left")
        ax.set_ylim(0, 1.02)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", lw=0.3, color="0.85")
    axs[0].set_ylabel("Доля / Share")
    h, lab = axs[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="upper center", ncol=2, fontsize=6.5, frameon=False,
               bbox_to_anchor=(0.5, 1.12))
    fig.tight_layout()
    _save(fig, out, "fig4_sensitivity")


ROW = ["ONB", "GPU", "PBB", "DEB", "UNL", "WAT", "CLN", "CAT", "FUEL", "LOD", "BRD", "LDS",
       "DRC", "OFB"]


def fig_example(cases, p: Params, pB: Params, out: Path) -> dict:
    """Пример оборота с ложным завершением заправки (V1), автоматический счётчик доступен."""
    pick = None
    for c in cases:
        if c.vtype == "V1" and c.gt_target == "FUEL" and \
                c.auto_avail.get("METER") and \
                not any(x.split(":")[0] in ("offline", "correction", "unmodeled_variant")
                        for x in c.features):
            steps = evaluate_case(c.meta(), c.messages, p)
            stepsB = evaluate_case(c.meta(), c.messages, pB)
            d1, d2 = true_readiness(c)
            oP = derive(steps, METHODS["P"], p.grace, p.missing_horizon, c.gt_inj_time, d1, d2)
            oB = derive(stepsB, METHODS["B2"], pB.grace, pB.missing_horizon, c.gt_inj_time, d1, d2)
            if oP["detect_time"] is not None and oB["d1_outcome"] == "false":
                pick = (c, oP, oB, steps, stepsB)
                break
    if pick is None:
        return {}
    c, oP, oB, steps, stepsB = pick
    groupsB = METHODS["B2"]
    d1_b = next(s.time for s in stepsB if s.d1 and not any(k[0] in groupsB for k in s.keys))
    hold_P = [s.time for s in steps if s.d1 and any(k[0] in METHODS["P"] for k in s.keys)]
    fig, ax = plt.subplots(figsize=(17 * CM, 8.0 * CM))
    ymap = {op: i for i, op in enumerate(ROW)}
    for op in ROW:
        y = ymap[op]
        if OPERATIONS[op].kind == "interval":
            s0, e0 = c.truth[(op, START)], c.truth[(op, END)]
            ax.barh(y, e0 - s0, left=s0, height=0.46, color="0.88", edgecolor="0.45", lw=0.4)
        else:
            ax.plot([c.truth[(op, END)]], [y], marker="D", color="0.6", ms=3)
    for m in {x["msg_id"]: x for x in c.messages}.values():
        y = ymap[m["op"]]
        if m["gt_injected"]:
            ax.plot(m["recv_time"], y - 0.3, marker="X", color="black", ms=6.5, zorder=5)
            continue
        mk = "^" if m["kind"] == AUTO else ("|" if m["status"] == START else "v")
        ax.plot(m["recv_time"], y + (0.3 if m["kind"] == AUTO else -0.3), marker=mk,
                color="black", ms=3.5, mew=0.8, zorder=4)
    t_alarm = oP["detect_time"]
    grp = oP["detect_key"][0]
    for x, txt, ls, col, ha, yt in (
            (c.gt_inj_time, "подложная отметка\nforged mark", ":", "0.3", "right", -1.85),
            (d1_b, "Б2: «готово к посадке»\nB2: “ready for boarding”", "-.", "0.45", "right", -0.55),
            (t_alarm, f"тревога П ({grp})\nalarm P ({grp})", "--", "black", "left", -1.85)):
        ax.axvline(x, color=col, lw=0.8, ls=ls)
        ax.text(x + (0.3 if ha == "left" else -0.3), yt, txt, fontsize=6, va="center", ha=ha,
                bbox=dict(fc="white", ec="none", pad=0.5))
    ax.set_yticks(range(len(ROW)))
    ax.set_yticklabels(ROW, fontsize=6.5)
    ax.set_ylim(len(ROW) - 0.4, -2.45)
    ax.set_xlabel("Время от постановки на стоянку, мин / Time from in-block, min")
    ax.spines[["top", "right"]].set_visible(False)
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    leg = [Patch(fc="0.88", ec="0.45", lw=0.4, label="фактическое выполнение / actual operation"),
           Line2D([], [], marker="|", ls="", color="black", label="ручная отметка начала / manual start"),
           Line2D([], [], marker="v", ls="", color="black", ms=3.5, label="ручная отметка окончания / manual end"),
           Line2D([], [], marker="^", ls="", color="black", ms=3.5, label="автоматический источник / automatic source"),
           Line2D([], [], marker="X", ls="", color="black", ms=6, label="подложное сообщение / forged message")]
    ax.legend(handles=leg, fontsize=5.8, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, -0.16), ncol=3)
    _save(fig, out, "fig2_example_case")
    return {"case_id": c.case_id, "forged_recv": c.gt_inj_time, "alarm_P": t_alarm,
            "alarm_key": list(oP["detect_key"]), "d1_B2_time": d1_b,
            "d1_true": true_readiness(c)[0], "d1_P_outcome": oP["d1_outcome"],
            "d1_B2_outcome": oB["d1_outcome"], "P_hold_from": hold_P[0] if hold_P else None,
            "fuel_true_end": c.truth[("FUEL", END)], "fuel_true_start": c.truth[("FUEL", START)]}


def make_all(res: Path, out: Path, sample_cases, p: Params, pB: Params) -> None:
    import json
    fig_process(out)
    ex = fig_example(sample_cases, p, pB, out)
    fig_by_type(res, out)
    fig_sensitivity(res, out)
    (res / "fig2_example.json").write_text(json.dumps(ex, ensure_ascii=False, indent=1),
                                           encoding="utf-8")


if __name__ == "__main__":                      # перестроить рисунки по готовым результатам
    import json
    from dataclasses import replace

    from .simulate import generate_dataset
    root = Path(__file__).resolve().parents[1]
    summ = json.loads((root / "results" / "summary.json").read_text(encoding="utf-8"))
    base = Params()
    pP = replace(base, **summ["calibrated"]["P"])
    pB = replace(base, **summ["calibrated"]["B2"])
    d = summ["dataset"]
    sample = generate_dataset(1, d["n_normal_per_seed"], d["n_per_type_per_seed"], base)
    make_all(root / "results", root / "figures", sample, pP, pB)


def fig_campaign(res: Path, out: Path, base: Params, pP: Params, pB: Params,
                 scenario: str = "GATE") -> dict:
    """Сутки с компрометацией терминала: число оборотов с тревогами за окно по терминалам роли."""
    import json

    import numpy as np

    from . import campaign as C
    rows = _read(res / "campaign_days.csv")
    det = [(float(r["hours_to_detect"]), int(r["seed"])) for r in rows if r["scenario"] == scenario
           and r["method"] == "P" and r["rule"] == "K3" and r["detected"] == "True"]
    if not det:
        return {}
    med = float(np.median([h for h, _ in det]))
    seed = min(det, key=lambda x: (abs(x[0] - med), x[1]))[1]      # сутки с медианным временем
    tr = C.day_trace(seed, scenario, base, pP, pB)
    role = C.ATTACK_ROLE[scenario]
    grid = np.arange(0, C.DAY_MIN + 61, 5.0)
    fig, axs = plt.subplots(1, 2, figsize=(17 * CM, 5.6 * CM), sharey=True)
    ymax = 1
    for method in ("P", "B2"):
        evs = [(t, k) for t, tm, k in tr["methods"][method]["events"]]
        for t0, _ in evs:
            ymax = max(ymax, len({k for t, k in evs if t0 - C.WINDOW <= t <= t0}))
    titles = {"P": "а / a — П / P", "B2": "б / b — Б2 / B2"}
    info = {"seed": seed, "scenario": scenario, "bad_term": tr["bad_term"],
            "n_forged": len(tr["forged"])}
    for ax, method in zip(axs, ("P", "B2")):
        ev = tr["methods"][method]["events"]
        terms = [f"{role}-T{i:02d}" for i in range(C.POOLS[role])]
        for term in terms:
            e = [(t, k) for t, tm, k in ev if tm == term]
            xs = sorted({0.0, float(grid[-1])} | {t for t, _ in e} | {t + C.WINDOW + 1e-6 for t, _ in e})
            y = [len({k for t, k in e if x - C.WINDOW <= t <= x}) for x in xs]
            bad = term == tr["bad_term"]
            ax.step(np.array(xs) / 60 + 6, y, where="post", color="black" if bad else "0.65",
                    lw=1.4 if bad else 0.7, zorder=3 if bad else 2,
                    label=("скомпрометированный терминал / compromised terminal" if bad else None))
        ax.axhline(3, color="0.3", ls="--", lw=0.7)
        ax.axvline(C.ATTACK_START / 60 + 6, color="0.3", ls=":", lw=0.8)
        ax.plot([t / 60 + 6 for t in tr["forged"]], [-0.25] * len(tr["forged"]), "|",
                color="black", ms=6, mew=0.8, clip_on=False)
        flag = tr["methods"][method]["flags"].get(tr["bad_term"])
        if flag is not None and flag >= C.ATTACK_START:
            ax.plot(flag / 60 + 6, 3, marker="o", color="black", ms=4, zorder=4)
            ax.annotate("подозрение / suspicion", (flag / 60 + 6, 3), xytext=(-70, 14),
                        textcoords="offset points", fontsize=6)
            info[f"flag_{method}_h"] = flag / 60 + 6
        ax.set_title(titles[method], fontsize=8, loc="left")
        ax.set_xlim(6, 24.5)
        ax.set_ylim(-0.6, ymax + 1.5)
        ax.set_xlabel("Время суток, ч / Time of day, h", fontsize=7)
        ax.spines[["top", "right"]].set_visible(False)
        ax.text(C.ATTACK_START / 60 + 6.15, ymax + 1.2, "начало атаки\nattack start", fontsize=5.8,
                va="top")
    axs[0].set_ylabel("Обороты с тревогами за 6 ч\nTurnarounds with alarms in 6 h", fontsize=7)
    from matplotlib.ticker import FuncFormatter
    for a_ in axs:
        a_.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))
    from matplotlib.lines import Line2D
    leg = [Line2D([], [], color="black", lw=1.4, label="скомпрометированный терминал / compromised terminal"),
           Line2D([], [], color="0.65", lw=0.7, label="другие терминалы той же роли / other terminals of the role"),
           Line2D([], [], color="0.3", ls="--", lw=0.7, label="порог K = 3 / threshold K = 3"),
           Line2D([], [], color="black", marker="|", ls="", ms=6, label="подложная отметка / forged mark")]
    fig.legend(handles=leg, loc="upper center", ncol=2, fontsize=6.2, frameon=False,
               bbox_to_anchor=(0.5, 1.13))
    fig.tight_layout()
    _save(fig, out, "fig5_campaign_day")
    (res / "fig5_campaign.json").write_text(json.dumps(info, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    return info
