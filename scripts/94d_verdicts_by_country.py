#!/usr/bin/env python3
"""The verdict by country and by year: where the indeterminacy comes from.

WHY THIS FIGURE
---------------
Section 5 reports one three-valued assessment over the whole record, and a
reader with a stake in it asks two questions the pooled figure cannot answer.

  IS THIS ONE COUNTRY'S PRACTICE?  If a handful of reporters produced most of
  the undecidable rows, the finding is about them and not about the Directive.
  The paper could answer that for the REPORTING defect -- the share declaring
  neither flag nor limit ranges from 3 % to 97 % between countries -- and could
  not answer it for the verdict, because the population table splits by
  substitution and outcome and never by who reported the row.

  IS IT GETTING BETTER?  The year series carries the undecidable total; the
  composition behind it is what says whether the record is improving or merely
  reporting more.

Both panels use the same six colours as Figure 5, so a reader who has read that
figure reads these without a second legend to learn.

The country panel is ordered by the undecidable share and shows every reporter
above a floor of assessable rows, because a country with 300 assessments has a
rate that is one laboratory's practice. The floor is drawn, not applied
silently: the countries below it are counted in the subtitle.

Inputs  : derived/processed/verdicts_by_country.csv
          derived/processed/exceedances_by_year.csv
Outputs : paper/figures/fig19_verdicts_by_country_year.{pdf,svg,png}
          paper/supplementary/figure_data/fig19_verdicts_by_country_year.csv

Usage:  python scripts/94d_verdicts_by_country.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
FDATA = ROOT / "paper" / "supplementary" / "figure_data"

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_figs", ROOT / "scripts" / "90_figures.py")
_figs = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_figs)
save, W2, V, RAMP = _figs.save, _figs.W2, _figs.V, _figs.RAMP

INK, MUTED, GRID = "#1f1f1f", "#8a8a8a", "#dcdfe3"
MIN_ROWS = 2000

# the same order and the same colours as Figure 5, so no second legend
SEGS = [("compliant", V["compliant"], "Compliant"),
        ("exceedance", V["exceed"], "Exceeding"),
        ("possible_exceedance", V["possible"], "Possible exceedance"),
        ("precondition_unmet", RAMP[2], "Standard not applicable"),
        ("method_insufficient", V["indeterminate"], "Method fails the standard"),
        ("bound", RAMP[0], "No bound established")]
IND = ("possible_exceedance", "precondition_unmet", "method_insufficient",
       "bound")


def read(name):
    p = PROC / name
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fold(d):
    """indeterminate_unresolved and indeterminate_other are one OWL class."""
    out = dict(d)
    out["bound"] = (d.get("indeterminate_unresolved", 0)
                    + d.get("indeterminate_other", 0))
    return out


def main() -> int:
    cty_rows = read("verdicts_by_country.csv")
    yr_rows = [r for r in read("exceedances_by_year.csv")
               if r.get("plotted") == "yes" and "n_compliant" in r]
    if not cty_rows or not yr_rows:
        print("  ! verdicts_by_country.csv or the per-year split is missing")
        return 0

    by_c = {}
    for r in cty_rows:
        by_c.setdefault(r["country"], {})[r["censo_outcome"]] = int(r["n"])
    cty = []
    small = 0
    for c, d in by_c.items():
        d = fold(d)
        t = sum(v for k, v in d.items()
                if k not in ("indeterminate_unresolved", "indeterminate_other"))
        if t < MIN_ROWS:
            small += 1
            continue
        cty.append((c, d, t, 100 * sum(d.get(k, 0) for k in IND) / t))
    cty.sort(key=lambda x: x[3])

    yrs = []
    for r in yr_rows:
        d = fold({k[2:]: int(v) for k, v in r.items()
                  if k.startswith("n_") and v})
        t = int(r["assessable"])
        yrs.append((int(r["year"]), d, t))
    yrs.sort()

    fig, (axc, axy) = plt.subplots(
        2, 1, figsize=(W2, 0.245 * len(cty) + 5.4),
        gridspec_kw={"height_ratios": [0.245 * len(cty) + 0.9, 2.5],
                     "hspace": 0.62})

    for i, (c, d, t, _) in enumerate(cty):
        left = 0
        for k, colr, lbl in SEGS:
            v = 100 * d.get(k, 0) / t
            axc.barh(i, v, left=left, height=0.62, color=colr,
                     edgecolor="white", linewidth=0.7,
                     label=lbl if i == 0 else None)
            left += v
        axc.text(101.5, i, f"{t:,}", va="center", fontsize=6.0, color=MUTED)
    axc.set_yticks(range(len(cty)))
    axc.set_yticklabels([c for c, _, _, _ in cty], fontsize=7.0)
    axc.set_xlim(0, 112)
    axc.set_ylim(-0.7, len(cty) - 0.3)
    axc.set_xticks([0, 25, 50, 75, 100])
    axc.set_xlabel("share of assessments (%)", fontsize=8.2)
    axc.tick_params(axis="y", length=0)
    for sp in ("top", "left", "right"):
        axc.spines[sp].set_visible(False)
    axc.set_title(
        f"(a)  By reporting country, worst first\n"
        f"      {len(cty)} reporters with at least {MIN_ROWS:,} assessable "
        f"station-years; {small} smaller ones omitted",
        fontsize=9.0, fontweight="bold", color=INK, loc="left", pad=8)

    xs = [y for y, _, _ in yrs]
    bottoms = [0.0] * len(yrs)
    for k, colr, lbl in SEGS:
        vals = [100 * d.get(k, 0) / t for _, d, t in yrs]
        axy.bar(xs, vals, bottom=bottoms, width=0.82, color=colr,
                edgecolor="white", linewidth=0.5)
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    axy.set_xlim(min(xs) - 0.6, max(xs) + 0.6)
    axy.set_ylim(0, 100)
    axy.set_ylabel("share of assessments (%)", fontsize=8.2)
    axy.set_xlabel("reference year", fontsize=8.2)
    axy.tick_params(labelsize=7.0)
    for sp in ("top", "right"):
        axy.spines[sp].set_visible(False)
    first, last = yrs[0], yrs[-1]
    f_mi = 100 * first[1].get("method_insufficient", 0) / first[2]
    l_mi = 100 * last[1].get("method_insufficient", 0) / last[2]
    axy.set_title(
        f"(b)  By reference year\n"
        f"      The pale band ends; the band this paper is about goes "
        f"{f_mi:.0f} % \u2192 {l_mi:.0f} %",
        fontsize=9.0, fontweight="bold", color=INK, loc="left", pad=8)

    # one legend for both panels, under the lower one, where there is room
    axy.legend(*axc.get_legend_handles_labels(), fontsize=6.8, frameon=False,
               ncol=3, loc="upper left", bbox_to_anchor=(0.0, -0.30))

    fig.subplots_adjust(left=0.075, right=0.975, top=0.93, bottom=0.155)
    save(fig, "fig19_verdicts_by_country_year")
    FDATA.mkdir(parents=True, exist_ok=True)
    with (FDATA / "fig19_verdicts_by_country_year.csv").open(
            "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["panel", "key", "assessable"] + [k for k, _, _ in SEGS])
        for c, d, t, _ in cty:
            w.writerow(["country", c, t] + [d.get(k, 0) for k, _, _ in SEGS])
        for y, d, t in yrs:
            w.writerow(["year", y, t] + [d.get(k, 0) for k, _, _ in SEGS])
    print(f"  fig19: {len(cty)} countries above {MIN_ROWS:,} rows "
          f"({small} omitted), {len(yrs)} years; undecidable share runs "
          f"{cty[0][3]:.0f}–{cty[-1][3]:.0f} % between countries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
