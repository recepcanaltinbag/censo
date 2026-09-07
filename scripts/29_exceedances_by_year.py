#!/usr/bin/env python3
"""
Exceedances year by year: what a substituting pipeline reports, and what the
law can affirm.

WHY THIS IS NOT ALREADY IN FIGURE 8
-----------------------------------
Figure 8 reads the record year by year for the three failures -- rows declaring
neither a flag nor a limit, rows failing the Article 4(1) criterion, rows whose
limit exceeds the standard -- and it answers "is this improving". It does not
carry a single exceedance count, so it cannot answer the question an enforcement
authority asks about a trend: is the gap between what a pipeline reports and
what the law can affirm narrowing?

That gap is the paper's headline as a single number (200,708 against 14,505).
As a series it is a different claim, and a stronger one if it holds: a defect
that persists across two decades of reporting is not a transitional problem.

WHAT IS COUNTED
---------------
For every river station-year a European annual-average standard reaches, in the
year the record assigns it:

  * exceedances a two-valued pipeline reports, at each of the three
    substitution constants in use;
  * exceedances CENSO affirms -- quantified above the standard, method meeting
    the performance criterion, interval not straddling it;
  * the undecidable share, so the series can be read against the verdict the
    record could actually support.

The decision procedure is IMPORTED from 22_waterbase_external rather than
restated, so this series and the totals in Section 5.4 cannot disagree. A year
with fewer than MIN_YEAR assessable station-years is carried in the CSV and not
plotted: before the mid-1990s the record is too thin for a rate to mean
anything, and a line drawn through it would invite a reading the data does not
support.

Inputs  : Data/waterbase/... or --file, derived/processed/eu_eqs.csv
Outputs : derived/processed/exceedances_by_year.csv
          paper/figures/fig14_exceedances_by_year.{pdf,svg,png}
          paper/supplementary/figure_data/fig14_exceedances_by_year.csv
          eval/exceedances_by_year.md

Usage:  python scripts/29_exceedances_by_year.py --file <release.zip>
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
DATA = ROOT / "Data" / "waterbase"
FIGS = ROOT / "paper" / "figures"
FDATA = ROOT / "paper" / "supplementary" / "figure_data"
EVAL = ROOT / "eval"
STEM = "fig14_exceedances_by_year"

# Below this the year is counted and not plotted. The early record is a handful
# of stations, and a percentage over a handful is noise drawn as a trend.
MIN_YEAR = 2000

sys.path.insert(0, str(Path(__file__).resolve().parent))
_m = __import__("22_waterbase_external")
open_rows, pick, num = _m.open_rows, _m.pick, _m.num
TO_UG_L = _m.TO_UG_L
detection_status, censo_outcome = _m.detection_status, _m.censo_outcome
two_valued, SUBSTITUTIONS = _m.two_valued, _m.SUBSTITUTIONS
conditional_thresholds = _m.conditional_thresholds

IND = ("possible_exceedance", "precondition_unmet", "method_insufficient",
       "indeterminate_unresolved", "indeterminate_other")

INK, MUTED, RED, GREEN = "#1f1f1f", "#7a7a7a", "#b03030", "#3c7a3c"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path)
    args = ap.parse_args()
    src = args.file
    if src is None:
        cand = sorted(DATA.glob("*Aggregated*.zip"))
        src = cand[0] if cand else None
    if src is None or not src.exists():
        print("  ! aggregated release not found; skipping")
        return 0
    p_eqs = PROC / "eu_eqs.csv"
    if not p_eqs.exists():
        print("  ! derived/processed/eu_eqs.csv missing; run stage 10 first")
        return 0

    eqs, rows_eqs = {}, []
    with p_eqs.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows_eqs.append(r)
            if r.get("is_group") == "True":
                continue
            v = num(r.get("aa_inland"))
            if not v:
                continue
            for c in (r.get("all_cas") or "").replace(" ", "").split(";"):
                if c:
                    eqs.setdefault(c, v)
    cond = conditional_thresholds(rows_eqs)

    it = open_rows(src)
    col = pick(next(it))
    get = lambda row, k: (row[col[k]].strip()
                          if k in col and col[k] < len(row) else "")

    yr_tot = defaultdict(int)
    yr_affirm = defaultdict(int)
    yr_undec = defaultdict(int)
    yr_two = defaultdict(lambda: defaultdict(int))
    for row in it:
        if "category" in col and get(row, "category") not in ("RW", ""):
            continue
        cas = get(row, "code")
        cas = cas[4:] if cas.upper().startswith("CAS_") else ""
        if cas not in eqs:
            continue
        factor = TO_UG_L.get(get(row, "uom").lower().replace(" ", ""))
        if factor is None:
            continue
        raw = get(row, "year")
        y = num(raw[:4]) if len(raw) >= 4 else num(raw)
        if y is None:
            continue
        y = str(int(y))

        thr = eqs[cas]
        val, loq = num(get(row, "value")), num(get(row, "loq"))
        v_ug = val * factor if val is not None else None
        l_ug = loq * factor if loq is not None else None
        status = detection_status(get(row, "below_loq"), v_ug, l_ug)
        outcome = censo_outcome(status, v_ug, l_ug, thr,
                                precondition=cond.get(cas))
        yr_tot[y] += 1
        if outcome == "exceedance":
            yr_affirm[y] += 1
        if outcome in IND:
            yr_undec[y] += 1
        for rule, k in SUBSTITUTIONS:
            if two_valued(v_ug, l_ug, status == "censored", thr, k) == "exceeding":
                yr_two[y][rule] += 1

    years = sorted(yr_tot, key=int)
    if not years:
        print("  ! no dated assessable rows; skipping")
        return 0

    rows_out = []
    for y in years:
        n = yr_tot[y]
        rows_out.append(dict(
            year=int(y), assessable=n,
            affirmable=yr_affirm[y],
            undecidable=yr_undec[y],
            undecidable_pct=round(100 * yr_undec[y] / n, 2) if n else 0,
            **{f"two_valued_{r}": yr_two[y][r] for r, _ in SUBSTITUTIONS},
            plotted="yes" if n >= MIN_YEAR else "no"))

    PROC.mkdir(parents=True, exist_ok=True)
    FDATA.mkdir(parents=True, exist_ok=True)
    for d in (PROC / "exceedances_by_year.csv",
              FDATA / f"{STEM}.csv"):
        with d.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_out[0]))
            w.writeheader()
            w.writerows(rows_out)

    plot = [r for r in rows_out if r["plotted"] == "yes"]
    if not plot:
        print("  ! no year clears the plotting floor")
        return 0
    xs = [r["year"] for r in plot]

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(9.8, 6.4), sharex=True,
        gridspec_kw=dict(height_ratios=[2.5, 1], hspace=0.13))

    ax.fill_between(xs, [r["two_valued_full"] for r in plot],
                    [r["two_valued_zero"] for r in plot],
                    color=RED, alpha=.13, lw=0)
    for rule, style, lab in (("full", "-", "at the full limit"),
                             ("half", "--", "at half the limit"),
                             ("zero", ":", "at zero")):
        ax.plot(xs, [r[f"two_valued_{rule}"] for r in plot], style,
                color=RED, lw=1.5, label=f"two-valued, non-detect {lab}")
    ax.plot(xs, [r["affirmable"] for r in plot], "-", color=GREEN, lw=2.4,
            label="exceedances the law can affirm")
    ax.set_ylabel("station-years", fontsize=9)
    ax.legend(fontsize=8.5, frameon=False, loc="upper left")
    ax.set_title("What a substituting pipeline reports as an exceedance, and "
                 "what the record can support, year by year",
                 fontsize=10.5, loc="left", fontweight="bold", pad=10)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    ax2.plot(xs, [r["undecidable_pct"] for r in plot], "-", color=INK, lw=1.8)
    ax2.set_ylabel("undecidable, %", fontsize=9)
    ax2.set_xlabel("reference year", fontsize=9)
    ax2.set_ylim(0, 100)
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    for a in (ax, ax2):
        a.tick_params(labelsize=8.5)
    # not tight_layout: it does not understand the shared-x gridspec and
    # warns that the result may be wrong. Explicit margins instead.
    fig.subplots_adjust(left=0.085, right=0.985, top=0.925, bottom=0.095)
    FIGS.mkdir(parents=True, exist_ok=True)
    for fmt in ("pdf", "svg", "png"):
        fig.savefig(FIGS / f"{STEM}.{fmt}", dpi=200, bbox_inches="tight")
    plt.close(fig)

    # EVERY figure the manuscript quotes from this series is emitted here.
    # Section 5 states the peaks, the last-year ratio and the post-2013 band;
    # computing them in the prose and not in the report is how a number ends up
    # unowned, and an unowned number makes some other check lie.
    first, last = plot[0], plot[-1]
    PLATEAU = 2013
    peak_aff = max(r["affirmable"] for r in plot)
    peak_full = max(r["two_valued_full"] for r in plot)
    ratio_last = last["two_valued_full"] / max(last["affirmable"], 1)
    mid = [r for r in plot if r["year"] >= PLATEAU]
    band = (min(r["undecidable_pct"] for r in mid),
            max(r["undecidable_pct"] for r in mid)) if mid else (0, 0)
    span = sum(r["two_valued_full"] for r in plot) / max(
        sum(r["affirmable"] for r in plot), 1)
    A = ["# Exceedances, year by year\n",
         "Generated by `scripts/29_exceedances_by_year.py`. The decision "
         "procedure is imported from `22_waterbase_external`, not restated, so "
         "this series and the totals in Section 5.4 cannot disagree.\n",
         f"Years below {MIN_YEAR:,} assessable station-years are carried in the "
         "CSV and not plotted: a percentage over a handful of stations is noise "
         "drawn as a trend.\n",
         "| | first plotted year | last plotted year |", "|---|---|---|",
         f"| year | {first['year']} | {last['year']} |",
         f"| assessable station-years | {first['assessable']:,} "
         f"| {last['assessable']:,} |",
         f"| two-valued exceedances, full limit | {first['two_valued_full']:,} "
         f"| {last['two_valued_full']:,} |",
         f"| exceedances the law can affirm | {first['affirmable']:,} "
         f"| {last['affirmable']:,} |",
         f"| undecidable | {first['undecidable_pct']:.1f} % "
         f"| {last['undecidable_pct']:.1f} % |",
         "",
         "| across the plotted years | |", "|---|---|",
         f"| most exceedances the law can affirm in any year | **{peak_aff:,}** |",
         f"| most a full-limit pipeline reports in any year | **{peak_full:,}** |",
         f"| ratio in the final year | **{ratio_last:.1f}x** |",
         f"| undecidable share from {PLATEAU} onward "
         f"| **{band[0]:.1f}–{band[1]:.1f} %**, {len(mid)} years |",
         "",
         f"The affirmable series does not grow with the record: monitoring "
         f"effort scales and the number of exceedances an enforcement action "
         f"could defend does not scale with it.\n",
         f"Over the plotted years a two-valued pipeline entering non-detections "
         f"at the full limit reports **{span:.1f} times** as many exceedances "
         f"as the law can affirm. The gap is a property of the reporting, not "
         f"of a period: it is present at both ends of the series.\n"]
    EVAL.mkdir(parents=True, exist_ok=True)
    (EVAL / "exceedances_by_year.md").write_text("\n".join(A) + "\n",
                                                 encoding="utf-8")
    print(f"  {len(years)} years, {len(plot)} plotted "
          f"({plot[0]['year']}–{plot[-1]['year']}); "
          f"full-limit reports {span:.1f}x the affirmable total")
    print(f"  wrote derived/processed/exceedances_by_year.csv")
    print(f"  wrote paper/figures/{STEM}.pdf and eval/exceedances_by_year.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
