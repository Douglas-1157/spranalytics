"""Gráficos em imagem (PNG, JPG, PDF) com matplotlib."""

import io
import zipfile

from .config import COLORS, SERIES
from .levels import deltas, level_value
from .models import Channel, InputError
from .parsing import clean_text, read_channels, safe_name


def _mt(s):
    return str(s).replace("$", r"\$")


def _draw(ch: Channel, levels, shade=False, dpi=150, size=(8, 5.6)):
    """Figura pela API orientada a objeto do matplotlib (segura com várias requisições simultâneas)."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    t, d = deltas(ch)
    fig = Figure(figsize=size, dpi=dpi)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.plot(t, d, color="#1A5F82", lw=2.2, label=_mt(ch.name), zorder=3)
    tmax = max(t)
    for j, lv in enumerate(levels or []):
        v = level_value(t, d, lv)
        col = "#" + COLORS[j % len(COLORS)]
        ax.plot(
            [0, tmax],
            [v, v],
            ls="--",
            lw=1.8,
            color=col,
            label=f"{v:.3f}".replace(".", ",") + " mdeg",
            zorder=2,
        )
        if shade:
            ax.axvspan(lv.start, lv.end, color=col, alpha=0.16, lw=0, zorder=1)
            ax.annotate(
                _mt(lv.label),
                xy=((lv.start + lv.end) / 2, 1.0),
                xycoords=("data", "axes fraction"),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9,
                color=col,
            )
    ax.set_xlim(left=0)
    ax.spines["bottom"].set_position(("data", 0))
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="x", labelbottom=True, pad=14)
    ax.xaxis.set_label_coords(0.5, -0.12)
    ax.set_xlabel("Time(min)", family="serif", fontsize=13, color="#404040")
    ax.set_ylabel("Δθ res (mdeg)", family="serif", fontsize=13, color="#404040")
    ax.margins(y=0.06)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        ncol=1 + len(levels or []),
        frameon=False,
        fontsize=11,
    )
    fig.tight_layout()
    return fig


def render_chart(ch: Channel, levels, fmt="png", shade=False, dpi=150) -> bytes:
    fig = _draw(ch, levels, shade=shade, dpi=dpi)
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="jpeg" if fmt == "jpg" else fmt,
        bbox_inches="tight",
        facecolor="white",
        **({"pil_kwargs": {"quality": 95}} if fmt == "jpg" else {}),
    )
    return buf.getvalue()


def convert_charts(data: bytes, metric="PeakMinAngle", selected=None, levels=None, fmt="png"):
    """Devolve (bytes, mimetype, nome). 1 canal -> imagem/PDF; vários -> ZIP (png/jpg) ou PDF com 1 página por canal."""
    chans = read_channels(data, metric)
    if selected:
        chans = [c for c in chans if c.name in selected]
    if not chans:
        raise InputError("Nenhum canal selecionado.")
    mname = safe_name(metric)
    if fmt == "pdf":
        from matplotlib.backends.backend_pdf import PdfPages

        buf = io.BytesIO()
        with PdfPages(buf) as pdf:
            for c in chans:
                pdf.savefig(_draw(c, levels), bbox_inches="tight", facecolor="white")
        return buf.getvalue(), "application/pdf", f"{mname}.pdf"
    mime = "image/jpeg" if fmt == "jpg" else "image/png"
    if len(chans) == 1:
        return render_chart(chans[0], levels, fmt), mime, f"{mname}_{safe_name(chans[0].name)}.{fmt}"
    zb = io.BytesIO()
    used = set()
    with zipfile.ZipFile(zb, "w", zipfile.ZIP_DEFLATED) as z:
        for c in chans:
            entry = f"{mname}_{safe_name(c.name)}"
            base, k = entry, 2
            while entry.lower() in used:
                entry = f"{base}_{k}"
                k += 1
            used.add(entry.lower())
            z.writestr(f"{entry}.{fmt}", render_chart(c, levels, fmt))
    return zb.getvalue(), "application/zip", f"{mname}_graficos_{fmt}.zip"


def _label_offsets(points, tmax, rng):
    """Decide se cada rótulo vai em cima ou embaixo da linha, para rótulos próximos não se sobreporem."""
    placed, out = [], []
    for x, y in points:
        below = any(abs(x - px) < 0.3 * tmax and abs(y - py) < 0.05 * rng and not pb for px, py, pb in placed)
        placed.append((x, y, below))
        out.append(below)
    return out


def _draw_compare(chs, names, levels, dpi=150, size=(9, 5.8)):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure(figsize=size, dpi=dpi)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    data = [deltas(c) for c in chs]
    tmax = max(max(t) for t, _ in data)
    allv = [v for _, d in data for v in d]
    rng = (max(allv) - min(allv)) or 1.0
    pts, meta = [], []
    for k, ((t, d), nm) in enumerate(zip(data, names)):
        col = "#" + SERIES[k % len(SERIES)]
        ax.plot(t, d, color=col, lw=2.2, label=_mt(nm), zorder=3)
        for lv in levels or []:
            v = level_value(t, d, lv)
            xm = (lv.start + lv.end) / 2
            ax.plot([0, max(t)], [v, v], ls=(0, (1, 2)), lw=1.6, color=col, zorder=2)
            pts.append((xm, v))
            meta.append((xm, v, col))
    for (xm, v, col), below in zip(meta, _label_offsets(pts, tmax, rng)):
        ax.annotate(
            f"{v:.3f}".replace(".", ",") + " mdeg",
            xy=(xm, v),
            xytext=(0, -4 if below else 4),
            textcoords="offset points",
            ha="center",
            va="top" if below else "bottom",
            fontsize=10,
            color=col,
            family="serif",
            zorder=5,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85),
        )
    ax.set_xlim(left=0)
    ax.spines["bottom"].set_position(("data", 0))
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="x", labelbottom=True, pad=14)
    ax.xaxis.set_label_coords(0.5, -0.12)
    ax.set_xlabel("Time(min)", family="serif", fontsize=13, color="#404040")
    ax.set_ylabel("Δθ res (mdeg)", family="serif", fontsize=13, color="#404040")
    ax.margins(y=0.08)
    ax.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=min(len(chs), 2), frameon=False, fontsize=11
    )
    fig.tight_layout()
    return fig


def convert_compare_chart(data: bytes, metric, compare, levels, fmt="png", dpi=150):
    chans = {c.name: c for c in read_channels(data, metric)}
    pick = [(chans[c], clean_text(lg) or c) for c, lg in compare if c in chans]
    if len(pick) < 2:
        raise InputError("Escolha pelo menos 2 canais para comparar.")
    fig = _draw_compare([c for c, _ in pick], [n for _, n in pick], levels, dpi=dpi)
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format={"jpg": "jpeg"}.get(fmt, fmt),
        bbox_inches="tight",
        facecolor="white",
        **({"pil_kwargs": {"quality": 95}} if fmt == "jpg" else {}),
    )
    mime = {"png": "image/png", "jpg": "image/jpeg", "pdf": "application/pdf"}[fmt]
    return buf.getvalue(), mime, f"{safe_name(metric)}_comparacao.{fmt}"
