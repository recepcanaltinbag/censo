#!/usr/bin/env python3
"""
Generate paper figures. VECTOR ONLY (PDF + SVG), ENGLISH ONLY.

No figure is ever edited by hand: every panel is regenerated from
derived/processed/* by this script, so the paper always matches the data.

Outputs -> paper/figures/
    fig01_graphical_abstract.{pdf,svg}
    fig02_study_area.{pdf,svg}
    fig03_censoring_profile.{pdf,svg}
    fig04_loq_vs_eqs.{pdf,svg}

Usage:  python scripts/90_figures.py [--only fig03]
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
FIGS = ROOT / "paper" / "figures"
FIGDATA = ROOT / "paper" / "supplementary" / "figure_data"
SHP = ROOT / "Data" / "ShapeFiles"

# ---- house style ----------------------------------------------------------
# Journal geometry: figures are drawn at final printed size, so 8 pt here is
# 8 pt on the page. Nothing is scaled at import time, which is what makes
# rescaled, mismatched type in a multi-panel figure impossible.
#
# Arial is listed FIRST deliberately. Listing Helvetica first resolves to
# Helvetica.ttc on macOS -- a TrueType *collection*, which matplotlib cannot
# subset cleanly into PDF; Arial.ttf embeds properly under pdf.fonttype 42.
def _set_rc(params):
    """Apply rcParams, skipping any this matplotlib is too old to know.

    The environment pins matplotlib 3.1 (Python 3.8), where `xtick.labelcolor`
    and `axes.titlelocation` do not exist. Failing hard on them would make the
    figures unbuildable on the recorded environment; failing silently would hide
    a style that never applied. So unknown keys are skipped and named.
    """
    unknown = []
    for k, v in params.items():
        try:
            plt.rcParams[k] = v
        except (KeyError, ValueError):
            unknown.append(k)
    if unknown:
        print(f"  note: matplotlib {matplotlib.__version__} ignores "
              f"{len(unknown)} style key(s): {', '.join(sorted(unknown))}")


_set_rc({
    "figure.dpi": 150,
    "savefig.dpi": 600,
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica Neue", "Helvetica", "DejaVu Sans"],
    "mathtext.fontset": "custom",
    "mathtext.rm": "Arial", "mathtext.it": "Arial:italic",
    "mathtext.bf": "Arial:bold",
    "font.size": 8,
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "axes.labelcolor": "#1f1f1f",
    "axes.edgecolor": "#3d3d3d",
    "axes.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titlelocation": "left",
    "axes.titlepad": 4.0,
    "xtick.labelsize": 7, "ytick.labelsize": 7,
    "xtick.color": "#3d3d3d", "ytick.color": "#3d3d3d",
    "xtick.labelcolor": "#1f1f1f", "ytick.labelcolor": "#1f1f1f",
    "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 2.6, "ytick.major.size": 2.6,
    "xtick.direction": "out", "ytick.direction": "out",
    "legend.fontsize": 7,
    "legend.frameon": False,
    "legend.handlelength": 1.3,
    "legend.handletextpad": 0.5,
    "legend.labelspacing": 0.35,
    "legend.borderaxespad": 0.2,
    "lines.linewidth": 1.0,
    "lines.solid_capstyle": "round",
    "pdf.fonttype": 42,     # embed as TrueType -> editable, not outlined
    "ps.fonttype": 42,
    "svg.fonttype": "none",  # keep text as text in SVG
})

# Elsevier column widths, inches (90 / 140 / 190 mm).
W1, W15, W2 = 3.54, 5.51, 7.48

INK = "#1f1f1f"
MUTED = "#6b7280"
GRID = "#e6e8eb"
SURFACE = "#ffffff"

# ---- palettes -------------------------------------------------------------
# Every palette below was checked with the six computable colour tests
# (lightness band, chroma floor, protan/deutan/tritan separation, normal-vision
# floor, contrast against the page) rather than chosen by eye.
#
#   verdict   categorical, all pairs   worst CVD dE 9.7, normal dE 20.5, all >= 3:1
#   ramp      ordinal, single hue      monotone L, light end 2.21:1
#
# The verdict palette is reserved for the compliance outcome -- three top
# values, the third split by the reason -- and is never reused as "some other
# series".
V = {
    "exceed":        "#a01e28",   # exceedance                     (critical)
    "possible":      "#c97b12",   # possible exceedance            (warning)
    "compliant":     "#128a6e",   # compliant                      (good)
    "indeterminate": "#7159a6",   # cannot be determined           (neutral)
}

# Detection status carries increasing information content, so it gets an
# ordinal ramp rather than four unrelated hues: the reader can see that
# censored < estimated < quantified without consulting the legend.
RAMP = ["#8ab0d6", "#3d78ad", "#123f66"]

C = {
    "water": "#3d78ad",
    "network": "#7f8c99",
    "industry": V["exceed"],
    "agri": V["compliant"],
    "urban": V["possible"],
    "censored": RAMP[0],
    "estimated": RAMP[1],
    "quantified": RAMP[2],
    "undecidable": V["indeterminate"],
    "exceed": V["exceed"],
    "compliant": V["compliant"],
}


def save(fig, name):
    """Save at EXACTLY the declared figure size.

    `bbox_inches="tight"` trims to content, which sounds harmless and is not:
    the saved width then depends on how much whitespace the labels happened to
    leave, so figures came out at 148, 152 and 135 mm rather than at a column
    width. A publisher rescales anything off-measure to fit the column, and
    rescaling changes the effective point size -- which defeats the entire
    reason for drawing at final size in the first place. Internal padding is
    handled by each figure's own layout call instead.
    """
    FIGS.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "svg"):
        fig.savefig(FIGS / f"{name}.{ext}", transparent=False,
                    facecolor=SURFACE)
    w_mm = fig.get_size_inches()[0] * 25.4
    target = min((90.0, 140.0, 190.0), key=lambda t: abs(t - w_mm))
    flag = "" if abs(target - w_mm) < 0.6 else f"  <-- {w_mm:.1f} mm, off-measure"
    plt.close(fig)
    print(f"  wrote paper/figures/{name}.pdf + .svg  "
          f"({w_mm:.0f} mm){flag}")


def panel(ax, letter, dx=-0.085, dy=1.02):
    """Panel letter, set outside the axes as journals expect."""
    ax.text(dx, dy, letter, transform=ax.transAxes, fontsize=9,
            fontweight="bold", va="bottom", ha="left", color=INK)


def title(ax, text):
    ax.set_title(text, loc="left", fontsize=8, color=INK, fontweight="normal")


def despine(ax, keep=("left", "bottom")):
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(s in keep)


def xgrid(ax, axis="x"):
    ax.grid(True, axis=axis, color=GRID, linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)


def wilson(x, n, z=1.96):
    """95 % Wilson score interval for a proportion, as percentages.

    Figure 4a selects substances BY their failure rate and then reports that
    rate, which is selection on the outcome: a substance with few assessable
    station-years can reach 100 % partly by chance, and ranking makes the
    highest estimates the ones on show. The interval is the honest answer --
    Wilson rather than Wald because these proportions sit at the boundary, where
    a normal approximation runs past 100 %.
    """
    if not n:
        return (0.0, 0.0)
    p = x / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z / d * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (100 * max(0.0, c - h), 100 * min(1.0, c + h))


def read_csv(path):
    p = PROC / path
    if not p.exists():
        return None
    return list(csv.DictReader(p.open(encoding="utf-8")))


def emit(name, header, rows):
    """Write the numbers a figure actually draws, as supplementary data.

    Called from inside each figure, at the point where the plotted values are
    final. A separate export script would be re-deriving them, and could
    therefore disagree with the figure without anything failing. Here the file
    cannot drift: it is written from the same variables the marks are drawn
    from, on the same pass.
    """
    FIGDATA.mkdir(parents=True, exist_ok=True)
    p = FIGDATA / f"{name}.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    print(f"    + {p.relative_to(ROOT)}  ({len(rows)} rows)")


# ============================================================ figure 01 ====

def fig_graphical_abstract():
    """The argument, not the architecture.

    An earlier version of this figure was a data-flow diagram: five inputs, a
    knowledge graph, a reasoner, four outputs. Two things were wrong with it. It
    showed the plumbing rather than the claim -- every knowledge-graph paper has
    that figure -- and its four output boxes were the verdicts of the
    single-basin analysis that has since been retired to attic/ and is no longer
    reported at all. The graphical abstract was leading with material the paper
    does not carry.

    This version shows one measurement read two ways against one threshold, and
    what that costs across the whole Waterbase river record.
    """
    # The mechanism is best shown on one measurement; the SCALE is what makes
    # it a finding, and the scale lives in the continental record. So the
    # consequence band reports Waterbase rather than this basin.
    wb = read_csv("waterbase_summary.csv")
    W = {}
    if wb:
        for r in wb:
            if r["scope"] == "total":
                W = {k: int(v) for k, v in r.items()
                     if k not in ("scope", "key")}
                break


    fig, ax = plt.subplots(figsize=(W2, 4.15))
    # This panel is drawn in its own 0-100 coordinate frame, so the default
    # axes margins were pure waste: a quarter of the height and a fifth of the
    # width went to blank paper, which pushed the text into the shapes and cost
    # the whole figure its point size on the journal page.
    fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")

    ax.text(50, 97, "A non-detection is an upper bound, not a zero",
            ha="center", va="top", fontsize=11, fontweight="bold", color=INK)
    ax.text(50, 91.5,
            "The same measurement, the same legal threshold, read two ways",
            ha="center", va="top", fontsize=7.6, color=MUTED)

    # shared vertical scale: y=42 is zero concentration
    Y0, LOQ_Y, T_Y, TOP = 42.0, 62.0, 54.0, 78.0

    def frame(x0, x1, accent, header, sub):
        ax.add_patch(FancyBboxPatch(
            (x0, 26), x1 - x0, 58,
            boxstyle="round,pad=0.6,rounding_size=1.4",
            linewidth=1.0, edgecolor=accent, facecolor=accent + "0e", zorder=1))
        ax.text((x0 + x1) / 2, 80.5, header, ha="center", va="top",
                fontsize=8.4, fontweight="bold", color=INK, zorder=3)
        ax.text((x0 + x1) / 2, 76.6, sub, ha="center", va="top",
                fontsize=6.6, color=MUTED, zorder=3)

    # ---------------- left: what the database stores ----------------
    frame(3, 47, V["exceed"], "What the record stores",
          "a number, indistinguishable from a measured zero")
    axl = 14.0
    ax.plot([axl, axl], [Y0, TOP - 6], color=MUTED, linewidth=0.8, zorder=2)
    ax.plot([axl - 1.2, axl + 1.2], [Y0, Y0], color=MUTED, linewidth=0.8, zorder=2)
    ax.plot([axl], [Y0], marker="o", markersize=8, color=RAMP[2],
            markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=4)
    ax.text(axl + 2.6, Y0, "0.0", fontsize=9, fontweight="bold", color=RAMP[2],
            va="center", ha="left", zorder=4)
    ax.plot([axl - 3, 43], [T_Y, T_Y], color=V["compliant"], linewidth=1.8,
            zorder=3)
    ax.text(43, T_Y + 1.6, "threshold $T$", fontsize=6.6,
            color=V["compliant"], ha="right", va="bottom", zorder=4)
    ax.text(25, 33.5, "Compliant", ha="center", fontsize=10,
            fontweight="bold", color=V["compliant"], zorder=4)
    ax.text(25, 29.6, "one of two possible verdicts", ha="center",
            fontsize=6.4, color=MUTED, zorder=4)

    # ---------------- right: what the measurement established -------
    frame(53, 97, V["compliant"], "What the measurement established",
          "an interval: the analyte may be present below the limit")
    axr = 64.0
    ax.plot([axr, axr], [Y0, TOP - 6], color=MUTED, linewidth=0.8, zorder=2)
    ax.plot([axr - 1.2, axr + 1.2], [Y0, Y0], color=MUTED, linewidth=0.8, zorder=2)
    ax.add_patch(plt.Rectangle((axr - 3.2, Y0), 6.4, LOQ_Y - Y0,
                               facecolor=RAMP[0], alpha=0.75,
                               edgecolor=RAMP[2], linewidth=1.0, zorder=3))
    ax.plot([axr - 5, 93], [LOQ_Y, LOQ_Y], color=MUTED, linewidth=0.7,
            linestyle=(0, (3, 2)), zorder=3)
    ax.text(93, LOQ_Y + 1.4, "LOQ", fontsize=6.6, color=MUTED, ha="right",
            va="bottom", zorder=4)
    # Left of the box and below the threshold line. Everything else is taken:
    # T runs across the middle and is annotated to the right, the incoming
    # arrow enters higher up, and the verdict caption sits underneath.
    ax.text(axr - 5.0, (Y0 + T_Y) / 2, "$[0,\\mathrm{LOQ}]$", fontsize=8.6,
            fontweight="bold", color=RAMP[2], va="center", ha="right", zorder=4)
    ax.plot([axr - 8, 93], [T_Y, T_Y], color=V["indeterminate"], linewidth=1.8,
            zorder=5)
    ax.text(93, T_Y - 2.4, "the same $T$ — now inside the interval",
            fontsize=6.6, color=V["indeterminate"], ha="right", va="top",
            zorder=5)
    ax.text(75, 33.5, "Cannot be determined", ha="center", fontsize=10,
            fontweight="bold", color=V["indeterminate"], zorder=4)
    ax.text(75, 29.6, "a verdict the two-valued model cannot express",
            ha="center", fontsize=6.4, color=MUTED, zorder=4)

    ax.add_patch(FancyArrowPatch((47.6, 55), (52.4, 55), arrowstyle="-|>",
                                 mutation_scale=11, linewidth=1.2,
                                 color=INK, zorder=6))

    # ---------------- the mechanism, in one line --------------------
    ax.text(50, 23.4,
            "CENSO binds the quantification limit to the analytical run rather "
            "than to the instrument, so the interval survives into the data.",
            ha="center", va="center", fontsize=7.2, color=INK, zorder=3)

    # ---------------- the consequence, at continental scale ---------
    ax.add_patch(FancyBboxPatch(
        (3, 6.6), 94, 14, boxstyle="round,pad=0.5,rounding_size=1.2",
        linewidth=0, facecolor="#f2f4f6", zorder=1))
    if W and W.get("n"):
        nrows, samp = W["n"], max(W.get("samples", 0), 1)
        stats = [
            (17, f"{100*W.get('samples_below',0)/samp:.0f}%", RAMP[2],
             f"of {samp/1e6:.0f} million European samples\n"
             f"lie below the quantification limit"),
            (50, f"{100*W.get('silent',0)/nrows:.0f}%", V["indeterminate"],
             "of station-years record neither a\n"
             "censoring flag nor a limit"),
            # Article 4(1) of 2009/90/EC, not the weaker Article 3(3b) test:
            # the law requires the limit to sit at or below 30% of the
            # standard, and that is the criterion the monitoring had to meet.
            (84, f"{100*W.get('loq_gt_30pct_eqs',0)/max(W.get('has_eqs',1),1):.0f}%",
             V["exceed"],
             # The denominator here is rows that HAVE a standard to be
             # assessed against, not all station-years. Leaving it implicit
             # invites the reader to divide by 4.2 million and be wrong by a
             # factor of five.
             "of assessments against a European\n"
             "standard use a method failing the\n"
             "legal LOQ criterion (2009/90/EC)"),
        ]
        emit("fig01_graphical_abstract",
             ["statistic", "numerator", "denominator", "percent"],
             [["samples below the quantification limit",
               W.get("samples_below", 0), samp,
               f"{100*W.get('samples_below',0)/samp:.3f}"],
              ["station-years with neither a flag nor a limit",
               W.get("silent", 0), nrows,
               f"{100*W.get('silent',0)/nrows:.3f}"],
              ["assessments whose LOQ exceeds 30% of the standard",
               W.get("loq_gt_30pct_eqs", 0), W.get("has_eqs", 0),
               f"{100*W.get('loq_gt_30pct_eqs',0)/max(W.get('has_eqs',1),1):.3f}"]])
        for x, big, colr, sub in stats:
            ax.text(x, 16.3, big, fontsize=16, fontweight="bold", color=colr,
                    ha="center", va="center", zorder=3)
            ax.text(x, 9.7, sub, fontsize=6.0, color=INK, ha="center",
                    va="center", zorder=3, linespacing=1.4)
        for xsep in (33.5, 67):
            ax.plot([xsep, xsep], [8.7, 18.9], color="#d5d9de",
                    linewidth=0.8, zorder=2)
        ax.text(50, 2.4,
                "EEA Waterbase: 4.2 million river station-years, 637 "
                "substances, 37 countries.\nThe share recording no limit "
                "ranges from 3\u2009% to 97\u2009% between countries "
                "\u2014 reporting practice, not chemistry.",
                fontsize=6.1, color=MUTED, ha="center", va="center", zorder=3,
                linespacing=1.5)


    save(fig, "fig01_graphical_abstract")


# ============================================================ figure 02 ====

def fig_europe_map():
    """Where the record carries its limit, and where it does not.

    A monitoring map would be decoration. What this shows instead is the split
    the paper is about, laid over geography: stations are coloured by whether
    their reporting authority records the limit of quantification, and the
    pattern follows borders rather than rivers.

    THREE THINGS THIS FIGURE HAS TO GET RIGHT, and did not before.

    Projection. Longitude and latitude plotted as x and y stretch northern
    Europe and squash the Mediterranean, so Scandinavia looked enormous and the
    Balkans cramped -- and the eye reads area. EPSG:3035 (ETRS89-LAEA) is the
    equal-area projection the EEA publishes European maps in, which is also the
    projection the reader will have seen this record in elsewhere.

    Honesty of the encoding. The colour is a property of the reporting AUTHORITY,
    not of the station: every dot in a country carries the same value. Drawn as
    bare points that invites the reader to see site-level variation that is not
    there, so each country is labelled at its own station centroid with its code
    and its rate. The quantity is national and now reads as national.

    Overplotting. 7,500 markers on 140 mm collide. Countries are drawn from the
    lowest rate to the highest, so the finding is never hidden underneath, and
    the markers carry a hairline edge that keeps a dense cluster legible instead
    of collapsing into a blob.

    No coastline is drawn: no boundary file ships with this repository and none
    is downloaded, so the outline of Europe here is the monitoring network
    itself. Drawing an invented border would be worse than drawing none.
    """
    st = read_csv("waterbase_stations.csv")
    summ = read_csv("waterbase_summary.csv")
    if not st or not summ:
        print("  skip fig02 (run scripts 22 and 23 first)")
        return

    silent, n_of = {}, {}
    for r in summ:
        if r["scope"] == "country" and int(r["n"]) >= 2000:
            silent[r["key"]] = 100 * int(r["silent"]) / int(r["n"])
            n_of[r["key"]] = int(r["n"])

    pts = [(float(s["lon"]), float(s["lat"]), silent.get(s["country"]),
            s["country"])
           for s in st if s["lat"] and s["lon"]]
    pts = [p for p in pts if -32 < p[0] < 45 and 33 < p[1] < 72]

    # Station coordinates are already public in Waterbase, and without them
    # the map cannot be checked at all. Shipped in lon/lat, not in projected
    # metres: a reader should not have to invert our projection to use them.
    emit("fig02_europe_map",
         ["lon", "lat", "country", "country_pct_silent"],
         [[f"{lo:.5f}", f"{la:.5f}", c,
           "" if v is None else f"{v:.3f}"] for lo, la, v, c in pts])

    # ETRS89-LAEA. If pyproj is missing the figure still draws, in lon/lat, and
    # says so rather than pretending to a projection it did not apply.
    proj_name = "longitude/latitude"
    try:
        from pyproj import Transformer
        tr = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
        xy = [tr.transform(lo, la) for lo, la, _, _ in pts]
        proj_name = "ETRS89-LAEA (EPSG:3035)"
    except Exception:
        xy = [(lo, la) for lo, la, _, _ in pts]

    fig, ax = plt.subplots(figsize=(W15, 4.7))
    P = [(x, y, v, c) for (x, y), (_, _, v, c) in zip(xy, pts)]
    unknown = [q for q in P if q[2] is None]
    known = [q for q in P if q[2] is not None]
    if unknown:
        ax.scatter([q[0] for q in unknown], [q[1] for q in unknown],
                   s=2.0, c="#ccd0d6", linewidths=0, zorder=2,
                   label=f"authority not summarised (n={len(unknown):,})")
    # lowest rate first, so a country that records its limits cannot be buried
    # under one that does not
    known.sort(key=lambda q: q[2])
    sc = ax.scatter([q[0] for q in known], [q[1] for q in known],
                    c=[q[2] for q in known], s=4.2, linewidths=0.15,
                    edgecolors=SURFACE, cmap="RdPu", vmin=0, vmax=100,
                    zorder=3)

    # One label per country, at its own station centroid: the value is national,
    # so it is written where the national cluster is. Countries with too few
    # stations to place a legible label are left to the colourbar.
    cent = defaultdict(list)
    for x, y, v, c in known:
        cent[c].append((x, y, v))
    # Greedy placement, biggest network first: the centroid if it is free, then
    # a ring of offsets. A label that cannot be placed without covering another
    # is dropped rather than overlapped -- LV over LT and HR over BA were both
    # unreadable, and an unreadable label is worse than none, since the country
    # is still coloured and still in the shipped data.
    xs_all = [q[0] for q in P]
    ys_all = [q[1] for q in P]
    span_x, span_y = max(xs_all) - min(xs_all), max(ys_all) - min(ys_all)
    lw, lh = 0.052 * span_x, 0.026 * span_y      # label half-extents
    RING = [(0, 0), (0, 1.35), (0, -1.35), (1.5, 0), (-1.5, 0),
            (1.3, 1.1), (-1.3, 1.1), (1.3, -1.1), (-1.3, -1.1)]
    placed, dropped = [], 0
    for c, qs in sorted(cent.items(), key=lambda kv: -len(kv[1])):
        if len(qs) < 25:
            continue
        cx = sum(q[0] for q in qs) / len(qs)
        cy = sum(q[1] for q in qs) / len(qs)
        spot = None
        for dx, dy in RING:
            px, py = cx + dx * lw, cy + dy * lh
            if not any(abs(px - qx) < 1.9 * lw and abs(py - qy) < 1.7 * lh
                       for qx, qy in placed):
                spot = (px, py)
                break
        if spot is None:
            dropped += 1
            continue
        placed.append(spot)
        if spot != (cx, cy):
            ax.plot([cx, spot[0]], [cy, spot[1]], color=MUTED, linewidth=0.4,
                    zorder=5)
        ax.annotate(f"{c} {qs[0][2]:.0f}\u2009%", xy=spot, fontsize=5.9,
                    ha="center", va="center", zorder=6, color=INK,
                    bbox=dict(boxstyle="round,pad=0.16", facecolor=SURFACE,
                              edgecolor="none", alpha=0.86))
    if dropped:
        print(f"    fig02: {dropped} label(s) dropped to avoid overlap")

    cb = fig.colorbar(sc, ax=ax, orientation="horizontal", fraction=0.036,
                      pad=0.03, aspect=42)
    cb.set_label("Station-years recording no quantification limit (%)",
                 fontsize=7)
    cb.set_ticks([0, 25, 50, 75, 100])
    cb.ax.tick_params(labelsize=6.5, length=2)
    cb.outline.set_visible(False)

    ax.set_aspect("equal")
    ax.set_xlim(min(xs_all) - 0.02 * span_x, max(xs_all) + 0.02 * span_x)
    ax.set_ylim(min(ys_all) - 0.03 * span_y, max(ys_all) + 0.05 * span_y)
    ax.set_xticks([]); ax.set_yticks([])
    despine(ax, keep=())
    if unknown:
        ax.legend(loc="lower left", fontsize=6.2, frameon=False,
                  markerscale=2.2, handletextpad=0.4)
    # The projection belongs on the map, not in the title, which ran off the
    # canvas once it carried both.
    ax.text(0.995, 0.005, proj_name, transform=ax.transAxes, fontsize=5.6,
            color=MUTED, ha="right", va="bottom")
    title(ax, f"The {len(pts):,} stations that carry coordinates, coloured by "
              f"whether their\nreporting authority records the quantification "
              f"limit")
    fig.tight_layout()
    save(fig, "fig02_europe_map")


# ============================================================ figure 03 ====

def fig_country_scatter():
    """Why the failure rate understates itself.

    A country can only be found to breach the quantification-limit criterion
    where it reported a limit to check. Plotting the two against each other
    makes the artefact visible: the authorities that record least appear to
    fail least, which is the opposite of what the numbers mean.
    """
    summ = read_csv("waterbase_summary.csv")
    if not summ:
        print("  skip fig03 (run scripts/22_waterbase_external.py first)")
        return
    rows = []
    for r in summ:
        if r["scope"] != "country" or int(r["n"]) < 5000:
            continue
        n, eq = int(r["n"]), int(r["has_eqs"])
        if eq < 500:
            continue
        rows.append((r["key"], 100 * int(r["silent"]) / n,
                     100 * int(r["loq_gt_30pct_eqs"]) / eq, n))
    if len(rows) < 6:
        print("  skip fig03 (too few countries)")
        return

    # Which reporters the Directive's quantification-limit criterion actually
    # binds. Colour carries this rather than country identity: with 28 points
    # a categorical hue per country would be unreadable and, worse, would
    # encode nothing. Flags were considered and rejected -- at 7 pt they are
    # raster noise, they vanish in greyscale, and they carry contested borders.
    # Guarded like every other read_csv in this file. It was not, and it is
    # the only one that was not: read_csv returns None for a missing file, so
    # `for r in conf` raised a bare TypeError and took figures 04, 05 and 06
    # down with it -- main() iterates FIGURES in order with no per-figure
    # recovery. Reachable whenever stage 25 is skipped or fails while
    # waterbase_summary.csv is present.
    eu_ms = set()
    for r in read_csv("country_confounders.csv") or []:
        if r.get("eu") == "yes":
            eu_ms.add(r["country"])

    fig, ax = plt.subplots(figsize=(W15, 3.9))
    # Marker size is reporting volume; a country with 5,000 station-years and
    # one with 400,000 should not read as equally settled.
    for nm, x, y, n in rows:
        member = nm in eu_ms
        ax.scatter([x], [y], s=max(14, min(150, 12 * (n / 20000) ** 0.5 * 6)),
                   c=V["indeterminate"] if member else "#b8bec7",
                   alpha=0.55 if member else 0.75, linewidths=0, zorder=3)

    # Every point is labelled. Partial labelling made the figure look like a
    # ranking of the few countries named, which is not what it shows.
    #
    # Placement tries candidate offsets in order and takes the first that
    # collides with nothing already placed. A single fixed offset with a
    # one-step nudge left BG over RS and PL over AT; candidates fix both
    # without hand-tuning per country, which would not survive a data update.
    xr = 108.0
    yr = max(70.0, max(r[2] for r in rows) + 8.0) + 4.0
    # label half-extents in data units, from 6.2 pt text on this axis size
    lw, lh = 0.030 * xr, 0.030 * yr
    CAND = [(5.0, 2.6, "left"), (-5.0, 2.6, "right"),
            (5.0, -5.4, "left"), (-5.0, -5.4, "right"),
            (0.0, 7.0, "center"), (0.0, -9.0, "center")]
    placed = []
    for nm, x, y, n in sorted(rows, key=lambda r: -r[3]):
        best = None
        for dx, dy, ha in CAND:
            cx = x + dx * xr / 380.0 + (lw if ha == "left" else
                                        -lw if ha == "right" else 0.0)
            cy = y + dy * yr / 260.0
            if not any(abs(cx - px) < 2 * lw and abs(cy - py) < 1.6 * lh
                       for px, py in placed):
                best = (dx, dy, ha, cx, cy)
                break
        dx, dy, ha, cx, cy = best or (CAND[0] + (x, y))
        ax.annotate(nm, (x, y), fontsize=6.2,
                    color=INK if nm in eu_ms else MUTED, ha=ha,
                    xytext=(dx, dy), textcoords="offset points", zorder=4)
        placed.append((cx, cy))

    emit("fig03_country_practice",
         ["country", "eu_member_state", "pct_silent", "pct_failing_criterion",
          "station_years"],
         [[nm, "yes" if nm in eu_ms else "no", f"{x:.3f}", f"{y:.3f}", n]
          for nm, x, y, n in sorted(rows)])

    ax.set_xlim(-4, 104)
    ax.set_ylim(-4, max(70, max(r[2] for r in rows) + 8))
    ax.set_xlabel("Station-years recording neither a censoring flag nor a "
                  "quantification limit (%)")
    ax.set_ylabel("Failing the legal\nLOQ criterion (%)")
    xgrid(ax, axis="both")
    ax.legend(handles=[
        Line2D([], [], marker="o", linestyle="none", markersize=5,
               markerfacecolor=V["indeterminate"], markeredgecolor="none",
               alpha=0.7, label="EU Member State (criterion is binding)"),
        Line2D([], [], marker="o", linestyle="none", markersize=5,
               markerfacecolor="#b8bec7", markeredgecolor="none",
               label="Other EEA reporter"),
        Line2D([], [], marker="o", linestyle="none", markersize=8,
               markerfacecolor=MUTED, markeredgecolor="none", alpha=0.4,
               label="Marker area: station-years reported")],
        loc="upper left", bbox_to_anchor=(0.0, -0.22), ncol=3,
        columnspacing=1.0)
    title(ax, "A country can only be found in breach where it recorded a limit\n"
              "to check, so the measured failure rate is a lower bound")
    fig.tight_layout()
    save(fig, "fig03_country_practice")


# ============================================================ figure 04 ====

def fig_loq_vs_eqs():
    """Substances whose quantification limit exceeds what the law allows.

    Drawn as a lollipop rather than as bars. Every value here sits between 85
    and 100 %, so filled bars produce a solid block that distinguishes nothing
    and reads as decoration; a thin stem with a dot keeps the ranking legible
    and lets the eye rest on the one thing that varies. The count of assessable
    station-years sits in its own column on the right, where it cannot collide
    with the substance names -- an earlier version put it beside the axis and
    the two overlapped into unreadable strings.
    """
    wb = read_csv("waterbase_summary.csv")
    if not wb:
        print("  skip fig04 (run scripts/22_waterbase_external.py first)")
        return
    euro = []
    for r in wb:
        if r["scope"] != "substance":
            continue
        n_eqs = int(r["has_eqs"])
        n_gt = int(r.get("loq_gt_30pct_eqs") or r["loq_gt_eqs"])
        if n_eqs >= 1000 and n_gt:
            lo, hi = wilson(n_gt, n_eqs)
            euro.append((r["key"], 100 * n_gt / n_eqs, n_eqs, lo, hi))
    if not euro:
        print("  skip fig04 (nothing above the criterion)")
        return
    euro.sort(key=lambda x: x[1])
    emit("fig04_loq_vs_eqs",
         ["substance", "pct_failing_30pct_criterion", "assessments_made",
          "ci95_low_pct", "ci95_high_pct", "plotted"],
         [[nm, f"{s:.3f}", n, f"{lo:.3f}", f"{hi:.3f}",
           "yes" if i >= len(euro) - 14 else "no"]
          for i, (nm, s, n, lo, hi) in enumerate(euro)])
    euro = euro[-14:]

    # Two panels. The ranking alone invites "these are exotic substances";
    # the second panel answers that by showing the failure against the
    # MAGNITUDE of the standard rather than against the identity of the
    # substance -- which is the question a reader of a micropollutant paper is
    # actually asking, because regulation keeps adding substances at lower
    # thresholds.
    dec = []
    for r in wb:
        if r["scope"] != "eqs_decade":
            continue
        n_eqs = int(r["has_eqs"])
        if n_eqs >= 500:
            dec.append((int(r["key"]), 100 * int(r["loq_gt_eqs"]) / n_eqs,
                        100 * int(r["loq_gt_30pct_eqs"]) / n_eqs, n_eqs))
    dec.sort()
    # How many SUBSTANCES stand behind each decade. A rate over one substance is
    # that substance's rate: the lowest decade is deltamethrin and nothing else,
    # so the reader has to be able to see that from the shipped data.
    comp = {int(r["decade_log10_ug_l"]): r
            for r in (read_csv("eqs_decade_substances.csv") or [])}
    if dec:
        emit("fig04b_undecidable_vs_standard",
             ["standard_decade_log10_ug_l", "pct_loq_above_standard",
              "pct_failing_30pct_criterion", "assessments_made",
              "n_substances", "largest_substance", "largest_share_pct"],
             [[d, f"{a:.2f}", f"{b:.2f}", n,
               comp.get(d, {}).get("n_substances", ""),
               comp.get(d, {}).get("top_substance", ""),
               comp.get(d, {}).get("top_share_pct", "")]
              for d, a, b, n in dec])

    fig, axes = plt.subplots(
        1, 2, figsize=(W2, 0.245 * len(euro) + 1.35),
        gridspec_kw={"width_ratios": [1.75, 1.0]}) if dec else \
        (lambda f: (f, [f.gca(), None]))(
            plt.figure(figsize=(W15, 0.245 * len(euro) + 1.05)))
    ax = axes[0]
    y = list(range(len(euro)))
    for i, (nm, share, n_eqs, lo, hi) in enumerate(euro):
        ax.plot([0, share], [i, i], color="#dfe3e8", linewidth=1.5,
                solid_capstyle="round", zorder=1)
        # The 95 % Wilson interval. These substances are SELECTED by this rate,
        # so the interval is not decoration: it is what separates a substance
        # measured 20,000 times from one measured 1,100 times, and the ranking
        # puts the least certain estimates at the top.
        ax.plot([lo, hi], [i, i], color=C["exceed"], linewidth=3.0, alpha=0.28,
                solid_capstyle="butt", zorder=2)
        ax.scatter([share], [i], s=30, c=C["exceed"], linewidths=1.0,
                   edgecolors=SURFACE, zorder=3)
        # The interval drawn on this axis is sub-pixel -- every value sits
        # between 92 and 100 %, so the band is 0.6 to 2.0 percentage points wide
        # and invisible at 0-100. Truncating the axis to make it visible would
        # exaggerate differences on a percentage scale, so the guarantee is
        # written instead: the LOWER bound is what answers "is a 100 % on 1,098
        # assessments noise?", and it answers it in one number.
        ax.text(share + 2.2, i, f"{share:.0f}%", va="center", ha="left",
                fontsize=6.6, color=C["exceed"], fontweight="bold")
        ax.text(share + 16.0, i, f"\u2265{lo:.1f}", va="center", ha="left",
                fontsize=5.8, color=MUTED)
        ax.text(152, i, f"{n_eqs:,}", va="center", ha="right", fontsize=6.2,
                color=MUTED)

    ax.set_yticks(y)
    ax.set_yticklabels([e[0][:28] for e in euro], fontsize=6.9)
    ax.set_xlim(0, 153)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_ylim(-0.9, len(euro) - 0.1)
    ax.tick_params(axis="y", length=0)
    despine(ax, keep=("bottom",))
    ax.grid(True, axis="x", color=GRID, linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.spines["bottom"].set_bounds(0, 100)
    # The count column and the axis were both labelled "station-years", so a
    # percentage axis and a count column carried the same word. Only the
    # column is a count; the axis is a share of it.
    ax.text(152, len(euro) - 0.75, "assessments\nmade", ha="right",
            va="bottom", fontsize=6.2, color=MUTED, linespacing=1.15)
    ax.text(108, len(euro) - 0.55, "95\u2009% bound", ha="left",
            va="bottom", fontsize=5.8, color=MUTED)
    ax.set_xlabel("Assessments whose limit exceeds 30\u2009% of the "
                  "standard (%)")
    title(ax, "Cannot be assessed against their own standard\u2009...")

    if dec and axes[1] is not None:
        bx = axes[1]
        xs = [d[0] for d in dec]
        bx.plot(xs, [d[1] for d in dec], marker="o", markersize=4.0,
                color=C["exceed"], markeredgecolor=SURFACE,
                markeredgewidth=0.9, linewidth=1.4, zorder=3,
                label="limit exceeds the standard")
        bx.plot(xs, [d[2] for d in dec], marker="s", markersize=3.4,
                color=V["possible"], markeredgecolor=SURFACE,
                markeredgewidth=0.9, linewidth=1.2, linestyle=(0, (3, 2)),
                zorder=2, label="fails the 30\u2009% criterion")
        # A decade behind which stands ONE substance is that substance's rate,
        # not a property of the decade. Marked on the axis rather than left for
        # a reader to discover from the shipped data: the lowest decade holds
        # deltamethrin alone, and it is the most striking point in the panel.
        alone = [d for d in xs
                 if str(comp.get(d, {}).get("n_substances", "")) == "1"]
        if alone:
            bx.scatter(alone, [d[1] for d in dec if d[0] in alone], s=110,
                       facecolors="none", edgecolors=INK, linewidths=0.9,
                       zorder=4)
            bx.annotate("one substance only",
                        xy=(min(alone), 100), xytext=(min(alone) + 0.35, 78),
                        fontsize=6.0, color=INK,
                        arrowprops=dict(arrowstyle="-", linewidth=0.6,
                                        color=INK))
        bx.set_xticks(xs)
        bx.set_xticklabels([("$10^{%d}$" % d) for d in xs], fontsize=6.4)
        bx.set_ylim(-4, 104)
        bx.set_yticks([0, 25, 50, 75, 100])
        bx.set_xlabel("Annual-average standard (µg/L)")
        bx.set_ylabel("Share of assessments (%)")
        despine(bx)
        bx.grid(True, axis="y", color=GRID, linewidth=0.5, zorder=0)
        bx.set_axisbelow(True)
        bx.legend(loc="lower left", fontsize=6.2)
        title(bx, " ...and with how low it is")
        panel(axes[0], "a", dx=-0.34, dy=1.04)
        panel(bx, "b", dx=-0.22, dy=1.04)

    if dec and axes[1] is not None:
        fig.subplots_adjust(left=0.20, right=0.985, top=0.86, bottom=0.20,
                            wspace=0.42)
    else:
        fig.tight_layout()
    save(fig, "fig04_loq_vs_eqs")


# ============================================================ figure 05 ====

def fig_verdicts():
    """What the ontology returns, against what a two-valued pipeline returns.

    The two-valued rows are COUNTED, not assumed. An earlier version of this
    figure folded every unsupportable assessment into "compliant", which is
    wrong in the direction that matters: substitution pushes censored results
    ABOVE the standard, so the pipeline reports exceedances no measurement
    supports. Drawing all three substitution conventions makes the dependence
    on an arbitrary rule the subject of the figure rather than a caveat.
    """
    # The POPULATION table when it exists, the graph's when it does not. The
    # counterfactual is arithmetic on four reported fields, so there was never
    # a reason to draw it from a 40,000-row sample; it was drawn that way only
    # because the classification used to live in the graph builder.
    rows = read_csv("waterbase_verdicts_population.csv")
    source = "population"
    if not rows:
        rows = read_csv("waterbase_verdicts.csv")
        source = "graph sample"
    if not rows:
        print("  skip fig05 (run scripts/22_waterbase_external.py first)")
        return
    print(f"    fig05 drawn from the {source}")
    n = defaultdict(int)
    for r in rows:
        n[(r["substitution"], r["censo_outcome"], r["two_valued_outcome"])] \
            += int(r["n"])

    # EVERY outcome, including possible_exceedance. Omitting it dropped 6,628
    # rows from each substitution bar -- so the figure showed a 3.4-fold spread
    # where the data give 3.1 -- and left the CENSO bar spanning 723,618 of
    # 742,591, a blank 2.6 % at the right end. The class missing from that gap
    # was PossibleExceedance: the figure captioned as showing the outcomes the
    # law distinguishes was the one figure that did not draw it.
    outcomes = ("compliant", "exceedance", "possible_exceedance",
                "precondition_unmet", "method_insufficient",
                "indeterminate_unresolved", "indeterminate_other")
    tot = sum(v for (s, _, _), v in n.items() if s == "zero")
    if not tot:
        print("  skip fig05 (verdict table empty)")
        return

    # One row per substitution convention, plus CENSO. The three top rows are
    # the same data under three defensible rules; they disagree with each other
    # by more than either disagrees with the measurement.
    bars = []
    for rule, lbl in (("zero", "at zero"), ("half", "at ½ LOQ"),
                      ("full", "at LOQ")):
        exc = sum(n[(rule, o, "exceeding")] for o in outcomes)
        bars.append((f"Substitution\n{lbl}",
                     [(tot - exc, V["compliant"], "Compliant"),
                      (exc, V["exceed"], "Exceeding")], False))
    comp = sum(n[("zero", "compliant", t)] for t in ("compliant", "exceeding"))
    exc = sum(n[("zero", "exceedance", t)] for t in ("compliant", "exceeding"))
    mi = sum(n[("zero", "method_insufficient", t)]
             for t in ("compliant", "exceeding"))
    poss = sum(n[("zero", "possible_exceedance", t)]
               for t in ("compliant", "exceeding"))
    pre = sum(n[("zero", "precondition_unmet", t)]
              for t in ("compliant", "exceeding"))
    unres = sum(n[("zero", o, t)]
                for o in ("indeterminate_unresolved", "indeterminate_other")
                for t in ("compliant", "exceeding"))
    segs = [(comp, V["compliant"], "Compliant"),
            (exc, V["exceed"], "Exceeding"),
            # Short enough that five entries still fit the legend inside the
            # canvas; the caption carries what the class means.
            (poss, V["possible"], "Possible exceedance"),
            (pre, RAMP[2], "Standard not applicable to what is reported"),
            (mi, V["indeterminate"], "Method fails the standard"),
            # "No limit recorded" was wrong for the smaller of the two
            # populations merged here: indeterminate_other DOES carry a limit,
            # and is indeterminate because the value contradicts it. Both are
            # censo:BoundNotEstablished, and what they share is the bound, not
            # the limit.
            (unres, RAMP[0], "No bound established")]
    # The bar must span the whole population, or the axis lies about what was
    # assessed. Checked rather than assumed.
    assert sum(s[0] for s in segs) == tot, (
        f"fig05: CENSO bar spans {sum(s[0] for s in segs):,} of {tot:,}")
    bars.append(("CENSO", segs, True))

    emit("fig05_verdicts",
         ["bar", "segment", "n", "pct_of_total"],
         [[label.replace("\n", " "), name, val, f"{100*val/tot:.3f}"]
          for label, segs, _ in bars for val, _, name in segs])

    fig, ax = plt.subplots(figsize=(W15, 2.9))
    for row, (label, segs, legend) in enumerate(bars):
        left = 0
        for val, colr, name in segs:
            ax.barh(row, 100 * val / tot, left=left, height=0.52, color=colr,
                    edgecolor=SURFACE, linewidth=1.0,
                    label=name if legend else None)
            if 100 * val / tot > 6:
                ax.text(left + 50 * val / tot, row, f"{100*val/tot:.0f}%",
                        ha="center", va="center", fontsize=7,
                        color="white" if colr != RAMP[0] else INK,
                        fontweight="bold")
            left += 100 * val / tot
    ax.set_yticks(range(len(bars)))
    ax.set_yticklabels([b[0] for b in bars])
    # a rule separating the three counterfactual rows from the proposal
    ax.axhline(len(bars) - 1.5, color=GRID, linewidth=0.8, zorder=0)
    ax.invert_yaxis()
    ax.set_ylim(len(bars) - 0.4, -0.6)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of assessments (%)")
    ax.tick_params(axis="y", length=0)
    despine(ax, keep=("bottom",))
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, -0.26), ncol=3,
              columnspacing=1.0)
    e0 = sum(n[("zero", o, "exceeding")] for o in outcomes)
    e2 = sum(n[("full", o, "exceeding")] for o in outcomes)
    real = n[("zero", "exceedance", "exceeding")]
    # Two short lines: the long single line ran past the 140 mm canvas.
    title(ax, f"The same {tot:,} assessments, read four ways\n"
              f"Substitution reports {e0:,}\u2013{e2:,} exceedances; "
              f"{real:,} are affirmed")
    fig.tight_layout()
    save(fig, "fig05_verdicts")


# ============================================================ figure 06 ====

def fig_decision_geometry():
    """Why two verdicts are not enough: the geometry of the decision.

    This is the paper's argument in one picture. A measurement is not a point
    but an interval whose extent depends on the method, and a threshold is a
    line that may fall inside or outside it. Where the line falls inside, no
    amount of statistics recovers a verdict -- the data do not contain one.

    Every panel is a REAL observation. The geometries were previously drawn
    with illustrative numbers, which left the paper's central picture as the
    one thing in it a reader could not check. Each panel now names the
    substance, the reporting country and the actual limits in ug/L, and each
    panel is scaled to its own quantification limit because the cases span
    orders of magnitude in concentration.

    THREE PANELS, NOT FOUR. A fourth used to split the undecidable case at the
    limit of DETECTION. Waterbase reports none; the one drawn was LOQ/3, this
    pipeline's own convention, so the boundary between two panels of a figure
    captioned "real observations" was a constant we chose. Both halves are the
    same case anyway -- censored, threshold below the quantification limit,
    verdict indeterminate -- and every provision applied here is written about
    the LOQ. The LOD argument survives in the text, where it is a claim about
    representation; it is out of this figure, where it would be a claim about
    this data.
    """
    ex = read_csv("waterbase_exemplars.csv")
    if not ex:
        print("  skip fig06 (run scripts/23_waterbase_abox.py first)")
        return
    by_case = {r["case"]: r for r in ex}
    order = [("compliant", "Threshold above the limit", "compliant",
              "The interval $[0,\\mathrm{LOQ}]$ lies\nwholly below $T$."),
             ("cannot_decide", "Threshold inside the interval",
              "indeterminate",
              "$T$ falls inside $[0,\\mathrm{LOQ}]$.\nNo result this method "
              "could\nreturn would decide."),
             ("quantified_exceedance", "Quantified exceedance", "exceed",
              "A measured value above $T$.")]
    if any(k not in by_case for k, _, _, _ in order):
        print("  skip fig06 (exemplar missing for a case)")
        return

    fig, axes = plt.subplots(1, 3, figsize=(W2, 2.75))

    emit("fig06_decision_geometry",
         ["panel", "case", "substance", "cas", "country",
          "loq_ug_l", "threshold_ug_l", "value_ug_l", "censored"],
         [["abc"[i], k, by_case[k]["substance"], by_case[k]["cas"],
           by_case[k]["country"],
           by_case[k]["loq_ug_l"], by_case[k]["threshold_ug_l"],
           by_case[k]["value_ug_l"], by_case[k]["censored"]]
          for i, (k, _, _, _) in enumerate(order)])

    for ax, (key, ttl, verdict, note) in zip(axes, order):
        r = by_case[key]
        LOQ_abs = float(r["loq_ug_l"])
        # each panel in units of its own LOQ: the real cases run from
        # 0.0005 to 0.03 ug/L and share nothing but their geometry
        LOQ = 1.0
        T = float(r["threshold_ug_l"]) / LOQ_abs
        # A censored row still carries a number in Waterbase -- usually the
        # limit itself. Inferring censoring from "is there a value" therefore
        # drew three non-detections as if they were measurements.
        v = (None if r["censored"] == "yes" or not r["value_ug_l"]
             else float(r["value_ug_l"]) / LOQ_abs)
        top = max(1.35, T * 1.25, (v or 0) * 1.2)

        ax.set_xlim(-0.35, 1.35)
        ax.set_ylim(0, top * 1.45)
        despine(ax, keep=("left",))
        ax.set_xticks([])
        ax.tick_params(axis="y", length=2.6)

        # the one limit the record actually states
        ax.axhline(LOQ, color=MUTED, linewidth=0.7, linestyle=(0, (3, 2)),
                   zorder=1)
        ax.text(1.33, LOQ, "LOQ", fontsize=6, color=MUTED, va="center",
                ha="right")

        col = V[verdict]
        if v is None:
            # a non-detection: an interval, not a value. It runs to the
            # QUANTIFICATION limit -- that is the bound the record actually
            # establishes, and the only one Waterbase reports.
            ax.add_patch(plt.Rectangle((0.14, 0.0), 0.40, LOQ,
                                       facecolor=RAMP[0], alpha=0.55,
                                       edgecolor=RAMP[2], linewidth=0.8,
                                       zorder=2))
            # beside the box, not inside it: in panel (b) the threshold line
            # runs straight through the middle of the interval.
            ax.text(0.60, LOQ * 0.55, "$[0,\\mathrm{LOQ}]$", fontsize=6.4,
                    ha="left", va="center", color=INK, zorder=4)
        else:
            ax.plot([0.34], [v], marker="o", markersize=6, color=RAMP[2],
                    markeredgecolor=SURFACE, markeredgewidth=1.0, zorder=3)
            ax.plot([0.34, 0.34], [0, v], color=RAMP[2], linewidth=1.0,
                    zorder=2)

        # the threshold
        ax.axhline(T, color=col, linewidth=1.6, zorder=3)
        ax.text(-0.30, T, "$T$", fontsize=7, color=col, va="center",
                fontweight="bold")

        ax.set_title(ttl, loc="left", fontsize=7.2, color=INK)
        # the real case behind the geometry, named so it can be looked up
        sub = r["substance"].split("(")[0].strip()
        ax.text(-0.30, -0.16 * top, f"{sub[:26]} ({r['country']})\n"
                f"LOQ {float(r['loq_ug_l']):.4g}, $T$ "
                f"{float(r['threshold_ug_l']):.3g} µg/L",
                fontsize=6.0, color=INK, va="top", ha="left",
                transform=ax.transData, linespacing=1.35)
        ax.text(-0.30, -0.52 * top, note, fontsize=6.1, color=MUTED, va="top",
                ha="left", transform=ax.transData)

        name = {"compliant": "Compliant", "exceed": "Exceedance",
                "indeterminate": "Cannot be\ndetermined"}[verdict]
        ax.text(0.5, top * 1.42, name, fontsize=7, color=col,
                fontweight="bold", ha="center", va="top")

    # No shared y-label: the panels do not share a scale, so one would be a
    # lie about the axis. The scaling is stated in the caption instead.
    for ax in axes:
        ax.set_yticks([])
    for i, ax in enumerate(axes):
        panel(ax, "abc"[i], dx=-0.12, dy=1.10)

    fig.subplots_adjust(bottom=0.30, top=0.86)
    save(fig, "fig06_decision_geometry")


# ============================================================ figure 07 ====

def _matrix(ax, rows, cols, cell, highlight, label, row_axis, col_axis, note):
    """A compliance cross-tabulation drawn as a matrix of real counts.

    Deliberately not a heat map. What matters here is not "how big" but "which
    cell is off the diagonal", and a continuous scale over counts spanning
    three orders of magnitude renders every off-diagonal cell as the same pale
    square -- which is exactly the information the figure exists to carry. So:
    agreement is grey, disagreement takes the verdict colour of what it changes
    INTO, empty cells take no fill at all, and the cell the argument turns on
    is outlined.
    """
    n_r, n_c = len(rows), len(cols)
    ax.set_xlim(-0.02, n_c)
    ax.set_ylim(n_r + 0.10, -1.15)
    ax.axis("off")
    total = sum(cell.get((r, c), 0) for r in rows for c in cols) or 1

    # Both axis names in AXES fractions, so they sit in the same place
    # whether the panel is two columns wide or four. Data coordinates put the
    # 2x2 panel's label on top of its own row labels.
    ax.text(0.5, 1.005, col_axis, transform=ax.transAxes, ha="center",
            va="bottom", fontsize=6.8, color=INK, fontweight="bold")
    # Offset in POINTS, not in axes fractions. A fraction of the axes width is
    # a different absolute distance in a two-column panel than in a four-column
    # one, so the narrow panel's label was pushed off the page.
    ax.annotate(row_axis, xy=(0, 0.5), xycoords="axes fraction",
                xytext=(-62, 0), textcoords="offset points", rotation=90,
                ha="center", va="center", fontsize=6.8, color=INK,
                fontweight="bold")

    for j, c in enumerate(cols):
        ax.text(j + 0.5, -0.14, label(c), ha="center", va="bottom",
                fontsize=6.4, color=MUTED, linespacing=1.2)
    for i, r in enumerate(rows):
        ax.text(-0.04 * n_c, i + 0.5, label(r), ha="right", va="center",
                fontsize=6.4, color=MUTED, linespacing=1.2)
        for j, c in enumerate(cols):
            v = cell.get((r, c), 0)
            if v:
                same = (r == c)
                face = GRID if same else V.get(_verdict_colour(c), MUTED)
                a = 0.28 if same else min(0.20 + 0.65 * (v / total) ** 0.35,
                                          0.85)
                ax.add_patch(plt.Rectangle((j + 0.04, i + 0.06), 0.92, 0.88,
                                           facecolor=face, alpha=a,
                                           edgecolor="none", zorder=1))
                ax.text(j + 0.5, i + 0.5, f"{v:,}", ha="center", va="center",
                        fontsize=6.8, color=INK, zorder=4,
                        fontweight="bold" if (r, c) == highlight else "normal")
            else:
                ax.text(j + 0.5, i + 0.5, "0", ha="center", va="center",
                        fontsize=6.4, color="#b8bcc2", zorder=4)
            if (r, c) == highlight:
                ax.add_patch(plt.Rectangle((j + 0.04, i + 0.06), 0.92, 0.88,
                                           facecolor="none", edgecolor=INK,
                                           linewidth=1.3, zorder=3))
    # Anchored in axes fractions and kept SHORT. A note long enough to carry
    # the argument runs past the panel it belongs to; the argument belongs in
    # the caption, and the panel gets the one number that identifies it.
    ax.text(0, -0.20, note, transform=ax.transAxes, ha="left", va="top",
            fontsize=6.2, color=MUTED, linespacing=1.45)


def _verdict_colour(outcome):
    o = str(outcome).lower()
    if "exceed" in o and "possible" not in o:
        return "exceed"
    if "compliant" in o:
        return "compliant"
    return "indeterminate"


def fig_two_thresholds():
    """What a threshold column cannot hold, on real observations.

    Figure 5 shows a verdict moving with a substitution CONVENTION. This one
    shows it moving with the two things that belong to the THRESHOLD rather
    than to the measurement, and that a single numeric column has nowhere to
    put:

      (a) which jurisdiction's standard applies, and
      (b) which KIND of standard it is -- an annual average, defined against a
          mean, or a maximum allowable concentration, defined against one
          sample.

    Both panels cross-tabulate the same observations assessed twice. Neither
    verdict in an off-diagonal cell is wrong: they answer different questions,
    and Annex I asks both. That is the argument for holding a compliance
    outcome on an observation-THRESHOLD pair rather than on an observation, and
    it is why the four outcomes are not disjoint at the class level.
    """
    dual = read_csv("dual_regulation.csv")
    mac = read_csv("mac_exceedance.csv")
    panels = []

    # MAC FIRST, deliberately. Both standards in panel (a) are stated by the
    # same instrument, are in force over the same waters, and apply to the same
    # substances -- nothing about it is counterfactual, so it carries the
    # argument on its own. The two-jurisdiction panel generalises the point to a
    # second legal instrument, but its second package is explicitly a
    # swappability demonstration rather than an assessment, and leading with it
    # would invite the reader to weigh a comparison the paper does not make.
    if mac:
        cross = {r["key"]: int(r["n"]) for r in mac
                 if r["scope"] == "station_year_cross"}
        both = cross.get("both_assessable", 0)
        if both:
            cell = {(a, b): cross.get(f"{a}_aa__{b}_mac", 0)
                    for a in ("compliant", "exceeding")
                    for b in ("compliant", "exceeding")}
            hidden = cell[("compliant", "exceeding")]
            other = cell[("exceeding", "compliant")]
            panels.append((
                "Two kinds of standard", ["compliant", "exceeding"],
                ["compliant", "exceeding"], cell,
                ("compliant", "exceeding"), lambda o: o,
                "annual average", "maximum allowable",
                f"{both:,} station-years, both standards\n"
                f"{hidden + other:,} ({100*(hidden+other)/both:.1f}%) "
                f"disagree"))

    if dual:
        cell, seen = {}, []
        for r in dual:
            if r["scope"] != "cross_co_regulated":
                continue
            a, b = r["eu_outcome"], r["tr_outcome"]
            cell[(a, b)] = cell.get((a, b), 0) + int(r["n"])
            for x in (a, b):
                if x not in seen:
                    seen.append(x)
        if cell:
            order = [o for o in ("Compliant", "MethodInsufficient",
                                 "Exceeding", "BoundNotEstablished")
                     if o in seen]
            order += [o for o in seen if o not in order]
            short = {"Compliant": "compliant",
                     "MethodInsufficient": "method\ninsufficient",
                     "Exceeding": "exceeding",
                     "BoundNotEstablished": "no bound\nestablished"}
            tot = sum(cell.values())
            diff = sum(v for (a, b), v in cell.items() if a != b)
            panels.append((
                "Two jurisdictions, one observation", order, order, cell,
                ("MethodInsufficient", "Compliant"),
                lambda o: short.get(o, o),
                "European standard", "Turkish standard",
                f"{tot:,} co-regulated assessments\n"
                f"{diff:,} ({100*diff/tot:.1f}%) off the diagonal"))

    if not panels:
        print("  skip fig07 (needs dual_regulation.csv or mac_exceedance.csv)")
        return

    emit("fig07_two_thresholds",
         ["panel", "row_standard", "row_outcome", "column_standard",
          "column_outcome", "n"],
         [["ab"[i], p[6], r, p[7], c, p[3].get((r, c), 0)]
          for i, p in enumerate(panels) for r in p[1] for c in p[2]])

    fig, axes = plt.subplots(1, len(panels), figsize=(W2, 3.1),
                             gridspec_kw={"width_ratios":
                                          [len(p[2]) + 1.7 for p in panels]})
    if len(panels) == 1:
        axes = [axes]
    for ax, p in zip(axes, panels):
        _matrix(ax, p[1], p[2], p[3], p[4], p[5], p[6], p[7], p[8])
        ax.set_title(p[0], loc="left", fontsize=7.4, color=INK, pad=16)
    for i, ax in enumerate(axes):
        panel(ax, "ab"[i], dx=-0.13, dy=1.05)
    fig.subplots_adjust(left=0.135, right=0.995, top=0.80, bottom=0.22,
                        wspace=0.80)
    save(fig, "fig07_two_thresholds")


# =============================================================== driver ====

# ============================================================ figure 08 ====

def fig_by_year():
    """Year by year: which failure was fixed, and which was not.

    The two-era split answers "was the boundary chosen to suit the answer".
    It cannot answer the question a reader of a monitoring paper actually asks:
    is this improving, or is it still happening. Only an annual series can, and
    the annual series says something sharper than the split does -- the
    record-keeping failure ends ABRUPTLY, in 2013, two years before the boundary
    the paper drew, and the analytical failure is where it was twelve years
    later.

    Panel (b) is not decoration. Before 2005 almost no row carries a limit at
    all, so the legal criteria read 0 % for want of anything to test rather than
    because the monitoring met them. Drawing the rates without the denominator
    invites exactly that misreading.
    """
    rows = [r for r in (read_csv("waterbase_summary.csv") or [])
            if r["scope"] == "year"]
    if not rows:
        print("  skip fig08 (no year scope; re-run scripts/22)")
        return
    rows.sort(key=lambda r: int(r["key"]))
    yr = [int(r["key"]) for r in rows]
    n = [int(r["n"]) for r in rows]
    eq = [max(int(r["has_eqs"]), 1) for r in rows]
    cen = [max(int(r["censored"]), 1) for r in rows]
    silent = [100 * int(r["silent"]) / max(int(r["n"]), 1) for r in rows]
    crit = [100 * int(r["loq_gt_30pct_eqs"]) / e for r, e in zip(rows, eq)]
    over = [100 * int(r["loq_gt_eqs"]) / e for r, e in zip(rows, eq)]
    subst = [100 * int(r["censored_with_value"]) / c for r, c in zip(rows, cen)]
    testable = [100 * int(r["has_eqs"]) / max(int(r["n"]), 1) for r in rows]

    # Only years the record can actually speak about. A year holding a few
    # thousand station-years from one or two reporters is noise on a percentage.
    FLOOR = 20000
    keep = [i for i, v in enumerate(n) if v >= FLOOR]
    if len(keep) < 5:
        print("  skip fig08 (too few years above the floor)")
        return
    k = lambda s: [s[i] for i in keep]

    emit("fig08_by_year",
         ["year", "station_years", "no_flag_no_limit_pct",
          "fails_30pct_criterion_pct", "loq_above_standard_pct",
          "censored_with_value_pct", "has_a_european_standard_pct", "plotted"],
         [[yr[i], n[i], f"{silent[i]:.3f}", f"{crit[i]:.3f}", f"{over[i]:.3f}",
           f"{subst[i]:.3f}", f"{testable[i]:.3f}", i in keep]
          for i in range(len(rows))])

    fig, (ax, bx) = plt.subplots(
        2, 1, figsize=(W15, 4.3), sharex=True,
        gridspec_kw={"height_ratios": [2.5, 1], "hspace": 0.18})

    series = [(k(silent), V["indeterminate"], "neither a flag nor a limit"),
              (k(crit), V["exceed"], "fails the 30\u2009% criterion"),
              (k(over), V["possible"], "limit above the standard"),
              (k(subst), V["compliant"], "censored rows carrying a value")]
    for ys, colr, lbl in series:
        ax.plot(k(yr), ys, marker="o", markersize=2.6, linewidth=1.4,
                color=colr, label=lbl)

    # the year the record-keeping failure stops, read from the data rather than
    # asserted: the first year at 0.0 % that is never followed by a non-zero one
    zero_from = None
    for i in keep:
        if silent[i] < 0.05 and all(silent[j] < 0.05 for j in keep if j >= i):
            zero_from = yr[i]
            break
    if zero_from:
        for a in (ax, bx):
            a.axvline(zero_from, color=INK, linewidth=0.8,
                      linestyle=(0, (4, 3)), zorder=0)
        ax.annotate(f"{zero_from}: no reporter\nomits the limit again",
                    xy=(zero_from, 62), xytext=(zero_from + 1.2, 72),
                    fontsize=6.4, color=INK,
                    arrowprops=dict(arrowstyle="-", linewidth=0.6, color=INK))

    ax.set_ylim(-4, 104)
    ax.set_ylabel("Share of station-years (%)")
    ax.legend(loc="center left", bbox_to_anchor=(0.005, 0.42), fontsize=6.2,
              frameon=False, labelspacing=0.35)
    xgrid(ax, axis="y")
    despine(ax, keep=("left", "bottom"))
    title(ax, "One failure was repaired on a date; the other was not")

    bx.bar(k(yr), [v / 1000 for v in k(n)], width=0.72, color=RAMP[1],
           edgecolor=SURFACE, linewidth=0.4, label="station-years reported")
    bx2 = bx.twinx()
    bx2.plot(k(yr), k(testable), color=INK, linewidth=1.1,
             label="carry a European standard")
    bx2.set_ylim(0, 104)
    bx2.set_ylabel("with a standard (%)", fontsize=6.6)
    bx2.tick_params(labelsize=6.4)
    bx.set_ylabel("station-years (thousands)")
    bx.set_xlabel("Reference year")
    despine(bx, keep=("left", "bottom"))
    for a in (bx, bx2):
        for s in ("top",):
            a.spines[s].set_visible(False)
    h1, l1 = bx.get_legend_handles_labels()
    h2, l2 = bx2.get_legend_handles_labels()
    bx.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=6.2, frameon=False,
              ncol=2)
    fig.tight_layout()
    save(fig, "fig08_by_year")


FIGURES = {
    "fig01": fig_graphical_abstract,
    "fig02": fig_europe_map,
    "fig03": fig_country_scatter,
    "fig04": fig_loq_vs_eqs,
    "fig05": fig_verdicts,
    "fig06": fig_decision_geometry,
    "fig07": fig_two_thresholds,
    "fig08": fig_by_year,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="generate a single figure, e.g. fig03")
    args = ap.parse_args()

    todo = {args.only: FIGURES[args.only]} if args.only else FIGURES
    if args.only and args.only not in FIGURES:
        sys.exit(f"unknown figure {args.only}; choose from {sorted(FIGURES)}")

    for name, fn in todo.items():
        print(f"{name}:")
        fn()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
