#!/usr/bin/env python3
"""
Do the SHACL rules and the Python pipeline reach the same verdict?

WHY THIS EXISTS
---------------
The vocabulary ships a rule layer -- censo:IndeterminateRuleShape and its four
siblings -- that materialises a verdict and its reason from the record. The
analysis does not use it: every number in the manuscript comes from
scripts/22_waterbase_external.py::assess(), in Python, because a triple store
cannot hold four million rows. Two implementations of one decision procedure is
exactly the arrangement that drifts, and drift here would be invisible: the
rules would go on producing a defensible-looking verdict that nothing compared
against the one the paper reports.

A sampled check found them disagreeing on 46 of 1,200 observations.
censo:PreconditionRuleShape fired from ANY threshold of the analyte, so an
annual-average assessment of lead was set aside because the maximum-allowable
threshold of the same substance carries the bioavailability condition; three
further cases needed censo:conditionScreened, which records that a verdict
holds for every value the condition could take. Both are fixed. That check was
run by hand, once, and left no artefact -- which is the same defect as shipping
a commitment as prose, and this file is the repair.

WHAT IS COMPARED, AND OVER WHAT
-------------------------------
The ABox types each observation with the verdict the pipeline reached
(`a censo:MethodInsufficient`). pyshacl then materialises the rules over the
same graph, which types observations from the rules alone. A rule producing TWO
reasons where the pipeline records one is a disagreement, and was the defect
that motivated this: the wrong one of the two is the reason a reader would most
likely believe.

The rule layer does not cover every verdict, and comparing it as though it did
would report a disagreement for each of the 746 sampled observations the
pipeline resolves. Four rules ship, and all four construct a reason for
censo:IndeterminateCompliance; censo:Compliant, censo:Exceedance and
censo:PossibleExceedance follow from comparing a value with a threshold, which
the shapes do not do. So the comparison is:

  * where the pipeline reaches a reason the rules implement, the rules must
    reach the same one -- no miss, and no second reason alongside it;
  * where the pipeline reaches anything else, the rules must stay SILENT. A
    rule firing on an observation the pipeline found compliant is a
    disagreement, and the one direction a check restricted to rule output
    cannot see.

Which reasons those are is read out of the CONSTRUCT clauses rather than listed
here: a fifth rule added to the shapes joins the comparison on its own, and a
verdict the rules stop covering leaves it.

WHY A SAMPLE
------------
pyshacl materialises and validates in one superlinear pass -- 6,551 s over the
full graph. The sample is deterministic: observations sorted by IRI, every
k-th taken, so the same 1,200 are checked on every run and a disagreement can
be looked up by name. Everything that is NOT an observation stays in the graph,
because the rules reach the regulation through the analyte and a subsetted
package would make them fire differently than they do in the shipped artefact.

Outputs: eval/rule_agreement.md

Usage:  python scripts/18b_rule_agreement.py [--n 1200] [--abox PATH]
"""
from __future__ import annotations
import argparse, re, sys, time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"

try:
    import rdflib, pyshacl
except ImportError:
    sys.exit("requires rdflib and pyshacl")

CENSO = rdflib.Namespace("https://w3id.org/censo/")

# The verdict classes, which are what the two implementations must agree on.
# Read from the ontology rather than listed here: a sixth reason added to the
# vocabulary and to only one of the two implementations is precisely the drift
# this stage is for, and a hand-written list would hide it.
def verdict_classes(g):
    out = {CENSO.Compliant, CENSO.Exceedance, CENSO.IndeterminateCompliance}
    for s in g.subjects(rdflib.RDFS.subClassOf, CENSO.IndeterminateCompliance):
        out.add(s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--abox", default=None)
    ap.add_argument("--n", type=int, default=1200,
                    help="observations to sample (0 = all, hours)")
    args = ap.parse_args()
    EVAL.mkdir(parents=True, exist_ok=True)

    abox = (Path(args.abox) if args.abox
            else ROOT / "derived" / "abox" / "censo-waterbase.ttl")
    if not abox.exists():
        print(f"  no ABox at {abox.name}; skipping. Build it with "
              f"scripts/23_waterbase_abox.py.")
        return 0

    d = rdflib.Graph()
    d.parse(abox, format="turtle")
    d.parse(ROOT / "ontology" / "censo-core.ttl", format="turtle")
    d.parse(ROOT / "ontology" / "censo-regulation.ttl", format="turtle")
    for pkg in sorted((ROOT / "ontology" / "reg").glob("*.ttl")):
        d.parse(pkg, format="turtle")
    for t in list(d.triples((None, rdflib.OWL.imports, None))):
        d.remove(t)

    VERDICTS = verdict_classes(d)

    # The same closure stage 18 runs, and for the same reason: the shapes
    # target censo:AssessedObservation and the ABox types observations by
    # detection status. Without it the rules have no targets and this stage
    # would report perfect agreement over an empty set.
    sweep = True
    while sweep:
        sweep = False
        for sub, _, sup in list(d.triples((None, rdflib.RDFS.subClassOf, None))):
            if isinstance(sup, rdflib.term.BNode):
                continue
            for s_ in set(d.subjects(rdflib.RDF.type, sub)):
                if (s_, rdflib.RDF.type, sup) not in d:
                    d.add((s_, rdflib.RDF.type, sup))
                    sweep = True

    obs = sorted(set(d.subjects(rdflib.RDF.type, CENSO.AssessedObservation)),
                 key=str)
    if not obs:
        sys.exit("no censo:AssessedObservation in the graph")
    if args.n and args.n < len(obs):
        step = len(obs) / args.n
        keep = {obs[int(i * step)] for i in range(args.n)}
    else:
        keep = set(obs)

    # What the pipeline wrote, recorded BEFORE the rules run and then removed:
    # a rule that merely re-states a triple already in the graph has not been
    # tested. The comparison is between what the pipeline wrote and what the
    # rules reconstruct from the record alone.
    pipeline = {o: {c for c in d.objects(o, rdflib.RDF.type)
                    if c in VERDICTS} for o in keep}
    for o in keep:
        for c in pipeline[o]:
            d.remove((o, rdflib.RDF.type, c))
    # The observations that are not sampled leave the graph entirely.
    #
    # Dropping only their AssessedObservation type left them as targets of
    # every other shape, so pyshacl went on validating 40,000 observations to
    # check 200 of them and a trial run passed twenty minutes without
    # finishing. Nothing a rule reads is reached through another observation --
    # the regulation is reached through the analyte -- so removing them changes
    # what is checked not at all and what it costs by two orders of magnitude.
    n_drop = 0
    for o in obs:
        if o in keep:
            continue
        for tr in list(d.triples((o, None, None))):
            d.remove(tr)
            n_drop += 1
    print(f"  {len(keep):,} observation(s) kept, {n_drop:,} triple(s) of the "
          f"rest dropped")

    s = rdflib.Graph()
    s.parse(ROOT / "ontology" / "censo-shapes.ttl", format="turtle")

    # What the rules undertake to produce, read from their own CONSTRUCT
    # clauses. Anything outside this set is a verdict the rule layer does not
    # implement, and silence there is the correct answer rather than a miss.
    SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
    covered = set()
    for q in s.objects(None, SH.construct):
        head = str(q).split("CONSTRUCT", 1)[-1].split("WHERE", 1)[0]
        for name in re.findall(r"censo:(\w+)", head):
            if CENSO[name] in VERDICTS:
                covered.add(CENSO[name])
    if not covered:
        sys.exit("no verdict class is constructed by any rule; "
                 "the shapes have no rule layer to compare")

    t0 = time.perf_counter()
    pyshacl.validate(d, shacl_graph=s, advanced=True, inplace=True)
    dt = time.perf_counter() - t0

    rules = {o: {c for c in d.objects(o, rdflib.RDF.type) if c in VERDICTS}
             for o in keep}

    def names(cs):
        return ", ".join(sorted(str(c).rsplit("/", 1)[-1] for c in cs)) or "—"

    # The pipeline's verdict, expressed as what the rules should produce: the
    # same classes where the reason is one they implement, and nothing at all
    # where it is not.
    expected = {o: (v if (v - {CENSO.IndeterminateCompliance}) <= covered
                      and v & covered else set())
                for o, v in pipeline.items()}
    out_of_scope = sorted({names(v) for o, v in pipeline.items()
                           if v and not expected[o]})

    bad = sorted((o for o in keep if rules[o] != expected[o]), key=str)
    pat = Counter((names(pipeline[o]), names(rules[o])) for o in bad)

    L = ["# Do the rules and the pipeline agree?\n",
         "Generated by `scripts/18b_rule_agreement.py`.\n",
         "The manuscript's verdicts are computed in Python, by "
         "`scripts/22_waterbase_external.py::assess()`. The vocabulary also "
         "ships a rule layer that derives a verdict from the record. Two "
         "implementations of one decision procedure drift unless something "
         "compares them; this is that comparison.\n",
         f"- observations sampled: **{len(keep):,}** of {len(obs):,} "
         f"(1 in {max(1, len(obs) // max(1, len(keep)))}, by IRI)",
         f"- rule materialisation: {dt:.1f}\\,s",
         f"- verdicts the rules implement: "
         + ", ".join(f"`{str(c).rsplit('/', 1)[-1]}`"
                     for c in sorted(covered, key=str)),
         f"- verdicts they do not, where silence is the right answer: "
         + (", ".join(f"`{v}`" for v in out_of_scope) or "none"),
         f"- **disagreements: {len(bad):,}**\n"]
    if bad:
        L += ["| n | the pipeline says | the rules say |", "|---|---|---|"]
        L += [f"| {n:,} | {a} | {b} |" for (a, b), n in pat.most_common()]
        L += ["", "Named, so each can be looked up: "
              + ", ".join(str(o).rsplit("/", 1)[-1] for o in bad[:20])
              + ("…" if len(bad) > 20 else "")]
    else:
        L += ["Every sampled observation receives the same verdict from the "
              "rule layer that the pipeline recorded, reason subtype "
              "included. The rules reconstruct it from the record: the "
              "pipeline's own type assertions are removed from the graph "
              "before they run."]
        got = Counter(names(rules[o]) for o in keep)
        L += ["", "| verdict, from the rules alone | n |", "|---|---|"]
        L += [f"| {k} | {v:,} |" for k, v in got.most_common()]

    (EVAL / "rule_agreement.md").write_text("\n".join(L) + "\n",
                                            encoding="utf-8")
    print(f"  {len(keep):,} sampled, {len(bad):,} disagreement(s), {dt:.1f}s")
    print(f"  wrote eval/rule_agreement.md")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
