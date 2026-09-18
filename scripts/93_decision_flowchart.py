#!/usr/bin/env python3
"""The decision procedure as a flowchart, with every path executed to prove it.

WHY THIS FIGURE
---------------
Figure 6 draws the decision GEOMETRY -- where the outcomes sit relative to the
threshold. Figure 11 walks four real rows through it twice. Neither shows the
procedure itself: the order the questions are asked in, and why that order is
not arbitrary. That order is the argument. A record with no bound is asked
nothing else; the fraction, the hardness class and the bioavailability tier are
asked before any comparison; Article 3(3b) reaches only a bounded result; the
uncertainty band applies only to a measured value. Get the order wrong and the
same fields yield a different verdict.

WHY IT CANNOT DRIFT
-------------------
A flowchart of an algorithm is a claim about the algorithm, and a drawing has
no way to be wrong loudly. So each outcome edge carries WITNESSES: concrete
inputs that must make assess() return the outcome the edge leads to. Every
witness is executed against the real function before the figure is written,
and a mismatch refuses to draw rather than shipping a picture of code that no
longer exists.

2.4.0. The procedure gained the applicability step (fraction, hardness class,
CIS Guidance No. 38 tier 1), a bound test before it, and Article 5(2) for a
mean below its own limit. The witness list gained a censored limit at 0.8 T:
the old "censored, compliant" witness sat at 0.5 T, exactly where a band
applied to non-detections would also have said Compliant, so the test could
not have seen that change.

Inputs  : scripts/22_waterbase_external.py (the function itself)
Outputs : paper/figures/fig15_decision_flow.{pdf,svg,png}
          paper/supplementary/figure_data/fig15_decision_flow.csv
          eval/decision_flowchart.md

Usage:  python scripts/93_decision_flowchart.py
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIGS = ROOT / "paper" / "figures"
FDATA = ROOT / "paper" / "supplementary" / "figure_data"
EVAL = ROOT / "eval"

sys.path.insert(0, str(Path(__file__).resolve().parent))
_m = __import__("22_waterbase_external")
assess = _m.assess
U = _m.LEGAL_UNCERTAINTY_AT_EQS

INK, MUTED = "#1f1f1f", "#8a8a8a"
ASK = "#f4f4f2"
OUT = {"exceedance": "#b03030", "compliant": "#3c7a3c",
       "indeterminate": "#c98a2e"}

CD, PB = "7440-43-9", "7439-92-1"
HC, BC = "censo:HardnessClassCondition", "censo:BioavailabilityCondition"

# Each test, in the order assess() asks it, with WHY it is asked there.
# (id, question, why this position)
STEPS = [
    ("bound", "Does the record establish a bound?\n"
     "(a flag or a limit, and a limit for a flag)",
     "First, because nothing else can be asked of a record that establishes no\n"
     "interval. A row with neither a censoring flag nor a limit, or flagged\n"
     "below a limit it does not state, is a defect of the record whatever the\n"
     "standard and its conditions are, and it is reported as that."),
    ("threshold", "Is a standard defined for\nthis substance here?",
     "Asked after the bound and before everything else, because it is a fact\n"
     "about the REGULATION and not about the record: a jurisdiction that sets\n"
     "no limit for a substance has not found it compliant. No row in this\n"
     "paper's denominator reaches it -- the population is the rows a European\n"
     "standard covers -- and it arises when the same observations are assessed\n"
     "under a second package, which regulates a different list."),
    ("fraction", "Metal: is the result on the\ndissolved fraction?\n"
     "(Annex I Part B point 3)",
     "The water standards for cadmium, lead, mercury and nickel refer to the\n"
     "dissolved concentration. A whole-water result is not a measurement of the\n"
     "quantity the standard is written on, so no verdict is drawn from it --\n"
     "not even a pass, which would rest on total >= dissolved, our reasoning and\n"
     "not the Directive's."),
    ("hardness", "Cadmium: is a hardness reported\nfor the station-year?\n"
     "(footnote 9; GD 38 tier 2)",
     "The cadmium standard depends on the hardness class of the water. The\n"
     "release reports hardness, or calcium and magnesium, on rows of their own;\n"
     "joined, it selects the class standard the comparison below uses. Without\n"
     "it the applicable standard is unknown."),
    ("bio", "Lead, nickel: does the dissolved\nresult pass the bioavailable\n"
     "standard?  (GD 38 tier 1)",
     "The bioavailable concentration cannot exceed the dissolved one, so a\n"
     "dissolved result that clears the bioavailable standard clears it. The\n"
     "comparison below is made, and only a pass or Article 3(3b) is kept;\n"
     "anything else needs a bioavailability model the record cannot feed."),
    ("status", "Detection status, read from the\ncensoring flag, the value"
     "\nand the LOQ",
     "A flag set below the limit is censored; an unflagged value is quantified.\n"
     "The flag and the limit are separate statements -- an empty flag says\n"
     "nothing, a '0' says not censored, which is information."),
    ("contra", "Is the reported mean below\nits own LOQ?  x < LOQ",
     "Directive 2009/90/EC Article 5(2): a calculated mean below the limit of\n"
     "quantification shall be referred to as 'less than limit of\n"
     "quantification'. It is a bounded result the reporter did not flag, and it\n"
     "is assessed as one."),
    ("art3", "Is the quantification limit\nabove the standard?  LOQ > T",
     "Article 3(3b) reaches a result reported as below the quantification limit,\n"
     "and compares the limit with the standard as a point. The band is not\n"
     "applied here: the Directive does not apply it, and a limit inside the\n"
     "band is flagged, not reclassified."),
    ("band", "Where is x against T ± U?\n"
     "(U reported, else 0.5 T)",
     "Article 4(1) sets a CEILING, not a test: a lawfully usable method has an\n"
     "expanded uncertainty of '50 % or below' at the level of the standard. A\n"
     "reported uncertainty is used where the record carries one; none does\n"
     "here, so U = 0.5 T, the widest the law permits, and a value inside it\n"
     "could have been produced on either side of the standard."),
]


def w(status, val, loq, thr, **kw):
    return dict(status=status, val_ug=val, loq_ug=loq, thr=thr, **kw)


# (from, label, to, witnesses) -- every witness must produce `to`.
EDGES = [
    ("threshold", "no", "no_threshold_defined",
     [w("quantified", 0.5, 0.01, None),
      w("censored", None, 0.01, None)]),
    ("threshold", "yes", "fraction", None),

    ("bound", "no flag, no limit", "indeterminate_unresolved",
     [w("unresolved", None, None, 1.0),
      w("unresolved", 0.3, None, 1.2, cas=PB, condition=BC, fraction="W")]),
    ("bound", "flag, no limit", "indeterminate_other",
     [w("censored", None, None, 1.0),
      w("censored", None, None, 0.08, cas=CD, condition=HC, fraction="W")]),
    ("bound", "yes", "threshold", None),

    ("fraction", "no", "precondition_unmet",
     [w("quantified", 0.3, 0.01, 1.2, cas=PB, condition=BC, fraction="W"),
      w("censored", None, 0.01, 0.08, cas=CD, condition=HC, fraction="W",
        hardness=300.0)]),
    ("fraction", "yes, or not a metal", "hardness", None),

    ("hardness", "no", "precondition_unmet",
     [w("quantified", 0.02, 0.005, 0.08, cas=CD, condition=HC,
        fraction="W-DIS")]),
    ("hardness", "yes: class standard,\nor not cadmium", "bio", None),

    ("bio", "no, and not Art. 3(3b)", "precondition_unmet",
     [w("quantified", 5.0, 0.01, 1.2, cas=PB, condition=BC, fraction="W-DIS"),
      w("quantified", 1.0, 0.01, 1.2, cas=PB, condition=BC, fraction="W-DIS")]),
    ("bio", "pass, or not lead/nickel", "status", None),

    ("status", "censored", "art3", None),
    ("status", "quantified", "contra", None),

    ("contra", "yes: '<LOQ', Art. 5(2)", "art3", None),
    ("contra", "no", "band", None),

    ("art3", "yes", "method_insufficient",
     [w("censored", None, 2.0, 1.0),
      w("quantified", 0.2, 5.0, 1.0),
      w("censored", None, 2.0, 1.2, cas=PB, condition=BC, fraction="W-DIS"),
      w("censored", None, 0.12, 0.08, cas=CD, condition=HC, fraction="W-DIS",
        hardness=30.0)]),
    ("art3", "no", "compliant",
     [w("censored", None, 0.8, 1.0),
      w("censored", None, 1.0, 1.0),
      w("quantified", 0.2, 0.5, 1.0),
      w("censored", None, 0.12, 0.08, cas=CD, condition=HC, fraction="W-DIS",
        hardness=150.0)]),

    ("band", "within", "possible_exceedance",
     [w("quantified", 1.2, 0.1, 1.0),
      w("quantified", 0.05, 0.01, 0.08, cas=CD, condition=HC,
        fraction="W-DIS", hardness=30.0)]),
    ("band", "above", "exceedance",
     [w("quantified", 9.0, 0.1, 1.0),
      w("quantified", 0.5, 0.01, 0.08, cas=CD, condition=HC,
        fraction="W-DIS", hardness=250.0)]),
    ("band", "below", "compliant",
     [w("quantified", 0.05, 0.01, 1.0),
      w("quantified", 0.3, 0.01, 1.2, cas=PB, condition=BC, fraction="W-DIS")]),
]

LEAF = {
    "no_threshold_defined": ("NoThresholdDefined", "indeterminate"),
    "precondition_unmet": ("PreconditionUnmet", "indeterminate"),
    "indeterminate_unresolved": ("BoundNotEstablished", "indeterminate"),
    "method_insufficient": ("MethodInsufficient", "indeterminate"),
    "indeterminate_other": ("BoundNotEstablished", "indeterminate"),
    "possible_exceedance": ("PossibleExceedance", "indeterminate"),
    "exceedance": ("Exceedance", "exceedance"),
    "compliant": ("Compliant", "compliant"),
}


def verify():
    """Execute every witness. A drawn outcome edge with no witness is not drawn."""
    bad, ok, n_wit = [], [], 0
    for src, lbl, dst, wits in EDGES:
        if wits is None:
            continue
        if not wits:
            bad.append(f"{src} --{lbl}--> {dst}: no witness")
            continue
        for wit in wits:
            kw = dict(wit)
            got = assess(kw.pop("status"), kw.pop("val_ug"), kw.pop("loq_ug"),
                         kw.pop("thr"), **kw)[0]
            n_wit += 1
            if got != dst:
                bad.append(f"{src} --{lbl}--> {dst}: {wit} returns {got}")
        ok.append((src, lbl, dst))
    return ok, bad, n_wit


def dot() -> str:
    L = ['digraph flow {', '  rankdir=TB; bgcolor="white";',
         '  node [fontname="Helvetica", fontsize=10, shape=box, style="filled,rounded"];',
         '  edge [fontname="Helvetica", fontsize=9, color="%s"];' % MUTED]
    L.append('  input [label="one reported row:  censoring flag,  value x,'
             '\\nquantification limit LOQ,  standard T,\\nfraction,  hardness '
             'of the station-year", '
             'shape=note, fillcolor="white", color="%s", fontsize=9];' % MUTED)
    L.append(f'  input -> {STEPS[0][0]} [style=dashed];')
    for sid, q, _ in STEPS:
        L.append(f'  {sid} [label="{q}", fillcolor="{ASK}", '
                 f'color="{INK}", shape=diamond, height=1.1, width=2.6];')
    # One node per OUTCOME CLASS, not per pipeline outcome: two reasons reach
    # censo:BoundNotEstablished, several reach PreconditionUnmet and Compliant,
    # and drawing any of them twice would show a class the vocabulary lacks.
    node = {d: (LEAF[d][0] if d in LEAF else d) for _, _, d, _ in EDGES}
    seen = set()
    for _, _, dst, _ in EDGES:
        if dst in LEAF and node[dst] not in seen:
            seen.add(node[dst])
            name, kind = LEAF[dst]
            L.append(f'  {node[dst]} [label="censo:{name}", '
                     f'fillcolor="{OUT[kind]}", fontcolor="white", '
                     f'color="{OUT[kind]}"];')
    for src, lbl, dst, _ in EDGES:
        L.append(f'  {src} -> {node[dst]} [label=" {lbl}"];')
    L.append('}')
    return "\n".join(L)


def main() -> int:
    ok, bad, n_wit = verify()
    if bad:
        print("  FAIL the flowchart draws paths the function does not take:")
        for b in bad:
            print(f"        {b}")
        print("  The figure is a claim about the code. Fix one of them, but do "
              "not draw it.")
        return 1

    FIGS.mkdir(parents=True, exist_ok=True)
    FDATA.mkdir(parents=True, exist_ok=True)
    src = dot()
    if not shutil.which("dot"):
        print("  ! graphviz 'dot' not found; wrote the source only")
        (FIGS / "fig15_decision_flow.dot").write_text(src, encoding="utf-8")
    else:
        for fmt in ("pdf", "svg", "png"):
            subprocess.run(["dot", f"-T{fmt}",
                            "-o", str(FIGS / f"fig15_decision_flow.{fmt}")],
                           input=src.encode(), check=True)

    with (FDATA / "fig15_decision_flow.csv").open(
            "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["from", "answer", "to", "witnesses_verified"])
        for src_, lbl, dst, wits in EDGES:
            wr.writerow([src_, lbl.replace("\n", " "), dst,
                         len(wits) if wits is not None else "—"])

    A = ["# The decision procedure, drawn and executed\n",
         "Generated by `scripts/93_decision_flowchart.py`.\n",
         "A flowchart of an algorithm is a claim about the algorithm, and a "
         "drawing has no way to be wrong loudly. Every edge leading to an "
         "outcome therefore carries witnesses --- concrete inputs that must "
         "make `assess()` return it --- and all of them are executed before "
         "the figure is written.\n",
         f"- tests drawn: **{len(STEPS)}**",
         f"- outcome edges drawn: **{len(ok)}**",
         f"- witnesses executed against the live function: **{n_wit}**",
         "- mismatches: **0**\n",
         "## Why the order is the argument\n"]
    for _, q, why in STEPS:
        A.append(f"**{q.replace(chr(10), ' ')}**\n")
        A.append(why.replace("\n", " ") + "\n")
    EVAL.mkdir(parents=True, exist_ok=True)
    (EVAL / "decision_flowchart.md").write_text("\n".join(A) + "\n",
                                                encoding="utf-8")
    print(f"  fig15: {len(STEPS)} tests, {len(ok)} outcome edges, {n_wit} "
          f"witnesses verified against assess()")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
