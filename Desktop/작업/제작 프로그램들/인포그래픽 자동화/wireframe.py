import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

THEME_COLORS = {
    "blue":   {"primary": "#1565C0", "secondary": "#42A5F5", "accent": "#E3F2FD", "bg": "#F8FBFF"},
    "green":  {"primary": "#2E7D32", "secondary": "#66BB6A", "accent": "#E8F5E9", "bg": "#F6FBF6"},
    "orange": {"primary": "#E65100", "secondary": "#FFA726", "accent": "#FFF3E0", "bg": "#FFFBF6"},
    "purple": {"primary": "#4527A0", "secondary": "#7E57C2", "accent": "#EDE7F6", "bg": "#F8F6FF"},
    "red":    {"primary": "#B71C1C", "secondary": "#EF5350", "accent": "#FFEBEE", "bg": "#FFF8F8"},
    "teal":   {"primary": "#00695C", "secondary": "#26A69A", "accent": "#E0F2F1", "bg": "#F4FBFA"},
}


def _get_colors(theme: str) -> dict:
    return THEME_COLORS.get(theme, THEME_COLORS["blue"])


def _add_placeholder_box(ax, x, y, w, h, label, colors, box_color=None, text_color="white", fontsize=9, radius=0.02):
    fc = box_color or colors["secondary"]
    box = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0", linewidth=0,
                         facecolor=fc, edgecolor="none")
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
            fontsize=fontsize, color=text_color, fontweight="bold",
            wrap=True, clip_on=True)


def _setup_fig(layout_type: str, colors: dict):
    fig, ax = plt.subplots(figsize=(8, 11))
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 11)
    ax.axis("off")
    fig.patch.set_facecolor(colors["bg"])
    ax.set_facecolor(colors["bg"])
    return fig, ax


def _draw_header(ax, layout_label: str, colors: dict):
    _add_placeholder_box(ax, 0.3, 9.9, 7.4, 0.8, layout_label, colors,
                         box_color=colors["primary"], fontsize=11)
    _add_placeholder_box(ax, 0.3, 9.3, 7.4, 0.5, "제목 입력 영역", colors,
                         box_color=colors["accent"], text_color=colors["primary"], fontsize=10)


def generate_wireframe(layout_type: str, sections: list, color_theme: str = "blue") -> bytes:
    colors = _get_colors(color_theme)
    generators = {
        "timeline": _timeline,
        "compare":  _compare,
        "flow":     _flow,
        "stats":    _stats,
        "report":   _report,
        "list":     _list_layout,
    }
    gen = generators.get(layout_type, _list_layout)
    fig = gen(sections, colors)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _timeline(sections: list, colors: dict) -> plt.Figure:
    fig, ax = _setup_fig("timeline", colors)
    _draw_header(ax, "TIMELINE 레이아웃", colors)

    n = len(sections)
    step_h = min(7.8 / max(n, 1), 1.4)
    y_start = 9.0

    for i, sec in enumerate(sections):
        y = y_start - i * (step_h + 0.15)
        # 타임라인 세로선
        if i < n - 1:
            ax.plot([1.1, 1.1], [y - step_h + 0.1, y - 0.05], color=colors["secondary"], lw=2, zorder=1)
        # 원형 마커
        circle = plt.Circle((1.1, y - step_h / 2 + step_h / 2), 0.18,
                             color=colors["primary"], zorder=2)
        ax.add_patch(circle)
        ax.text(1.1, y - step_h / 2 + step_h / 2, str(i + 1),
                ha="center", va="center", fontsize=8, color="white", fontweight="bold")
        # 컨텐츠 박스
        _add_placeholder_box(ax, 1.5, y - step_h + 0.05, 6.2, step_h - 0.05,
                             sec["label"], colors, box_color=colors["accent"],
                             text_color=colors["primary"], fontsize=9)

    return fig


def _compare(sections: list, colors: dict) -> plt.Figure:
    fig, ax = _setup_fig("compare", colors)
    _draw_header(ax, "COMPARE 레이아웃", colors)

    # 헤더 컬럼
    _add_placeholder_box(ax, 0.3, 8.7, 3.6, 0.5, "항목 A", colors,
                         box_color=colors["primary"], fontsize=10)
    _add_placeholder_box(ax, 4.1, 8.7, 3.6, 0.5, "항목 B", colors,
                         box_color=colors["secondary"], fontsize=10)

    n = len(sections)
    row_h = min(7.8 / max(n, 1), 1.2)
    for i, sec in enumerate(sections):
        y = 8.5 - i * (row_h + 0.1)
        _add_placeholder_box(ax, 0.3, y - row_h, 3.6, row_h - 0.05,
                             f"{sec['label']}\n(A 값 입력)", colors,
                             box_color=colors["accent"], text_color=colors["primary"], fontsize=8)
        _add_placeholder_box(ax, 4.1, y - row_h, 3.6, row_h - 0.05,
                             f"{sec['label']}\n(B 값 입력)", colors,
                             box_color="#F3E5F5", text_color=colors["primary"], fontsize=8)
        # 중앙 레이블
        ax.text(4.0, y - row_h / 2, sec["label"][:8],
                ha="center", va="center", fontsize=7, color=colors["primary"],
                style="italic")

    return fig


def _flow(sections: list, colors: dict) -> plt.Figure:
    fig, ax = _setup_fig("flow", colors)
    _draw_header(ax, "FLOW 레이아웃", colors)

    n = len(sections)
    box_h = 0.7
    gap = 0.4
    total_h = n * box_h + (n - 1) * gap
    y_start = 9.0 - (9.0 - 0.3 - total_h) / 2

    for i, sec in enumerate(sections):
        y = y_start - i * (box_h + gap)
        _add_placeholder_box(ax, 1.0, y - box_h, 6.0, box_h,
                             sec["label"], colors, fontsize=9)
        if i < n - 1:
            ax.annotate("", xy=(4.0, y - box_h - gap + 0.05),
                        xytext=(4.0, y - box_h - 0.02),
                        arrowprops=dict(arrowstyle="-|>", color=colors["primary"], lw=2))

    return fig


def _stats(sections: list, colors: dict) -> plt.Figure:
    fig, ax = _setup_fig("stats", colors)
    _draw_header(ax, "STATS 레이아웃", colors)

    number_secs = [s for s in sections if s["type"] == "number"]
    other_secs = [s for s in sections if s["type"] != "number"]

    # 숫자 카드 상단
    n_nums = min(len(number_secs), 4) if number_secs else 0
    if n_nums:
        card_w = 7.4 / n_nums - 0.1
        for i, sec in enumerate(number_secs[:4]):
            x = 0.3 + i * (card_w + 0.1)
            _add_placeholder_box(ax, x, 7.8, card_w, 1.2,
                                 f"{sec['label']}\n\n000", colors,
                                 box_color=colors["primary"], fontsize=8)

    # 차트 영역
    chart_top = 7.5 if n_nums else 9.0
    _add_placeholder_box(ax, 0.3, chart_top - 3.8, 4.5, 3.6,
                         "차트 영역\n(데이터 입력 후 표시)", colors,
                         box_color=colors["accent"], text_color=colors["primary"], fontsize=9)

    # 나머지 섹션
    if other_secs:
        row_h = 3.6 / max(len(other_secs), 1)
        for i, sec in enumerate(other_secs):
            y = chart_top - 0.2 - i * (row_h + 0.1)
            _add_placeholder_box(ax, 5.0, y - row_h, 2.7, row_h - 0.05,
                                 sec["label"], colors,
                                 box_color="#E8EAF6", text_color=colors["primary"], fontsize=8)

    return fig


def _report(sections: list, colors: dict) -> plt.Figure:
    fig, ax = _setup_fig("report", colors)
    _draw_header(ax, "REPORT 레이아웃", colors)

    # 요약 영역
    _add_placeholder_box(ax, 0.3, 8.1, 7.4, 1.0,
                         "요약 / 핵심 내용 입력 영역", colors,
                         box_color=colors["primary"], fontsize=10)

    n = len(sections)
    if n == 0:
        return fig

    cols = 2 if n > 3 else 1
    rows = (n + cols - 1) // cols
    cell_w = 7.4 / cols - 0.1
    cell_h = min(6.8 / rows - 0.1, 1.8)

    for i, sec in enumerate(sections):
        col = i % cols
        row = i // cols
        x = 0.3 + col * (cell_w + 0.1)
        y = 7.8 - row * (cell_h + 0.15)
        _add_placeholder_box(ax, x, y - cell_h, cell_w, cell_h,
                             sec["label"], colors,
                             box_color=colors["accent"], text_color=colors["primary"], fontsize=9)

    return fig


def _list_layout(sections: list, colors: dict) -> plt.Figure:
    fig, ax = _setup_fig("list", colors)
    _draw_header(ax, "LIST 레이아웃", colors)

    n = len(sections)
    item_h = min(8.0 / max(n, 1), 1.3)
    icons = ["●", "■", "▲", "◆", "★", "✦", "◉", "▶"]

    for i, sec in enumerate(sections):
        y = 9.0 - i * (item_h + 0.12)
        # 아이콘 원
        circle = plt.Circle((0.65, y - item_h / 2), 0.22,
                             color=colors["primary"])
        ax.add_patch(circle)
        ax.text(0.65, y - item_h / 2, icons[i % len(icons)],
                ha="center", va="center", fontsize=9, color="white")
        # 내용 박스
        _add_placeholder_box(ax, 1.0, y - item_h + 0.05, 6.7, item_h - 0.1,
                             sec["label"], colors,
                             box_color=colors["accent"], text_color=colors["primary"], fontsize=9)

    return fig
