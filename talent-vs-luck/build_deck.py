"""Вставляет слайды пункта 5 «Неожиданные выводы» в общую презентацию группы.

    python3 build_deck.py <исходная.pptx> <результат.pptx>

Новые слайды встают после слайда «Карьера: удача старта и пути» (перед «Спасибо»),
используют те же макеты (фиолетовый, красный, белый), шрифт Golos Text и цвета группы.
Графики и формулы берутся из figures/ (см. make_figures.py).
"""
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

HERE = Path(__file__).resolve().parent
FIG = HERE / 'figures'
SKILL_SCRIPTS = Path('/root/.claude/skills/synced/e70e6ec1-fcaf-491d-b69d-21c5de7dcaed_'
                     'ca48b7ba-a793-4688-8eb7-e5d893a84a53/pptx/scripts')

EMU = 914400
PURPLE, RED, INK, MUTED = '9307FE', 'FF3E35', '1A1A1A', '5E5A66'
LAYOUT = {'purple': 'slideLayout2.xml', 'red': 'slideLayout12.xml', 'white': 'slideLayout6.xml'}
AFTER_SLIDE = 'slide16.xml'   # «Карьера: удача старта и пути»

NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')


def emu(v):
    return int(round(v * EMU))


# ---------- примитивы DrawingML ----------
class Slide:
    def __init__(self, title, layout):
        self.title, self.layout = title, layout
        self.shapes, self.images, self.notes = [], [], ''
        self._id = 10

    def nid(self):
        self._id += 1
        return self._id

    def xfrm(self, x, y, w, h):
        return (f'<a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/>'
                f'<a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm>')

    def text(self, x, y, w, h, paras, anchor='t', name='Текст'):
        sid = self.nid()
        self.shapes.append(
            f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{name} {sid}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr>{self.xfrm(x, y, w, h)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            f'<a:noFill/><a:ln><a:noFill/></a:ln></p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" anchor="{anchor}" '
            f'anchorCtr="0"><a:noAutofit/></a:bodyPr><a:lstStyle/>{"".join(paras)}</p:txBody></p:sp>')

    def box(self, x, y, w, h, color, name='Рамка'):
        sid = self.nid()
        self.shapes.append(
            f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{name} {sid}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr>{self.xfrm(x, y, w, h)}<a:prstGeom prst="roundRect"><a:avLst>'
            f'<a:gd name="adj" fmla="val 12000"/></a:avLst></a:prstGeom><a:noFill/>'
            f'<a:ln w="19050"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:ln></p:spPr>'
            f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="ru-RU"/></a:p></p:txBody></p:sp>')

    def picture(self, file, x, y, w=None, h=None, descr='', scale=1.0):
        """Картинка из figures/. Без w/h — натуральный размер (300 dpi) × scale."""
        path = FIG / file
        px_w, px_h = Image.open(path).size
        if w is None and h is None:
            w, h = px_w / 300 * scale, px_h / 300 * scale
        elif h is None:
            h = w * px_h / px_w
        elif w is None:
            w = h * px_w / px_h
        rid = f'rId{3 + len(self.images)}'
        self.images.append((rid, path))
        sid = self.nid()
        self.shapes.append(
            f'<p:pic><p:nvPicPr><p:cNvPr id="{sid}" name="{escape(file)}" descr="{escape(descr, {chr(34): "&quot;"})}"/>'
            f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            f'<p:spPr>{self.xfrm(x, y, w, h)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')
        return w, h

    def xml(self):
        title = (
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Заголовок"/><p:cNvSpPr txBox="1"/>'
            '<p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr><p:spPr>'
            '<a:xfrm><a:off x="457200" y="306435"/><a:ext cx="6824400" cy="527400"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr>'
            '<p:txBody><a:bodyPr anchorCtr="0" anchor="ctr" bIns="45700" lIns="91425" spcFirstLastPara="1" '
            'rIns="91425" wrap="square" tIns="45700"><a:normAutofit/></a:bodyPr><a:lstStyle/>'
            '<a:p><a:pPr indent="0" lvl="0" marL="0" rtl="0" algn="l"><a:lnSpc><a:spcPct val="100000"/></a:lnSpc>'
            '<a:spcBef><a:spcPts val="0"/></a:spcBef><a:spcAft><a:spcPts val="0"/></a:spcAft><a:buNone/></a:pPr>'
            f'<a:r><a:rPr lang="ru-RU" sz="2800"/><a:t>{escape(self.title)}</a:t></a:r></a:p></p:txBody></p:sp>')
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<p:sld {NS}><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
                '</p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
                '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
                f'{title}{"".join(self.shapes)}</p:spTree></p:cSld>'
                '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')


def run(text, size=13, color=INK, bold=False):
    text = text.replace(' = ', '\u00a0=\u00a0')   # «p = 0,75» не разрывать переносом
    return (f'<a:r><a:rPr lang="ru-RU" sz="{int(size * 100)}" b="{int(bold)}" i="0" dirty="0">'
            f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
            '<a:latin typeface="Golos Text"/><a:ea typeface="Golos Text"/><a:cs typeface="Golos Text"/>'
            f'<a:sym typeface="Golos Text"/></a:rPr><a:t>{escape(text)}</a:t></a:r>')


def para(*runs, align='l', line=115, after=0, bullet=False):
    bu = ('<a:buClr><a:srgbClr val="9307FE"/></a:buClr><a:buFont typeface="Arial"/><a:buChar char="•"/>'
          if bullet else '<a:buNone/>')
    ind = 'marL="228600" indent="-228600"' if bullet else 'marL="0" indent="0"'
    return (f'<a:p><a:pPr {ind} algn="{align}"><a:lnSpc><a:spcPct val="{line * 1000}"/></a:lnSpc>'
            f'<a:spcBef><a:spcPts val="0"/></a:spcBef><a:spcAft><a:spcPts val="{after * 100}"/></a:spcAft>'
            f'{bu}</a:pPr>{"".join(runs)}</a:p>')


def rich(text, size=13, color=INK, accent=INK):
    """«обычный **жирный** текст» → список runs; жирные куски окрашиваются в accent."""
    out = []
    for i, part in enumerate(re.split(r'\*\*', text)):
        if part:
            out.append(run(part, size, accent if i % 2 else color, bold=bool(i % 2)))
    return out


# ---------- составные элементы в стиле слайдов группы ----------
def subtitle(s, text):
    s.text(0.65, 1.27, 7.9, 0.25, [para(run(text, 11, MUTED))], name='Подзаголовок')


def stat_row(s, x, y, w, h, number, text, color):
    """Рамка: крупное число слева, пояснение справа (как на слайде «Карьера»)."""
    s.box(x, y, w, h, color)
    s.text(x + 0.2, y, 1.35, h, [para(run(number, 30, color, bold=True))], anchor='ctr', name='Число')
    s.text(x + 1.6, y + 0.08, w - 1.8, h - 0.16, [para(*rich(text, 13))], anchor='ctr', name='Пояснение')


def stat_card(s, x, y, w, h, number, text, color):
    """Рамка: крупное число сверху, пояснение снизу, по центру (как на слайде «Наука»)."""
    s.box(x, y, w, h, color)
    s.text(x + 0.12, y + 0.12, w - 0.24, 0.55, [para(run(number, 30, color, bold=True), align='ctr')],
           anchor='ctr', name='Число')
    s.text(x + 0.15, y + 0.72, w - 0.3, h - 0.82, [para(*rich(text, 12), align='ctr')], name='Пояснение')


# ---------- содержание ----------
def slides():
    out = []

    s = Slide('Кто на пьедестале?', 'purple')
    subtitle(s, '1000 участников: 10 талантов (p = 0,75) и 990 обычных (p = 0,6), тест из 20 вопросов')
    s.picture('c1_podium.png', 0.55, 1.6, descr='Сколько человек в среднем набирает от 14 до 20 баллов: '
              'в призовой зоне обычных участников больше, чем талантов')
    s.picture('f1_count.png', 0.62, 4.45, descr='M(число набравших k) = N·C(n,k)·p^k·q^(n−k)')
    stat_row(s, 4.95, 1.62, 4.35, 1.0, '74%', 'побед достаются **обычным** участникам', RED)
    stat_row(s, 4.95, 2.77, 4.35, 1.0, '×35', 'у **таланта** шанс победить выше, чем у обычного, — но обычных в 99 раз больше',
             PURPLE)
    stat_row(s, 4.95, 3.92, 4.35, 1.0, '1,5', 'таланта из 10 в среднем попадают **в топ-10**, остальные — за кадром',
             PURPLE)
    s.notes = (
        'Неожиданный вывод №1: на пьедестале в основном не таланты.\n'
        'Берём ту же модель, что и раньше: 1000 участников, 10 талантов с p = 0,75 и 990 обычных с p = 0,6, '
        'тест из 20 вопросов. На графике — сколько человек в среднем набирает каждое число баллов, это N·C(n,k)·p^k·q^(n−k) '
        '(шкала логарифмическая). Каждый талант по отдельности сильнее, но обычных в 99 раз больше, и в призовой зоне '
        '(17 баллов и выше) их в среднем около 16 против двух-трёх талантов.\n'
        'Точный расчёт через распределение максимума (ничьи — жребием): победитель оказывается обычным участником '
        'с вероятностью 0,74. Отдельный талант выигрывает в 35 раз чаще отдельного обычного участника, но этого не хватает, '
        'чтобы перевесить их численность. В топ-10 в среднем попадают лишь 1,5 таланта, остальные 8,5 остаются незамеченными.')
    out.append(s)

    s = Slide('Проклятие победителя', 'red')
    subtitle(s, 'Победитель — это ещё и самый везучий, поэтому его балл завышает способности')
    s.picture('c2_curse.png', 0.55, 1.6, descr='Доля верных ответов у победителя и его настоящая способность '
              'в зависимости от длины теста: при 20 вопросах 93% против 64%')
    stat_card(s, 4.95, 1.62, 2.08, 1.3, '93%', 'видим: доля верных ответов **победителя**', PURPLE)
    stat_card(s, 7.22, 1.62, 2.08, 1.3, '64%', 'на самом деле: его **способность** p', RED)
    s.text(4.95, 3.12, 4.35, 0.25, [para(run('Муавр–Лаплас: лучший из N = 1000 одинаковых, p = 0,6', 11, MUTED))])
    s.picture('f2_ml.png', 4.95, 3.42, descr='k_max ≈ np + z·√(npq), где 1 − Φ(z) = 1/N')
    s.picture('f2_ml_num.png', 4.95, 4.27, descr='k_max ≈ 12 + 3,09·√4,8 ≈ 18,8 из 20')
    s.notes = (
        'Вывод №2: проклятие победителя. Победителем становится тот, кому повезло сильнее всех, поэтому его результат '
        'систематически завышает способности.\n'
        'При 20 вопросах победитель отвечает в среднем на 93% вопросов, а его настоящая вероятность правильного ответа '
        'в среднем всего 64%: ведь в трёх случаях из четырёх это обычный участник с p = 0,6.\n'
        'Откуда такой высокий балл? Даже если все 1000 участников одинаковы, лучший результат можно оценить по '
        'интегральной теореме Муавра–Лапласа: k_max ≈ np + z·√(npq), где z находим из условия 1 − Φ(z) = 1/N, то есть '
        'в среднем ровно один человек из N забирается так высоко. При p = 0,6 получаем 12 + 3,09·2,19 ≈ 18,8 из 20 — '
        'это 94% при способности 60% (точный расчёт даёт 18,4).\n'
        'На графике видно, что с ростом длины теста завышение тает: разброс доли верных ответов падает как √(pq/n). '
        'Но при 20 вопросах оно огромно.')
    out.append(s)

    s = Slide('Регрессия к среднему', 'white')
    subtitle(s, 'Топ-10 первого тура пишет второй тест той же длины (средние по 100 000 симуляций)')
    s.picture('c3_regression.png', 0.55, 1.6, descr='Средний балл топ-10 в первом и втором туре: '
              'падение с 17,5 до 12,4, победитель — с 18,6 до 12,8')
    s.text(4.95, 1.65, 4.35, 0.3, [para(run('Балл = способность + удача', 14, INK, bold=True))])
    s.picture('f3_reg.png', 4.95, 2.02, descr='X = np + ε, Mε = 0')
    s.picture('f3_reg2.png', 4.95, 2.62, descr='M(ε₁ | победил) > 0, M(ε₂ | победил) = 0')
    stat_card(s, 4.95, 3.3, 2.08, 1.55, '0,7%', 'шанс, что победитель **выиграет снова**', RED)
    stat_card(s, 7.22, 3.3, 2.08, 1.55, '26%', 'шанс, что победитель вообще **талант**', PURPLE)
    s.notes = (
        'Вывод №3: регрессия к среднему. Представим балл как способность плюс удача: X = np + ε, где удача в среднем '
        'нулевая.\n'
        'Отбирая лучших в первом туре, мы отбираем и способных, и везучих: у них ε₁ заметно больше нуля. Но во втором туре '
        'удача новая, и для тех же людей M(ε₂) = 0. Поэтому топ-10 в среднем падает с 17,5 до 12,4 балла, а победитель — '
        'с 18,6 до 12,8, почти до уровня обычного участника.\n'
        'Победитель первого тура выигрывает и второй лишь в 0,7% случаев, хотя талантом он оказывается в 26% случаев. '
        'Это не «звёздная болезнь» и не расслабленность: так ведёт себя любая величина, в которой есть случайная часть. '
        'Если бы все участники были одинаковы, шанс повторной победы был бы ровно 1/1000.')
    out.append(s)

    s = Slide('Ошибка выжившего', 'purple')
    subtitle(s, '1000 трейдеров 10 дней подряд угадывают рынок, подбрасывая честную монетку')
    s.picture('c4_traders.png', 0.55, 1.6, descr='Сколько трейдеров угадали все дни подряд: '
              '1000, 500, 250, … и к десятому дню в среднем 0,98')
    s.picture('f4_exp.png', 4.95, 1.66, descr='M(угадали все 10) = 1000·2^(−10) ≈ 0,98')
    s.picture('f4_atleast.png', 4.95, 2.2, descr='P(хотя бы один) = 1 − (1 − 2^(−10))^1000 ≈ 0,62')
    s.box(4.95, 2.88, 4.35, 2.02, PURPLE)
    s.text(5.15, 3.0, 4.0, 0.3, [para(*rich('А если среди них есть **один талант** (p = 0,75)?', 12))])
    s.picture('f4_bayes.png', 5.08, 3.38, descr='P(талант | 10 из 10) = 0,75^10 / (0,75^10 + 999·2^(−10)) ≈ 0,05')
    s.text(5.15, 4.2, 4.0, 0.55, [para(*rich('Герой интервью «10 из 10» почти наверняка просто **везунчик**', 12,
                                             accent=RED))])
    s.notes = (
        'Вывод №4: ошибка выжившего. 1000 трейдеров 10 дней угадывают направление рынка честной монеткой. Каждый день '
        'выбывает примерно половина, и в среднем 1000·2^(−10) ≈ 0,98 человека угадают все 10 дней; вероятность, что такой '
        'найдётся хотя бы один, — 0,62.\n'
        'Именно у него возьмут интервью о «безошибочной стратегии», а 999 остальных в кадр не попадут. Так же, как '
        'самолёты Вальда, которые не вернулись, или бросившие университет, которые не стали миллиардерами.\n'
        'Добавим в группу одного настоящего таланта, который угадывает с вероятностью 0,75. По формуле Байеса шанс, '
        'что герой с результатом 10 из 10 — именно он, всего около 5%. Выдающийся результат, найденный среди множества '
        'попыток, почти ничего не доказывает.')
    out.append(s)

    s = Slide('Так судить ли победителей?', 'red')
    subtitle(s, 'Главный вопрос: честно ли награждать победителей и считать проигравших менее достойными?')
    cards = [
        (0.65, PURPLE, 'Модель'),
        (3.6, RED, 'Наш опыт'),
        (6.55, PURPLE, 'Как честнее'),
    ]
    for x, color, head in cards:
        s.box(x, 1.65, 2.75, 2.45, color)
        s.text(x + 0.2, 1.8, 2.35, 0.3, [para(run(head, 14, color, bold=True))])
    s.picture('f5_sigma.png', 0.85, 2.18, h=0.62, descr='σ(X/n) = √(pq/n)')
    s.text(0.85, 2.95, 2.35, 1.05, [para(*rich('Чем короче испытание, тем **больше удачи** в результате', 12))])
    s.text(3.8, 2.2, 2.35, 1.8, [
        para(*rich('Экзамен в один день — **короткий тест**', 12), after=6),
        para(*rich('Рейтинг за весь семестр — **длинный**, в нём удача усредняется', 12)),
    ])
    s.text(6.75, 2.2, 2.35, 1.8, [
        para(run('длиннее испытание', 12), bullet=True, after=4),
        para(run('несколько туров', 12), bullet=True, after=4),
        para(run('право на пересдачу', 12), bullet=True, after=4),
        para(run('оценка по сумме попыток', 12), bullet=True),
    ])
    s.box(0.65, 4.27, 8.65, 0.68, RED)
    s.text(0.85, 4.27, 8.25, 0.68, [para(*rich('Наградить победителя — можно. Списать проигравшего '
                                              'по одной попытке — **нельзя**', 14, accent=RED), align='ctr')],
           anchor='ctr')
    s.notes = (
        'Главный вопрос. Наша модель показывает: результат одного испытания складывается из способностей и удачи, '
        'а доля удачи падает как 1/√n. Значит, победа — это свидетельство таланта, но не доказательство, а поражение — '
        'тем более не приговор.\n'
        'По нашему опыту: экзамен в один день похож на тест из 20 вопросов — одна неудачная задача может всё перевернуть. '
        'Накопительный рейтинг за семестр — это сотни «вопросов», и в нём удача усредняется.\n'
        'На наш взгляд, награждать победителей справедливо: результат реален, и стимул важен. Несправедливо делать '
        'по одной попытке выводы о человеке. Честная система — длинные испытания, несколько туров, право на пересдачу '
        'и оценка по сумме попыток.')
    out.append(s)
    return out


# ---------- сборка пакета ----------
def notes_xml(text, slide_name):
    paras = ''.join(
        '<a:p><a:pPr marL="0" indent="0"><a:buNone/></a:pPr>'
        f'<a:r><a:rPr lang="ru-RU" sz="1200" dirty="0"/><a:t>{escape(line)}</a:t></a:r></a:p>'
        for line in text.split('\n'))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<p:notes {NS}><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
            '</p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
            '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image"/><p:cNvSpPr><a:spLocks noGrp="1" noRot="1" '
            'noChangeAspect="1"/></p:cNvSpPr><p:nvPr><p:ph type="sldImg" idx="2"/></p:nvPr></p:nvSpPr>'
            '<p:spPr><a:xfrm><a:off x="381000" y="685800"/><a:ext cx="6096000" cy="3429000"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:sp>'
            '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Notes"/><p:cNvSpPr txBox="1"/><p:nvPr>'
            '<p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="685800" y="4343400"/>'
            '<a:ext cx="5486400" cy="4114800"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            f'<p:txBody><a:bodyPr/><a:lstStyle/>{paras}</p:txBody></p:sp>'
            '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>')


def build(src, dst):
    work = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(src) as z:
        z.extractall(work)
    ct_path = work / '[Content_Types].xml'
    media = work / 'ppt' / 'media'
    next_img = max(int(m.group(1)) for p in media.iterdir() if (m := re.match(r'image(\d+)\.', p.name))) + 1

    after = AFTER_SLIDE
    for s in slides():
        res = subprocess.run([sys.executable, str(SKILL_SCRIPTS / 'add_slide.py'), str(work),
                              LAYOUT[s.layout], '--after', after], capture_output=True, text=True, check=True)
        name = re.search(r'(slide\d+\.xml)', res.stdout.split('from')[0]).group(1)
        num = re.search(r'\d+', name).group(0)
        (work / 'ppt' / 'slides' / name).write_text(s.xml(), encoding='utf-8')

        rels = [f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                f'relationships/slideLayout" Target="../slideLayouts/{LAYOUT[s.layout]}"/>',
                f'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                f'relationships/notesSlide" Target="../notesSlides/notesSlide{num}.xml"/>']
        for rid, path in s.images:
            target = f'image{next_img}.png'
            next_img += 1
            shutil.copy(path, media / target)
            rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                        f'relationships/image" Target="../media/{target}"/>')
        (work / 'ppt' / 'slides' / '_rels' / f'{name}.rels').write_text(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(rels) +
            '</Relationships>', encoding='utf-8')

        notes_dir = work / 'ppt' / 'notesSlides'
        (notes_dir / f'notesSlide{num}.xml').write_text(notes_xml(s.notes, name), encoding='utf-8')
        (notes_dir / '_rels' / f'notesSlide{num}.xml.rels').write_text(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'notesMaster" Target="../notesMasters/notesMaster1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            f'slide" Target="../slides/{name}"/></Relationships>', encoding='utf-8')
        ct = ct_path.read_text(encoding='utf-8')
        ct = ct.replace('</Types>', '<Override ContentType="application/vnd.openxmlformats-officedocument.'
                        f'presentationml.notesSlide+xml" PartName="/ppt/notesSlides/notesSlide{num}.xml"/></Types>')
        ct_path.write_text(ct, encoding='utf-8')
        after = name
        print(f'{name}: {s.title}')

    dst = Path(dst)
    dst.unlink(missing_ok=True)
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(ct_path, '[Content_Types].xml')
        for p in sorted(work.rglob('*')):
            if p.is_file() and p != ct_path:
                z.write(p, p.relative_to(work).as_posix())
    shutil.rmtree(work)
    print('сохранено:', dst)


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
