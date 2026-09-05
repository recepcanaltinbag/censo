#!/usr/bin/env python3
"""
Four real rows, decided twice: once by CENSO, once by a two-valued schema.

WHY THIS FIGURE AND NOT ANOTHER ONE
-----------------------------------
Figure 6 draws the decision GEOMETRY -- where a threshold falls relative to a
method's quantification limit -- for three cases, and it is the right picture
for that. What it does not show is the comparison the whole paper turns on:
what a schema with only two verdicts returns for the SAME row, and whether that
answer depends on a convention nobody recorded.

That is what this figure is. Each row is one real station-year drawn from the
shipped graph, decided by CENSO on the left and by a two-valued pipeline on the
right -- at zero, at half the limit, and at the limit, because those are the
three substitutions in use and the point is that they disagree.

The four cases are chosen to be the four answers, not four illustrations of
one: a row both systems get right, a row where the two-valued verdict is the
substitution constant rather than the measurement, a row where a quantified
value sits inside the interval the law's own uncertainty allowance permits, and
a row where the standard is not defined on anything that was measured.

WHERE THE CASES COME FROM
-------------------------
Read out of derived/abox/censo-waterbase.ttl, first match per outcome class in
sorted order, so the figure cannot be accused of picking flattering rows and a
rebuild selects the same ones. The two-valued verdicts are computed by
importing 22_waterbase_external.two_valued rather than reimplementing it: the
figure and the counts in Section 5.4 must not be able to disagree.

Inputs  : derived/abox/censo-waterbase.ttl, ontology/reg/eu-2008-105-2026.ttl
Outputs : paper/figures/fig11_decision_walkthrough.{pdf,svg,png}
          paper/supplementary/figure_data/fig11_decision_walkthrough.csv
          eval/decision_walkthrough.md

Usage:  python scripts/92_decision_walkthrough.py
"""

from __future__ import annotations

import csv
import re
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                   # noqa: E402
from matplotlib.patches import Rectangle, FancyBboxPatch          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ABOX = ROOT / "derived" / "abox" / "censo-waterbase.ttl"
REGF = ROOT / "ontology" / "reg" / "eu-2008-105-2026.ttl"
FIGS = ROOT / "paper" / "figures"
FDATA = ROOT / "paper" / "supplementary" / "figure_data"
EVAL = ROOT / "eval"
STEM = "fig11_decision_walkthrough"

sys.path.insert(0, str(Path(__file__).resolve().parent))
_m = __import__("22_waterbase_external")
two_valued = _m.two_valued
SUBSTITUTIONS = _m.SUBSTITUTIONS

# The four answers, in the order the argument needs them: agreement first, so
# the figure is not read as "CENSO always says it cannot decide".
CASES = [
    ("Compliant", "both systems agree",
     "The bound clears the standard. Nothing is lost by the simpler model, "
     "and a vocabulary that could not say this would be useless."),
    ("MethodInsufficient", "the verdict IS the convention",
     "Art. 3(3b): a below-quantification result whose limit exceeds the "
     "standard shall not be considered. The two-valued answer flips with the "
     "substitution constant, and the record does not say which was used."),
    ("PossibleExceedance", "inside the law's own uncertainty",
     "Art. 4(1) permits 50 % expanded uncertainty at the level of the "
     "standard, so this interval straddles it. A method meeting only the "
     "legal minimum cannot decide either way."),
    ("PreconditionUnmet", "the standard is not defined on what was measured",
     "Annex I footnote 9 makes the cadmium standard vary with water hardness. "
     "WISE-6 reports no hardness on the row, so the number in the table and "
     "the number in the record are not measurements of the same quantity."),
]

FILL = {"Compliant": "#cfe3cf", "MethodInsufficient": "#f6ddc0",
        "PossibleExceedance": "#f6e8c0", "PreconditionUnmet": "#f2d6d6"}
TWO = {"compliant": ("#3c7a3c", "compliant"),
       "exceeding": ("#b03030", "exceeding")}


def blocks(txt):
    out, cur = [], None
    for line in txt.splitlines():
        if line.startswith("wb:obs-"):
            cur = [line]
        elif cur is not None:
            cur.append(line)
        if cur is not None and line.rstrip().endswith("."):
            out.append("\n".join(cur))
            cur = None
    return out


def load_cases():
    if not ABOX.exists():
        sys.exit(f"missing {ABOX}; run scripts/23_waterbase_abox.py first")
    reg = REGF.read_text(encoding="utf-8")
    thr, cur = {}, None
    for line in reg.splitlines():
        m = re.match(r"^(cereg:\S+)\s", line)
        if m:
            cur = m.group(1)
        m = re.search(r'censo:thresholdValue "([^"]+)"', line)
        if m and cur:
            thr[cur] = float(m.group(1))
    label = dict(re.findall(
        r'^(cereg:\S+) a censo:Analyte ;\s*\n\s*rdfs:label "([^"]*)"',
        reg, re.M))

    bs = blocks(ABOX.read_text(encoding="utf-8"))
    found = {}
    for cls, _, _ in [(c, a, b) for c, a, b in CASES]:
        for b in bs:
            if f"censo:{cls}" not in b:
                continue
            t = re.search(r"censo:assessableAgainst (cereg:\S+) ;", b)
            a = re.search(r"censo:hasAnalyte (cereg:\S+) ;", b)
            if not (t and a and t.group(1) in thr):
                continue
            g = lambda p: (lambda m: float(m.group(1)) if m else None)(
                re.search(rf'censo:{p} "([^"]+)"', b))
            found[cls] = dict(
                substance=label.get(a.group(1), a.group(1)),
                threshold=thr[t.group(1)],
                lo=g("resultLowerBound"), hi=g("resultUpperBound"),
                value=g("reportedValue"),
                censored="censo:CensoredObservation" in b)
            break
    return found


def main() -> int:
    found = load_cases()
    missing = [c for c, _, _ in CASES if c not in found]
    if missing:
        print("  ! no row in the graph for: " + ", ".join(missing))

    rows = [(c, h, why, found[c]) for c, h, why in CASES if c in found]
    fig, axes = plt.subplots(len(rows), 1, figsize=(11.6, 2.95 * len(rows)))
    if len(rows) == 1:
        axes = [axes]
    plt.subplots_adjust(left=0.005, right=0.995, top=0.955, bottom=0.055,
                        hspace=1.05)

    out_csv = []
    for ax, (cls, head, why, d) in zip(axes, rows):
        T, lo, hi = d["threshold"], d["lo"], d["hi"],
        lo = 0.0 if lo is None else lo
        hi = d["hi"] if d["hi"] is not None else (d["value"] or T)
        # the two-valued answers, from the shared implementation
        tv = [two_valued(d["value"], hi if d["censored"] else None,
                         d["censored"], T, k) for _, k in SUBSTITUTIONS]

        ax.set_xscale("log")
        span = [x for x in (lo, hi, T, d["value"]) if x and x > 0]
        left, right = min(span) / 3.2, max(span) * 3.2
        ax.set_xlim(left, right)
        ax.set_ylim(0, 1)
        ax.set_yticks([])
        for s in ("top", "left", "right"):
            ax.spines[s].set_visible(False)
        ax.tick_params(axis="x", labelsize=8.5)

        # the interval the observation actually establishes
        x0 = max(lo, left * 1.02)
        ax.add_patch(Rectangle((x0, 0.40), max(hi - x0, left * 0.01), 0.20,
                               facecolor=FILL[cls], edgecolor="#555555",
                               linewidth=1.0, zorder=3))
        ax.text(hi, 0.68, f"  upper bound {hi:g}", fontsize=8.5,
                va="center", color="#333333", zorder=4)
        if d["censored"]:
            ax.text(x0, 0.28, "0 — a non-detection permits any value down to zero",
                    fontsize=8, color="#666666", zorder=4)
        # the threshold
        ax.axvline(T, color="#b03030", linewidth=1.9, zorder=5)
        ax.text(T, 0.90, f" standard {T:g} µg/L", fontsize=9, color="#b03030",
                fontweight="bold", va="center", zorder=6)
        if d["value"] is not None and not d["censored"]:
            ax.plot([d["value"]], [0.50], "o", color="#1f4e79", ms=7, zorder=7)
            ax.text(d["value"], 0.14, f"measured {d['value']:g}", fontsize=8.5,
                    ha="center", color="#1f4e79", zorder=7)

        ax.set_title(
            f"{d['substance'].split(' (')[0][:44]}   —   CENSO: censo:{cls}   ({head})",
            fontsize=10.5, loc="left", color="#111111", fontweight="bold",
            pad=8)
        ax.set_xlabel("concentration, µg/L (log scale)", fontsize=8.5,
                      labelpad=1)

        # what a two-valued schema returns, at the three constants
        chips = " ".join(f"{n}: {v}" for (n, _), v in zip(SUBSTITUTIONS, tv))
        flips = len(set(tv)) > 1
        ax.text(1.005, 0.78,
                "two-valued schema, same row:", transform=ax.transAxes,
                fontsize=8.5, color="#333333", fontweight="bold")
        for i, ((name, _), v) in enumerate(zip(SUBSTITUTIONS, tv)):
            col, txt = TWO.get(v, ("#666666", v))
            ax.text(1.005, 0.56 - i * 0.20,
                    f"non-detect → {name}:  {txt}",
                    transform=ax.transAxes, fontsize=8.5, color=col)
        if flips:
            ax.text(1.005, -0.10,
                    "the answer is the constant, not the measurement",
                    transform=ax.transAxes, fontsize=8.5, color="#b03030",
                    fontweight="bold")
        ax.text(0.0, -0.52, textwrap.fill(why, 118),
                transform=ax.transAxes, fontsize=8.4,
                color="#444444", va="top", linespacing=1.45)

        out_csv.append(dict(
            case=cls, substance=d["substance"], threshold_ug_l=T,
            lower_bound=lo, upper_bound=hi, reported_value=d["value"],
            censored="yes" if d["censored"] else "no",
            two_valued_zero=tv[0], two_valued_half=tv[1],
            two_valued_full=tv[2],
            two_valued_depends_on_constant="yes" if flips else "no"))

    FIGS.mkdir(parents=True, exist_ok=True)
    for fmt in ("pdf", "svg", "png"):
        fig.savefig(FIGS / f"{STEM}.{fmt}", dpi=200, bbox_inches="tight")
    plt.close(fig)

    FDATA.mkdir(parents=True, exist_ok=True)
    with (FDATA / f"{STEM}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_csv[0]))
        w.writeheader()
        w.writerows(out_csv)

    n_flip = sum(1 for r in out_csv
                 if r["two_valued_depends_on_constant"] == "yes")
    A = ["# Four rows, decided twice\n",
         "Generated by `scripts/92_decision_walkthrough.py` into "
         f"`paper/figures/{STEM}.pdf`.\n",
         "Each row is one real station-year from the shipped graph, decided by "
         "CENSO and by a two-valued pipeline at each of the three substitution "
         "constants in use. The two-valued verdicts come from "
         "`22_waterbase_external.two_valued`, imported rather than "
         "reimplemented, so this figure and the counts in Section 5.4 cannot "
         "disagree. Cases are the first match per outcome class in sorted "
         "order, so a rebuild selects the same rows and the choice cannot "
         "flatter the argument.\n",
         "| case | substance | standard | interval | two-valued: zero / half / "
         "full | depends on the constant |", "|---|---|---|---|---|---|"]
    for r in out_csv:
        A.append(f"| `{r['case']}` | {r['substance']} | "
                 f"{r['threshold_ug_l']:g} | "
                 f"[{r['lower_bound']:g}, {r['upper_bound']:g}] | "
                 f"{r['two_valued_zero']} / {r['two_valued_half']} / "
                 f"{r['two_valued_full']} | "
                 f"**{r['two_valued_depends_on_constant']}** |")
    A += ["",
          f"**{n_flip} of {len(out_csv)} rows get a different two-valued "
          f"verdict depending on which substitution the pipeline happened to "
          f"use**, and nothing in a two-valued output records that a choice "
          f"was made. That is the difference the vocabulary exists to carry: "
          f"not a better estimate, a statement the schema can hold.\n"]
    EVAL.mkdir(parents=True, exist_ok=True)
    (EVAL / "decision_walkthrough.md").write_text("\n".join(A) + "\n",
                                                  encoding="utf-8")
    print(f"  wrote paper/figures/{STEM}.pdf/.svg/.png  "
          f"({len(out_csv)} cases, {n_flip} flip with the constant)")
    print(f"  wrote paper/supplementary/figure_data/{STEM}.csv")
    print(f"  wrote eval/decision_walkthrough.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
