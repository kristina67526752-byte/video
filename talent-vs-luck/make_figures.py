"""Графики и формулы для слайдов пункта 5 (в стиле общей презентации).

Цвета как на слайдах группы: фиолетовый — таланты/сильный, красный — обычные/слабый.
Формулы — картинки в стиле LaTeX (matplotlib mathtext, шрифт STIX).
"""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.offsetbox import AnchoredOffsetbox, HPacker, TextArea
from scipy.stats import binom

import compute as c

OUT = Path(__file__).with_name('figures')
OUT.mkdir(exist_ok=True)

PURPLE, RED = '#9307FE', '#FF3E35'
INK, MUTED, GRID = '#1A1A1A', '#5E5A66', '#E6E3EC'
LIGHT_PURPLE = '#E9D6FF'

plt.rcParams.update({
    'font.family': 'Golos Text',
    'font.size': 10,
    'axes.edgecolor': MUTED,
    'axes.labelcolor': MUTED,
    'xtick.color': MUTED,
    'ytick.color': MUTED,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'mathtext.fontset': 'stix',
    'axes.formatter.use_locale': False,
})
DPI = 300


def comma(x, nd=1):
    return f'{x:.{nd}f}'.replace('.', ',')


def tex_num(x, nd=1):
    """Число с десятичной запятой без лишнего пробела в mathtext."""
    return f'{x:.{nd}f}'.replace('.', '{,}')


def save(fig, name):
    fig.savefig(OUT / name, dpi=DPI, transparent=True)
    plt.close(fig)


# ---------- формулы ----------
FORMULA_PT = 17


def formula(name, parts, size=FORMULA_PT):
    """parts: список (mathtext, цвет). Склеивает куски по базовой линии."""
    fig = plt.figure(figsize=(12, 2))
    boxes = [TextArea(t, textprops=dict(color=col, size=size)) for t, col in parts]
    pack = HPacker(children=boxes, align='baseline', pad=0, sep=0)
    anchored = AnchoredOffsetbox(loc='center', child=pack, frameon=False,
                                  bbox_to_anchor=(0.5, 0.5), bbox_transform=fig.transFigure)
    fig.add_artist(anchored)
    fig.savefig(OUT / name, dpi=DPI, transparent=True, bbox_inches='tight', pad_inches=0.04)
    plt.close(fig)


def make_formulas():
    n = 20
    pt, em = c.exact_winner(n)
    formula('f1_count.png', [
        (r'$M(\mathrm{число\ набравших\ }k) = N\cdot C_n^k\,p^k q^{\,n-k}$', INK)])
    formula('f2_ml.png', [
        (r'$k_{\max}\approx np+z\sqrt{npq},\qquad 1-\Phi(z)=\dfrac{1}{N}$', INK)])
    k, z = c.ml_best_of_equal(20, 0.6, 1000)
    formula('f2_ml_num.png', [
        (r'$k_{\max}\approx 12+3{,}09\cdot\sqrt{4{,}8}\approx $', INK),
        (r'$\mathbf{' + tex_num(k) + r'}$', RED),
        (r'$\ \mathrm{из}\ 20$', INK)])
    formula('f3_reg.png', [
        (r'$X = np+\varepsilon,\qquad M\varepsilon=0$', INK)])
    formula('f3_reg2.png', [
        (r'$M(\varepsilon_1\mid\mathrm{победил})>0,\quad'
         r'M(\varepsilon_2\mid\mathrm{победил})=0$', INK)], size=16)
    e, p1, pb = c.traders()
    formula('f4_exp.png', [
        (r'$M(\mathrm{угадали\ все\ 10}) = 1000\cdot 2^{-10}\approx $', INK),
        (r'$\mathbf{' + tex_num(e, 2) + r'}$', RED)], size=16)
    formula('f4_atleast.png', [
        (r'$P(\mathrm{хотя\ бы\ один}) = 1-\left(1-2^{-10}\right)^{1000}\approx $', INK),
        (r'$\mathbf{' + tex_num(p1, 2) + r'}$', RED)], size=16)
    formula('f4_bayes.png', [
        (r'$P(\mathrm{талант}\mid 10\ \mathrm{из}\ 10)='
         r'\dfrac{0{,}75^{10}}{0{,}75^{10}+999\cdot 2^{-10}}\approx $', INK),
        (r'$\mathbf{' + tex_num(pb, 2) + r'}$', RED)], size=14)
    formula('f5_sigma.png', [
        (r'$\sigma\left(\dfrac{X}{n}\right)=\sqrt{\dfrac{pq}{n}}$', INK)])


# ---------- графики ----------
def chart_podium():
    """Сколько человек в среднем набирает k баллов из 20 (зона призёров)."""
    n = 20
    ks = np.arange(14, n + 1)
    talents = c.N_T * binom.pmf(ks, n, c.P_T)
    ordinary = c.N_O * binom.pmf(ks, n, c.P_O)
    fig, ax = plt.subplots(figsize=(4.15, 2.75))
    fig.subplots_adjust(left=0.1, right=0.99, top=0.86, bottom=0.19)
    w = 0.38
    ax.bar(ks - w / 2, talents, w, color=PURPLE, label='таланты (10 чел.)')
    ax.bar(ks + w / 2, ordinary, w, color=RED, label='обычные (990 чел.)')
    ax.set_yscale('log')
    ax.set_ylim(0.01, 200)
    ax.set_yticks([0.01, 0.1, 1, 10, 100])
    ax.set_yticklabels(['0,01', '0,1', '1', '10', '100'])
    ax.set_xticks(ks)
    ax.set_xlabel('баллов из 20')
    ax.set_ylabel('человек (в среднем)')
    ax.axvspan(16.5, 20.5, color=LIGHT_PURPLE, alpha=0.45, lw=0, zorder=0)
    ax.text(18.5, 110, 'призовая зона', ha='center', va='center', color=PURPLE, size=10, weight='semibold')
    for x, t, o in zip(ks, talents, ordinary):
        if 17 <= x <= 19:
            ax.text(x - w / 2, t * 1.25, comma(t), ha='center', va='bottom', size=7.5, color=PURPLE)
            ax.text(x + w / 2, o * 1.25, comma(o), ha='center', va='bottom', size=7.5, color=RED)
    ax.legend(frameon=False, loc='upper left', bbox_to_anchor=(0, 1.2), ncol=2, fontsize=9,
              handlelength=1, columnspacing=1)
    ax.grid(axis='y', color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    save(fig, 'c1_podium.png')


def chart_curse():
    """Результат победителя против его настоящей способности при росте длины теста."""
    ns = np.unique(np.round(np.geomspace(10, 1000, 40)).astype(int))
    score, ability = [], []
    for n in ns:
        pt, em = c.exact_winner(int(n))
        score.append(em / n)
        ability.append(pt * c.P_T + (1 - pt) * c.P_O)
    score, ability = np.array(score) * 100, np.array(ability) * 100
    fig, ax = plt.subplots(figsize=(4.15, 2.75))
    fig.subplots_adjust(left=0.12, right=0.97, top=0.95, bottom=0.19)
    ax.fill_between(ns, ability, score, color=LIGHT_PURPLE, alpha=0.6, lw=0)
    ax.plot(ns, score, color=PURPLE, lw=2.2)
    ax.plot(ns, ability, color=RED, lw=2.2)
    ax.set_xscale('log')
    ax.set_xticks([10, 20, 50, 100, 200, 500, 1000])
    ax.set_xticklabels(['10', '20', '50', '100', '200', '500', '1000'])
    ax.minorticks_off()
    ax.set_ylim(55, 102)
    ax.set_yticks([60, 70, 80, 90, 100])
    ax.set_yticklabels([f'{v}%' for v in (60, 70, 80, 90, 100)])
    ax.set_xlabel('число вопросов в тесте')
    ax.grid(axis='y', color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    i20 = list(ns).index(20)
    ax.scatter([20, 20], [score[i20], ability[i20]], color=[PURPLE, RED], s=28, zorder=3)
    ax.text(26, score[i20] + 1.2, 'результат победителя', color=PURPLE, size=9.5, weight='semibold')
    ax.text(26, ability[i20] - 4.8, 'его настоящая способность', color=RED, size=9.5, weight='semibold')
    ax.text(45, 76, 'завышение', color=PURPLE, size=9.5, ha='center')
    save(fig, 'c2_curse.png')


def chart_regression(r):
    """Топ-10 первого тура: баллы в первом и во втором туре (средние по симуляциям)."""
    r1, r2 = r['top10_r1'], r['top10_r2']
    fig, ax = plt.subplots(figsize=(4.15, 2.75))
    fig.subplots_adjust(left=0.13, right=0.8, top=0.95, bottom=0.12)
    for i, (a, b) in enumerate(zip(r1, r2)):
        col = PURPLE if i == 0 else '#B98CF5'
        ax.plot([0, 1], [a, b], color=col, lw=2.4 if i == 0 else 1.2, zorder=3 if i == 0 else 2)
        ax.scatter([0, 1], [a, b], color=col, s=18 if i else 30, zorder=3)
    ax.axhline(12, color=RED, lw=1, ls='--')
    ax.axhline(15, color=PURPLE, lw=1, ls='--', alpha=0.6)
    ax.text(1.05, 12, 'средний\nобычный, 12', color=RED, size=8.5, va='center')
    ax.text(1.05, 15, 'средний\nталант, 15', color=PURPLE, size=8.5, va='center')
    ax.text(-0.05, r1[0], f'победитель {comma(r1[0])}', ha='right', va='center', size=9, color=PURPLE, weight='semibold')
    ax.text(1.05, r2[0] + 0.55, f'{comma(r2[0])}', ha='left', va='center', size=9, color=PURPLE, weight='semibold')
    ax.set_xlim(-0.75, 1.0)
    ax.set_ylim(10.5, 19.5)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(['1-й тур', '2-й тур'], size=10, color=INK)
    ax.set_ylabel('баллов из 20')
    ax.spines['bottom'].set_visible(False)
    ax.tick_params(axis='x', length=0)
    ax.grid(axis='y', color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    save(fig, 'c3_regression.png')


def chart_traders():
    """Сколько «гениев» остаётся после каждого дня (в среднем)."""
    days = np.arange(0, 11)
    alive = 1000 * 0.5 ** days
    fig, ax = plt.subplots(figsize=(4.15, 2.75))
    fig.subplots_adjust(left=0.1, right=0.98, top=0.93, bottom=0.19)
    cols = [RED] * 10 + [PURPLE]
    ax.bar(days, alive, 0.7, color=cols)
    for d, a in zip(days, alive):
        lab = f'{a:.0f}' if a >= 10 else comma(a, 0 if a >= 1.95 else 2)
        ax.text(d, a + 15, lab, ha='center', va='bottom', size=8, color=PURPLE if d == 10 else MUTED)
    ax.annotate('«гений рынка»', xy=(10, 75), xytext=(8.4, 380), color=PURPLE, size=10,
                weight='semibold', ha='center',
                arrowprops=dict(arrowstyle='->', color=PURPLE, lw=1.2))
    ax.set_xticks(days)
    ax.set_xlabel('день')
    ax.set_ylabel('угадали все дни подряд')
    ax.set_ylim(0, 1100)
    ax.grid(axis='y', color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    save(fig, 'c4_traders.png')


if __name__ == '__main__':
    make_formulas()
    chart_podium()
    chart_curse()
    chart_traders()
    chart_regression(c.simulate(20))
    print('готово:', sorted(p.name for p in OUT.iterdir()))
