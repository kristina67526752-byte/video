"""Рисунки к решению типового расчёта, вариант 7."""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
os.makedirs(OUT, exist_ok=True)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "mathtext.fontset": "dejavuserif"})
INK = "#1a1a1a"; FILL1 = "#9ec5e8"; FILL2 = "#f3c58c"; ACC = "#c0392b"


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), bbox_inches="tight")
    plt.close(fig)


def axes2d(ax, xlim, ylim, xt, yt, xl="$x$", yl="$y$"):
    ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.set_aspect("equal")
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_position(("data", 0)); ax.spines["bottom"].set_position(("data", 0))
    ax.plot(1, 0, ">k", transform=ax.get_yaxis_transform(), clip_on=False, ms=5)
    ax.plot(0, 1, "^k", transform=ax.get_xaxis_transform(), clip_on=False, ms=5)
    ax.set_xticks(xt); ax.set_yticks(yt)
    ax.grid(True, color="#d9d9d9", lw=0.6)
    ax.text(xlim[1], -0.04 * (ylim[1] - ylim[0]), xl, ha="right", va="top", fontsize=12)
    ax.text(0.04 * (xlim[1] - xlim[0]), ylim[1], yl, ha="left", va="top", fontsize=12)


# ---------------- Задание 1 ----------------
f_exp = lambda x: 2.0 ** (-x)
l1 = lambda x: x + 1
l2 = lambda x: -4 * x - 4


def draw_task1(ax, split=None):
    xs = np.linspace(-2.25, 0.75, 400)
    ax.plot(xs, f_exp(xs), color=INK, lw=1.6)
    xl = np.linspace(-1.6, 0.75, 10); ax.plot(xl, l1(xl), color=INK, lw=1.6)
    xm = np.linspace(-2.2, -0.85, 10); ax.plot(xm, l2(xm), color=INK, lw=1.6)
    if split is None:
        x1 = np.linspace(-2, -1, 200); x2 = np.linspace(-1, 0, 200)
        ax.fill_between(x1, l2(x1), f_exp(x1), color=FILL1, alpha=0.8, lw=0)
        ax.fill_between(x2, l1(x2), f_exp(x2), color=FILL1, alpha=0.8, lw=0)
        ax.text(-1.05, 1.45, "$D$", fontsize=15)
    elif split == "x":
        x1 = np.linspace(-2, -1, 200); x2 = np.linspace(-1, 0, 200)
        ax.fill_between(x1, l2(x1), f_exp(x1), color=FILL1, alpha=0.85, lw=0)
        ax.fill_between(x2, l1(x2), f_exp(x2), color=FILL2, alpha=0.85, lw=0)
        ax.plot([-1, -1], [0, 2], "--", color=ACC, lw=1.2)
        ax.text(-1.55, 2.0, "$D_1$", fontsize=13); ax.text(-0.75, 0.8, "$D_2$", fontsize=13)
    else:
        y1 = np.linspace(0, 1, 200); y2 = np.linspace(1, 4, 200)
        ax.fill_betweenx(y1, -1 - y1 / 4, y1 - 1, color=FILL2, alpha=0.85, lw=0)
        ax.fill_betweenx(y2, -1 - y2 / 4, -np.log2(y2), color=FILL1, alpha=0.85, lw=0)
        ax.plot([-1.25, 0], [1, 1], "--", color=ACC, lw=1.2)
        ax.text(-1.25, 1.8, "$D_1$", fontsize=13); ax.text(-0.85, 0.35, "$D_2$", fontsize=13)
    for (px, py, lab, dx, dy) in [(-1, 0, "$A(-1;\\,0)$", 0.1, -0.5), (0, 1, "$B(0;\\,1)$", 0.08, 0.12),
                                  (-2, 4, "$C(-2;\\,4)$", 0.12, 0.08)]:
        ax.plot(px, py, "o", color=INK, ms=4); ax.text(px + dx, py + dy, lab, fontsize=10)


def task1_axes(ax):
    axes2d(ax, (-2.6, 1.0), (-0.9, 4.9), [-2, -1], [1, 2, 3, 4])
    ax.text(-0.08, -0.08, "0", ha="right", va="top", fontsize=10)


fig, ax = plt.subplots(figsize=(5.2, 5.6))
draw_task1(ax); task1_axes(ax)
ax.annotate("$y=\\left(\\frac{1}{2}\\right)^x$", xy=(-1.45, f_exp(-1.45)), xytext=(-1.2, 3.45), fontsize=11,
            arrowprops=dict(arrowstyle="-", color="#666", lw=0.8))
ax.annotate("$y+4x=-4$", xy=(-1.7, l2(-1.7)), xytext=(-2.55, 1.2), fontsize=11,
            arrowprops=dict(arrowstyle="-", color="#666", lw=0.8))
ax.annotate("$y-x=1$", xy=(0.45, l1(0.45)), xytext=(0.15, 2.4), fontsize=11,
            arrowprops=dict(arrowstyle="-", color="#666", lw=0.8))
save(fig, "fig1_region.svg")

fig, axs = plt.subplots(1, 2, figsize=(9.4, 5.0))
draw_task1(axs[0], "x"); task1_axes(axs[0])
axs[0].set_title("а) I способ: разбиение прямой $x=-1$", fontsize=11)
draw_task1(axs[1], "y"); task1_axes(axs[1])
axs[1].set_title("б) II способ: разбиение прямой $y=1$", fontsize=11)
save(fig, "fig2_split.svg")


# ---------------- косоугольная (кабинетная) проекция ----------------
def cab(x, y, z):
    """Ось Ox направлена «на нас» (вниз-влево), Oy — вправо, Oz — вверх."""
    x = np.asarray(x, float)
    return y - 0.5 * x, z - 0.38 * x


def cab_line(ax, P, Q, **kw):
    u, v = cab(*np.array([P, Q], float).T); ax.plot(u, v, **kw)


def cab_axis(ax, a, b, which, label, off=(0.08, 0.08), proj=None):
    proj = proj or cab
    P = [0, 0, 0]; Q = [0, 0, 0]; i = "xyz".index(which); P[i] = a; Q[i] = b
    u0, v0 = proj(*P); u1, v1 = proj(*Q)
    ax.plot([u0, u1], [v0, v1], color=INK, lw=1.0)
    ax.annotate("", xy=(u1, v1), xytext=(u0 + 0.9 * (u1 - u0), v0 + 0.9 * (v1 - v0)), annotation_clip=False,
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.0, mutation_scale=12))
    ax.text(u1 + off[0], v1 + off[1], label, fontsize=12)


def ortho(azim_deg, elev_deg):
    a, e = np.radians(azim_deg), np.radians(elev_deg)
    r = np.array([-np.sin(a), np.cos(a), 0.0])
    up = np.array([-np.sin(e) * np.cos(a), -np.sin(e) * np.sin(a), np.cos(e)])

    def proj(x, y, z):
        x, y, z = (np.asarray(t, float) for t in (x, y, z))
        return r[0] * x + r[1] * y + r[2] * z, up[0] * x + up[1] * y + up[2] * z
    return proj


def cab_arrow_mid(ax, P, Q, color, proj=None):
    proj = proj or cab
    P = np.array(P, float); Q = np.array(Q, float)
    a = proj(*(P + 0.45 * (Q - P))); b = proj(*(P + 0.58 * (Q - P)))
    ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="-|>", color=color, lw=1.6, mutation_scale=16))


# ---------------- общие 3D-утилиты ----------------
def clean3d(ax, elev, azim):
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    ax.set_proj_type("ortho")


def axis_arrow(ax, p0, p1, label, off=(0, 0, 0)):
    p0 = np.array(p0, float); p1 = np.array(p1, float)
    ax.plot(*zip(p0, p1), color=INK, lw=1.1)
    d = p1 - p0; d /= np.linalg.norm(d)
    ax.quiver(*(p1 - 0.001 * d), *d, length=0.35, color=INK, arrow_length_ratio=1.0, lw=1.1)
    ax.text(*(p1 + np.array(off)), label, fontsize=12)


# ---------------- Задание 2 ----------------
R0, Z0 = 12 / 5, 3.0
fig = plt.figure(figsize=(6.6, 6.2))
ax = fig.add_subplot(111, projection="3d", computed_zorder=False)
clean3d(ax, 16, 205)
ph = np.linspace(np.pi / 2, 3 * np.pi / 2, 60)
rr = np.linspace(0, R0, 40)
P, Rg = np.meshgrid(ph, rr)
Xe, Ye = Rg * np.cos(P), Rg * np.sin(P)
yy = np.linspace(-R0, R0, 80)
zz_top = 5 / 3 * np.sqrt(9 - yy ** 2); zz_bot = 1.25 * np.abs(yy)
verts = list(zip(np.zeros_like(yy), yy, zz_bot)) + list(zip(np.zeros_like(yy), yy[::-1], zz_top[::-1]))
ax.add_collection3d(Poly3DCollection([verts], facecolor="#d6e9c6", edgecolor=INK, lw=0.8, alpha=0.5, zorder=1))
ax.plot_surface(Xe, Ye, 1.25 * Rg, color="#f0b070", alpha=0.75, lw=0, shade=True, zorder=2)
ax.plot_surface(Xe, Ye, 5 / 3 * np.sqrt(9 - Rg ** 2), color="#7fb3e0", alpha=0.75, lw=0, shade=True, zorder=3)
ax.plot(R0 * np.cos(ph), R0 * np.sin(ph), Z0 * np.ones_like(ph), color=ACC, lw=2.4, zorder=6)
axis_arrow(ax, (-4.0, 0, 0), (1.6, 0, 0), "$x$", (0.2, 0, -0.25))
axis_arrow(ax, (0, -3.6, 0), (0, 3.6, 0), "$y$", (0, 0.2, 0))
axis_arrow(ax, (0, 0, 0), (0, 0, 6.2), "$z$", (0, 0.45, -0.3))
ax.text(0, -0.3, 5.15, "5", fontsize=10, zorder=7)
ax.text(0.15, 0, -0.55, "$O$", fontsize=11)
ax.text2D(0.0, 0.60, "окружность\n$r=\\frac{12}{5},\\ z=3$", transform=ax.transAxes, color=ACC, fontsize=11)
ax.text2D(0.66, 0.76, "$z=\\frac{5}{3}\\sqrt{9-x^2-y^2}$", transform=ax.transAxes, fontsize=12)
ax.text2D(0.68, 0.34, "$z=\\frac{5}{4}\\sqrt{x^2+y^2}$", transform=ax.transAxes, fontsize=12)
ax.text2D(0.40, 0.92, "вид со стороны отрицательных $x$", transform=ax.transAxes, fontsize=10, color="#666")
ax.set_xlim(-4, 1.6); ax.set_ylim(-3.6, 3.6); ax.set_zlim(0, 6.2)
ax.set_box_aspect((5.6, 7.2, 6.2))
save(fig, "fig3_body.svg")

# осевое сечение (плоскость y = 0, x <= 0)
fig, ax = plt.subplots(figsize=(5.2, 5.4))
xs = np.linspace(-3, 3, 400)
ax.plot(xs, 5 / 3 * np.sqrt(9 - xs ** 2), color="#999", lw=1, ls="--")
xs2 = np.linspace(-3, 0, 300)
ax.plot(xs2, 5 / 3 * np.sqrt(9 - xs2 ** 2), color=INK, lw=1.6)
xc = np.linspace(-3, 0, 10); ax.plot(xc, -1.25 * xc, color=INK, lw=1.6)
xf = np.linspace(-R0, 0, 200)
ax.fill_between(xf, -1.25 * xf, 5 / 3 * np.sqrt(9 - xf ** 2), color=FILL1, alpha=0.85, lw=0)
ax.plot([-R0, -R0], [0, Z0], ":", color=ACC); ax.plot([-R0, 0], [Z0, Z0], ":", color=ACC)
ax.plot(-R0, Z0, "o", color=ACC, ms=4)
axes2d(ax, (-3.5, 1.6), (-0.4, 5.8), [-3, -2, -1, 1], [1, 2, 3, 4, 5], "$x$", "$z$")
ax.text(-R0 - 0.1, -0.45, "$-\\frac{12}{5}$", fontsize=11, color=ACC, ha="center")
ax.annotate("$z=\\frac{5}{3}\\sqrt{9-x^2}$", xy=(-1.0, 5 / 3 * np.sqrt(8)), xytext=(-3.4, 5.6), fontsize=11,
            arrowprops=dict(arrowstyle="-", color="#666", lw=0.8))
ax.annotate("$z=-\\frac{5}{4}x$", xy=(-1.2, 1.5), xytext=(-3.45, 0.6), fontsize=11,
            arrowprops=dict(arrowstyle="-", color="#666", lw=0.8))
ax.text(-1.3, 3.2, "$T$", fontsize=14)
save(fig, "fig4_section.svg")


# ---------------- Задание 3 ----------------
fig, axs = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1.5, 1]})
ax = axs[0]
xs = np.linspace(0, 16, 400); ax.plot(xs, 2 * np.sqrt(xs), color="#aaa", lw=1)
xa = np.linspace(3, 15, 200); ax.plot(xa, 2 * np.sqrt(xa), color=ACC, lw=2.4)
ax.plot([3, 15], [2 * np.sqrt(3), 2 * np.sqrt(15)], "o", color=INK, ms=4)
ax.text(3.2, 2 * np.sqrt(3) - 0.9, "$A(3;\\,2\\sqrt{3})$"); ax.text(12.0, 2 * np.sqrt(15) + 0.3, "$B(15;\\,2\\sqrt{15})$")
ax.text(6.5, 6.4, "$y=2\\sqrt{x}$", fontsize=12)
axes2d(ax, (-0.5, 17), (-0.5, 9.5), [3, 6, 9, 12, 15], [2, 4, 6, 8]); ax.set_aspect("auto")
ax.set_title("а) $y=2\\sqrt{x},\\ 3\\leq x\\leq 15$", fontsize=11)
ax = axs[1]
ts = np.linspace(0.6, 2.2, 300); ax.plot(np.log(ts), 1 / ts, color="#aaa", lw=1)
tb = np.linspace(1, np.sqrt(2), 200); ax.plot(np.log(tb), 1 / tb, color=ACC, lw=2.4)
ax.plot([0, np.log(np.sqrt(2))], [1, 1 / np.sqrt(2)], "o", color=INK, ms=4)
ax.text(0.02, 1.05, "$A(0;\\,1)$"); ax.text(0.05, 0.52, "$B\\left(\\ln\\sqrt{2};\\,\\frac{1}{\\sqrt{2}}\\right)$")
ax.text(0.42, 0.74, "$y=e^{-x}$", fontsize=12)
axes2d(ax, (-0.55, 0.85), (-0.05, 1.45), [-0.4, 0.4], [0.5, 1.0]); ax.set_aspect("auto")
ax.set_title("б) $x=\\ln t,\\ y=1/t,\\ 1\\leq t\\leq\\sqrt{2}$", fontsize=11)
save(fig, "fig5_curves.svg")


# ---------------- Задание 4 ----------------
fig, ax = plt.subplots(figsize=(6.4, 5.6))
ax.set_aspect("equal"); ax.axis("off")
th = np.linspace(0, 2 * np.pi, 200)
for yv in (0, np.pi / 2):
    u, v = cab(np.sin(th), yv + 0 * th, 2 * np.cos(th)); ax.plot(u, v, color="#c8c8c8", lw=0.9, ls="--")
tt = np.linspace(-0.25, np.pi + 0.35, 300)
u, v = cab(np.sin(tt), tt, 2 * np.cos(tt)); ax.plot(u, v, color="#a8a8a8", lw=1.0)
ta = np.linspace(0, np.pi / 2, 200)
u, v = cab(np.sin(ta), ta, 2 * np.cos(ta)); ax.plot(u, v, color=ACC, lw=2.6)
cab_axis(ax, -0.6, 1.9, "x", "$x$", (-0.2, -0.25))
cab_axis(ax, -0.8, 4.3, "y", "$y$", (0.05, 0.1))
cab_axis(ax, -2.4, 2.8, "z", "$z$", (0.1, -0.15))
B = (1, np.pi / 2, 0)
cab_line(ax, (1, 0, 0), B, color="#777", lw=0.8, ls=":")
cab_line(ax, (0, np.pi / 2, 0), B, color="#777", lw=0.8, ls=":")
for P_, lab, d in [((0, 0, 2), "$A(0;\\,0;\\,2)$", (0.12, 0.1)), (B, "$B\\left(1;\\,\\frac{\\pi}{2};\\,0\\right)$", (0.1, -0.35))]:
    u, v = cab(*P_); ax.plot(u, v, "o", color=INK, ms=4); ax.text(u + d[0], v + d[1], lab, fontsize=11)
u, v = cab(1, 0, 0); ax.text(u - 0.15, v - 0.3, "1", fontsize=10)
u, v = cab(0, np.pi / 2, 0); ax.text(u - 0.05, v + 0.12, "$\\frac{\\pi}{2}$", fontsize=11)
ax.text(-0.25, -0.25, "$O$", fontsize=11)
ax.text(1.95, 1.55, "$x^2+\\frac{z^2}{4}=1$", fontsize=11, color="#888")
save(fig, "fig6_helix.svg")


# ---------------- Задание 5 ----------------
# вид со стороны отрицательного октанта: треугольник KLM виден «снаружи», нормаль n — на нас
pr = ortho(225, 25)
K = (-1, 0, 0); L = (0, -1, 0); M = (0, 0, -2); O = (0, 0, 0)
fig, ax = plt.subplots(figsize=(6.0, 6.4))
ax.set_aspect("equal"); ax.axis("off")
tri = np.array([pr(*P_) for P_ in (K, L, M)])
ax.fill(tri[:, 0], tri[:, 1], color=FILL1, alpha=0.7, lw=0)
tri2 = np.array([pr(*P_) for P_ in (O, K, L)])
ax.fill(tri2[:, 0], tri2[:, 1], color=FILL2, alpha=0.8, lw=0)
cab_axis(ax, -1.2, 1.4, "x", "$x$", (0.05, 0.05), proj=pr)
cab_axis(ax, -1.2, 1.4, "y", "$y$", (-0.2, 0.05), proj=pr)
cab_axis(ax, -2.5, 1.2, "z", "$z$", (0.08, -0.1), proj=pr)
# невидимое ребро OM (за гранью KLM) — пунктиром
u, v = pr(*np.array([O, M], float).T); ax.plot(u, v, color=FILL1, lw=2.2)
ax.plot(u, v, color=INK, lw=1.0, ls="--")
for P_, Q_ in [(O, K), (O, L)]:
    u, v = pr(*np.array([P_, Q_], float).T); ax.plot(u, v, color=INK, lw=1.2)
for P_, Q_ in [(K, L), (L, M), (M, K)]:
    u, v = pr(*np.array([P_, Q_], float).T); ax.plot(u, v, color=ACC, lw=2.0)
    cab_arrow_mid(ax, P_, Q_, ACC, proj=pr)
c = np.mean([K, L, M], axis=0) + np.array([0.12, 0.12, -0.25]); n = np.array([-2, -2, -1]) / 3
u0, v0 = pr(*c); u1, v1 = pr(*(c + 0.8 * n))
ax.plot(u0, v0, "o", color="#1f6fb2", ms=3)
ax.annotate("", xy=(u1, v1), xytext=(u0, v0), arrowprops=dict(arrowstyle="-|>", color="#1f6fb2", lw=1.6, mutation_scale=14))
ax.text(u1 - 0.22, v1 + 0.02, "$\\vec n$", color="#1f6fb2", fontsize=13)
for P_, lab, d in [(K, "$K(-1;\\,0;\\,0)$", (-0.75, -0.14)), (L, "$L(0;\\,-1;\\,0)$", (0.06, -0.14)),
                   (M, "$M(0;\\,0;\\,-2)$", (0.1, -0.1)), (O, "$O$", (0.07, 0.04))]:
    u, v = pr(*P_); ax.plot(u, v, "o", color=INK, ms=4); ax.text(u + d[0], v + d[1], lab, fontsize=11)
u, v = pr(*(np.mean([K, L, M], axis=0))); ax.text(u - 0.32, v - 0.15, "$S$", fontsize=14)
save(fig, "fig7_tetra.svg")

fig, ax = plt.subplots(figsize=(4.2, 4.2))
ax.fill([0, -1, 0], [0, 0, -1], color=FILL2, alpha=0.85, lw=0)
ax.plot([-1, 0], [0, -1], color=INK, lw=1.6)
xx = -0.55; ax.plot([xx, xx], [-1 - xx, 0], color=ACC, lw=1.2)
ax.annotate("", xy=(xx, -0.02), xytext=(xx, -1 - xx + 0.02), arrowprops=dict(arrowstyle="->", color=ACC))
ax.text(xx - 0.1, -0.62, "$y=-1-x$", fontsize=10, color=ACC, ha="right")
ax.text(-0.42, -0.42, "$D_{xy}$", fontsize=13)
ax.text(-1.12, 0.07, "$K(-1;\\,0)$", fontsize=10); ax.text(0.05, -1.08, "$L(0;\\,-1)$", fontsize=10)
ax.text(-0.75, 0.06, "$y=0$", fontsize=10, color=ACC)
axes2d(ax, (-1.35, 0.5), (-1.35, 0.5), [], [])
ax.text(0.04, 0.04, "$O$", fontsize=10)
save(fig, "fig8_dxy.svg")
print("ok")
