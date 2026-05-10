import io
import json
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False

from wireframe import THEME_COLORS, _get_colors

# ──────────────────────────────────────────────
# matplotlib 기반 최종 인포그래픽 렌더러
# ──────────────────────────────────────────────

def render_infographic(layout_type: str, title: str, sections: list,
                       user_data: dict, color_theme: str = "blue") -> bytes:
    """사용자 데이터를 채워 최종 인포그래픽 PNG를 반환한다."""
    colors = _get_colors(color_theme)
    renderers = {
        "timeline": _render_timeline,
        "compare":  _render_compare,
        "flow":     _render_flow,
        "stats":    _render_stats,
        "report":   _render_report,
        "list":     _render_list,
    }
    renderer = renderers.get(layout_type, _render_list)
    fig = renderer(title, sections, user_data, colors)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _setup(colors):
    fig, ax = plt.subplots(figsize=(8, 11))
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 11)
    ax.axis("off")
    fig.patch.set_facecolor(colors["bg"])
    ax.set_facecolor(colors["bg"])
    return fig, ax


def _draw_title(ax, title: str, colors: dict, y_top: float = 10.5):
    ax.add_patch(mpatches.FancyBboxPatch((0.2, y_top - 0.7), 7.6, 0.7,
                                         boxstyle="round,pad=0.05", linewidth=0,
                                         facecolor=colors["primary"]))
    ax.text(4.0, y_top - 0.35, title or "제목 없음",
            ha="center", va="center", fontsize=14, color="white", fontweight="bold")


def _text_box(ax, x, y, w, h, text, colors, bg=None, fc="black", fs=9, bold=False):
    bg = bg or colors["accent"]
    ax.add_patch(mpatches.FancyBboxPatch((x, y), w, h,
                                         boxstyle="round,pad=0.03", linewidth=0.5,
                                         facecolor=bg, edgecolor=colors["secondary"]))
    fw = "bold" if bold else "normal"
    ax.text(x + w / 2, y + h / 2, str(text)[:200],
            ha="center", va="center", fontsize=fs, color=fc,
            fontweight=fw, wrap=True, clip_on=True)


def _render_timeline(title, sections, data, colors):
    fig, ax = _setup(colors)
    _draw_title(ax, title, colors)
    n = len(sections)
    step_h = min(8.5 / max(n, 1), 1.5)
    y_start = 9.6

    for i, sec in enumerate(sections):
        y = y_start - i * (step_h + 0.12)
        val = data.get(sec["id"], "")
        if i < n - 1:
            ax.plot([1.0, 1.0], [y - step_h - 0.02, y - 0.22],
                    color=colors["secondary"], lw=2.5, zorder=1)
        c = plt.Circle((1.0, y - step_h / 2), 0.20, color=colors["primary"], zorder=2)
        ax.add_patch(c)
        ax.text(1.0, y - step_h / 2, str(i + 1),
                ha="center", va="center", fontsize=9, color="white", fontweight="bold")
        # 헤더
        _text_box(ax, 1.35, y - 0.38, 6.3, 0.35, sec["label"],
                  colors, bg=colors["primary"], fc="white", fs=8, bold=True)
        # 내용
        _text_box(ax, 1.35, y - step_h, 6.3, step_h - 0.42,
                  val or "(내용 없음)", colors, fs=8)

    return fig


def _render_compare(title, sections, data, colors):
    fig, ax = _setup(colors)
    _draw_title(ax, title, colors)

    col_a = data.get("col_a_label", "항목 A")
    col_b = data.get("col_b_label", "항목 B")
    _text_box(ax, 0.2, 9.1, 3.7, 0.45, col_a, colors, bg=colors["primary"], fc="white", fs=11, bold=True)
    _text_box(ax, 4.1, 9.1, 3.7, 0.45, col_b, colors, bg=colors["secondary"], fc="white", fs=11, bold=True)

    n = len(sections)
    row_h = min(8.3 / max(n, 1), 1.3)
    for i, sec in enumerate(sections):
        y = 9.0 - i * (row_h + 0.1)
        val_a = data.get(f"{sec['id']}_a", "")
        val_b = data.get(f"{sec['id']}_b", "")
        _text_box(ax, 0.2, y - row_h, 3.7, row_h - 0.05,
                  f"{sec['label']}\n{val_a or '—'}", colors,
                  bg=colors["accent"], fc=colors["primary"], fs=8)
        _text_box(ax, 4.1, y - row_h, 3.7, row_h - 0.05,
                  f"{sec['label']}\n{val_b or '—'}", colors,
                  bg="#F3E5F5", fc=colors["primary"], fs=8)
        ax.text(3.95, y - row_h / 2, "↔", ha="center", va="center",
                fontsize=11, color=colors["primary"])

    return fig


def _render_flow(title, sections, data, colors):
    fig, ax = _setup(colors)
    _draw_title(ax, title, colors)
    n = len(sections)
    box_h = 0.75
    gap = 0.45
    total = n * box_h + (n - 1) * gap
    y_start = 9.5 - (9.5 - 0.3 - total) / 2

    for i, sec in enumerate(sections):
        val = data.get(sec["id"], "")
        y = y_start - i * (box_h + gap)
        _text_box(ax, 0.8, y - box_h, 6.4, box_h,
                  f"{sec['label']}\n{val or '—'}", colors,
                  bg=colors["primary"] if i % 2 == 0 else colors["secondary"],
                  fc="white", fs=9, bold=(i % 2 == 0))
        if i < n - 1:
            ax.annotate("", xy=(4.0, y - box_h - gap + 0.08),
                        xytext=(4.0, y - box_h - 0.03),
                        arrowprops=dict(arrowstyle="-|>", color=colors["primary"], lw=2.5))

    return fig


def _render_stats(title, sections, data, colors):
    fig, ax = _setup(colors)
    _draw_title(ax, title, colors)

    number_secs = [s for s in sections if s["type"] == "number"]
    chart_secs  = [s for s in sections if s["type"] == "chart"]
    text_secs   = [s for s in sections if s["type"] not in ("number", "chart")]

    y_cur = 9.6

    # 숫자 카드
    if number_secs:
        n = min(len(number_secs), 4)
        cw = 7.6 / n - 0.1
        for i, sec in enumerate(number_secs[:4]):
            x = 0.2 + i * (cw + 0.1)
            val = data.get(sec["id"], "0")
            _text_box(ax, x, y_cur - 1.1, cw, 1.0,
                      f"{sec['label']}\n\n{val}", colors,
                      bg=colors["primary"], fc="white", fs=10, bold=True)
        y_cur -= 1.25

    # 차트 (막대)
    if chart_secs:
        sec = chart_secs[0]
        raw = data.get(sec["id"], "")
        chart_img = _make_bar_chart(sec["label"], raw, colors)
        if chart_img:
            from matplotlib.image import imread
            img_arr = plt.imread(io.BytesIO(chart_img))
            ax.imshow(img_arr, extent=[0.2, 7.8, y_cur - 3.5, y_cur], aspect="auto", zorder=3)
            y_cur -= 3.65

    # 텍스트 섹션
    if text_secs:
        tw = 7.6 / min(len(text_secs), 2) - 0.1
        for i, sec in enumerate(text_secs):
            col = i % 2
            x = 0.2 + col * (tw + 0.1)
            val = data.get(sec["id"], "")
            _text_box(ax, x, y_cur - 1.1, tw, 1.0,
                      f"{sec['label']}\n{val or '—'}", colors, fs=8)
            if col == 1 or i == len(text_secs) - 1:
                y_cur -= 1.2

    return fig


def _make_bar_chart(label: str, raw: str, colors: dict) -> bytes | None:
    if not raw.strip():
        return None
    try:
        labels, values = [], []
        for line in raw.strip().splitlines():
            parts = line.split(",")
            if len(parts) >= 2:
                labels.append(parts[0].strip())
                values.append(float(parts[1].strip()))
        if not labels:
            return None
        fig2, ax2 = plt.subplots(figsize=(6, 2.8))
        bars = ax2.bar(labels, values, color=colors["secondary"], edgecolor=colors["primary"])
        ax2.set_title(label, fontsize=9, color=colors["primary"])
        ax2.tick_params(labelsize=7)
        fig2.patch.set_facecolor(colors["bg"])
        ax2.set_facecolor(colors["bg"])
        buf = io.BytesIO()
        fig2.savefig(buf, format="png", dpi=100, bbox_inches="tight")
        plt.close(fig2)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


def _render_report(title, sections, data, colors):
    fig, ax = _setup(colors)
    _draw_title(ax, title, colors)

    summary = data.get("summary", "")
    _text_box(ax, 0.2, 8.9, 7.6, 0.8,
              summary or "요약을 입력하세요", colors,
              bg=colors["primary"], fc="white", fs=10)

    n = len(sections)
    cols = 2 if n > 3 else 1
    rows = (n + cols - 1) // cols
    cw = 7.6 / cols - 0.1
    ch = min(7.8 / rows - 0.1, 2.0)

    for i, sec in enumerate(sections):
        col = i % cols
        row = i // cols
        x = 0.2 + col * (cw + 0.1)
        y = 8.6 - row * (ch + 0.12)
        val = data.get(sec["id"], "")
        _text_box(ax, x, y - ch, cw, ch,
                  f"[{sec['label']}]\n\n{val or '—'}", colors,
                  bg=colors["accent"], fc=colors["primary"], fs=9)

    return fig


def _render_list(title, sections, data, colors):
    fig, ax = _setup(colors)
    _draw_title(ax, title, colors)
    n = len(sections)
    item_h = min(8.8 / max(n, 1), 1.4)
    icons = ["01", "02", "03", "04", "05", "06", "07", "08"]

    for i, sec in enumerate(sections):
        y = 9.6 - i * (item_h + 0.1)
        val = data.get(sec["id"], "")
        c = plt.Circle((0.62, y - item_h / 2), 0.23, color=colors["primary"])
        ax.add_patch(c)
        ax.text(0.62, y - item_h / 2, icons[i % len(icons)],
                ha="center", va="center", fontsize=7, color="white", fontweight="bold")
        ax.text(1.1, y - 0.2, sec["label"],
                fontsize=9, color=colors["primary"], fontweight="bold")
        _text_box(ax, 1.0, y - item_h, 6.8, item_h - 0.3,
                  val or "—", colors, fs=8)

    return fig


# ──────────────────────────────────────────────
# PDF 변환
# ──────────────────────────────────────────────

def export_pdf(png_bytes: bytes) -> bytes:
    """PNG를 PDF로 변환. WeasyPrint 미사용 시 PNG를 그대로 반환."""
    if not WEASYPRINT_AVAILABLE:
        return png_bytes

    b64 = base64.b64encode(png_bytes).decode()
    html = f"""<!DOCTYPE html>
<html><head><style>
  @page {{ margin: 0; size: A4; }}
  body {{ margin: 0; padding: 0; }}
  img {{ width: 100%; height: 100vh; object-fit: contain; }}
</style></head>
<body><img src="data:image/png;base64,{b64}"></body></html>"""
    pdf_bytes = HTML(string=html).write_pdf()
    return pdf_bytes
