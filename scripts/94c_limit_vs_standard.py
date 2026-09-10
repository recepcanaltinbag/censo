#!/usr/bin/env python3
"""What the law asks for, against what the laboratories reached. One axis.

WHY THIS REPLACES A RATE WITH A DISTANCE
----------------------------------------
This paper compares a quantification limit with a standard on every page, and
until now no figure put the two on the same axis. Both were shown through a
derived rate -- "98 % of assessments use a method failing the criterion" -- and
a rate answers how OFTEN and never how FAR. A method missing the criterion by
ten per cent and one missing it by three decades are the same 98 %.

Here the two quantities are drawn where the law writes them, in ug/L on a log
axis. Each substance is one row:

  the bar     the middle 80 % of the quantification limits actually reported
  the dot     their median
  the line    the annual-average standard the substance must be assessed against
  the tick    30 % of that standard, which is the ceiling Article 4(1) sets on
              a usable method's limit

A row whose bar sits to the RIGHT of its tick is a substance the monitoring
cannot decide, and the reader measures the shortfall in decades by eye instead
of taking a percentage on trust. The spread of the bar is Commitment 1 in the
same picture: if the limit belonged to the instrument the bar would be a point.

Substances are ordered by median limit over the criterion, so the worst case is
at the top and the reader can see where the ordering stops being dramatic.

Inputs  : derived/processed/loq_vs_standard.csv
Outputs : paper/figures/fig18_limit_vs_standard.{pdf,svg,png}
          paper/supplementary/figure_data/fig18_limit_vs_standard.csv

Usage:  python scripts/94c_limit_vs_standard.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                   # noqa: E402
from matplotlib.lines import Line2D                               # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
FDATA = ROOT / "paper" / "supplementary" / "figure_data"

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_figs", ROOT / "scripts" / "90_figures.py")
_figs = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_figs)
save, W2 = _figs.save, _figs.W2

INK, MUTED, GRID = "#1f1f1f", "#8a8a8a", "#dcdfe3"
LIMIT, STD, CRIT = "#1f4e79", "#3c7a3c", "#b03030"
CRITERION = 0.30            # Article 4(1): LOQ at or below 30 % of the standard
TOP = 18


def main() -> int:
    p = PROC / "loq_vs_standard.csv"
    if not p.exists():
        print("  ! loq_vs_standard.csv missing; run scripts/22_waterbase_external.py")
        return 0
    # THE LAST FIVE YEARS, not the pooled record.
    # Analytical capability moved over 1975-2024, so a shortfall measured on
    # the whole span can always be answered with "those are old limits". It
    # cannot be answered that way here: these are the limits laboratories are
    # reporting now, against the standards in force now. The pooled quantiles
    # stay in the shipped table for anyone who wants the comparison.
    with p.open(encoding="utf-8") as fh:
        rows, since = [], None
        for r in csv.DictReader(fh):
            try:
                t = float(r["standard_ug_l"])
                n = int(r["n_limits_recent"])
                q25, q50, q75 = (float(r["loq_p25_recent"]),
                                 float(r["loq_p50_recent"]),
                                 float(r["loq_p75_recent"]))
                since = int(r["recent_from"])
            except (TypeError, ValueError, KeyError):
                continue
            if t > 0 and q50 > 0 and n >= 100:
                rows.append((r["substance"] or r["cas"], t,
                             [q25, q25, q50, q75, q75], n))
    if not rows:
        print("  ! no substance has both a standard and reported limits")
        return 0

    # how far the median limit sits above the ceiling the criterion sets
    rows.sort(key=lambda x: x[2][2] / (CRITERION * x[1]))
    shown = rows[-TOP:] if len(rows) > TOP else rows
    n_fail = sum(1 for _, t, q, _ in rows if q[2] > CRITERION * t)

    fig, ax = plt.subplots(figsize=(W2, 0.34 * len(shown) + 2.2))
    ax.set_xscale("log")
    for i, (name, t, q, n) in enumerate(shown):
        p10, p25, p50, p75, p90 = q
        ax.plot([p25, p75], [i, i], color=LIMIT, alpha=0.75, linewidth=5.0,
                solid_capstyle="butt", zorder=3)
        ax.plot([p50], [i], marker="o", markersize=4.6, color=LIMIT,
                markeredgecolor="white", markeredgewidth=0.9, zorder=5)
        ax.plot([t, t], [i - 0.34, i + 0.34], color=STD, linewidth=2.0,
                zorder=4)
        ax.plot([CRITERION * t, CRITERION * t], [i - 0.26, i + 0.26],
                color=CRIT, linewidth=1.6, zorder=4)
        # the shortfall, in decades, written where the eye already is
        import math
        d = math.log10(p50 / (CRITERION * t))
        if d > 0:
            ax.annotate("", xy=(p50, i + 0.40),
                        xytext=(CRITERION * t, i + 0.40),
                        arrowprops=dict(arrowstyle="<->", color=CRIT,
                                        linewidth=0.6, alpha=0.55, shrinkA=0,
                                        shrinkB=0, mutation_scale=5))
            ax.text((p50 * CRITERION * t) ** 0.5, i + 0.46, f"{d:.1f}",
                    ha="center", va="bottom", fontsize=5.6, color=CRIT)
    ax.set_yticks(range(len(shown)))
    ax.set_yticklabels([(nm if len(nm) <= 30 else nm[:29] + "\u2026")
                        for nm, _, _, _ in shown], fontsize=7.0)
    ax.set_ylim(-0.9, len(shown) - 0.3)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("concentration (µg/L, log scale)", fontsize=8.4)
    ax.grid(True, axis="x", color=GRID, linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    for sp in ("top", "left", "right"):
        ax.spines[sp].set_visible(False)

    hs = [Line2D([], [], color=LIMIT, linewidth=5.0, alpha=.75),
          Line2D([], [], color="white"),
          Line2D([], [], marker="o", color=LIMIT, linestyle="none",
                 markersize=4.6),
          Line2D([], [], color=STD, linewidth=2.0),
          Line2D([], [], color=CRIT, linewidth=1.6)]
    ax.legend(hs, ["reported limits, middle half", "",
                   "median limit", "the standard",
                   "30 % of it \u2014 the ceiling",
                   "the number on each row is that shortfall, in decades"],
              fontsize=6.3, frameon=False, ncol=2,
              loc="upper left",
              bbox_to_anchor=(0.0, -0.05 - 1.3 / len(shown)))

    ax.set_title(
        f"What the laboratories reached since {since}, against what the "
        f"law asked for\n"
        f"{n_fail} of {len(rows)} carry a median limit above "
        f"Article 4(1)'s ceiling",
        fontsize=9.4, fontweight="bold", color=INK, loc="left", pad=10)

    fig.subplots_adjust(left=0.235, right=0.985, top=0.90,
                        bottom=0.10 + 0.6 / len(shown))
    save(fig, "fig18_limit_vs_standard")
    FDATA.mkdir(parents=True, exist_ok=True)
    with (FDATA / "fig18_limit_vs_standard.csv").open(
            "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["substance", "standard_ug_l", "ceiling_ug_l",
                    "loq_p25", "loq_p50", "loq_p75", "n_limits_since_" +
                    str(since), "decades_above_ceiling", "plotted"])
        import math
        for nm, t, q, n in rows:
            w.writerow([nm, f"{t:.6g}", f"{CRITERION*t:.6g}",
                        f"{q[0]:.6g}", f"{q[2]:.6g}", f"{q[3]:.6g}", n,
                       f"{math.log10(q[2]/(CRITERION*t)):.3f}",
                       "yes" if (nm, t, q, n) in shown else "no"])
    print(f"  fig18: since {since}, {len(rows)} substances, {n_fail} above "
          f"the ceiling, {len(shown)} plotted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
