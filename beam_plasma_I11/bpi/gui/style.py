"""Цвета и оформление. Палитра проверена на различимость при нарушениях
цветового зрения (дейтеранопия, протанопия, тританопия).

Роли цветов одинаковы во всех окнах:
    синий      — электроны плазмы
    оранжевый  — электроны пучка
    бирюзовый  — электрическое поле / волны
    фиолетовый — главная (самая неустойчивая) волна
    розовый    — ионы (концентрация, каверны)
    серый пунктир — теория
"""
import matplotlib as mpl
import numpy as np

THEMES = {
    "dark": dict(
        surface="#1a1a19", panel="#20201f", text="#f0efec", text2="#c3c2b7",
        muted="#8a897f", grid="#383835",
        plasma="#3987e5", beam="#d95926", field="#199e70", main="#9085e9", ion="#e87ba4",
        # более яркие варианты для «свечения» частиц на фазовом портрете
        plasma_glow="#6da7ec", beam_glow="#f08a4b",
        spec_lo="#1a1a19", spec_mid="#127a57", spec_hi="#c9f2e1",
    ),
    "light": dict(
        surface="#fcfcfb", panel="#f4f3f0", text="#0b0b0b", text2="#52514e",
        muted="#8a897f", grid="#dddcd6",
        plasma="#2a78d6", beam="#eb6834", field="#1baf7a", main="#6250d6", ion="#c2407a",
        plasma_glow="#1c5cab", beam_glow="#c0451a",
        spec_lo="#fcfcfb", spec_mid="#1baf7a", spec_hi="#0b3d2b",
    ),
}

C = dict(THEMES["dark"])
MONO = "DejaVu Sans Mono"
_current = ["dark"]


def current_theme():
    return _current[0]


def use(theme="dark"):
    _current[0] = theme
    C.clear()
    C.update(THEMES[theme])
    rc = mpl.rcParams
    rc["figure.facecolor"] = C["surface"]
    rc["axes.facecolor"] = C["panel"]
    rc["savefig.facecolor"] = C["surface"]
    rc["axes.edgecolor"] = C["grid"]
    rc["axes.labelcolor"] = C["text2"]
    rc["axes.titlecolor"] = C["text"]
    rc["axes.titlesize"] = 9.5
    rc["axes.titleweight"] = "bold"
    rc["axes.labelsize"] = 8.5
    rc["axes.grid"] = True
    rc["grid.color"] = C["grid"]
    rc["grid.linewidth"] = 0.6
    rc["xtick.color"] = C["text2"]
    rc["ytick.color"] = C["text2"]
    rc["xtick.labelsize"] = 7.5
    rc["ytick.labelsize"] = 7.5
    rc["text.color"] = C["text"]
    rc["legend.fontsize"] = 7.5
    rc["legend.frameon"] = True
    rc["legend.facecolor"] = C["panel"]
    rc["legend.edgecolor"] = C["grid"]
    rc["legend.labelcolor"] = C["text"]
    rc["lines.linewidth"] = 1.6
    rc["font.size"] = 9
    rc["toolbar"] = "toolbar2"
    # горячие клавиши приложения не должны конфликтовать со стандартными
    for key in ("keymap.home", "keymap.back", "keymap.forward", "keymap.save",
                "keymap.pan", "keymap.zoom", "keymap.grid", "keymap.yscale",
                "keymap.xscale"):
        rc[key] = [k for k in rc[key] if k not in
                   ("h", "r", "left", "right", "c", "v", "s", "p", "o", "g", "l", "k", "backspace")]


def hex2rgb(h):
    return np.array(mpl.colors.to_rgb(h), dtype=np.float32)


def seq_cmap():
    """Последовательная одноцветная шкала (поверхность → бирюзовый → светлый)
    для спектрограммы."""
    return mpl.colors.LinearSegmentedColormap.from_list(
        "spec", [C["spec_lo"], C["spec_mid"], C["spec_hi"]])


def div_cmap():
    """Расходящаяся шкала (синий — яма концентрации, красный — уплотнение)."""
    return mpl.colors.LinearSegmentedColormap.from_list(
        "div", [C["plasma"], C["surface"], C["beam"]])


def style_widget_axes(ax):
    ax.set_facecolor(C["panel"])
    for sp in ax.spines.values():
        sp.set_color(C["grid"])


def maximize(fig):
    """Развернуть окно на весь экран (если бэкенд это умеет)."""
    try:
        mng = fig.canvas.manager
        w = mng.window
        if hasattr(w, "showMaximized"):          # Qt
            w.showMaximized()
        elif hasattr(w, "state"):                # Tk
            try:
                w.state("zoomed")                # Windows / macOS
            except Exception:
                w.attributes("-zoomed", True)    # Linux
    except Exception:
        pass
