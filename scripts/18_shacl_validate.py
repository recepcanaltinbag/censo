#!/usr/bin/env python3
"""
Validate the populated knowledge graph against the SHACL shapes.

Run over the Waterbase graph. pyshacl materialises as well as validates, so
the cost is superlinear; the sampled graph is the same one the competency
questions and the reported verdicts use, which is what makes this a check on
the artefact rather than on a convenient subset
of the survey and exercises every shape, which is what the shapes are for.

Every violation reported here is a defect in the source data or in our own
pipeline, not a modelling artefact -- that is the point of running it.

Outputs: eval/shacl_validation.md

Usage:  python scripts/18_shacl_validate.py [--abox PATH]
"""
from __future__ import annotations
import argparse, sys, time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"

try:
    import rdflib, pyshacl
except ImportError:
    sys.exit("requires rdflib and pyshacl")


CENSO = rdflib.Namespace("https://w3id.org/censo/")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--abox", default=None,
                    help="graph to validate; defaults to the Waterbase ABox")
    args = ap.parse_args()
    EVAL.mkdir(parents=True, exist_ok=True)

    abox = (Path(args.abox) if args.abox
            else ROOT / "derived" / "abox" / "censo-waterbase.ttl")
    if not abox.exists():
        # Skip, do not fail: the ABox comes from the Waterbase download, and a
        # stage with no input is skipped everywhere else in this pipeline.
        print(f"  no ABox at {abox.name}; skipping. Build it with "
              f"scripts/23_waterbase_abox.py.")
        return 0

    d = rdflib.Graph()
    d.parse(abox, format="turtle")
    d.parse(ROOT / "ontology" / "censo-core.ttl", format="turtle")
    # The regulation packages carry the thresholds. Three shapes target
    # censo:Threshold and none of them could bind without these.
    d.parse(ROOT / "ontology" / "censo-regulation.ttl", format="turtle")
    for pkg in sorted((ROOT / "ontology" / "reg").glob("*.ttl")):
        d.parse(pkg, format="turtle")
    for t in list(d.triples((None, rdflib.OWL.imports, None))):
        d.remove(t)

    # ---------------------------------------------------------------------
    #  THE SHAPES HAD NO TARGETS, AND THE RUN REPORTED "0 violations".
    #
    #  Two shapes target censo:AssessedObservation and three target
    #  censo:Threshold. The ABox types observations as CensoredObservation /
    #  QuantifiedObservation / UnresolvedObservation, and the packages type
    #  thresholds as AnnualAverageThreshold / MaximumAllowableThreshold.
    #
    #  AssessedObservation is a DEFINED class -- owl:equivalentClass over a
    #  union -- so no rdfs:subClassOf connects the members to it, and SHACL
    #  does not reason: a censored observation is not a SHACL instance of
    #  AssessedObservation unless something says so. Threshold fails for the
    #  simpler reason that the subclass axioms were never in the data graph.
    #
    #  So "conforms: True, 0 violations" was a search of an empty set, and the
    #  manuscript cited it as validation. The same two entailments stage 17
    #  materialises for the competency questions are materialised here, and the
    #  count of nodes each shape can now see is reported, so a target count of
    #  zero can never again be read as a clean bill of health.
    # ---------------------------------------------------------------------
    # This was a hand-written table of the two union-defined classes plus a
    # single pass over rdfs:subClassOf. Both are gone. The union definitions
    # were the axioms that put the vocabulary outside OWL 2 RL, and replacing
    # them with plain subclass assertions made the table a second copy of what
    # the ontology now states -- a copy that would go stale the next time a
    # status class is added.
    #
    # The single pass is gone for a separate reason: it was not a closure.
    # CensoredObservation is an AssessedObservation is a sosa:Observation, and
    # one pass over a snapshot of the triples completes that chain only if the
    # edges happen to be visited in the right order. Iterating to a fixed point
    # costs one extra sweep and is correct regardless.
    n_sub, sweep = 0, True
    while sweep:
        sweep = False
        for sub, _, sup in list(d.triples((None, rdflib.RDFS.subClassOf, None))):
            if isinstance(sup, rdflib.term.BNode):
                continue
            for s_ in set(d.subjects(rdflib.RDF.type, sub)):
                if (s_, rdflib.RDF.type, sup) not in d:
                    d.add((s_, rdflib.RDF.type, sup))
                    n_sub += 1
                    sweep = True
    print(f"  materialised {n_sub:,} "
          f"subclass type assertion(s) so the shapes have targets")

    s = rdflib.Graph()
    s.parse(ROOT / "ontology" / "censo-shapes.ttl", format="turtle")

    # What each shape can now see. A shape with zero targets is reported as
    # such: it is the difference between "nothing is wrong" and "nothing was
    # looked at".
    targets = {}
    for sh in set(s.subjects(rdflib.RDF.type, None)):
        for cls in s.objects(sh, rdflib.URIRef(
                "http://www.w3.org/ns/shacl#targetClass")):
            targets[str(cls)] = len(set(d.subjects(rdflib.RDF.type, cls)))
    for cls, n in sorted(targets.items(), key=lambda kv: -kv[1]):
        print(f"    target {cls.rsplit('/', 1)[-1]:26} {n:>7,} node(s)")
    empty = [c for c, n in targets.items() if not n]

    t0 = time.perf_counter()
    conforms, _, txt = pyshacl.validate(d, shacl_graph=s, advanced=True,
                                        inplace=False)
    dt = time.perf_counter() - t0
    msgs = Counter(l.split("Message:", 1)[1].strip()
                   for l in txt.splitlines() if "Message:" in l)

    L = [f"# SHACL validation of the knowledge graph\n",
         "Generated by `scripts/18_shacl_validate.py`.\n",
         f"- graph: `{abox.name}` plus the ontology, "
         f"**{len(d):,} triples**",
         f"- conforms: **{conforms}** ({dt:.1f}\\,s)",
         f"- distinct violation types: **{len(msgs)}**\n",
         "**What the shapes could see.** A validation that reports no "
         "violations over a graph in which the shapes match nothing is not a "
         "result, and this run reported exactly that until subclass type "
         "assertions were materialised below: the ABox types observations by "
         "their detection status, SHACL does not reason, and a shape targeting "
         "`censo:AssessedObservation` sees a `censo:CensoredObservation` only "
         "if something has drawn the connection. Until the OWL 2 RL repair "
         "that connection was a union definition, which no subclass axiom "
         "expressed and which this script had to special-case by hand; it is "
         "an ordinary `rdfs:subClassOf` now, so one closure covers it.\n",
         "| shape target | nodes |", "|---|---|"]
    L += [f"| `{c.rsplit('/', 1)[-1]}` | {n:,} |"
          for c, n in sorted(targets.items(), key=lambda kv: -kv[1])]
    L += [""]
    if empty:
        L += ["> **Targets still empty:** "
              + ", ".join(f"`{c.rsplit('/', 1)[-1]}`" for c in empty)
              + ". Those shapes were not exercised by this graph, and their "
                "silence is not evidence.\n"]
    if msgs:
        L += ["| n | message |", "|---|---|"]
        L += [f"| {c} | {m} |" for m, c in msgs.most_common()]
        L += ["", "Each is a defect in the source data or in this pipeline, "
                  "which is what the shapes exist to surface.\n"]
    text = "\n".join(L)
    (EVAL / "shacl_validation.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
