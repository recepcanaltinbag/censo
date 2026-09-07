#!/usr/bin/env python3
"""
Two use-case figures, each answering one question with one picture.

WHY TWO MORE, AND WHY THESE
---------------------------
Figure 5 compares the substitution constants; Figure 6 draws the decision
geometry; Figure 11 decides four rows twice. What none of them shows is the
question the two people most likely to adopt this actually ask.

  fig12  An enforcement lawyer asks: of the exceedances my pipeline reports,
         how many could I defend? The attrition from 200,708 to 14,505 is the
         paper's most striking single number and it appears nowhere as a
         picture. Each step removes a stratum and says why it was removed, so
         the figure is the argument rather than an illustration of it.

  fig13  A basin authority on a border asks: the same measurement, two regimes
         -- how far apart are they? Chlorpyrifos is the sharpest real case in
         the record: 0.00046 ug/L in Annex I against 0.03 in the Turkish table,
         a factor of 65, over 23,208 station-years whose verdict changes with
         the package. Figure 7 compares two standards WITHIN one jurisdiction;
         this compares two jurisdictions, which is what the swappable
         regulation packages are for.

Both are drawn from the shipped tables, both ship their data, and neither
restates a number the pipeline computes elsewhere -- they read it.

Inputs  : derived/processed/waterbase_verdicts_population.csv
          derived/processed/dual_regulation.csv, ontology/reg/*.ttl
Outputs : paper/figures/fig12_enforcement_funnel.{pdf,svg,png}
          paper/figures/fig13_two_regimes.{pdf,svg,png}
          paper/supplementary/figure_data/fig1{2,3}_*.csv

Usage:  python scripts/92b_use_case_figures.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
REG = ROOT / "ontology" / "reg"
FIGS = ROOT / "paper" / "figures"
FDATA = ROOT / "paper" / "supplementary" / "figure_data"

INK, MUTED, RED, GREEN, BLUE = "#1f1f1f", "#7a7a7a", "#b03030", "#3c7a3c", "#1f4e79"

# Why each stratum is not an exceedance the law can affirm. Keyed on the
# outcome class so a renamed class breaks the figure rather than mislabelling it.
WHY = {
    "method_insufficient":
        "the quantification limit exceeds the standard\nArt. 3(3b): shall not be considered",
    "precondition_unmet":
        "the standard is defined on a quantity\nthe record does not report",
    "indeterminate_unresolved":
        "no censoring flag and no limit\nso there is no bound to compare",
    "possible_exceedance":
        "the interval the legal uncertainty permits\nstraddles the standard",
    "indeterminate_other":
        "the reported value contradicts\nthe limit beside it",
}


def funnel():
    p = PROC / "waterbase_verdicts_population.csv"
    if not p.exists():
        print("  ! waterbase_verdicts_population.csv missing; skipping fig12")
        return None
    with p.open(encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh)
                if r["substitution"] == "full"
                and r["two_valued_outcome"] == "exceeding"]
    if not rows:
        return None
    total = sum(int(r["n"]) for r in rows)
    affirm = sum(int(r["n"]) for r in rows if r["censo_outcome"] == "exceedance")
    drops = sorted(((r["censo_outcome"], int(r["n"])) for r in rows
                    if r["censo_outcome"] != "exceedance"),
                   key=lambda t: -t[1])

    # One row per step: the bar, then the deduction and its reason beside it.
    # No connector lines -- they crossed the labels and struck them through.
    WHY1 = {k: v.replace("\n", " — ") for k, v in WHY.items()}
    fig, ax = plt.subplots(figsize=(11.2, 0.62 * (len(drops) + 2) + 1.4))
    y, running, bars = 0, total, []
    ax.barh(y, total, height=0.46, color=RED, alpha=.24, edgecolor=RED,
            linewidth=.9)
    ax.text(total * 1.20, y, f"{total:,}", va="center", ha="right",
            fontsize=12, fontweight="bold", color=RED)
    bars.append(("reported at the full limit", total, ""))
    for name, n in drops:
        y -= 1
        running -= n
        ax.barh(y, running, height=0.46, color=RED, alpha=.13,
                edgecolor=MUTED, linewidth=.6)
        ax.text(total * 1.20, y, f"−{n:,}", va="center", ha="right",
                fontsize=9.5, color=MUTED, fontweight="bold")
        ax.text(total * 1.27, y, WHY1.get(name, name), va="center",
                fontsize=8.8, color=INK)
        bars.append((name, -n, WHY1.get(name, "")))
    y -= 1
    ax.barh(y, affirm, height=0.46, color=GREEN, edgecolor=GREEN)
    ax.text(total * 1.20, y, f"{affirm:,}", va="center", ha="right",
            fontsize=12, fontweight="bold", color=GREEN)
    ax.text(total * 1.27, y,
            "quantified above the standard, method meets the criterion,\n"
            "interval does not straddle it — the law can affirm these",
            va="center", fontsize=8.8, color=GREEN)
    bars.append(("affirmable in law", affirm, ""))

    ax.set_title("Of the exceedances a substituting pipeline reports, how many "
                 "could an enforcement action defend?",
                 fontsize=10.5, loc="left", fontweight="bold", pad=12)
    ax.set_xlim(0, total * 2.75)
    ax.set_ylim(y - 0.75, 0.75)
    ax.set_yticks([])
    ax.set_xticks([0, total // 2, total])
    ax.set_xticklabels(["0", f"{total // 2:,}", f"{total:,}"], fontsize=8.5)
    ax.set_xlabel("station-years", fontsize=9)
    for sp in ("top", "left", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    for fmt in ("pdf", "svg", "png"):
        fig.savefig(FIGS / f"fig12_enforcement_funnel.{fmt}", dpi=200,
                    bbox_inches="tight")
    plt.close(fig)

    FDATA.mkdir(parents=True, exist_ok=True)
    with (FDATA / "fig12_enforcement_funnel.csv").open(
            "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["step", "station_years", "reason"])
        w.writerows(bars)
    return total, affirm, len(drops)


def two_regimes():
    """One substance, two jurisdictions, read from the released packages."""
    thr = {}
    for stem, tag in (("eu-2008-105-2026", "EU"), ("tr-ysky-2016", "TR")):
        f = REG / f"{stem}.ttl"
        if not f.exists():
            return None
        src = f.read_text(encoding="utf-8")
        a = re.search(r"^(cereg:\S+) a censo:Analyte ;(?:(?!\n\n).)*?"
                      r'censo:casNumber "2921-88-2"', src, re.S | re.M)
        if not a:
            return None
        for t in re.finditer(r"^(cereg:\S+) a censo:AnnualAverageThreshold ;"
                             r"\n(.*?)\.\n", src, re.S | re.M):
            if a.group(1) in t.group(2):
                v = re.search(r'thresholdValue "([^"]+)"', t.group(2))
                lab = re.search(r'rdfs:label "([^"]*)"', t.group(2))
                if v:
                    thr[tag] = (float(v.group(1)), lab.group(1) if lab else "")
    if len(thr) != 2:
        print("  ! chlorpyrifos not in both packages; skipping fig13")
        return None

    n_diff = 0
    p = PROC / "dual_regulation.csv"
    if p.exists():
        with p.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("scope") == "substance" and \
                        r.get("key", "").startswith("2921-88-2"):
                    n_diff = int(r["n"])

    eu, tr = thr["EU"][0], thr["TR"][0]
    lo, hi = min(eu, tr), max(eu, tr)
    fig, ax = plt.subplots(figsize=(9.6, 2.85))
    ax.set_xscale("log")
    ax.set_xlim(lo / 6, hi * 6)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    for s in ("top", "left", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="x", labelsize=9)

    ax.axvspan(lo, hi, color=RED, alpha=.10)
    ax.text((lo * hi) ** .5, 0.63,
            "a measurement in this band is an exceedance under one regime\n"
            "and compliant under the other",
            ha="center", va="center", fontsize=10, color=RED)
    for x, tag, col in ((eu, "EU · Annex I", BLUE), (tr, "TR · Table 4", INK)):
        ax.axvline(x, color=col, lw=2.0)
        ax.text(x, 0.94, f" {tag}\n {x:g} µg/L", fontsize=9.5, color=col,
                va="top", fontweight="bold")
    ax.annotate("", xy=(lo, 0.26), xytext=(hi, 0.26),
                arrowprops=dict(arrowstyle="<->", color=MUTED, lw=1.1))
    ax.text((lo * hi) ** .5, 0.18, f"×{hi / lo:.0f}", ha="center", fontsize=11,
            color=MUTED, fontweight="bold")
    ax.set_xlabel("chlorpyrifos, annual average, µg/L (log scale)", fontsize=9)
    ax.set_title(
        f"One substance, two regulation packages — {n_diff:,} station-years "
        f"whose verdict changes with the package",
        fontsize=10.5, loc="left", fontweight="bold", pad=10)
    fig.tight_layout()
    for fmt in ("pdf", "svg", "png"):
        fig.savefig(FIGS / f"fig13_two_regimes.{fmt}", dpi=200,
                    bbox_inches="tight")
    plt.close(fig)

    with (FDATA / "fig13_two_regimes.csv").open(
            "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["jurisdiction", "threshold_ug_l", "label"])
        for tag in ("EU", "TR"):
            w.writerow([tag, thr[tag][0], thr[tag][1]])
        w.writerow(["ratio", f"{hi / lo:.1f}", ""])
        w.writerow(["station_years_differing", n_diff, ""])
    return eu, tr, n_diff


def main() -> int:
    FIGS.mkdir(parents=True, exist_ok=True)
    FDATA.mkdir(parents=True, exist_ok=True)
    f = funnel()
    if f:
        print(f"  fig12: {f[0]:,} reported -> {f[1]:,} affirmable, "
              f"{f[2]} attrition steps")
    r = two_regimes()
    if r:
        print(f"  fig13: EU {r[0]:g} vs TR {r[1]:g} ug/L "
              f"(x{max(r[:2])/min(r[:2]):.0f}), {r[2]:,} station-years differ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
