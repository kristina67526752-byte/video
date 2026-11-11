"""Тексты и таблицы рукописи версии 3.3. Все числа — из results/summary.json."""
from __future__ import annotations

import math

FOOTNOTES_EXTRA = {
    6: "Об утверждении Требований по обеспечению безопасности значимых объектов критической "
       "информационной инфраструктуры Российской Федерации: приказ ФСТЭК России от 25.12.2017 "
       "№ 239.",
    8: "Методика оценки угроз безопасности информации: методический документ. Утв. ФСТЭК России "
       "05.02.2021. П. 5.1.5, приложение 8.",
}
DELETE: list[str] = ["Дальнейшая работа:"]


def pc(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}".replace(".", ",")


def nm(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def pe(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}"


class D:
    def __init__(self, S: dict):
        self.S = S
        self.m = {r["method"]: r for r in S["main"]}
        self.sub = {(r["method"], r["subtype"]): r for r in S["by_subtype"]}
        self.typ = {(r["method"], r["vtype"]): r for r in S["by_type"]}
        self.work = {r["method"]: r for r in S["workload"]}
        self.timing = {r["method"]: r for r in S["timing"]}
        self.sev = {r["method"]: r for r in S["severity"]}
        self.cal = S["calibrated"]
        self.camp = {(r["scenario"], r["method"], r["rule"]): r for r in S["campaign"]["summary"]}

    def kv(self, method: str) -> int:
        r = self.sev[method]
        return r["К_n"] + r["В_n"]

    def cerr(self, method: str, q: float) -> float:
        return next(r["false_decisions_KV"] for r in self.S["check_error"]
                    if r["method"] == method and abs(r["q_miss"] - q) < 1e-9)

    def ctime(self, method: str, ct: float) -> dict:
        return next(r for r in self.S["check_time"] if r["method"] == method
                    and abs(r["check_time"] - ct) < 1e-9)

    def mag(self, vt: str, value: float, method: str = "P") -> float:
        return next(r["recall"] for r in self.S["magnitude"] if r["vtype"] == vt
                    and abs(r["value"] - value) < 1e-9 and r["method"] == method)

    def sens(self, factor: str, value: float, method: str = "P") -> dict:
        return next(r for r in self.S["sensitivity"] if r["factor"] == factor
                    and abs(r["value"] - value) < 1e-9 and r["method"] == method)

    def cross(self, gen: str, rules: str) -> dict:
        return next(r for r in self.S["cross_model"] if r["generator"] == gen and r["rules"] == rules)

    def budget(self, b: float, method: str) -> dict:
        return next(r for r in self.S["budgets"] if abs(r["budget"] - b) < 1e-9
                    and r["method"] == method)


def _rng(vals, d=0, f=nm):
    lo, hi = min(vals), max(vals)
    return f(lo, d) if f(lo, d) == f(hi, d) else f"{f(lo, d)}–{f(hi, d)}"


def facts(S: dict) -> dict:
    """Производные величины, общие для русского и английского текста."""
    d = D(S)
    P, B3, B2, PV = d.m["P"], d.m["B3"], d.m["B2"], d.m["P_v2"]
    n_int = P["n_pos_V1_7"]
    f = {
        "fpr": P["fpr"], "int": P["recall_V1_7"], "sub": P["recall_subst"],
        "share_c": P["n_construct"] / n_int, "share_r": P["n_reach"] / n_int,
        "share_s": P["n_subst"] / n_int, "n_sub": P["n_subst"],
        "sub_B3": B3["recall_subst"], "sub_B2": B2["recall_subst"], "sub_PV": PV["recall_subst"],
        "v1b": d.sub[("P", "V1b")]["recall"],
        "lat_min": P["lat_int_min"], "lat_med": P["lat_int_median"], "lat_p90": P["lat_int_p90"],
        "before_d1": d.timing["P"]["before_d1"], "after_ofb": d.timing["P"]["after_ofb"],
        "W": d.cal["P"]["grace"], "H": d.cal["P"]["missing_horizon"],
    }
    f["gap"] = f["sub"] - f["sub_B3"]
    f["overlap"] = (P["subst_seed_min"] <= B3["subst_seed_max"]
                    and B3["subst_seed_min"] <= P["subst_seed_max"])
    q = d.camp[("GATE_QUIET", "P", "K3")]
    qc = d.camp[("GATE_QUIET", "P", "CUSUM")]
    f.update(quiet_k3=q["detected_share"], quiet_cusum=qc["detected_share"],
             quiet_h=q["hours_to_detect_median"], q_quiet=S["campaign"]["q_quiet"])
    return f


def gap_phrase(f: dict) -> tuple[str, str]:
    g = 100 * f["gap"]
    if f["overlap"]:
        return (f"различие с монитором ограничений при одинаковых правилах ({nm(abs(g))} п. п.) "
                "лежит в пределах разброса между выборками",
                f"the difference from the constraint monitor given the same rules ({abs(g):.1f} pp) "
                "is within the spread between samples")
    if g > 0:
        return (f"преимущество перед монитором ограничений при одинаковых правилах — {nm(g)} п. п.",
                f"the advantage over the constraint monitor given the same rules is {g:.1f} pp")
    return (f"монитор ограничений при одинаковых правилах выявил на {nm(-g)} п. п. больше",
            f"the constraint monitor given the same rules detected {-g:.1f} pp more")


# ---------------------------------------------------------------- фрагментные правки
def edits(S: dict) -> list[tuple[str, str, str]]:
    return [
        ("Цель работы — разработать такой метод",
         "Цель работы — разработать такой метод и в модельном эксперименте сравнить его с "
         "проверкой полей и временных меток и с монитором декларативных ограничений. Гипотезы: "
         "учёт технологических зависимостей повышает долю обнаруживаемых нарушений при приемлемой "
         "доле ложных тревог; модель доверия и удержание решений снижают число ложных решений о "
         "готовности;",
         "Цель работы — описать такой метод и в модельном эксперименте сравнить его с проверкой "
         "полей и временных меток и с монитором декларативных ограничений, которому переданы те "
         "же правила. Гипотезы: учёт технологических зависимостей повышает долю обнаруживаемых "
         "нарушений при приемлемой доле ложных тревог; удержание решений снижает число ложных "
         "решений о готовности;"),
        ("Сопоставление с ближайшими подходами дано в табл. 1.",
         "что метод не выявляет и при каких допущениях.",
         "что метод не выявляет и при каких допущениях. Преимущество перед известным монитором "
         "ограничений при одинаковых правилах не предполагается заранее и проверяется "
         "экспериментом."),
        ("Таблица 1. Сопоставление", "(по полным текстам источников)",
         "(по текстам источников; [22] — по описанию модели в литературе)"),
        ("Table 1. Comparison", "(based on full texts)",
         "(based on source texts; [22] from secondary descriptions)"),
        ("Примечание. + — есть;", "− — в источнике не найдено.",
         "− — в источнике не найдено. Оценка предлагаемого метода — самооценка авторов."),
        ("Note. + present;", "− not found in the source.",
         "− not found in the source. The rating of the proposed method is the authors' "
         "self-assessment."),
        ("Объект защиты.",
         "По данным формируются статусы D1 — готовность к посадке пассажиров и D2 — завершение "
         "обслуживания; это сведения для диспетчера, а не разрешение действия.",
         "По данным формируются статусы: D1 — готовность к посадке пассажиров (завершены все "
         "операции, предшествующие посадке по модели: уборка, бортпитание, обслуживание водой, "
         "погрузка багажа и заправка, если меры безопасности не подтверждены) и D2 — завершение "
         "обслуживания; это сведения для диспетчера, а не разрешение действия."),
        ("Примечание. АИЭП —",
         "Подсистема контроля и справочные значения рейса — доверенные. Требуемая оперативность — "
         "секунды и минуты.",
         "Подсистема контроля и справочные значения рейса (из DCS) приняты доверенными; это "
         "допущение — их искажение методом не выявляется. Тревога формируется не раньше окна W "
         "или H после несоответствия."),
        ("Note. GPU —",
         "The monitoring subsystem and flight reference values are trusted. Required timeliness — "
         "seconds to minutes.",
         "The monitoring subsystem and flight reference values (from the DCS) are assumed trusted; "
         "their tampering is not detected. An alarm is raised no earlier than window W or H after "
         "the inconsistency."),
        ("Модель нарушителя.", "Сервер контроля и правила доверенные.",
         "Сервер контроля, правила и справочные значения рейса приняты доверенными. В терминах "
         "Методики оценки угроз безопасности информации ФСТЭК России{FN8} это внутренние "
         "нарушители: А1 и А2 — авторизованные пользователи с базовыми возможностями, а при "
         "захвате чужого терминала или канала — с базовыми повышенными; А3 — группа лиц, "
         "действующих по единому плану. Системные администраторы и администраторы безопасности, "
         "а также нарушители со средними и высокими возможностями в модель не входят — это её "
         "граница, а не утверждение об их отсутствии."),
        ("Модель доверия.",
         "конкретную роль закрепляет эксплуатант в руководстве по организации наземного "
         "обслуживания",
         "конкретную роль закрепляет эксплуатант в руководстве по организации наземного "
         "обслуживания. Независимым такое подтверждение делают отдельная учётная запись, "
         "аутентификация и журналирование действий; введённое в той же системе со слов экипажа, "
         "оно защищает от захвата терминала заправщика, но не от захвата обеих учётных записей "
         "или сговора (V7b)"),
        ("Условная шкала последствий", "К — объявлена", "С1 — объявлена"),
        ("Условная шкала последствий", "; В — при незавершённой", "; С2 — при незавершённой"),
        ("Условная шкала последствий", "; С — ложного решения нет", "; С3 — ложного решения нет"),
        ("Условная шкала последствий", "; Н — нарушение обнаружено", "; С4 — нарушение обнаружено"),
        ("Если тревога выдана раньше", "; модель доверия не применяется.",
         ". Правила доверия — подтверждение SAF и сверка со справочными значениями — выражаются "
         "ограничениями предшествования с условием по данным и потому тоже переданы Б3. Б3 — не "
         "сторонний инструмент, а тот же программный код в другом режиме: от П он отличается "
         "единым буфером β вместо окон W и H и тем, что ожидаемые обязательства не удерживают "
         "решение."),
        ("Сутки работы аэропорта:", "(V7a). Сценарии без атаки",
         f"(V7a). Отдельно рассмотрен «тихий» нарушитель, подделывающий отметку агента выхода в "
         f"{pc(S['campaign']['q_quiet'], 0)} % оборотов. Сценарии без атаки"),
        ("Использование генеративного искусственного интеллекта.",
         "Постановку задачи, модель процесса, допущения и интерпретацию результатов определяли и "
         "проверяли авторы",
         "Постановку задачи определили авторы; модель процесса и допущения сформированы с помощью "
         "ассистента по графу [21] и нормативным документам и на данных эксплуатации не "
         "проверялись"),
        ("1Regional Information", "Center “Pulkovo”", "Center Pulkovo"),
        ("Gleb V. Golovchenko", "Center “Pulkovo”", "Center Pulkovo"),
        ("Veronika V. Gorbatko", "Center “Pulkovo”", "Center Pulkovo"),
        ("5. Mashoshin", "(2026). Protection",
         "(2026). Zashchita korporativnykh informatsionnykh sistem aviapredpriyatiy ot atak "
         "nulevogo dnya: podkhod k obnaruzheniyu vtorzheniy na osnove glubokogo "
         "nekontroliruyemogo obucheniya [Protection"),
        ("5. Mashoshin", "learning. Civil Aviation High Technologies,",
         "learning]. Nauchnyy vestnik MGTU GA [Civil Aviation High Technologies],"),
        ("20. Kondratyeva", "(2026). A calculation",
         "(2026). Metodika rascheta kolichestvennykh parametrov operativnogo tsikla ekspluatatsii "
         "vozdushnogo sudna na osnove deystvuyushchikh normativov [A calculation"),
        ("20. Kondratyeva", "standards. Civil Aviation High Technologies,",
         "standards]. Nauchnyy vestnik MGTU GA [Civil Aviation High Technologies],"),
        ("21. Golovchenko", "(2026). Aircraft ground",
         "(2026). Avtomatizatsiya nazemnogo obsluzhivaniya vozdushnykh sudov: sravnitelnyy analiz "
         "intellektualnykh sistem i chislennyy eksperiment [Aircraft ground"),
        ("21. Golovchenko",
         "experiment. Scientific Bulletin of The State Scientific Research Institute of Civil "
         "Aviation,",
         "experiment]. Nauchnyy vestnik GosNII GA [Scientific Bulletin of The State Scientific "
         "Research Institute of Civil Aviation],"),
    ]


def cell_edits(S: dict) -> list[tuple[str, str]]:
    return []


# ---------------------------------------------------------------- абзацы целиком
def paragraphs(S: dict) -> list[tuple[str, str | None, str]]:
    d = D(S)
    f = facts(S)
    P, B3, B2, B1, PV = d.m["P"], d.m["B3"], d.m["B2"], d.m["B1"], d.m["P_v2"]
    cp, c3 = d.cal["P"], d.cal["B3"]
    gap_ru, gap_en = gap_phrase(f)
    kv = {m: d.kv(m) for m in ("B1", "B2", "B3", "P_v2", "P")}
    n_viol = d.sev["P"]["n"]
    wP = d.work["P"]
    c1, c10 = d.ctime("P", 1.0), d.ctime("P", 10.0)
    sc = S["safety_check"]
    early = sc["true_d1"] - sc["v2"]["d1_time"]
    camp = d.camp
    att = ["GATE", "FUEL", "SAFETY", "CLEAN"]
    flt = ["CLOCK", "NET", "METER"]
    a_share = [camp[(s, "P", "K3")]["detected_share"] for s in att]
    a_h = [camp[(s, "P", "K3")]["hours_to_detect_median"] for s in att]
    f_share = [camp[(s, "P", "K3")]["detected_share"] for s in flt]
    f_h = [camp[(s, "P", "K3")]["hours_to_detect_median"] for s in flt]
    none_k3 = camp[("none", "P", "K3")]["false_incidents_per_day"]
    none_cu = camp[("none", "P", "CUSUM")]["false_incidents_per_day"]
    clock_other = camp[("CLOCK", "P", "K3")]["false_incidents_per_day"]
    gate_p = camp[("GATE", "P", "K3")]["false_ready_before_detect_mean"]
    gate_b = camp[("GATE", "B2", "K3")]["false_ready_before_detect_mean"]
    b25P, b25B = d.budget(0.025, "P"), d.budget(0.025, "B3")
    b10P, b10B = d.budget(0.10, "P"), d.budget(0.10, "B3")
    ppv1, ppv01 = P["ppv_V1_7_0.01"], P["ppv_V1_7_0.001"]
    grid = S["grid_P"]                                  # сетка П из gh_integrity/run.py
    sym = {"prec_tol": "δ_{p}", "dur_tol": "δ_{d}", "cross_tol": "δ_{c}", "stale_max": "Δ_{max}",
           "grace": "W", "missing_horizon": "H"}
    on_edge = [sym[k] for k, v in grid.items() if cp[k] in (v[0], v[-1])]
    edge = (f"На границе перебранной сетки оказались {', '.join(on_edge)}, то есть оптимум по "
            "этим допускам не локализован. " if on_edge else "")

    abstract = (
        " Решения о готовности воздушного судна к посадке пассажиров и о завершении его "
        "обслуживания принимаются по отметкам исполнителей с мобильных рабочих мест и сообщениям "
        "оборудования; ошибочная или подложная отметка создаёт ложное представление о готовности. "
        "Предложен метод контроля целостности этих данных по технологическим зависимостям "
        "операций: он проверяет последовательность и полноту событий, минимальные длительности и "
        "согласованность источников, принимает поля, ослабляющие контроль, только при независимом "
        "подтверждении, удерживает решение о готовности до устранения несоответствий и по "
        "совокупности оборотов формирует подозрение на источник данных. Метод оценён в модельном эксперименте на синтетических журналах (14 000 "
        "оборотов, восемь видов нарушений); параметры генератора — допущения, не опирающиеся на "
        f"данные эксплуатации. При доле ложных тревог {pc(f['fpr'])} % выявлено {pc(f['int'])} % "
        f"нарушений целостности, но этот показатель задан составом выборки: {pc(f['share_c'], 0)} % "
        f"нарушений обнаруживаются по построению, {pc(f['share_r'], 0)} % лежат вне возможностей "
        f"метода. В содержательных случаях, где исход зависит от правил и допусков, метод выявил "
        f"{pc(f['sub'])} % нарушений, монитор декларативных ограничений с теми же правилами — "
        f"{pc(f['sub_B3'])} %, проверка полей и времени — {pc(f['sub_B2'])} %; {gap_ru}. Подлог с "
        f"подавлением подлинной отметки выявлен в {pc(f['v1b'], 0)} % случаев; правдоподобная "
        "ранняя отметка исполнителя, знающего нормы, и согласованная подмена нескольких "
        f"источников не выявляются. Тревога формируется не раньше чем через {nm(f['lat_min'], 0)} "
        f"мин после нарушения (медиана {nm(f['lat_med'], 0)} мин), и до фактической готовности к "
        f"посадке выявлено {pc(f['before_d1'], 0)} % нарушений. При моделировании суток "
        "подозрение на источник возникало и при атаках на терминал, и при неисправностях часов, "
        f"связи и счётчика; нарушитель, подделывающий {pc(f['q_quiet'], 0)} % отметок, выявлялся "
        f"в {pc(f['quiet_k3'], 0)} % суток. Метод применим как контроль качества данных, а не как "
        "средство обнаружения атак; результаты требуют проверки на обезличенных журналах.")

    abstract_en = (
        " Decisions on aircraft readiness for boarding and on completion of ground handling are "
        "taken from staff completion marks and equipment messages; an erroneous or forged mark "
        "creates a false picture of readiness. A method is proposed for checking the integrity of "
        "these data against the technological dependencies of operations: it checks the sequence "
        "and completeness of events, minimum durations and the consistency of sources, accepts "
        "fields that relax the checks only if independently confirmed, holds the readiness "
        "decision until inconsistencies are resolved, and raises a suspicion about a data source "
        "across turnarounds. The method was evaluated in a model "
        "experiment on synthetic logs (14,000 turnarounds, eight violation types); the generator "
        f"parameters are assumptions not based on operational data. At a false alarm rate of "
        f"{pe(f['fpr'])}%, {pe(f['int'])}% of integrity violations were detected, but this figure "
        f"is set by the sample composition: {pe(f['share_c'], 0)}% of violations are detectable by "
        f"construction and {pe(f['share_r'], 0)}% are beyond the reach of the method. In the "
        f"substantive cases, where the outcome depends on rules and tolerances, the method "
        f"detected {pe(f['sub'])}% of violations, a declarative constraint monitor with the same "
        f"rules {pe(f['sub_B3'])}%, and field and time checks {pe(f['sub_B2'])}%; {gap_en}. A "
        f"forgery with the genuine mark suppressed was detected in {pe(f['v1b'], 0)}% of cases; a "
        "plausible early mark by an informed insider and a coordinated substitution of several "
        f"sources are not detected. An alarm is raised no earlier than {f['lat_min']:.0f} min "
        f"after the violation (median {f['lat_med']:.0f} min), and {pe(f['before_d1'], 0)}% of "
        "violations were detected before actual readiness for boarding. In simulated days a "
        f"source suspicion arose for both attacks and equipment faults; an intruder forging {pe(f['q_quiet'], 0)}% of marks was detected on "
        f"{pe(f['quiet_k3'], 0)}% of days. The method is a data quality control rather than an "
        "attack detector; the results need validation on anonymised operational logs.")

    experiment = (
        " Все данные синтетические; параметры генератора — допущения, приведённые в исходном "
        "коде, и на данные эксплуатации они не опираются. Штатные отклонения: 15 % ручных отметок "
        "запаздывают (в среднем на 1,5 мин); в 30 % оборотов терминал теряет связь (3 мин и "
        "экспоненциально распределённая добавка со средним 9 мин, не более 90 мин); 3 % сообщений "
        "доставляются повторно; в 15 % оборотов отметка вводится с ошибкой 5–30 мин и в 90 % "
        "таких случаев исправляется (через 1 мин и добавку со средним 4 мин), а в 10 % остаётся в "
        "данных; в 20 % затягивается операция; в 25 % заправка идёт с пассажирами, причём в 5 % "
        "таких заправок подтверждение мер безопасности вводится после начала заправки, а в 2 % "
        "не вводится; в 5 % обслуживание водой начинается до окончания высадки — вариант, не "
        "учтённый моделью. Нарушение считается обнаруженным, если тревога выдана не раньше его "
        "внесения и отсутствует у «двойника» — того же оборота без нарушения. Виды нарушений "
        "целостности (все, кроме V5a) разделены на три группы: обнаруживаемые по построению "
        "(V1a, V3, V4, V7a — дубль, пропажа сообщения или признак без подтверждения), лежащие вне "
        "возможностей метода (V6, V7b, V8) и содержательные (V1b, V2, V5b, V7c), по которым и "
        "сравниваются методы.")

    calib = (
        "Допуски подбирались на калибровочной выборке (600 штатных оборотов и по 100 оборотов с "
        "нарушениями V1–V5) по максимуму полноты при доле ложных тревог не выше 5 %: для П — "
        f"δ_{{p}} = {cp['prec_tol']}, δ_{{d}} = {cp['dur_tol']}, δ_{{c}} = {cp['cross_tol']}, "
        f"Δ_{{max}} = {cp['stale_max']}, W = {cp['grace']}, H = {cp['missing_horizon']} мин; для "
        f"Б3 — δ_{{p}} = {c3['prec_tol']}, δ_{{d}} = {c3['dur_tol']}, δ_{{c}} = {c3['cross_tol']}, "
        f"Δ_{{max}} = {c3['stale_max']}, β = {c3['grace']} мин. {edge}Проверка — на 10 "
        "независимых выборках по 600 штатных оборотов и по 100 оборотов каждого из восьми видов "
        "(14 000 оборотов), а также на данных варианта модели с уборкой после высадки. Интервалы "
        "в таблицах отражают только случайность генератора при заданных параметрах, но не "
        "неопределённость самих параметров; поэтому приведён и разброс между выборками.")

    res1 = (
        f" При доле ложных тревог {pc(P['fpr'])} % (между выборками "
        f"{pc(P['fpr_seed_min'])}–{pc(P['fpr_seed_max'])} %) метод П выявил {pc(P['recall_V1_7'])} % "
        f"нарушений целостности, монитор Б3 — {pc(B3['recall_V1_7'])} % при {pc(B3['fpr'])} %, Б2 — "
        f"{pc(B2['recall_V1_7'])} %, Б1 — {pc(B1['recall_V1_7'])} %. Общий показатель определяется "
        f"составом выборки: {pc(f['share_c'], 0)} % нарушений обнаруживаются по построению "
        f"(П — {pc(P['recall_construct'])} %), {pc(f['share_r'], 0)} % лежат вне возможностей метода "
        f"(П — {pc(P['recall_reach'])} %). В содержательных случаях (n = {P['n_subst']}) П "
        f"выявил {pc(P['recall_subst'])} % (между выборками "
        f"{pc(P['subst_seed_min'])}–{pc(P['subst_seed_max'])} %), Б3 — {pc(B3['recall_subst'])} % "
        f"({pc(B3['subst_seed_min'])}–{pc(B3['subst_seed_max'])} %), Б2 — {pc(B2['recall_subst'])} %: "
        f"{gap_ru}. По подвидам (рис. 2) П и Б3 близки: подлог с подавлением подлинной отметки "
        f"(V1b) — {pc(d.sub[('P', 'V1b')]['recall'], 0)} и {pc(d.sub[('B3', 'V1b')]['recall'], 0)} %, "
        f"сдвиг метки окончания — {pc(d.sub[('P', 'V2-end')]['recall'], 0)} и "
        f"{pc(d.sub[('B3', 'V2-end')]['recall'], 0)} %, нарушение порядка только в данных (V5b) — "
        f"{pc(d.sub[('P', 'V5b')]['recall'], 0)} и {pc(d.sub[('B3', 'V5b')]['recall'], 0)} %. V6, V7b "
        "и V8, включая сценарий из введения — раннюю отметку исполнителя, знающего нормы, — не "
        f"выявлены. При бюджете ложных тревог 2,5 % полнота V1–V5 — {pc(b25P['recall'])} % у П и "
        f"{pc(b25B['recall'])} % у Б3 (ложных тревог на проверке {pc(b25P['fpr'])} и "
        f"{pc(b25B['fpr'])} %), при бюджете 10 % — {pc(b10P['recall'])} и {pc(b10B['recall'])} %.")

    res_mag = (
        "Обнаружение определяется величиной нарушения относительно допусков. Ложная отметка "
        f"окончания, поставленная, когда выполнено 10 % операции, выявляется в "
        f"{pc(d.mag('V1', 0.1), 0)} % случаев, 40 % — в {pc(d.mag('V1', 0.4), 0)} %, 55 % и более — "
        f"не более чем в {pc(max(d.mag('V1', 0.55), d.mag('V1', 0.7), d.mag('V1', 0.85)), 0)} %; сдвиг "
        f"метки на 4 мин — в {pc(d.mag('V2', 4), 0)} %, на 12 мин — в {pc(d.mag('V2', 12), 0)} %; "
        f"нарушение порядка на 5 мин — в {pc(d.mag('V5', 5), 0)} %, на 10 мин — в "
        f"{pc(d.mag('V5', 10), 0)} % (допуск δ_{{p}} = {cp['prec_tol']} мин). Нарушитель, знающий "
        "допуски, может оставаться в их пределах.")

    res_trust = (
        "Правила доверия закрывают обход через поля, ослабляющие контроль: ложный признак заправки "
        f"с пассажирами (V7a) П и Б3 выявили в {pc(d.sub[('P', 'V7a')]['recall'], 0)} % случаев "
        f"против {pc(d.sub[('P_v2', 'V7a')]['recall'], 0)} % без этих правил, занижение количества "
        f"(V7c) — в {pc(d.sub[('P', 'V7c')]['recall'], 0)} % против "
        f"{pc(d.sub[('P_v2', 'V7c')]['recall'], 0)} %; подложное подтверждение (V7b) не выявляется. "
        "Монитор Б3 с теми же правилами даёт тот же результат: вклад — в формулировке правил, а "
        "не в алгоритме. В контрольном опыте вариант без правил доверия объявил готовность на "
        f"{nm(early)} мин раньше фактической без тревоги. Обход значим там, где заправка "
        f"заканчивается последней из операций перед посадкой, — в "
        f"{pc(sc['share_fuel_last_normal'], 0)} % штатных оборотов.")

    res_dec = (
        f"Ложных решений категорий С1 и С2 у П — {kv['P']} на {n_viol} оборотов с нарушениями, у "
        f"Б3 — {kv['B3']}, у Б2 — {kv['B2']}, у варианта без правил доверия — {kv['P_v2']}. Оценка "
        "держится на допущении о безошибочной проверке: если проверка пропускает нарушение с "
        f"вероятностью 0,5, у П будет {nm(d.cerr('P', 0.5), 0)}, если всегда — "
        f"{nm(d.cerr('P', 1.0), 0)} (у Б3 — {nm(d.cerr('B3', 1.0), 0)}). На штатных оборотах — "
        f"около {nm(wP['alarms_per_day'], 0)} оборотов с тревогой и "
        f"{nm(wP['checks_per_day'], 0)} проверок решений в сутки: "
        f"{nm(c1['check_minutes_per_day'], 0)}–{nm(c10['check_minutes_per_day'], 0)} мин работы при "
        f"1–10 мин на проверку; задержка D1 — в среднем {nm(wP['d1_delay_mean'])} мин, 95-й "
        f"процентиль — {nm(wP['d1_delay_p95'])} мин при 3 мин на проверку. Оперативность "
        f"ограничена окнами ожидания: ни одна тревога по нарушению не выдана раньше чем через "
        f"{nm(f['lat_min'], 0)} мин, медиана — {nm(f['lat_med'], 0)} мин, 90-й процентиль — "
        f"{nm(f['lat_p90'], 0)} мин при обороте около 55 мин. До фактической готовности к посадке "
        f"П выявил {pc(f['before_d1'])} % нарушений, после ухода ВС — {pc(f['after_ofb'])} %.")

    res_cross = (
        f" При одинаковой модели данных и правил доля ложных тревог П — "
        f"{pc(d.cross('alt', 'alt')['fpr'])} % (основная модель) и "
        f"{pc(d.cross('base', 'base')['fpr'])} % (вариант с уборкой после высадки), при расхождении "
        f"— {pc(d.cross('alt', 'base')['fpr'])} и {pc(d.cross('base', 'alt')['fpr'])} % при близкой "
        "полноте. Метод применим только с моделью, согласованной с утверждённым технологическим "
        "графиком.")

    quiet = camp[("GATE_QUIET", "P", "K3")]
    quiet_c = camp[("GATE_QUIET", "P", "CUSUM")]
    res_flow = (
        f" При атаке в 70 % оборотов подозрение на захваченный терминал при K = 3 возникало в "
        f"{_rng(a_share, 0, pc)} % суток за {_rng(a_h, 1)} ч; у Б2 — ни разу. «Тихий» нарушитель "
        f"({pc(f['q_quiet'], 0)} % отметок) выявлялся в {pc(quiet['detected_share'], 0)} % суток "
        f"правилом K = 3 и в {pc(quiet_c['detected_share'], 0)} % — CUSUM и давал "
        f"{nm(quiet['false_ready_before_detect_mean'])} ложного решения в сутки. Неисправности "
        f"часов, связи и счётчика давали подозрение в {_rng(f_share, 0, pc)} % суток за "
        f"{_rng(f_h, 1)} ч — быстрее и надёжнее, чем атаки; спешащие часы давали {nm(clock_other, 2)} "
        f"подозрения в сутки на терминалы других исполнителей (без неисправности — "
        f"{nm(none_k3, 2)}), неисправный счётчик — подозрение на заправщика. CUSUM давал меньше "
        f"ложных подозрений ({nm(none_cu, 2)} против {nm(none_k3, 2)} в сутки), но и реже выявлял "
        "атаки (табл. 5): ни одно из правил не лучше другого, и правило «K за окно» — простой "
        "вариант, а не вклад работы. Ложных решений до подозрения при атаке на агента выхода — "
        f"{nm(gate_p)} в сутки у П и {nm(gate_b)} у Б2.")

    s0, sw = d.sens("grace_W", 0), d.sens("grace_W", 10)
    res_sens = (
        f"Чувствительность (три выборки): без окна ожидания доля ложных тревог П — "
        f"{pc(s0['fpr'])} %, при 45 % запаздывающих отметок — "
        f"{pc(d.sens('late_mark_share', 0.45)['fpr'])} %, при 20 % неучтённых вариантов — "
        f"{pc(d.sens('p_unmodeled_variant', 0.2)['fpr'])} %.")

    disc1 = (
        "Гипотезы подтверждаются частично. Учёт технологических зависимостей повышает полноту "
        "относительно проверки полей и времени, но эту полноту дают сами ограничения: известный "
        f"монитор декларативных ограничений с теми же правилами выявил {pc(f['sub_B3'])} % "
        f"содержательных нарушений против {pc(f['sub'])} % у предложенного метода. Новизны "
        "алгоритма относительно такого монитора эксперимент не показывает; результат работы — "
        "набор правил для данных о наземном обслуживании, включая правила доверия к полям, "
        "ослабляющим контроль, и количественные границы применимости. Удержание решений уменьшает "
        f"число ложных решений ({kv['P']} против {kv['B3']} у Б3) лишь при действенной ручной "
        "проверке. Нарушения в пределах допусков и правдоподобные отметки осведомлённого "
        "исполнителя не выявляются, а подозрение на источник возникает при неисправностях не "
        "реже, чем при атаках. Поэтому метод следует позиционировать как контроль качества "
        "данных, дополняющий меры защиты, а не как средство обнаружения атак.")

    disc2 = (
        "Предлагается ступенчатое реагирование. Тревога по обороту запускает лёгкую проверку и "
        f"удерживает решение. Тревога приходится в среднем на каждый {round(1 / P['fpr'])}-й "
        f"оборот; если нарушения есть в 1 % оборотов, с ними связано около {pc(ppv1, 0)} % тревог, "
        f"если в 0,1 % — около {pc(ppv01)} %, поэтому одиночная тревога — не инцидент. Подозрение "
        "на источник запускает проверку терминала: часов, связи, оборудования, журналов доступа. "
        "Блокировка, перепроверка данных и, для объектов КИИ, информирование об инциденте по "
        "Федеральному закону № 187-ФЗ целесообразны после подтверждения вмешательства, что "
        "соответствует рекомендациям по реагированию на инциденты [25]. Удержание решений и "
        "блокировка сами создают вектор атаки на доступность: вбрасывая противоречивые отметки, "
        "нарушитель может задерживать решения и вызывать подозрения на чужие терминалы. Поэтому "
        "удержание ограничено временем проверки, а автоматическая блокировка не рекомендуется. "
        "Соответствие метода конкретным мерам требований ФСТЭК России не оценивалось.")

    disc3 = (
        "Аутентификация сообщений защищает от подмены в канале, но не подтверждает истинность "
        "события: захваченный терминал отправляет ложные сообщения со своими действительными "
        "учётными данными. Подпись сообщений, счётчики и привязка к устройству — базовые меры: "
        "они закрывают подмену в канале и повтор (V3), и метод их не заменяет, а рассчитан на "
        "сообщения, подлинные по происхождению, но ложные по содержанию. При захвате терминала "
        "(А1, А2) нужны технологический контроль и независимые подтверждения. Согласованный "
        "захват нескольких источников (А3, V6, V7b), искажение справочных данных и правдоподобная "
        "отметка осведомлённого исполнителя (V8) по содержанию данных не обнаруживаются; против "
        "них применимы меры вне метода — выборочный контроль на месте в случайные моменты, "
        "нераскрытие и смена допусков, разделение ролей и каналов, — что согласуется с "
        "требованием Приложения 17 защищать критически важные системы и данные. Оценивать нужно "
        "и последствия необнаруженных нарушений [18].")

    limits = (
        "Ограничения работы. 1. Эксперимент замкнут на себя: данные синтетические, параметры "
        "генератора, время проверки и нормы длительности — допущения, не опирающиеся на данные "
        "эксплуатации. 2. Данные и правила построены по одной модели процесса; при её расхождении "
        "с технологией ложных тревог в разы больше. 3. Общий показатель полноты зависит от "
        "состава выборки, а величины нарушений заданы генератором. 4. Монитор Б3 — тот же "
        "программный код в другом режиме, а не независимый инструмент. 5. Ручная проверка в "
        "основном расчёте безошибочна. 6. Категории последствий условны. 7. Не моделировались "
        "привилегированный нарушитель, нарушитель, знающий порог K, атаки на доступность и "
        "несколько одновременных нарушений.")

    concl = (
        "Описан метод контроля целостности данных о наземном обслуживании ВС, сопоставляющий "
        "сообщения с технологией обслуживания, принимающий поля, ослабляющие контроль, только при "
        "независимом подтверждении, удерживающий решения о готовности до устранения "
        "несоответствий и формирующий подозрение на источник данных. В модельном эксперименте на "
        f"14 000 синтетических оборотах при {pc(f['fpr'])} % ложных тревог он выявил "
        f"{pc(f['int'])} % нарушений целостности, а в содержательных случаях — {pc(f['sub'])} % "
        f"против {pc(f['sub_B3'])} % у монитора декларативных ограничений с теми же правилами и "
        f"{pc(f['sub_B2'])} % у проверки полей и времени: {gap_ru}. Подлог с подавлением подлинной "
        f"отметки выявлялся в {pc(f['v1b'], 0)} %; нарушения в пределах допусков, согласованная "
        "подмена и правдоподобная отметка осведомлённого исполнителя не выявлялись; до "
        f"фактической готовности к посадке обнаружено {pc(f['before_d1'], 0)} % нарушений. "
        "Подозрение на источник возникает и при атаках, и при неисправностях. Метод применим как "
        "контроль качества данных при модели процесса, согласованной с утверждённым "
        "технологическим графиком; параметры и выводы требуют проверки на данных эксплуатации.")

    note4 = (
        " Полнота — доля обнаруженных нарушений; в скобках — 95 %-й интервал по Уилсону (только "
        "случайность генератора). Все нарушения — все виды, кроме V5a; содержательные — V1b, V2, "
        "V5b, V7c; по построению — V1a, V3, V4, V7a; вне возможностей — V6, V7b, V8. Ложные "
        f"решения — число оборотов категорий С1 и С2 из {n_viol} с нарушениями при безошибочной "
        "ручной проверке; проверки — на штатных оборотах при 180 оборотах в сутки.")
    note4_en = (
        " Recall is the share of detected violations; 95% Wilson intervals in brackets (generator "
        "randomness only). All violations: all types except V5a; substantive: V1b, V2, V5b, V7c; "
        "by construction: V1a, V3, V4, V7a; out of reach: V6, V7b, V8. False decisions are "
        f"turnarounds of categories C1 and C2 (С1, С2) out of {n_viol:,} with violations, assuming an "
        "error-free manual check; checks are on normal turnarounds, 180 per day.")

    return [
        ("Аннотация.", "Аннотация.", abstract),
        ("Abstract.", "Abstract.", abstract_en),
        ("Эксперимент.", "Эксперимент.", experiment),
        ("Допуски подбирались", None, calib),
        ("Уровень оборота (табл. 4).", "Уровень оборота (табл. 4).", res1),
        ("Обнаружение определяется величиной", None, res_mag),
        ("Модель доверия закрывает обход", None, res_trust),
        ("Ложных решений категорий", None, res_dec),
        ("Согласованность модели процесса.", "Согласованность модели процесса.", res_cross),
        ("Уровень потока оборотов (табл. 5).", "Уровень потока оборотов (табл. 5).", res_flow),
        ("Чувствительность (", None, res_sens),
        ("Гипотезы подтверждаются частично.", None, disc1),
        ("Предлагается ступенчатое реагирование.", None, disc2),
        ("Аутентификация сообщений защищает", None, disc3),
        ("Ограничения работы.", None, limits),
        ("Предложен метод контроля целостности", None, concl),
        ("Примечание. Полнота —", "Примечание.", note4),
        ("Note. Recall is", "Note.", note4_en),
    ]


# ---------------------------------------------------------------- таблицы
def table4(S: dict) -> list[list[list[str] | None]]:
    d = D(S)
    head = [["Метод /", "Method"], ["Ложные тревоги, % /", "False alarms, %"],
            ["Все нарушения, % /", "All violations, %"],
            ["Содержа-", "тельные, % /", "Substantive, %"],
            ["По постро-", "ению, % /", "By construc-", "tion, %"],
            ["Вне возмож-", "ностей, % /", "Out of reach, %"],
            ["Ложных решений С1 и С2 /", "False decisions"],
            ["Проверок в сутки /", "Checks per day"]]
    rows = [head]
    names = {"B1": ["Б1 / B1"], "B2": ["Б2 / B2"], "B3": ["Б3 / B3"],
             "P_v2": ["П без правил доверия /", "P w/o trust rules"], "P": ["П / P"]}
    for m in ("B1", "B2", "B3", "P_v2", "P"):
        r = d.m[m]
        checks = "—" if m == "B1" else nm(d.work[m]["checks_per_day"], 0)
        rows.append([
            names[m],
            [pc(r["fpr"]), f"({pc(r['fpr_lo'])}–{pc(r['fpr_hi'])})"],
            [pc(r["recall_V1_7"]), f"({pc(r['recall_V1_7_lo'])}–{pc(r['recall_V1_7_hi'])})"],
            [pc(r["recall_subst"]), f"({pc(r['recall_subst_lo'])}–{pc(r['recall_subst_hi'])})"],
            [pc(r["recall_construct"])], [pc(r["recall_reach"])],
            [str(d.kv(m))], [checks]])
    return rows


def table5(S: dict) -> list[list[list[str] | None]]:
    d = D(S)
    c = d.camp

    def cell(r, hours=True):
        if r["detected_share"] <= 0:
            return ["0"]
        h = r["hours_to_detect_median"]
        return [pc(r["detected_share"], 0)] + ([f"({nm(h)})"] if hours and not math.isnan(h) else [])
    rows: list = [None]                       # шапка без изменений
    order = ["GATE", "FUEL", "SAFETY", "CLEAN", "GATE_QUIET", "CLOCK", "NET", "METER"]
    label = {"GATE_QUIET": [f"Атака: агент выхода, {pc(S['campaign']['q_quiet'], 0)} % отметок /",
                            f"Attack: gate agent, {pe(S['campaign']['q_quiet'], 0)}% of marks"]}
    out = []
    for s in order:
        p3, pc_, b3 = c[(s, "P", "K3")], c[(s, "P", "CUSUM")], c[(s, "B2", "K3")]
        out.append([label.get(s), cell(p3), cell(pc_), cell(b3),
                    [f"{nm(p3['false_ready_before_detect_mean'])} / "
                     f"{nm(b3['false_ready_before_detect_mean'])}"],
                    [nm(p3["prevented_by_block_mean"])],
                    [nm(p3["false_incidents_per_day"], 2)],
                    [nm(p3["manual_after_block_mean"])]])
    n = c[("none", "P", "K3")]
    out.append([None, ["—"], ["—"], ["—"], ["—"], ["—"],
                [nm(n["false_incidents_per_day"], 2)], [nm(n["manual_after_block_mean"])]])
    # шапку не трогаем: fill_table вызывается со всеми строками, None в ячейке = без изменений
    head = [None] * 8
    return [head] + out
