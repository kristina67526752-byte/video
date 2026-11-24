"""Рисунки статьи: оттенки серого, подписи на русском и английском языках.

Каждый рисунок сохраняется отдельно в PDF (вектор) и TIFF (600 dpi, оттенки серого) в папку
2-risunki комплекта. В статье два рисунка: модель процесса и доля выявленных нарушений по подвидам.
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

from .model import AUTO, START, Params, precedence  # noqa: E402

PRECEDENCE = precedence(Params().ctrl_model)   # основная модель процесса

plt.rcParams.update({"font.family": "serif",
                     "font.serif": ["Liberation Serif", "Times New Roman", "DejaVu Serif"],
                     "font.size": 8, "axes.linewidth": 0.6, "pdf.fonttype": 42,
                     "savefig.dpi": 600})
CM = 1 / 2.54
# Обозначения статьи с версии 3.7: Б — проверка полей и времени (в коде B2), М — монитор
# декларативных ограничений (B3), М с допусками П (B3-Ptol), П — предложенные правила (P).
GREYS = {"B2": "0.85", "B3": "0.6", "B3-Ptol": "0.4", "P": "0.1"}
HATCH = {"B2": "///", "B3": "..", "B3-Ptol": "xx", "P": ""}
LABEL = {"B2": "Б — поля и время / B — fields and time",
         "B3": "М — монитор ограничений / M — constraint monitor",
         "B3-Ptol": "М с допусками П / M with P tolerances",
         "P": "П — правила / P — rules"}


def _save(fig, out: Path, name: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / f"{name}.pdf", bbox_inches="tight", metadata={"CreationDate": None})
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=600)
    buf.seek(0)
    Image.open(buf).convert("L").save(out / f"{name}.tif", compression="tiff_lzw", dpi=(600, 600))
    plt.close(fig)


NODES = {  # узел: (столбец, строка, подпись); английские названия — в подписи к рисунку
    "ONB": (0, 2, "ONB\nПостановка"),
    "GPU+": (1, 0, "GPU+\nАИЭП\nподключён"),
    "PBB+": (1, 1, "PBB+\nТрап подан"),
    "UNL": (1, 3, "UNL\nВыгрузка"),
    "WAT": (1, 4, "WAT\nВода,\nсанузлы"),
    "SAF": (2, 0, "SAF\nМеры\nбезопасности"),
    "DEB": (2, 1, "DEB\nВысадка"),
    "CLN": (3, 0, "CLN\nУборка"),
    "CAT": (3, 1, "CAT\nБортпитание"),
    "FUEL": (3, 2, "FUEL\nЗаправка"),
    "LOD": (3, 3, "LOD\nПогрузка"),
    "BRD": (4, 1, "BRD\nПосадка"),
    "LDS": (5, 2, "LDS\nВедомость"),
    "DRC": (6, 2, "DRC\nДвери\nзакрыты"),
    "PBB-": (7, 1, "PBB−\nТрап убран"),
    "GPU-": (7, 3, "GPU−\nАИЭП\nотключён"),
    "OFB": (8, 2, "OFB\nБуксировка"),
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
    fig, ax = plt.subplots(figsize=(17 * CM, 8.4 * CM))
    w, h, dx, dy = 1.8, 0.92, 2.0, 1.2
    pos = {k: (c * dx, -r * dy) for k, (c, r, _) in NODES.items()}
    for k, (x, y) in pos.items():
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02",
                                    fc="white", ec="black", lw=0.7))
        if k in AUTO_NODES:
            ax.add_patch(FancyBboxPatch((x - w / 2 + 0.07, y - h / 2 + 0.07), w - 0.14,
                                        h - 0.14, boxstyle="round,pad=0.02", fc="none",
                                        ec="black", lw=0.4))
        code, *rest = NODES[k][2].split("\n")
        ax.text(x, y + 0.22, code, ha="center", va="center", fontsize=8, fontweight="bold")
        ax.text(x, y - 0.13, "\n".join(rest), ha="center", va="center", fontsize=6.6,
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
    ax.set_ylim(-4 * dy - 1.6, 0.62)
    ax.axis("off")
    ax.text(-0.9, -4 * dy - 0.62,
            "Двойная рамка — событие подтверждается оборудованием (при оснащении стоянки); "
            "штриховая стрелка — зависимость снимается при заправке\nс пассажирами на борту "
            "только после подтверждения мер безопасности SAF (пунктир); транзитивные "
            "зависимости не показаны.\n"
            "Double frame — event confirmed by equipment (if the stand is equipped); dashed "
            "arrow — dependency waived for refuelling with passengers\non board only after "
            "safety measures are confirmed (SAF, dotted); transitive dependencies omitted.",
            fontsize=7, va="top", linespacing=1.15)
    _save(fig, out, "ris1_process_model")


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


GROUPS_FIG = [("Содержательные\nSubstantive", ["V1b", "V2-end", "V2-start", "V5b", "V7c"]),
              ("Обнаруживаемые по построению\nDetectable by construction",
               ["V1a", "V3a", "V3b", "V4-start", "V4-end", "V7a"]),
              ("Вне возможностей метода\nOut of reach", ["V6", "V7b", "V8"])]


def fig_by_subtype(res: Path, out: Path) -> None:
    """Доля выявленных нарушений по подвидам, сгруппированным как в табл. 4 (V5a — нарушение
    технологии при правдивых данных — не входит)."""
    rows = _read(res / "by_subtype.csv")
    if (res / "rev_by_subtype.csv").exists():          # М с допусками П (версия 3.7)
        have = {(r["method"], r["subtype"]) for r in rows}
        rows += [r for r in _read(res / "rev_by_subtype.csv")
                 if (r["method"], r["subtype"]) not in have]
    fig, ax = plt.subplots(figsize=(17 * CM, 6.8 * CM))
    bw, gap = 0.2, 0.8
    xs_all, labels, x = [], [], 0.0
    spans = []
    for gname, subs in GROUPS_FIG:
        x0 = x
        for st in subs:
            xs_all.append(x)
            labels.append(st)
            x += 1
        spans.append((x0, x - 1, gname))
        x += gap
    meths = ["B2", "B3", "B3-Ptol", "P"]
    for i, m in enumerate(meths):
        vals, lo, hi = [], [], []
        for _, subs in GROUPS_FIG:
            for st in subs:
                r = next(y for y in rows if y["method"] == m and y["subtype"] == st)
                v = float(r["recall"])
                vals.append(v)
                lo.append(v - float(r["ci_lo"]))
                hi.append(float(r["ci_hi"]) - v)
        ax.bar([xx + (i - 1.5) * bw for xx in xs_all], vals, bw, color=GREYS[m], hatch=HATCH[m],
               edgecolor="black", lw=0.5, label=LABEL[m], yerr=[lo, hi],
               error_kw=dict(lw=0.6, capsize=1.2))
    ax.set_xticks(xs_all)
    ax.set_xticklabels(labels, fontsize=7)
    for a, b, gname in spans:
        ax.annotate(gname, xy=((a + b) / 2, 0), xycoords=("data", "axes fraction"),
                    xytext=(0, -20), textcoords="offset points", ha="center", va="top",
                    fontsize=7)
        ax.annotate("", xy=(a - 0.4, -0.115), xytext=(b + 0.4, -0.115),
                    xycoords=("data", "axes fraction"), textcoords=("data", "axes fraction"),
                    arrowprops=dict(arrowstyle="-", lw=0.5))
    ax.set_ylabel("Доля обнаруженных нарушений\nShare of violations detected")
    ax.set_ylim(0, 1.05)
    ax.set_xlim(-0.6, xs_all[-1] + 0.6)
    from matplotlib.ticker import FuncFormatter
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}".replace(".", ",")))
    ax.legend(fontsize=7, frameon=False, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.22))
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, out, "ris2_detection_by_subtype")


def make_all(res: Path, out: Path) -> None:
    fig_process(out)
    fig_by_subtype(res, out)


if __name__ == "__main__":                      # перестроить рисунки по готовым результатам
    root = Path(__file__).resolve().parents[1]
    make_all(root / "results", root.parent / "2-risunki")
