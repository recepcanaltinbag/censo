#!/usr/bin/env python3
"""The two claims with no picture, on one shared concentration axis.

WHY THIS FIGURE
---------------
Two arguments in this paper carried real numbers and no image.

(a) COMMITMENT 1, that the quantification limit belongs to the analytical run
    and not to the instrument. Its whole evidence is one sentence: of the
    station-substance pairs reported in more than one year, 56.4 % report more
    than one limit. Stated as a share that is a fact about counting; drawn as a
    distribution it is a fact about MAGNITUDE, which is the part that decides
    the modelling question. A limit that wobbles by ten per cent between years
    is consistent with one instrument having a bad day. A limit that moves by
    two decades is not a property of the instrument at all.

(b) DIRECTIVE (EU) 2026/805, the paper's forward-looking claim. The additions
    are said to sit in the decades where the monitoring already cannot decide,
    and the reader has to take that on the numbers.

They share an axis -- concentration in ug/L, log scale -- and that is why they
belong in one figure rather than two. Read together they say: the limit varies
by more than the distance between a standard and the values near it, and the
standards are moving down into the region the limits already cannot follow.

Inputs  : derived/processed/limit_variation.csv, eu_eqs.csv, waterbase_summary.csv
Outputs : paper/figures/fig16_commitment_evidence.{pdf,svg,png}
          paper/supplementary/figure_data/fig16_commitment_evidence.csv

Usage:  python scripts/94_commitment_figures.py
"""

from __future__ import annotations

import csv
import math
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
FIGS = ROOT / "paper" / "figures"
FDATA = ROOT / "paper" / "supplementary" / "figure_data"

INK, MUTED, RED, BLUE, GREEN = "#1f1f1f", "#8a8a8a", "#b03030", "#1f4e79", "#3c7a3c"
FIRST_ADDED = 46          # Annex I numbers the 2026 additions from 46 upward


def rows(name):
    p = PROC / name
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    var = rows("limit_variation.csv")
    eqs = rows("eu_eqs.csv")
    if not var or not eqs:
        print("  ! limit_variation.csv or eu_eqs.csv missing; skipping fig16")
        return 0

    fig, (axa, axb) = plt.subplots(2, 1, figsize=(9.2, 6.4),
                                   gridspec_kw={"height_ratios": [1.0, 0.85]})

    # ---- (a) how far the limit moves inside one station-substance pair ----
    var = sorted(var, key=lambda r: int(r["log10_spread_bin"]))
    SHORT = {"changed, ratio not computable": "changed,\nnot measurable"}
    labels = [SHORT.get(r["label"], r["label"]) for r in var]
    counts = [int(r["pairs"]) for r in var]
    bins = [int(r["log10_spread_bin"]) for r in var]
    total = sum(counts)
    # The first bin is the prediction the instrument reading makes; every other
    # bin is a pair that reading cannot account for. Colour says which is which.
    cols = [MUTED] + [RED] * (len(counts) - 1)
    bars = axa.bar(range(len(counts)), counts, color=cols, width=0.62,
                   edgecolor="none")
    for i, (b, c) in enumerate(zip(bars, counts)):
        axa.text(b.get_x() + b.get_width() / 2, c, f"  {100*c/total:.1f}%",
                 ha="center", va="bottom", fontsize=8.5,
                 color=MUTED if i == 0 else RED, fontweight="bold")
    axa.set_xticks(range(len(labels)))
    axa.set_xticklabels(labels, fontsize=8.2)
    axa.set_ylabel("station–substance pairs", fontsize=8.5)
    axa.set_ylim(0, max(counts) * 1.22)
    axa.tick_params(axis="y", labelsize=8)
    for sp in ("top", "right"):
        axa.spines[sp].set_visible(False)
    moved = total - counts[0]
    axa.set_title(
        "(a)  If the quantification limit were a property of the instrument, "
        "every pair would sit in the first bar\n"
        f"        {100*moved/total:.1f}% do not, and the limit moves by more "
        f"than a factor of ten in "
        f"{100*sum(c for b, c in zip(bins, counts) if 2 <= b <= 4)/total:.1f}%"
        f" of them",
        fontsize=9.2, loc="left", fontweight="bold", color=INK, pad=8)

    # ---- (b) where the standards are, and where the law is moving them ----
    def decade(v):
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        return math.floor(math.log10(x)) if x > 0 else None

    def entry(r):
        m = re.match(r"(\d+)", str(r.get("entry_no", "")))
        return int(m.group(1)) if m else 10 ** 6

    split = {"legacy": {}, "added": {}}
    for r in eqs:
        d = decade(r.get("aa_inland"))
        if d is None:
            continue
        k = "added" if entry(r) >= FIRST_ADDED else "legacy"
        split[k][d] = split[k].get(d, 0) + 1

    ds = sorted(set(split["legacy"]) | set(split["added"]))
    x = range(len(ds))
    w = 0.4
    axb.bar([i - w / 2 for i in x], [split["legacy"].get(d, 0) for d in ds],
            width=w, color=BLUE, label="on the list before 2026", edgecolor="none")
    axb.bar([i + w / 2 for i in x], [split["added"].get(d, 0) for d in ds],
            width=w, color=RED, label="added by Directive (EU) 2026/805",
            edgecolor="none")
    axb.set_xticks(list(x))
    axb.set_xticklabels([f"$10^{{{d}}}$" for d in ds], fontsize=8.5)
    axb.set_xlabel("annual-average standard, µg/L (decade)", fontsize=8.5)
    axb.set_ylabel("substances", fontsize=8.5)
    axb.tick_params(axis="y", labelsize=8)
    for sp in ("top", "right"):
        axb.spines[sp].set_visible(False)
    axb.legend(fontsize=8, frameon=False, loc="upper right")

    # the decades where the record already cannot decide, shaded rather than
    # asserted: the audit fixes this cut at 1e-4 and below
    low = [i for i, d in enumerate(ds) if d <= -4]
    if low:
        axb.axvspan(min(low) - 0.5, max(low) + 0.5, color=RED, alpha=0.07,
                    zorder=0)
        axb.text((min(low) + max(low)) / 2, axb.get_ylim()[1] * 0.92,
                 "the monitoring already\ncannot decide here", ha="center",
                 va="top", fontsize=7.6, color=RED)
    na = sum(split["added"].values())
    la = sum(v for d, v in split["added"].items() if d <= -4)
    nl = sum(split["legacy"].values())
    ll = sum(v for d, v in split["legacy"].items() if d <= -4)
    axb.set_title(
        f"(b)  The amendment moves the list into those decades:  "
        f"{la} of {na} additions sit below $10^{{-3}}$ µg/L "
        f"({100*la/na:.0f}%), against {ll} of {nl} on the legacy list "
        f"({100*ll/nl:.0f}%)",
        fontsize=9.2, loc="left", fontweight="bold", color=INK, pad=8)

    fig.tight_layout(h_pad=2.4)
    FIGS.mkdir(parents=True, exist_ok=True)
    for fmt in ("pdf", "svg", "png"):
        fig.savefig(FIGS / f"fig16_commitment_evidence.{fmt}", dpi=200,
                    bbox_inches="tight")
    plt.close(fig)

    FDATA.mkdir(parents=True, exist_ok=True)
    with (FDATA / "fig16_commitment_evidence.csv").open(
            "w", newline="", encoding="utf-8") as fh:
        w_ = csv.writer(fh)
        w_.writerow(["panel", "series", "bin", "n"])
        for r in var:
            w_.writerow(["a", "station-substance pairs", r["label"],
                         r["pairs"]])
        for k in ("legacy", "added"):
            for d in ds:
                w_.writerow(["b", k, f"1e{d}", split[k].get(d, 0)])

    print(f"  fig16: (a) {moved:,} of {total:,} pairs move their limit; "
          f"(b) {la}/{na} additions vs {ll}/{nl} legacy below 1e-3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
