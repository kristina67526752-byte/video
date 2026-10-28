"""Мемы для слайдов пункта 5: русские подписи поверх популярных шаблонов.

Шаблоны скачиваются с imgflip в templates/ (если их там ещё нет).
Самолёт Вальда нарисован заново как схема (в духе известной картинки про ошибку выжившего).
"""
import urllib.request
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Ellipse, FancyBboxPatch, Polygon
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / 'figures'
TPL = HERE / 'templates'
OUT.mkdir(exist_ok=True)
TPL.mkdir(exist_ok=True)

TEMPLATES = {
    'drake.jpg': 'https://i.imgflip.com/30b1gx.jpg',
    'pigeon.jpg': 'https://i.imgflip.com/1o00in.jpg',
    'doge.png': 'https://i.imgflip.com/43a45p.png',
    'panik.png': 'https://i.imgflip.com/3qqcim.png',
}
FONT_DIRS = [Path.home() / '.fonts', Path('/usr/share/fonts')]
INK = (26, 26, 26)


def font(name, size):
    for d in FONT_DIRS:
        hits = list(d.rglob(name))
        if hits:
            return ImageFont.truetype(str(hits[0]), size)
    raise FileNotFoundError(name)


def golos(size):
    return font('GolosText-SemiBold.ttf', size)


def oswald(size):
    return font('Oswald-Bold.ttf', size)


def template(name):
    path = TPL / name
    if not path.exists():
        req = urllib.request.Request(TEMPLATES[name], headers={'User-Agent': 'Mozilla/5.0'})
        path.write_bytes(urllib.request.urlopen(req, timeout=30).read())
    return Image.open(path).convert('RGB')


def centered(draw, xy, text, fnt, fill=INK, stroke=0, stroke_fill=None, spacing=8):
    draw.multiline_text(xy, text, font=fnt, fill=fill, anchor='mm', align='center', spacing=spacing,
                        stroke_width=stroke, stroke_fill=stroke_fill)


def meme_text(draw, xy, text, size):
    """Белый текст с чёрной обводкой — классические подписи мемов."""
    centered(draw, xy, text, oswald(size), fill='white', stroke=max(3, size // 12), stroke_fill='black')


def drake():
    im = template('drake.jpg')            # 1200×1200: Drake слева, белые ячейки справа
    d = ImageDraw.Draw(im)
    centered(d, (900, 300), '10 талантов\nс p = 0,75', golos(84), spacing=14)
    centered(d, (900, 900), '990 обычных\nс p = 0,6', golos(84), spacing=14)
    im.save(OUT / 'm1_drake.jpg', quality=92)


def pigeon():
    im = template('pigeon.jpg')           # 1587×1425
    d = ImageDraw.Draw(im)
    meme_text(d, (1225, 520), '19 ИЗ 20', 130)
    meme_text(d, (470, 1010), 'МЫ', 150)
    meme_text(d, (793, 1300), 'ЭТО ГЕНИЙ?', 170)
    im.save(OUT / 'm2_pigeon.jpg', quality=92)


def doge():
    src = template('doge.png').crop((0, 60, 937, 560))   # обе собаки
    im = Image.new('RGB', (937, 500 + 190), 'white')
    im.paste(src, (0, 190))
    d = ImageDraw.Draw(im)
    centered(d, (215, 105), 'Победитель\nв 1-м туре', golos(54), spacing=10)
    centered(d, (750, 105), 'Он же\nво 2-м туре', golos(54), spacing=10)
    im.save(OUT / 'm3_doge.jpg', quality=92)


def panik():
    src = template('panik.png')           # 640×881, картинки в ячейках x 308–634
    rows = [(2, 297), (301, 593), (597, 876)]
    texts = ['Завалил\nэкзамен', 'Вспомнил про\nрегрессию\nк среднему', 'Пересдачи\nне будет']
    cell_h, img_w, txt_w, line = 300, 330, 430, 5
    im = Image.new('RGB', (txt_w + img_w + 3 * line, 3 * cell_h + 4 * line), 'black')
    d = ImageDraw.Draw(im)
    for i, ((y0, y1), text) in enumerate(zip(rows, texts)):
        top = line + i * (cell_h + line)
        d.rectangle((line, top, line + txt_w - 1, top + cell_h - 1), fill='white')
        cell = src.crop((308, y0, 634, y1)).resize((img_w, cell_h))
        im.paste(cell, (2 * line + txt_w, top))
        centered(d, (line + txt_w / 2, top + cell_h / 2), text, golos(50), spacing=10)
    im.save(OUT / 'm5_panik.jpg', quality=92)


def wald_plane():
    """Схема бомбардировщика с пробоинами только там, где попадание не смертельно."""
    fig, ax = plt.subplots(figsize=(3.0, 3.1))
    fig.subplots_adjust(0, 0, 1, 1)
    ax.set_xlim(-5.2, 5.2)
    ax.set_ylim(-6.3, 5.0)
    ax.set_aspect('equal')
    ax.axis('off')
    grey, edge = '#C9C6CF', '#8E8A96'
    kw = dict(fc=grey, ec=edge, lw=1.2)
    ax.add_patch(Polygon([(-5, 0.3), (-0.45, 1.6), (0.45, 1.6), (5, 0.3), (5, -0.4), (0.45, 0.3),
                          (-0.45, 0.3), (-5, -0.4)], closed=True, **kw))                    # крылья
    ax.add_patch(Polygon([(-1.9, -3.6), (-0.3, -3.0), (0.3, -3.0), (1.9, -3.6), (1.9, -4.1),
                          (0.3, -3.9), (-0.3, -3.9), (-1.9, -4.1)], closed=True, **kw))    # хвост
    ax.add_patch(FancyBboxPatch((-0.45, -4.6), 0.9, 8.4, boxstyle='round,pad=0,rounding_size=0.45',
                                **kw))                                                       # фюзеляж
    for x in (-3.1, -1.6, 1.6, 3.1):
        ax.add_patch(Ellipse((x, 1.25), 0.55, 1.5, **kw))                                  # двигатели
    rng = np.random.default_rng(7)
    holes = []
    for x0, x1, y0, y1, n in [(-4.8, -2.2, -0.3, 0.6, 9), (2.2, 4.8, -0.3, 0.6, 9),
                              (-1.1, -0.6, 0.0, 0.9, 2), (0.6, 1.1, 0.0, 0.9, 2),
                              (-0.3, 0.3, -2.8, -0.2, 7), (-1.7, 1.7, -3.95, -3.35, 7)]:
        holes += list(zip(rng.uniform(x0, x1, n), rng.uniform(y0, y1, n)))
    hx, hy = np.array(holes).T
    ax.scatter(hx, hy, s=9, color='#FF3E35', zorder=5)
    ax.text(0, 4.6, 'Пробоины у вернувшихся', ha='center', va='center', size=10.5,
            family='Golos Text', weight='semibold', color='#1A1A1A')
    ax.text(0, -5.5, 'Вальд: бронировать там,\nгде дыр НЕТ', ha='center', va='center', size=9.5,
            family='Golos Text', color='#9307FE', weight='semibold', linespacing=1.15)
    fig.savefig(OUT / 'm4_plane.png', dpi=300, transparent=True)
    plt.close(fig)


if __name__ == '__main__':
    drake()
    pigeon()
    doge()
    panik()
    wald_plane()
    print('готово:', sorted(p.name for p in OUT.glob('m*')))
