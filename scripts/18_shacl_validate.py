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
    UNIONS = {
        CENSO.DetectedObservation: [CENSO.EstimatedObservation,
                                    CENSO.QuantifiedObservation],
        CENSO.AssessedObservation: [CENSO.CensoredObservation,
                                    CENSO.EstimatedObservation,
                                    CENSO.QuantifiedObservation,
                                    CENSO.UnresolvedObservation],
    }
    n_union = 0
    for parent, members in UNIONS.items():
        for m in members:
            for s_ in set(d.subjects(rdflib.RDF.type, m)):
                if (s_, rdflib.RDF.type, parent) not in d:
                    d.add((s_, rdflib.RDF.type, parent))
                    n_union += 1
    n_sub = 0
    for sub, _, sup in list(d.triples((None, rdflib.RDFS.subClassOf, None))):
        if isinstance(sup, rdflib.term.BNode):
            continue
        for s_ in set(d.subjects(rdflib.RDF.type, sub)):
            if (s_, rdflib.RDF.type, sup) not in d:
                d.add((s_, rdflib.RDF.type, sup))
                n_sub += 1
    print(f"  materialised {n_union:,} union membership(s) and {n_sub:,} "
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
         "result, and this run reported exactly that until the two entailments "
         "below were materialised: the ABox types observations by their "
         "detection status, and `censo:AssessedObservation` is a defined class "
         "over a union, so no subclass axiom connects them and SHACL -- which "
         "does not reason -- saw no targets at all.\n",
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
