"""Сборка рукописи версии 3.2 из DOCX версии 3.1.

    python3 build_v32.py <распакованный DOCX v3.1> <каталог результата>

Делает три файла: statya_mgtu_ga.docx, statya_mgtu_ga_izmeneniya.docx (новый и изменённый
текст выделен жёлтым) и statya_mgtu_ga_anonim.docx. Что меняется относительно версии 3.1:
  * нормативные документы вынесены из списка литературы в подстрочные сноски
    (правила журнала: «следует избегать включения в список литературы нормативных материалов»);
  * список литературы перенумерован (25 источников), авторы — в начале описания, полужирным;
  * английский блок (название, авторы, аннотация, ключевые слова) перенесён после русских
    ключевых слов, порядок концевых разделов — как в образце журнала;
  * правки текста: технологический график по ФАП № 89, подтверждение мер безопасности
    по ФАП № 128, раскрытие использования ИИ по политике журнала.
Числа эксперимента не меняются.
"""
from __future__ import annotations

import copy
import re
import shutil
import sys
import zipfile
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W}


def q(tag: str) -> str:
    return "{%s}%s" % (W, tag)


# ---------------------------------------------------------------- сноски
FOOTNOTES = {
    1: "Об утверждении Федеральных авиационных правил «Правила наземного обслуживания "
       "гражданских воздушных судов»: приказ Минтранса России от 20.03.2023 № 89 "
       "(зарегистрирован в Минюсте России 30.03.2023, № 72804; действует с 01.03.2026). П. 1, 19.",
    2: "Manual on Ground Handling: Doc 10121. 1st ed. Montréal: ICAO, 2019; Airport Handling "
       "Manual. 46th ed. Montreal; Geneva: IATA, 2026; IATA Ground Operations Manual (IGOM). "
       "14th ed. Montreal; Geneva: IATA, 2026.",
    3: "Airport CDM Implementation Manual. Version 5.0. Brussels: EUROCONTROL, 2017.",
    4: "Annex 17 to the Convention on International Civil Aviation. Aviation Security: "
       "Safeguarding International Civil Aviation against Acts of Unlawful Interference. "
       "12th ed. Montréal: ICAO, 2022.",
    5: "О безопасности критической информационной инфраструктуры Российской Федерации: "
       "федеральный закон от 26.07.2017 № 187-ФЗ.",
    6: "Об утверждении Требований по обеспечению безопасности значимых объектов критической "
       "информационной инфраструктуры Российской Федерации: приказ ФСТЭК России от 25.12.2017 "
       "№ 239 (мера ОЦЛ.4).",
    7: "Об утверждении Федеральных авиационных правил «Подготовка и выполнение полетов в "
       "гражданской авиации Российской Федерации»: приказ Минтранса России от 31.07.2009 № 128. "
       "П. 8.4.",
}

# ---------------------------------------------------------------- правки текста
# (начало абзаца, старый фрагмент, новый фрагмент); {FNn} — место сноски n
EDITS = [
    ("Наземное обслуживание воздушного судна (ВС)",
     "Федеральными авиационными правилами [1] и руководствами ИКАО и ИАТА [2–4].",
     "Федеральными авиационными правилами{FN1} и руководствами ИКАО и ИАТА{FN2}; "
     "последовательность и длительность операций определяет технологический график, который "
     "эксплуатант формирует для конкретного типа ВС."),
    ("Наземное обслуживание воздушного судна (ВС)",
     "служат вехами для прогнозов и решений [5].",
     "служат вехами для прогнозов и решений{FN3}."),
    ("По этим данным система формирует статусы",
     "от актов незаконного вмешательства [6].",
     "от актов незаконного вмешательства{FN4}."),
    ("По этим данным система формирует статусы",
     "реагировать на компьютерные инциденты [7], а требования к значимым объектам КИИ включают "
     "контроль данных, вводимых в систему [8].",
     "реагировать на компьютерные инциденты{FN5}, а требования к значимым объектам КИИ включают "
     "контроль данных, вводимых в систему{FN6}."),
    ("Объект защиты.",
     "Состав операций, нормы и доли оснащения — допущения.",
     "Состав операций, нормы и доли оснащения — допущения: при внедрении зависимости и "
     "минимальные длительности берутся из технологического графика эксплуатанта для типа ВС и "
     "задаются как параметры метода."),
    ("Модель доверия.",
     "с отдельного рабочего места — руководителя смены или экипажа; подтверждение",
     "с отдельного рабочего места; подтверждение"),
    ("Модель доверия.",
     "Кто подтверждает меры безопасности, устанавливает эксплуатант в руководстве по наземному "
     "обслуживанию [1]; в модели это допущение.",
     "Условия такой заправки{FN7} — подготовленный персонал на борту, оповещение экипажа и "
     "пассажиров, выключенное табло «Пристегнуть ремни», свободные пути эвакуации, средства "
     "пожаротушения у ВС — обеспечивают экипаж и службы аэропорта, а не заправщик. Поэтому в "
     "модели подтверждение SAF вводит экипаж или координатор оборота со слов экипажа; "
     "конкретную роль закрепляет эксплуатант в руководстве по организации наземного "
     "обслуживания."),
    ("Использование генеративного искусственного интеллекта.",
     "Программный код эксперимента, черновик текста статьи и поиск источников выполнены с "
     "помощью ассистента на основе большой языковой модели Claude (Anthropic).",
     "С помощью ассистента на основе большой языковой модели Claude (Anthropic) подготовлены: "
     "программный код эксперимента (генератор данных, методы контроля, расчёт показателей, "
     "построение графиков); первичные тексты всех разделов статьи — введения, методов, "
     "результатов, обсуждения, заключения и аннотаций на русском и английском языках; поиск "
     "источников. Постановку задачи, модель процесса, допущения и интерпретацию результатов "
     "определяли и проверяли авторы."),
    ("Использование генеративного искусственного интеллекта.",
     "Рисунки построены программно; генеративные модели изображений не использовались.",
     "Рисунки построены программно по результатам расчётов; генеративные модели для создания "
     "и редактирования изображений не применялись."),
    ("Предлагается ступенчатое реагирование.",
     "информирование об инциденте [7] целесообразны",
     "информирование об инциденте по Федеральному закону № 187-ФЗ целесообразны"),
    ("Предлагается ступенчатое реагирование.",
     "как реализацию контроля целостности вводимых данных [8] на уровне",
     "как реализацию контроля вводимых данных, предусмотренного требованиями ФСТЭК России, на "
     "уровне"),
    ("Аутентификация сообщений защищает",
     "что согласуется с требованием защищать критически важные системы и данные [6].",
     "что согласуется с требованием Приложения 17 защищать критически важные системы и данные."),
    ("Abstract.",
     "The results are model-based.",
     "The results are model-based and need validation on anonymised operational logs."),
]

# правки в ячейках таблиц: (старый текст прогона, новый текст)
CELL_EDITS = [
    ("Рабочее место руководителя смены (SAF) /", "Экипаж или координатор оборота (SAF) /"),
    ("Supervisor workstation", "Crew or turnaround coordinator"),
]

URBINA_AUTHORS = ("Urbina, D.I., Giraldo, J.A., Cardenas, A.A., Tippenhauer, N.O., Valente, J., "
                  "Faisal, M., Ruths, J., Candell, R., Sandberg, H.")
N_NORMATIVE = 8          # источники 1–8 версии 3.1 — нормативные документы
SELF_REF_OLD = 29        # статья соавтора в нумерации версии 3.1


class Builder:
    def __init__(self, src: Path, highlight: bool):
        self.src = src
        self.highlight = highlight
        self.tree = etree.parse(str(src / "word" / "document.xml"))
        self.body = self.tree.getroot().find("w:body", NS)
        self.fn_used: list[int] = []

    # ------------------------------------------------------------ служебное
    @staticmethod
    def text(el) -> str:
        return "".join(t.text or "" for t in el.iter(q("t")))

    def paras(self):
        return [el for el in self.body if el.tag == q("p")]

    def find(self, prefix: str):
        hits = [p for p in self.paras() if self.text(p).startswith(prefix)]
        assert len(hits) == 1, (prefix, len(hits))
        return hits[0]

    def mk_run(self, src_run, text: str, *, bold=None, mark=False):
        r = etree.Element(q("r"))
        rpr = src_run.find(q("rPr"))
        rpr = copy.deepcopy(rpr) if rpr is not None else etree.Element(q("rPr"))
        r.append(rpr)
        if bold is not None:
            for b in rpr.findall(q("b")):
                rpr.remove(b)
            b = etree.Element(q("b"))
            if not bold:
                b.set(q("val"), "0")
            fonts = rpr.find(q("rFonts"))
            rpr.insert(1 if fonts is not None else 0, b)
        if mark and self.highlight:
            h = etree.SubElement(rpr, q("highlight"))
            h.set(q("val"), "yellow")
        t = etree.SubElement(r, q("t"))
        t.text = text
        if text != text.strip():
            t.set("{%s}space" % XML, "preserve")
        return r

    def mk_fnref(self, src_run, n: int):
        r = etree.Element(q("r"))
        rpr = copy.deepcopy(src_run.find(q("rPr")))
        r.append(rpr)
        va = etree.SubElement(rpr, q("vertAlign"))
        va.set(q("val"), "superscript")
        if self.highlight:
            h = etree.SubElement(rpr, q("highlight"))
            h.set(q("val"), "yellow")
        ref = etree.SubElement(r, q("footnoteReference"))
        ref.set(q("id"), str(n))
        self.fn_used.append(n)
        return r

    def replace(self, p, old: str, new: str):
        runs = [r for r in p.findall(q("r")) if old in self.text(r)]
        assert len(runs) == 1, (old[:50], len(runs))
        run = runs[0]
        full = self.text(run)
        assert full.count(old) == 1, old[:50]
        i = full.index(old)
        before, after = full[:i], full[i + len(old):]
        # общие начало и конец старого и нового фрагмента не выделяются
        plain_new = re.sub(r"\{FN\d+\}", "", new)
        k = 0
        while k < min(len(old), len(new)) and old[k] == new[k] and new[k] != "{":
            k += 1
        m = 0
        while (m < min(len(old), len(plain_new)) - k and old[-1 - m] == new[-1 - m]
               and new[-1 - m] != "}"):
            m += 1
        before += new[:k]
        middle = new[k:len(new) - m] if m else new[k:]
        after = (new[len(new) - m:] if m else "") + after
        out = []
        if before:
            out.append(self.mk_run(run, before))
        for part in re.split(r"(\{FN\d+\})", middle):
            if not part:
                continue
            fn = re.fullmatch(r"\{FN(\d+)\}", part)
            out.append(self.mk_fnref(run, int(fn.group(1))) if fn
                       else self.mk_run(run, part, mark=True))
        if after:
            out.append(self.mk_run(run, after))
        idx = list(p).index(run)
        p.remove(run)
        for j, r in enumerate(out):
            p.insert(idx + j, r)

    # ------------------------------------------------------------ шаги
    def apply_edits(self):
        for prefix, old, new in EDITS:
            self.replace(self.find(prefix), old, new)
        for old, new in CELL_EDITS:
            hits = [t for t in self.body.iter(q("t")) if t.text == old]
            assert len(hits) == 1, old
            hits[0].text = new
            if self.highlight:
                rpr = hits[0].getparent().find(q("rPr"))
                etree.SubElement(rpr, q("highlight")).set(q("val"), "yellow")

    def section(self, start: str, stop_prefixes: tuple[str, ...]):
        """Абзацы после заголовка start до первого абзаца с одним из префиксов."""
        ps = self.paras()
        i = next(k for k, p in enumerate(ps) if self.text(p) == start)
        out = []
        for p in ps[i + 1:]:
            if self.text(p).startswith(stop_prefixes) or not self.text(p).strip():
                break
            out.append(p)
        return ps[i], out

    @staticmethod
    def first_author(resp: str) -> str:
        first = resp.split(",")[0].strip()
        toks = first.split(" ")
        k = 0
        while k < len(toks) and toks[k].endswith("."):
            k += 1
        return " ".join(toks[k:]) + " " + "".join(toks[:k])

    AUTH = r"(?:(?:van der|van|Di|de) )?[A-ZА-ЯЁ][A-Za-zА-Яа-яёЁ\-]+ (?:[A-ZА-ЯЁ]\.)+"

    def rebuild_ref(self, p, num: int, head: str, rest: str):
        run = p.findall(q("r"))[0]
        for r in p.findall(q("r")):
            p.remove(r)
        p.append(self.mk_run(run, f"{num}. ", bold=False))
        p.append(self.mk_run(run, head, bold=True))
        p.append(self.mk_run(run, rest, bold=False))

    def references(self):
        _, ru = self.section("СПИСОК ЛИТЕРАТУРЫ", ("СВЕДЕНИЯ ОБ АВТОРАХ",))
        _, en = self.section("REFERENCES", ("Conflict of interest", "INFORMATION ABOUT"))
        assert len(ru) == len(en) == 33, (len(ru), len(en))
        for p in ru:
            n, body = re.match(r"(\d+)\. (.*)$", self.text(p)).groups()
            n = int(n)
            if n <= N_NORMATIVE:
                self.body.remove(p)
                continue
            if " / " in body and (" // " not in body or body.index(" / ") < body.index(" // ")):
                title, tail = body.split(" / ", 1)          # описание под заглавием
                resp = re.split(r" // |\. (?=Gaithersburg)", tail, maxsplit=1)[0]
                head = self.first_author(resp)
                rest = f" {title} / {tail}"
            else:
                m = re.match(rf"^({self.AUTH}(?:, {self.AUTH})*)( .*)$", body)
                assert m, body[:60]
                head, rest = m.group(1), m.group(2)
            self.rebuild_ref(p, n - N_NORMATIVE, head, rest)
        for p in en:
            n, body = re.match(r"(\d+)\. (.*)$", self.text(p)).groups()
            n = int(n)
            if n <= N_NORMATIVE:
                self.body.remove(p)
                continue
            m = re.match(r"^(.*?)( \(\d{4}\)\..*)$", body)
            assert m, body[:60]
            head, rest = m.group(1), m.group(2)
            if head.endswith("et al."):
                assert head.startswith("Urbina"), head
                head = URBINA_AUTHORS
            head = head.replace(" and ", ", ")
            rest = rest.replace("(in press). (in Russian).", "(in press). (in Russian)")
            self.rebuild_ref(p, n - N_NORMATIVE, head, rest)

    def renumber_citations(self):
        def one(m):
            def num(x):
                v = int(x.group(0))
                assert v > N_NORMATIVE, m.group(0)
                return str(v - N_NORMATIVE)
            return "[" + re.sub(r"\d+", num, m.group(1)) + "]"
        for t in self.body.iter(q("t")):
            if t.text and "[" in t.text:
                t.text = re.sub(r"\[(\d+(?:(?:–|, )\d+)*)\]", one, t.text)

    def reorder(self):
        ps = self.paras()
        txt = [self.text(p) for p in ps]
        kw = next(p for p in ps if self.text(p).startswith("Ключевые слова:"))
        i_title = next(k for k, s in enumerate(txt) if s.startswith("METHOD FOR DETECTING"))
        en_head = ps[i_title:i_title + 5]            # название, авторы, организация, Abstract, Key words
        assert self.text(en_head[4]).startswith("Key words:")
        blank = ps[i_title - 1]
        assert not self.text(blank).strip()
        self.body.remove(blank)
        anchor = kw
        for p in en_head:
            self.body.remove(p)
            anchor.addnext(p)
            anchor = p
        en_head[0].find(q("pPr")).find(q("spacing")).set(q("before"), "120")
        # английский текст о конфликте интересов в состав английской части по правилам не входит
        self.body.remove(self.find("Conflict of interest."))
        info_ru_head, info_ru = self.section("СВЕДЕНИЯ ОБ АВТОРАХ", ("REFERENCES",))
        info_en_head = next(p for p in self.paras() if self.text(p) == "INFORMATION ABOUT THE AUTHORS")
        for p in [info_ru_head] + info_ru:
            self.body.remove(p)
            info_en_head.addprevious(p)

    def anonymize(self):
        note = "[Сведения об авторах скрыты для рецензирования]"
        for prefix in ("Г.В. ГОЛОВЧЕНКО", "G.V. GOLOVCHENKO"):
            p = self.find(prefix)
            nxt = p.getnext()                         # организация
            self.body.remove(nxt)
            run = p.findall(q("r"))[0]
            for r in p.findall(q("r")):
                p.remove(r)
            p.append(self.mk_run(run, note if prefix[0] == "Г" else "[Author details hidden for review]",
                                 bold=False))
        p = self.find("Конфликт интересов.")
        runs = p.findall(q("r"))
        runs[1].find(q("t")).text = " [Скрыто для рецензирования.]"
        for p in self.paras():
            s = self.text(p)
            if re.match(r"\d+\. Головченко Г\.В\.", s) or re.match(r"\d+\. Golovchenko, G\.V\.", s):
                n = s.split(".")[0]
                run = p.findall(q("r"))[0]
                for r in p.findall(q("r")):
                    p.remove(r)
                p.append(self.mk_run(run, f"{n}. [Ссылка на работу автора скрыта для рецензирования]"
                                     if "Головченко" in s else f"{n}. [Self-citation hidden for review]",
                                     bold=False))
        for head in ("СВЕДЕНИЯ ОБ АВТОРАХ", "INFORMATION ABOUT THE AUTHORS"):
            h, items = self.section(head, ("INFORMATION ABOUT",))
            for p in [h] + items[:2]:
                self.body.remove(p)

    # ------------------------------------------------------------ запись
    def footnotes_xml(self) -> bytes:
        root = etree.Element(q("footnotes"), nsmap={"w": W})
        for fid, kind in ((-1, "separator"), (0, "continuationSeparator")):
            fn = etree.SubElement(root, q("footnote"))
            fn.set(q("type"), kind)
            fn.set(q("id"), str(fid))
            p = etree.SubElement(fn, q("p"))
            ppr = etree.SubElement(p, q("pPr"))
            sp = etree.SubElement(ppr, q("spacing"))
            sp.set(q("before"), "0"); sp.set(q("after"), "0")
            ind = etree.SubElement(ppr, q("ind")); ind.set(q("firstLine"), "0")
            r = etree.SubElement(p, q("r"))
            etree.SubElement(r, q(kind))
        for n in sorted(set(self.fn_used)):
            fn = etree.SubElement(root, q("footnote"))
            fn.set(q("id"), str(n))
            p = etree.SubElement(fn, q("p"))
            ppr = etree.SubElement(p, q("pPr"))
            sp = etree.SubElement(ppr, q("spacing"))
            sp.set(q("before"), "0"); sp.set(q("after"), "0")
            ind = etree.SubElement(ppr, q("ind")); ind.set(q("firstLine"), "0")
            jc = etree.SubElement(ppr, q("jc")); jc.set(q("val"), "both")

            def rpr(parent, sup=False):
                x = etree.SubElement(parent, q("rPr"))
                f = etree.SubElement(x, q("rFonts"))
                f.set(q("ascii"), "Times New Roman"); f.set(q("hAnsi"), "Times New Roman")
                etree.SubElement(x, q("b")).set(q("val"), "0")
                etree.SubElement(x, q("i")).set(q("val"), "0")
                etree.SubElement(x, q("sz")).set(q("val"), "20")
                if sup:
                    etree.SubElement(x, q("vertAlign")).set(q("val"), "superscript")
            r = etree.SubElement(p, q("r")); rpr(r, sup=True)
            etree.SubElement(r, q("footnoteRef"))
            r = etree.SubElement(p, q("r")); rpr(r)
            t = etree.SubElement(r, q("t")); t.text = " " + FOOTNOTES[n]
            t.set("{%s}space" % XML, "preserve")
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    def save(self, out: Path, core_from: Path | None = None):
        tmp = out.with_suffix(".tmpdir")
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(self.src, tmp)
        self.tree.write(str(tmp / "word" / "document.xml"), xml_declaration=True,
                        encoding="UTF-8", standalone=True)
        (tmp / "word" / "footnotes.xml").write_bytes(self.footnotes_xml())
        rels = tmp / "word" / "_rels" / "document.xml.rels"
        s = rels.read_text(encoding="utf-8")
        s = s.replace("</Relationships>",
                      '<Relationship Id="rId90" Type="http://schemas.openxmlformats.org/officeDocument/'
                      '2006/relationships/footnotes" Target="footnotes.xml"/></Relationships>')
        rels.write_text(s, encoding="utf-8")
        ct = tmp / "[Content_Types].xml"
        s = ct.read_text(encoding="utf-8")
        s = s.replace("</Types>",
                      '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-'
                      'officedocument.wordprocessingml.footnotes+xml"/></Types>')
        ct.write_text(s, encoding="utf-8")
        thumb = tmp / "docProps" / "thumbnail.jpeg"     # миниатюра от версии 3.1 — убрать
        if thumb.exists():
            thumb.unlink()
            r = tmp / "_rels" / ".rels"
            r.write_text(re.sub(r'<Relationship [^>]*thumbnail[^>]*/>', "", r.read_text(encoding="utf-8")),
                         encoding="utf-8")
        if core_from is not None:
            shutil.copy(core_from, tmp / "docProps" / "core.xml")
        if out.exists():
            out.unlink()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            names = sorted(p for p in tmp.rglob("*") if p.is_file())
            names.sort(key=lambda p: p.name != "[Content_Types].xml")
            for f in names:
                z.write(f, f.relative_to(tmp).as_posix())
        shutil.rmtree(tmp)


def build(src: Path, out: Path, *, highlight=False, anonymous=False, core_from=None):
    b = Builder(src, highlight)
    b.apply_edits()
    b.references()
    b.renumber_citations()
    b.reorder()
    if anonymous:
        b.anonymize()
    b.save(out, core_from)
    return b


if __name__ == "__main__":
    src, outdir = Path(sys.argv[1]), Path(sys.argv[2])
    anon_core = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    outdir.mkdir(parents=True, exist_ok=True)
    build(src, outdir / "statya_mgtu_ga.docx")
    build(src, outdir / "statya_mgtu_ga_izmeneniya.docx", highlight=True)
    build(src, outdir / "statya_mgtu_ga_anonim.docx", anonymous=True, core_from=anon_core)
    print("ok")
