"""Сборка рукописи версии 3.3: шаги версии 3.2 + правки по рецензии 10.11.2026.

    python3 build_v33.py <распакованный DOCX v3.1> <results/> <figures/> <каталог результата> [core.xml для обезличенной копии]

Все числа в тексте и таблицах берутся из results/summary.json (см. texts_v33.py), рисунки —
из figures/. Жёлтым в statya_mgtu_ga_izmeneniya.docx выделено изменённое относительно 3.1.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).parent))
import build_v32 as B32          # noqa: E402
from build_v32 import Builder, q  # noqa: E402
import texts_v33 as T            # noqa: E402

B32.FOOTNOTES.update(T.FOOTNOTES_EXTRA)


class Builder33(Builder):
    def set_par(self, prefix: str, new_text: str, lead: str | None = None):
        """Заменить текст абзаца целиком. lead — выделенное начало (формат первого прогона).
        Разметка _{x} даёт подстрочный индекс, {FNn} — сноску."""
        p = self.find(prefix)
        runs = p.findall(q("r"))
        tmpl_lead = copy.deepcopy(runs[0])
        tmpl = copy.deepcopy(runs[1] if (lead and len(runs) > 1) else runs[0])
        for t_ in (tmpl_lead, tmpl):
            rpr = t_.find(q("rPr"))
            for va in rpr.findall(q("vertAlign")):
                rpr.remove(va)
        for el in list(p):
            if el.tag != q("pPr"):
                p.remove(el)
        if lead:
            p.append(self.mk_run(tmpl_lead, lead))
        for part in re.split(r"(\{FN\d+\}|_\{[^}]*\})", new_text):
            if not part:
                continue
            fn = re.fullmatch(r"\{FN(\d+)\}", part)
            sb = re.fullmatch(r"_\{([^}]*)\}", part)
            if fn:
                p.append(self.mk_fnref(tmpl, int(fn.group(1))))
            elif sb:
                r = self.mk_run(tmpl, sb.group(1), mark=True)
                etree.SubElement(r.find(q("rPr")), q("vertAlign")).set(q("val"), "subscript")
                p.append(r)
            else:
                p.append(self.mk_run(tmpl, part, mark=True))

    def tables(self):
        return [el for el in self.body if el.tag == q("tbl")]

    def set_cell(self, tc, lines: list[str]):
        p = tc.find(q("p"))
        runs = p.findall(q("r"))
        tmpl = copy.deepcopy(next(r for r in runs if r.find(q("t")) is not None))
        old = [t.text for r in runs for t in r.findall(q("t"))]
        for r in runs:
            p.remove(r)
        for i, line in enumerate(lines):
            if i:
                br = etree.SubElement(p, q("r"))
                etree.SubElement(br, q("br"))
            p.append(self.mk_run(tmpl, line, mark=(old != lines)))

    def fill_table(self, tbl, rows: list[list[list[str] | None]], first_row: int = 0):
        trs = tbl.findall(q("tr"))
        for i, row in enumerate(rows):
            tcs = trs[first_row + i].findall(q("tc"))
            assert len(tcs) == len(row), (i, len(tcs), len(row))
            for tc, lines in zip(tcs, row):
                if lines is not None:
                    self.set_cell(tc, lines)

    def rename_levels(self):
        """Уровни нарушителя Н1–Н3 → А1–А3 (в Методике ФСТЭК Н1–Н4 значат другое; «Н» — ещё и
        категория последствий)."""
        for t in self.body.iter(q("t")):
            if t.text:
                t.text = re.sub(r"Н([123])(?!\d)", r"А\1", t.text)
                t.text = re.sub(r"\bH([123])\b", r"A\1", t.text)

    def apply_v33(self, S: dict):
        self.rename_levels()
        for prefix, old, new in T.edits(S):
            self.replace(self.find(prefix), old, new)
        for prefix, lead, text in T.paragraphs(S):
            self.set_par(prefix, text, lead)
        for old, new in T.cell_edits(S):
            hits = [t for t in self.body.iter(q("t")) if t.text == old]
            assert len(hits) == 1, (old, len(hits))
            hits[0].text = new
            if self.highlight:
                rpr = hits[0].getparent().find(q("rPr"))
                etree.SubElement(rpr, q("highlight")).set(q("val"), "yellow")
        tbls = self.tables()
        t4, t5 = tbls[3], tbls[4]
        self.fill_table(t4, T.table4(S))
        widths = [1500, 1150, 1250, 1350, 1150, 1150, 1150, 938]      # сумма прежняя, 9638
        for g, w in zip(t4.find(q("tblGrid")).findall(q("gridCol")), widths):
            g.set(q("w"), str(w))
        for tr in t4.findall(q("tr")):
            for tc, w in zip(tr.findall(q("tc")), widths):
                tc.find(q("tcPr")).find(q("tcW")).set(q("w"), str(w))
        trs = t5.findall(q("tr"))
        new_row = copy.deepcopy(trs[1])
        trs[4].addnext(new_row)                    # строка «тихого» нарушителя — после атак
        self.fill_table(t5, T.table5(S))
        for prefix in T.DELETE:
            self.body.remove(self.find(prefix))

    def save33(self, out: Path, figures: Path, core_from=None):
        self.save(out, core_from)
        # заменить рисунки в готовом файле
        import zipfile
        tmp = out.with_suffix(".zip.tmp")
        with zipfile.ZipFile(out) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "word/media/image1.png":
                    data = (figures / "fig1_process_model.png").read_bytes()
                if item.filename == "word/media/image2.png":
                    data = (figures / "fig3_detection_by_type.png").read_bytes()
                zout.writestr(item, data)
        shutil.move(tmp, out)


def build(src, results, figures, out, *, highlight=False, anonymous=False, core_from=None):
    S = json.loads((results / "summary.json").read_text(encoding="utf-8"))
    S["_tradeoff"] = json.loads((results / "tradeoff_W.json").read_text(encoding="utf-8"))["points"]
    b = Builder33(src, highlight)
    b.apply_edits()
    b.references()
    b.renumber_citations()
    b.reorder()
    b.apply_v33(S)
    if anonymous:
        b.anonymize()
    b.save33(out, figures, core_from)


if __name__ == "__main__":
    src, results, figures, outdir = map(Path, sys.argv[1:5])
    core = Path(sys.argv[5]) if len(sys.argv) > 5 else None
    outdir.mkdir(parents=True, exist_ok=True)
    build(src, results, figures, outdir / "statya_mgtu_ga.docx")
    build(src, results, figures, outdir / "statya_mgtu_ga_izmeneniya.docx", highlight=True)
    build(src, results, figures, outdir / "statya_mgtu_ga_anonim.docx", anonymous=True, core_from=core)
    print("ok")
