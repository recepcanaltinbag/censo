#!/usr/bin/env python3
"""The field-wide gap, as a matrix rather than a supplementary table.

WHY THIS FIGURE
---------------
The paper's broadest claim is about a literature, not about a record: of the
ontologies parsed -- reaching outside the water domain to the laboratory
vocabularies -- none carries a censoring status, and the one that defines the
quantification limit most carefully still binds it to the method. That claim
lives in a supplementary table and in prose. A reader who wants to check it has
to read twenty-three rows and hold six columns in their head.

Drawn, it takes a second, and it carries two things the table does not.

  WHERE THE LIMIT IS BOUND is the paper's thesis, and in the table it is one
  string in one column among six numbers. Here it gets its own channel, at the
  left, with its own colours: sensor, method, result. Three ontologies have a
  detection limit at all and each binds it somewhere different; only the
  rightmost of those can say that a particular measurement fell below one.

  SIZE IS NOT THE ISSUE. CENSO has 51 entities against ENVO's 7,208 and AFO's
  3,864, and fills columns neither of them fills. Without the entity counts a
  reader may reasonably suspect the comparison rewards a vocabulary for being
  narrow. The counts are drawn, so the suspicion can be checked rather than
  entertained.

The matrix is deliberately unflattering to this work in one respect: the
`undecidable` column is generous, matching any term for an indeterminate or
unknown value, and eight ontologies earn it. The claim is not that nobody has a
word for "unknown". It is that nobody has one for a MEASUREMENT that is a
bound, which is the `censoring` column, and that column has one mark in it.

Inputs  : derived/processed/gap_matrix.csv
Outputs : paper/figures/fig17_field_gap.{pdf,svg,png}
          paper/supplementary/figure_data/fig17_field_gap.csv

Usage:  python scripts/94b_gap_matrix.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                   # noqa: E402
from matplotlib.patches import Rectangle                          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
FDATA = ROOT / "paper" / "supplementary" / "figure_data"

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_figs", ROOT / "scripts" / "90_figures.py")
_figs = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_figs)
save, W2 = _figs.save, _figs.W2

INK, MUTED, GRID = "#1f1f1f", "#8a8a8a", "#dcdfe3"
FILL, EMPTY = "#1f4e79", "#eef0f2"
OURS = "#b03030"
# where the limit is bound: the three answers the literature gives, in the
# order the argument moves through them
BOUND = {"sensor": ("#7a7a7a", "on the sensor"),
         "method": ("#c98a2e", "on the method"),
         "result": ("#b03030", "on the result"),
         "unclear": ("#c9c9c9", "not stated")}

COLS = [("detection_limit", "a detection or\nquantification limit"),
        ("censoring", "a censored\nresult"),
        ("interval_result", "a result that is\nan interval"),
        ("undecidable", "an undecidable\nvalue"),
        ("threshold", "a regulatory\nthreshold"),
        ("applicability", "a condition on\nwhen it applies")]


def main() -> int:
    p = PROC / "gap_matrix.csv"
    if not p.exists():
        print("  ! gap_matrix.csv missing; run scripts/07_verify_gap_table.py")
        return 0
    with p.open(encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("status") == "OK"]
    if not rows:
        print("  ! no parsed ontologies in gap_matrix.csv")
        return 0

    def score(r):
        return sum(int(r.get(c) or 0) for c, _ in COLS)

    ours = [r for r in rows if "this work" in r["ontology"]]
    others = sorted([r for r in rows if "this work" not in r["ontology"]],
                    key=lambda r: (score(r), int(r.get("entities") or 0)))
    order = others + ours

    n = len(order)
    fig, (axb, ax, axe) = plt.subplots(
        1, 3, figsize=(W2, 0.30 * n + 3.4),
        gridspec_kw={"width_ratios": [0.20, 1.0, 0.34], "wspace": 0.06})

    # ---- centre: the concept matrix ---------------------------------------
    for i, r in enumerate(order):
        mine = "this work" in r["ontology"]
        for j, (c, _) in enumerate(COLS):
            on = int(r.get(c) or 0)
            ax.add_patch(Rectangle((j, i), 0.86, 0.78,
                                   facecolor=(OURS if mine else FILL) if on
                                   else EMPTY,
                                   edgecolor="white", linewidth=1.2))
    ax.set_xlim(-0.08, len(COLS))
    ax.set_ylim(n, -0.4)
    ax.set_xticks([j + 0.43 for j in range(len(COLS))])
    # rotated, because six two-line headers over six narrow columns collide
    # at any font size that is still readable
    ax.set_xticklabels([lbl.replace("\n", " ") for _, lbl in COLS],
                       fontsize=7.2, rotation=32, ha="left",
                       rotation_mode="anchor")
    ax.xaxis.set_ticks_position("top")
    ax.set_yticks([])
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)

    # ---- left: where the limit is bound, and the name ---------------------
    seen_bound = []
    for i, r in enumerate(order):
        mine = "this work" in r["ontology"]
        b = (r.get("lod_bound_to") or "").strip()
        if b and b != "0":
            colr, lab = BOUND.get(b, ("#c9c9c9", b))
            axb.add_patch(Rectangle((0.55, i), 0.42, 0.78, facecolor=colr,
                                    edgecolor="white", linewidth=1.2))
            if lab not in seen_bound:
                seen_bound.append(lab)
        axb.text(0.45, i + 0.39, r["ontology"], ha="right", va="center",
                 fontsize=7.4, color=OURS if mine else INK,
                 fontweight="bold" if mine else "normal")
    axb.set_xlim(-2.6, 1.0)
    axb.set_ylim(n, -0.4)
    axb.axis("off")

    # ---- right: how many entities each one declares -----------------------
    mx = max(int(r.get("entities") or 0) for r in order) or 1
    for i, r in enumerate(order):
        e = int(r.get("entities") or 0)
        mine = "this work" in r["ontology"]
        axe.barh(i + 0.39, e, height=0.62,
                 color=OURS if mine else "#c5cbd2", edgecolor="none")
        axe.text(e + mx * 0.02, i + 0.39, f"{e:,}", va="center", fontsize=6.4,
                 color=OURS if mine else MUTED,
                 fontweight="bold" if mine else "normal")
    axe.set_xlim(0, mx * 1.30)
    axe.set_ylim(n, -0.4)
    axe.set_yticks([])
    axe.set_xticks([])
    for sp in axe.spines.values():
        sp.set_visible(False)
    axe.set_title("entities\ndeclared", fontsize=7.2, color=MUTED, pad=6)

    # ---- legends ----------------------------------------------------------
    hs = [Rectangle((0, 0), 1, 1, facecolor=BOUND[k][0])
          for k in ("sensor", "method", "result") ]
    ax.legend(hs, [BOUND[k][1] for k in ("sensor", "method", "result")],
              title="where the limit is bound", title_fontsize=7.2,
              fontsize=7.2, frameon=False, ncol=3,
              loc="upper left", bbox_to_anchor=(0.0, -0.02 - 0.9 / n))

    n_cens = sum(1 for r in order if int(r.get("censoring") or 0))
    n_ext = len(others)
    fig.text(0.01, 1.0,
             f"Of {n_ext} ontologies parsed, one carries a censored result\n"
             f"and every vocabulary that defines a limit binds it to what "
             f"produced the result",
             fontsize=9.4, fontweight="bold", color=INK, ha="left", va="top")

    # the two-line heading and the rotated column headers both want the top
    # of the canvas; give the matrix a lower ceiling rather than shrink either
    fig.subplots_adjust(top=0.83)
    save(fig, "fig17_field_gap")
    FDATA.mkdir(parents=True, exist_ok=True)
    with (FDATA / "fig17_field_gap.csv").open("w", newline="",
                                              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ontology", "entities", "limit_bound_to"]
                   + [c for c, _ in COLS])
        for r in order:
            w.writerow([r["ontology"], r.get("entities") or 0,
                        r.get("lod_bound_to") or ""]
                       + [int(r.get(c) or 0) for c, _ in COLS])
    print(f"  fig17: {len(order)} ontologies, {n_cens} carrying a censored "
          f"result, {n_ext} external")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
