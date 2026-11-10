"""Модель процесса оборотного обслуживания узкофюзеляжного ВС.

Все числовые параметры — условные допущения для синтетического эксперимента.
Их нужно сверить с шаблонами технологических графиков (например, АС «КОБРА»)
и с эксплуатационной постановкой соавтора. Источник каждого параметра — этот файл.

Версия 3: порядок бортпитания и типовые длительности согласованы с модельным графом
Г.В. Головченко и К.А. Асмоловской (9 операций, 12 связей); исключение при заправке
с пассажирами на борту требует независимого подтверждения мер безопасности (SAF);
нормы длительности рассчитываются по справочным значениям, а не по полям проверяемого
сообщения. Сопоставление с графом — ../../podacha/sopostavlenie-modeley.md.
"""
from __future__ import annotations

from dataclasses import dataclass

START = "START"
END = "END"

MANUAL = "MANUAL"   # отметка с мобильного рабочего места исполнителя
AUTO = "AUTO"       # автоматический источник (телеметрия оборудования)
SYSTEM = "SYSTEM"   # другая информационная система (DCS — загрузочная ведомость)


@dataclass(frozen=True)
class Operation:
    code: str
    name_ru: str
    name_en: str
    kind: str                 # "interval" (START и END) или "instant" (только END)
    manual_role: str | None   # роль, отмечающая операцию вручную
    auto_source: str | None   # автоматический источник, если стоянка им оснащена
    auto_availability: float  # доля оборотов, где автоматический источник доступен


OPERATIONS: dict[str, Operation] = {op.code: op for op in [
    Operation("ONB", "Постановка ВС на стоянку (колодки установлены)",
              "In-block (chocks on)", "instant", "RAMP", "VDGS", 0.8),
    Operation("GPU", "Наземный источник питания: подключение / отключение",
              "Ground power unit: connect / disconnect", "interval", "RAMP", "GPU", 0.6),
    Operation("PBB", "Телетрап: стыковка / отстыковка",
              "Passenger boarding bridge: dock / retract", "interval", "PBB_OP", "PBB", 0.7),
    Operation("DEB", "Высадка пассажиров", "Passenger deboarding",
              "interval", "GATE", None, 0.0),
    Operation("UNL", "Выгрузка багажа и груза", "Baggage and cargo unloading",
              "interval", "RAMP", None, 0.0),
    Operation("CLN", "Уборка салона", "Cabin cleaning",
              "interval", "CLEAN", None, 0.0),
    Operation("CAT", "Обслуживание бортовым питанием", "Catering",
              "interval", "CATER", None, 0.0),
    Operation("SAF", "Подтверждение мер безопасности при заправке с пассажирами",
              "Confirmation of safety measures for fuelling with passengers on board",
              "instant", "SUPV", None, 0.0),
    Operation("FUEL", "Заправка топливом", "Refuelling",
              "interval", "FUEL", "METER", 0.7),
    Operation("WAT", "Обслуживание водой и санузлами", "Potable water and lavatory service",
              "interval", "RAMP", None, 0.0),
    Operation("LOD", "Загрузка багажа и груза", "Baggage and cargo loading",
              "interval", "RAMP", None, 0.0),
    Operation("BRD", "Посадка пассажиров", "Passenger boarding",
              "interval", "GATE", None, 0.0),
    Operation("LDS", "Выпуск загрузочной ведомости", "Final loadsheet issued",
              "instant", None, "DCS", 1.0),
    Operation("DRC", "Закрытие дверей и люков", "Doors and holds closed",
              "instant", "RAMP", None, 0.0),
    Operation("OFB", "Уборка колодок, начало буксировки", "Off-block (pushback)",
              "instant", "RAMP", "VDGS", 0.8),
]}

INTERVAL_OPS = [c for c, o in OPERATIONS.items() if o.kind == "interval"]
SERVICE_OPS = ["DEB", "UNL", "CLN", "CAT", "FUEL", "WAT", "LOD", "BRD"]


@dataclass(frozen=True)
class Precedence:
    pred: tuple[str, str]
    succ: tuple[str, str]
    waiver: str | None = None   # "safety": снимается при подтверждённой заправке с пассажирами


# Технологические зависимости: событие succ не может наступить раньше события pred.
PRECEDENCE: list[Precedence] = [
    Precedence(("ONB", END), ("GPU", START)),
    Precedence(("ONB", END), ("PBB", START)),
    Precedence(("ONB", END), ("UNL", START)),
    Precedence(("ONB", END), ("WAT", START)),
    Precedence(("ONB", END), ("FUEL", START)),
    Precedence(("PBB", START), ("DEB", START)),
    Precedence(("DEB", END), ("CLN", START)),
    Precedence(("PBB", START), ("CAT", START)),  # как в графе [Головченко]: после установки трапа
    Precedence(("DEB", END), ("FUEL", START), waiver="safety"),
    Precedence(("UNL", END), ("LOD", START)),
    Precedence(("CLN", END), ("BRD", START)),
    Precedence(("CAT", END), ("BRD", START)),
    Precedence(("FUEL", END), ("BRD", START), waiver="safety"),
    Precedence(("LOD", END), ("LDS", END)),
    Precedence(("BRD", END), ("LDS", END)),
    *[Precedence((op, END), ("DRC", END)) for op in ["CLN", "CAT", "FUEL", "WAT", "LOD", "BRD"]],
    Precedence(("LDS", END), ("DRC", END)),
    Precedence(("DRC", END), ("PBB", END)),
    Precedence(("DRC", END), ("GPU", END)),
    Precedence(("PBB", END), ("OFB", END)),
    Precedence(("GPU", END), ("OFB", END)),
    Precedence(("DRC", END), ("OFB", END)),
]

# Вариант правил по графу [Головченко, Асмоловская]: уборка — после установки трапа (может
# идти во время высадки), обслуживание водой — после высадки, посадка — после обслуживания
# водой и погрузки багажа. Зависимость заправки и посадки сохраняется: её снятие требует
# мер безопасности, которые в планировочной модели не рассматриваются.
_ALT_REPLACE = {(("DEB", END), ("CLN", START)): (("PBB", START), ("CLN", START)),
                (("ONB", END), ("WAT", START)): (("DEB", END), ("WAT", START))}
PRECEDENCE_ALT: list[Precedence] = [
    Precedence(*_ALT_REPLACE.get((c.pred, c.succ), (c.pred, c.succ)), waiver=c.waiver)
    for c in PRECEDENCE] + [Precedence(("WAT", END), ("BRD", START)),
                            Precedence(("LOD", END), ("BRD", START))]


def precedence(ctrl_model: str = "base") -> list[Precedence]:
    return PRECEDENCE_ALT if ctrl_model == "alt" else PRECEDENCE


# События, по которым сравниваются ручная отметка и автоматический источник.
CROSS_EVENTS = [("ONB", END), ("GPU", START), ("GPU", END), ("PBB", START), ("PBB", END),
                ("FUEL", START), ("FUEL", END), ("OFB", END)]

# Решения о готовности, принимаемые по данным (информационный статус для диспетчера,
# а не разрешение физического действия).
# D1 — готовность к посадке пассажиров, D2 — завершение всех операций обслуживания.
D1_OPS = ["CLN", "CAT", "FUEL"]           # FUEL — если исключение не подтверждено
D2_EVENTS = [(op, END) for op in SERVICE_OPS]   # все операции обслуживания завершены


@dataclass(frozen=True)
class Params:
    """Параметры генератора и правил контроля (минуты, если не указано иное)."""
    # --- генератор: ВС и рейс
    seats: tuple[int, ...] = (150, 158, 174, 180)
    planned_turnaround: float = 50.0
    fuel_capacity_kg: float = 19000.0
    # --- генератор: отметки и доставка сообщений
    late_mark_share: float = 0.15     # доля ручных отметок, сделанных с запаздыванием
    late_mark_mean: float = 1.5       # среднее запаздывание такой отметки
    late_mark_cap: float = 10.0
    clock_skew_sd: float = 0.1        # погрешность часов терминала
    net_delay_median: float = 0.05    # медианная задержка доставки (3 с)
    net_delay_sigma: float = 1.0
    retry_share: float = 0.03         # повторная доставка с тем же msg_id
    # --- генератор: штатные отклонения (вероятность на оборот)
    p_offline: float = 0.30           # терминал без связи, отложенная доставка
    offline_range: tuple[float, float] = (3.0, 25.0)
    p_correction: float = 0.15        # ошибка ручного ввода времени и её исправление
    corr_error_range: tuple[float, float] = (5.0, 30.0)
    corr_delay_range: tuple[float, float] = (1.0, 10.0)
    p_operational_delay: float = 0.20
    p_safety_fuelling: float = 0.25   # заправка с пассажирами на борту (с мерами безопасности)
    p_unmodeled_variant: float = 0.05 # допустимый вариант технологии, не отражённый в модели
    gen_model: str = "alt"            # порядок операций: "alt" — граф [Головченко] (основной
    ctrl_model: str = "alt"           # с версии 3.1), "base" — модель версии 3.0
    # --- правила контроля
    window_before: float = 60.0       # окно рейса до планового прибытия
    window_after: float = 180.0       # окно рейса после планового вылета
    future_tol: float = 0.5           # допустимое опережение времени события над временем приёма
    stale_max: float = 15.0           # Δmax: предельная «давность» сообщения
    order_tol: float = 0.5            # END не раньше START той же операции
    prec_tol: float = 2.0             # допуск технологической последовательности
    dur_tol: float = 1.0              # допуск минимальной длительности
    cross_tol: float = 5.0            # допуск расхождения ручной и автоматической отметки
    fuel_rel_tol: float = 0.01        # допуск расхождения количества топлива
    grace: float = 5.0                # W: ожидание исправления до тревоги о противоречии
    missing_horizon: float = 15.0     # H: ожидание недостающего сообщения до тревоги
    # --- модель доверия (версия 3; значения версии 2 — "manual" и False)
    safety_trust: str = "confirmed"   # исключение по заправке: "confirmed" — только при
                                      # подтверждении SAF с другого рабочего места
    trusted_norms: bool = True        # нормы длительности — по справочным значениям рейса
    min_dur_share: float = 0.5        # α: минимальная длительность = α × типовая (допущение)
    # --- последствия
    check_time: float = 3.0           # длительность ручной проверки по тревоге, мин


# Типовые длительности, мин: по модельному сценарию [Головченко, Асмоловская] (уборка 15,
# бортпитание 12, обслуживание водой 8, погрузка багажа 18); выгрузки в сценарии нет (10 —
# допущение). Это не нормы: минимально допустимая длительность — их доля α (min_dur_share).
TYPICAL = {"UNL": 10.0, "CLN": 15.0, "CAT": 12.0, "WAT": 8.0, "LOD": 18.0}


def min_duration(op: str, pax: int | None, fuel_kg: float | None, seats: int,
                 share: float = 0.5) -> float:
    """Минимальная технологически возможная длительность операции (допущение).

    Высадка и посадка — по предельному темпу 25 и 18 пасс./мин, заправка — 1 мин на
    подготовку и 1000 кг/мин; остальные операции — доля α от типовой длительности."""
    if op == "DEB":
        return (pax if pax is not None else seats) / 25.0
    if op == "BRD":
        return (pax if pax is not None else seats) / 18.0
    if op == "FUEL":
        return 1.0 + (fuel_kg if fuel_kg is not None else 0.0) / 1000.0
    return share * TYPICAL.get(op, 0.0)
