"""Расчёты для пункта 5 «Неожиданные выводы» (тема «Победителей не судят»).

Модель конкурса (как на слайде «Если участников много»):
  N = 1000 участников: 10 «талантов» с p = 0,75 и 990 «обычных» с p = 0,60,
  тест из n независимых вопросов, балл участника ~ Bin(n, p).
  Ничьи за первое место разыгрываются жребием.

Точные значения считаются через распределение максимума, остальное — симуляцией.
"""
import numpy as np
from scipy.special import comb
from scipy.stats import binom, norm

N_T, P_T = 10, 0.75     # таланты
N_O, P_O = 990, 0.60    # обычные
N = N_T + N_O
RNG = np.random.default_rng(2026)


def exact_winner(n):
    """P(победитель — талант) и E[балл победителя] — точно, ничьи жребием."""
    k = np.arange(n + 1)
    fT, FT = binom.pmf(k, n, P_T), binom.cdf(k, n, P_T)
    fO, FO = binom.pmf(k, n, P_O), binom.cdf(k, n, P_O)
    FT_prev = np.concatenate([[0.0], FT[:-1]])
    FO_prev = np.concatenate([[0.0], FO[:-1]])
    a = np.arange(1, N_T + 1)[:, None]          # талантов на максимуме
    b = np.arange(0, N_O + 1)[None, :]          # обычных на максимуме
    p_talent = 0.0
    for s in range(n + 1):
        # P(ровно a талантов набрали s, остальные меньше): C(10,a)·f^a·F(s-1)^(10-a)
        pa = comb(N_T, a) * fT[s] ** a * FT_prev[s] ** (N_T - a)
        pb = comb(N_O, b) * fO[s] ** b * FO_prev[s] ** (N_O - b)
        p_talent += float(np.sum(pa * pb * a / (a + b)))
    # E[max] = sum_{s>=1} P(max >= s)
    cdf_max = FT ** N_T * FO ** N_O
    e_max = float(np.sum(1 - cdf_max[:-1]))
    return p_talent, e_max


def simulate(n, runs=100_000, chunk=5_000):
    """Два независимых тура. Возвращает словарь со статистикой."""
    p = np.r_[np.full(N_T, P_T), np.full(N_O, P_O)]
    talent = np.r_[np.ones(N_T, bool), np.zeros(N_O, bool)]
    res = dict(win_talent=0, repeat=0, top10_talents=0.0,
               top10_r1=np.zeros(10), top10_r2=np.zeros(10), win_score=[])
    done = 0
    while done < runs:
        m = min(chunk, runs - done)
        x1 = RNG.binomial(n, p, size=(m, N))
        x2 = RNG.binomial(n, p, size=(m, N))
        # ранжирование со случайным разрешением ничьих
        key1 = x1 + RNG.random((m, N)) * 0.5
        key2 = x2 + RNG.random((m, N)) * 0.5
        order1 = np.argsort(-key1, axis=1)[:, :10]
        w1, w2 = order1[:, 0], np.argmax(key2, axis=1)
        res['win_talent'] += int(talent[w1].sum())
        res['repeat'] += int((w1 == w2).sum())
        res['top10_talents'] += float(talent[order1].sum())
        res['top10_r1'] += np.take_along_axis(x1, order1, 1).sum(0)
        res['top10_r2'] += np.take_along_axis(x2, order1, 1).sum(0)
        res['win_score'].append(x1[np.arange(m), w1])
        done += m
    res['win_talent'] /= runs
    res['repeat'] /= runs
    res['top10_talents'] /= runs
    res['top10_r1'] /= runs
    res['top10_r2'] /= runs
    res['win_score'] = np.concatenate(res['win_score'])
    return res


def ml_best_of_equal(n, p, n_people):
    """Муавр–Лаплас: балл лучшего из n_people одинаковых ≈ np + z·sqrt(npq)."""
    z = norm.ppf(1 - 1 / n_people)
    return n * p + z * np.sqrt(n * p * (1 - p)), z


def traders(n_people=1000, days=10, p_skill=0.75):
    exp_lucky = n_people * 0.5 ** days
    p_at_least_one = 1 - (1 - 0.5 ** days) ** n_people
    # среди n_people один настоящий талант (угадывает с p_skill), остальные — монетки
    lik_t = p_skill ** days
    p_talent_given_perfect = lik_t / (lik_t + (n_people - 1) * 0.5 ** days)
    return exp_lucky, p_at_least_one, p_talent_given_perfect


if __name__ == '__main__':
    print('=== Кто побеждает (точно) ===')
    for n in (10, 20, 50, 100, 200, 500, 1000):
        pt, em = exact_winner(n)
        ep = pt * P_T + (1 - pt) * P_O
        print(f'n={n:5d}: P(победил талант)={pt:.3f}  P(победил обычный)={1-pt:.3f}  '
              f'E[балл победителя]={em:.2f} ({em/n:.1%})  E[p победителя]={ep:.3f}')

    n = 20
    pt, em = exact_winner(n)
    w_ratio = (pt / N_T) / ((1 - pt) / N_O)
    print(f'\nn=20: отдельный талант побеждает в {w_ratio:.1f} раз чаще обычного, '
          f'но обычных в {N_O // N_T} раз больше')

    print('\n=== Муавр–Лаплас: лучший из 1000 одинаковых (p=0,6) ===')
    for n in (20, 100, 1000):
        k, z = ml_best_of_equal(n, P_O, 1000)
        exact = float(np.sum(1 - binom.cdf(np.arange(n), n, P_O) ** 1000))
        print(f'n={n:4d}: z={z:.2f}  ML≈{k:.1f} ({k/n:.1%})  точно E[max]={exact:.2f} ({exact/n:.1%})')

    print('\n=== Симуляция двух туров, n=20 ===')
    r = simulate(20)
    print(f"P(победил талант)={r['win_talent']:.3f}  P(повторная победа)={r['repeat']:.3f}")
    print(f"талантов в топ-10 в среднем: {r['top10_talents']:.2f}")
    print('топ-10, тур 1:', np.round(r['top10_r1'], 2), 'среднее', r['top10_r1'].mean().round(2))
    print('топ-10, тур 2:', np.round(r['top10_r2'], 2), 'среднее', r['top10_r2'].mean().round(2))
    print(f"средний балл победителя: {r['win_score'].mean():.2f}")
    print('распределение балла победителя:',
          {int(s): round(float((r['win_score'] == s).mean()), 3) for s in np.unique(r['win_score'])})

    print('\n=== Одинаковые способности (все p=0,6): повторная победа ===')
    print('по симметрии P = 1/N =', 1 / N)

    print('\n=== Трейдеры с монетками ===')
    e, p1, pb = traders()
    print(f'E[угадали 10 из 10]={e:.3f}  P(хотя бы один)={p1:.3f}  P(талант | 10 из 10)={pb:.3f}')
