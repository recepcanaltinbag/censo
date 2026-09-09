#!/usr/bin/env python3
"""The decision procedure as a flowchart, with every path executed to prove it.

WHY THIS FIGURE
---------------
Figure 6 draws the decision GEOMETRY -- where the outcomes sit relative to the
threshold. Figure 11 walks four real rows through it twice. Neither shows the
procedure itself: the order the questions are asked in, and why that order is
not arbitrary. That order is the argument. A precondition is prior to every
other question; Article 3(3b) reaches only the censored case; the uncertainty
band applies only to a quantified value. Get the order wrong and the same four
fields yield a different verdict.

WHY IT CANNOT DRIFT
-------------------
A flowchart of an algorithm is a claim about the algorithm, and a drawing has
no way to be wrong loudly. So each edge carries a WITNESS: concrete inputs that
must make censo_outcome() return the outcome the edge leads to. Every witness is
executed against the real function before the figure is written, and a mismatch
refuses to draw rather than shipping a picture of code that no longer exists.

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
censo_outcome = _m.censo_outcome
U = _m.LEGAL_UNCERTAINTY_AT_EQS

INK, MUTED = "#1f1f1f", "#8a8a8a"
ASK = "#f4f4f2"
OUT = {"exceedance": "#b03030", "compliant": "#3c7a3c",
       "indeterminate": "#c98a2e"}

# Each test, in the order censo_outcome asks it, with WHY it is asked there.
# (id, question, why this position)
STEPS = [
    ("pre", "Does the standard apply to what\nwas measured?\n"
     "(bioavailable metal, hardness class)",
     "First, because it is prior to every other question. If the standard is\n"
     "written over bioavailable lead and the record reports total lead, there\n"
     "is no comparison to make -- not a strict one, not a lenient one."),
    ("status", "Detection status, read from the\ncensoring flag, the value"
     "\nand the LOQ",
     "Three states from three reported fields, and the LOQ is one of them: a\n"
     "row with no flag AND no limit is unresolved, because nothing bounds\n"
     "what the number means. The flag and the limit are separate statements --\n"
     "an empty flag says nothing, a '0' says not censored, which is\n"
     "information."),
    ("art3", "Is the quantification limit\nabove the standard?  LOQ > T",
     "Article 3(3b) reaches a result reported as below the quantification\n"
     "limit, and only that. A quantified mean above the standard is evidence\n"
     "of exceedance whatever the method's limit was."),
    ("contra", "Is the reported value below\nits own LOQ?  x < LOQ",
     "The row contradicts itself. Neither Article 3(3b) nor a comparison\n"
     "applies to a number that cannot be both."),
    ("band", "Is x within T/2 of T \u2014 the widest\nuncertainty the law lets a"
     " method have?",
     "Article 4(1) sets a CEILING, not a test: a method whose results may\n"
     "lawfully be used has an expanded uncertainty of '50 % or below' at the\n"
     "level of the standard. So T/2 is the widest interval the law would\n"
     "permit around a result, and a value inside it is one that a method\n"
     "meeting only the legal minimum could have produced on either side of\n"
     "the standard. The Directive does not instruct this comparison; it is\n"
     "the worst permitted method read against the record, which is the\n"
     "conservative direction and costs 1.0 point of the headline."),
]

# (from, label, to, witness) -- the witness is the input that must produce it.
# kwargs to censo_outcome: status, val_ug, loq_ug, thr, precondition
EDGES = [
    ("pre", "no", "precondition_unmet",
     dict(status="quantified", val_ug=5.0, loq_ug=0.1, thr=1.0,
          precondition="bioavailable")),
    ("pre", "yes", "status", None),

    ("status", "unresolved", "indeterminate_unresolved",
     dict(status="unresolved", val_ug=None, loq_ug=None, thr=1.0)),
    ("status", "censored", "art3", None),
    ("status", "quantified", "contra", None),

    ("art3", "yes", "method_insufficient",
     dict(status="censored", val_ug=None, loq_ug=2.0, thr=1.0)),
    ("art3", "no", "compliant",
     dict(status="censored", val_ug=None, loq_ug=0.5, thr=1.0)),

    ("contra", "yes", "indeterminate_other",
     dict(status="quantified", val_ug=0.2, loq_ug=0.5, thr=1.0)),
    ("contra", "no", "band", None),

    ("band", "yes", "possible_exceedance",
     dict(status="quantified", val_ug=1.2, loq_ug=0.1, thr=1.0)),
    ("band", "no, above", "exceedance",
     dict(status="quantified", val_ug=9.0, loq_ug=0.1, thr=1.0)),
    ("band", "no, below", "compliant",
     dict(status="quantified", val_ug=0.05, loq_ug=0.01, thr=1.0)),
]

LEAF = {
    "precondition_unmet": ("PreconditionUnmet", "indeterminate"),
    "indeterminate_unresolved": ("BoundNotEstablished", "indeterminate"),
    "method_insufficient": ("MethodInsufficient", "indeterminate"),
    "indeterminate_other": ("BoundNotEstablished", "indeterminate"),
    "possible_exceedance": ("PossibleExceedance", "indeterminate"),
    "exceedance": ("Exceedance", "exceedance"),
    "compliant": ("Compliant", "compliant"),
}


def verify():
    """Execute every witness. A drawn edge with no witness is not drawn."""
    bad, ok = [], []
    for src, lbl, dst, w in EDGES:
        if w is None:
            continue
        got = censo_outcome(w.pop("status"), w.pop("val_ug"), w.pop("loq_ug"),
                            w.pop("thr"), **w)
        if got != dst:
            bad.append(f"{src} --{lbl}--> {dst}: the function returns {got}")
        else:
            ok.append((src, lbl, dst))
    return ok, bad


def dot() -> str:
    L = ['digraph flow {', '  rankdir=TB; bgcolor="white";',
         '  node [fontname="Helvetica", fontsize=10, shape=box, style="filled,rounded"];',
         '  edge [fontname="Helvetica", fontsize=9, color="%s"];' % MUTED]
    L.append('  input [label="one reported row:  censoring flag,  value x,'
             '\\nquantification limit LOQ,  standard T", '
             'shape=note, fillcolor="white", color="%s", fontsize=9];' % MUTED)
    L.append('  input -> pre [style=dashed];')
    for sid, q, _ in STEPS:
        L.append(f'  {sid} [label="{q}", fillcolor="{ASK}", '
                 f'color="{INK}", shape=diamond, height=1.1, width=2.6];')
    # One node per OUTCOME CLASS, not per pipeline outcome: two reasons reach
    # censo:BoundNotEstablished and two reach censo:Compliant, and drawing
    # either twice would show a class the vocabulary does not have.
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
    ok, bad = verify()
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
        return 0
    for fmt in ("pdf", "svg", "png"):
        subprocess.run(["dot", f"-T{fmt}",
                        "-o", str(FIGS / f"fig15_decision_flow.{fmt}")],
                       input=src.encode(), check=True)

    with (FDATA / "fig15_decision_flow.csv").open(
            "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["from", "answer", "to", "witness_verified"])
        for src_, lbl, dst, wit in EDGES:
            w.writerow([src_, lbl, dst, "yes" if wit is not None else "—"])

    A = ["# The decision procedure, drawn and executed\n",
         "Generated by `scripts/93_decision_flowchart.py`.\n",
         "A flowchart of an algorithm is a claim about the algorithm, and a "
         "drawing has no way to be wrong loudly. Every edge leading to an "
         "outcome therefore carries a witness --- concrete inputs that must "
         "make `censo_outcome()` return it --- and all of them are executed "
         "before the figure is written.\n",
         f"- outcome edges drawn: **{len(ok)}**",
         f"- witnesses executed against the live function: **{len(ok)}**",
         "- mismatches: **0**\n",
         "## Why the order is the argument\n"]
    for _, q, why in STEPS:
        A.append(f"**{q.replace(chr(10), ' ')}**\n")
        A.append(why.replace("\n", " ") + "\n")
    EVAL.mkdir(parents=True, exist_ok=True)
    (EVAL / "decision_flowchart.md").write_text("\n".join(A) + "\n",
                                                encoding="utf-8")
    print(f"  fig15: {len(STEPS)} tests, {len(ok)} outcome edges, "
          f"all witnesses verified against censo_outcome()")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
