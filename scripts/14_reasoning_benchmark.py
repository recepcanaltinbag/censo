#!/usr/bin/env python3
"""
Reasoning cost of CENSO as the knowledge graph grows.

WHY
---
An ontology paper that reports no reasoning cost invites the assumption that it
was never run at scale. This measures the OWL 2 RL deductive closure and the
SHACL validation over synthetic ABoxes of increasing size, on the same
vocabulary used in the study.

WHAT IS MEASURED
----------------
For each ABox size n (observations):
  * triples in, triples entailed by the RL closure, and wall-clock time
  * SHACL validation time and conformance
Both engines are pure Python (owlrl, pyshacl), so the figures describe the
configuration a reader can reproduce without a JVM.

WHAT THIS IS NOT
----------------
Not a claim that CENSO scales to arbitrary size, and not a comparison against
a native triple store. RL closure is materialising; a production deployment
would use a store with rule support. The point is to state the cost honestly
for the configuration described in the paper.

Outputs: derived/processed/reasoning_benchmark.csv
         eval/reasoning_benchmark.md

Usage:  python scripts/14_reasoning_benchmark.py [--sizes 50,100,200,400,800]
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONTO = ROOT / "ontology"
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

try:
    import rdflib
    import owlrl
except ImportError:
    sys.exit("requires rdflib and owlrl:  pip install rdflib owlrl")

PREFIX = """@prefix censo: <https://w3id.org/censo/> .
@prefix ex:    <https://example.org/bench/> .
@prefix owl:   <http://www.w3.org/2002/07/owl#> .
@prefix rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .
@prefix sosa:  <http://www.w3.org/ns/sosa/> .
@prefix qudt:  <http://qudt.org/schema/qudt/> .
"""

FIXTURE = """
ex:ugPerL a qudt:Unit .
ex:reg    a censo:Regulation .
"""


def abox(n: int) -> str:
    """A well-formed ABox: n observations over n/10 analytes and 4 campaigns.

    Deliberately consistent -- we are measuring the cost of classifying a
    correct graph, not of detecting a clash, which short-circuits.
    """
    out = [FIXTURE]
    n_analyte = max(1, n // 10)
    for a in range(n_analyte):
        out.append(f"""
ex:analyte{a} a censo:Analyte .
ex:method{a} a censo:AnalyticalMethod ;
    censo:limitOfDetection "0.02"^^xsd:decimal ;
    censo:limitOfQuantification "0.06"^^xsd:decimal ;
    censo:limitUnit ex:ugPerL ;
    censo:determinesAnalyte ex:analyte{a} .
ex:thr{a} a censo:MaximumAllowableThreshold ;
    censo:thresholdValue "0.5"^^xsd:decimal ;
    censo:thresholdUnit ex:ugPerL ;
    censo:definedBy ex:reg ;
    censo:appliesToAnalyte ex:analyte{a} .""")
    for c in range(4):
        out.append(f"ex:camp{c} a censo:Campaign .")
    for i in range(n):
        a, c = i % n_analyte, i % 4
        st = i // 4
        # alternate censored and quantified so both branches are exercised
        if i % 3 == 0:
            cls, lo, hi = "censo:CensoredObservation", "0.0", "0.02"
            extra = ""
        else:
            cls, lo, hi = "censo:QuantifiedObservation", "0.80", "0.90"
            extra = f" ;\n    censo:exceeds ex:thr{a}"
        out.append(f"""
ex:st{st} a sosa:FeatureOfInterest .
ex:obs{i} a sosa:Observation , {cls} ;
    censo:hasAnalyte ex:analyte{a} ;
    censo:atStation ex:st{st} ;
    censo:duringCampaign ex:camp{c} ;
    sosa:usedProcedure ex:method{a} ;
    censo:resultLowerBound "{lo}"^^xsd:decimal ;
    censo:resultUpperBound "{hi}"^^xsd:decimal{extra} .""")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="50,100,200,400,800")
    args = ap.parse_args()
    # Every output directory this stage writes to, created here rather
    # than assumed. On a fresh clone derived/processed/ does not exist,
    # and a stage that only made eval/ died on its first write -- a
    # failure invisible for as long as anyone's tree already had the
    # directory from an earlier run.
    EVAL.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)
    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]

    core = ONTO / "censo-core.ttl"
    shapes = ONTO / "censo-shapes.ttl"
    if not core.exists():
        sys.exit(f"missing {core}")

    shapes_graph = None
    have_shacl = False
    try:
        import pyshacl                                   # noqa: F401
        have_shacl = shapes.exists()
        if have_shacl:
            shapes_graph = rdflib.Graph()
            shapes_graph.parse(shapes, format="turtle")
    except ImportError:
        pass

    rows = []
    for n in sizes:
        g = rdflib.Graph()
        g.parse(core, format="turtle")
        g.parse(data=PREFIX + abox(n), format="turtle")
        for tr in list(g.triples((None, rdflib.OWL.imports, None))):
            g.remove(tr)                                 # offline, deterministic
        n_in = len(g)

        t0 = time.perf_counter()
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False,
                               datatype_axioms=False).expand(g)
        t_rl = time.perf_counter() - t0
        n_out = len(g)

        t_shacl, conforms = None, None
        if have_shacl:
            import pyshacl
            data = rdflib.Graph()
            data.parse(core, format="turtle")
            data.parse(data=PREFIX + abox(n), format="turtle")
            for tr in list(data.triples((None, rdflib.OWL.imports, None))):
                data.remove(tr)
            t1 = time.perf_counter()
            conforms, _, _ = pyshacl.validate(data, shacl_graph=shapes_graph,
                                              advanced=True, inplace=False)
            t_shacl = time.perf_counter() - t1

        rows.append({
            "observations": n,
            "triples_asserted": n_in,
            "triples_after_closure": n_out,
            "triples_entailed": n_out - n_in,
            "rl_closure_seconds": round(t_rl, 3),
            "shacl_seconds": None if t_shacl is None else round(t_shacl, 3),
            "shacl_conforms": conforms,
        })
        print(f"  n={n:5d}  asserted={n_in:7d}  entailed={n_out-n_in:8d}  "
              f"RL={t_rl:7.2f}s" +
              (f"  SHACL={t_shacl:6.2f}s conforms={conforms}"
               if t_shacl is not None else ""))

    with (PROC / "reasoning_benchmark.csv").open("w", newline="",
                                                 encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    L = []
    A = L.append
    A("# Reasoning cost\n")
    A("Generated by `scripts/14_reasoning_benchmark.py`. OWL 2 RL deductive "
      "closure via `owlrl` and SHACL validation via `pyshacl`, both pure "
      "Python, over synthetic but well-formed ABoxes on the CENSO "
      "vocabulary.\n")
    A("| observations | triples asserted | entailed | RL closure (s) | SHACL (s) | conforms |")
    A("|---|---|---|---|---|---|")
    for r in rows:
        A(f"| {r['observations']:,} | {r['triples_asserted']:,} | "
          f"{r['triples_entailed']:,} | {r['rl_closure_seconds']} | "
          f"{r['shacl_seconds'] if r['shacl_seconds'] is not None else '—'} | "
          f"{r['shacl_conforms'] if r['shacl_conforms'] is not None else '—'} |")
    A("")
    if len(rows) >= 2:
        a_, b_ = rows[0], rows[-1]
        fx = b_["observations"] / max(a_["observations"], 1)
        ft = b_["rl_closure_seconds"] / max(a_["rl_closure_seconds"], 1e-9)
        A(f"Between the smallest and largest ABox the observation count grows "
          f"{fx:.0f}-fold and closure time {ft:.0f}-fold, so the cost is "
          f"{'super-linear' if ft > fx * 1.5 else 'roughly linear'} in this "
          f"range.\n")
    A("## Honest reading\n")
    A("RL closure is materialising: every entailment is written into the graph, "
      "so memory and time grow with the entailed set, not merely with the "
      "asserted one. This is the right configuration for a reproducible, "
      "JVM-free pipeline and it is what the reported figures describe. A "
      "production deployment over a full basin would use a triple store with "
      "native rule support rather than in-memory materialisation, and these "
      "numbers should not be read as a limit on the approach.\n")

    text = "\n".join(L)
    (EVAL / "reasoning_benchmark.md").write_text(text, encoding="utf-8")
    print("\n" + text)
    print(f"\nwrote: {EVAL/'reasoning_benchmark.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
