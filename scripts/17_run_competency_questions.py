#!/usr/bin/env python3
"""
Run the competency questions against the populated knowledge graph.

WHY
---
A competency question that has never been executed is a wish, not an
evaluation. Each question in queries/ is a SPARQL query; this script runs every
one over the real ABox built by scripts/15_build_abox.py, records the answer,
and fails loudly on any question that returns nothing -- an empty answer means
either the ontology cannot express the question or the data cannot support it,
and both need to be seen rather than glossed over.

REASONING
---------
Full OWL 2 RL closure over 618k triples is impractical in pure Python (see
eval/reasoning_benchmark.md), so rather than claim reasoning that was not run,
this script materialises exactly two things and states them in the report:

  * union memberships for the defined classes DetectedObservation and
    AssessedObservation;
  * rdfs:subClassOf entailment on type assertions -- without it, thresholds
    asserted as MaximumAllowableThreshold did not match `?t a censo:Threshold`
    and two questions returned nothing. Any triple store does this; omitting it
    was our oversight, not a limit of the ontology.

Nothing else is assumed: every remaining answer comes from asserted triples.

Inputs  : derived/abox/censo-waterbase.ttl, ontology/censo-core.ttl, queries/*.rq
Outputs : eval/competency_questions.md
          derived/processed/cq_results.csv

Usage:  python scripts/17_run_competency_questions.py [--abox FILE]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
Q = ROOT / "queries"
ABOX = ROOT / "derived" / "abox" / "censo-waterbase.ttl"
ONTO = ROOT / "ontology" / "censo-core.ttl"
REG = ROOT / "ontology" / "censo-regulation.ttl"
# The regulation PACKAGES carry the threshold individuals. rdflib does not
# follow owl:imports, so a graph built from the vocabularies alone contains no
# threshold at all -- which is why five competency questions about thresholds
# returned nothing while appearing to be about the ontology's expressiveness.
REG_PACKAGES = sorted((ROOT / "ontology" / "reg").glob("*.ttl"))
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

try:
    import rdflib
except ImportError:
    sys.exit("rdflib is required:  pip install rdflib")

CENSO = rdflib.Namespace("https://w3id.org/censo/")

# The only entailment we materialise, and only because the alternative is to
# claim reasoning we did not run.
UNIONS = {
    CENSO.DetectedObservation: [CENSO.EstimatedObservation,
                                CENSO.QuantifiedObservation],
    CENSO.AssessedObservation: [CENSO.CensoredObservation,
                                CENSO.EstimatedObservation,
                                CENSO.QuantifiedObservation,
                                CENSO.UnresolvedObservation],
}


def fmt(v) -> str:
    if v is None:
        return ""
    s = str(v)
    if s.startswith("https://w3id.org/censo/"):
        s = s.replace("https://w3id.org/censo/waterbase/", "")
        s = s.replace("https://w3id.org/censo/", "censo:")
    return s[:58]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--abox", default=str(ABOX))
    args = ap.parse_args()
    # Every output directory this stage writes to, created here rather
    # than assumed. On a fresh clone derived/processed/ does not exist,
    # and a stage that only made eval/ died on its first write -- a
    # failure invisible for as long as anyone's tree already had the
    # directory from an earlier run.
    EVAL.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)

    abox = Path(args.abox).resolve()
    if not abox.exists():
        # Skip, do not fail. The ABox is built by scripts/23_waterbase_abox.py
        # from the Waterbase download, so on a clone without it this stage has
        # no input -- the same position every other download-dependent stage is
        # in, and they are skipped.
        print(f"  no ABox at {abox.name}; skipping. Build it with "
              f"scripts/23_waterbase_abox.py, which needs the Waterbase "
              f"release. (15_build_abox.py belonged to the retired "
              f"single-basin survey and is in attic/.)")
        return 0

    print("loading …")
    g = rdflib.Graph()
    t0 = time.perf_counter()
    g.parse(ONTO, format="turtle")
    g.parse(REG, format="turtle")
    for pkg in REG_PACKAGES:
        g.parse(pkg, format="turtle")
    if REG_PACKAGES:
        print(f"  loaded {len(REG_PACKAGES)} regulation package(s): "
              f"{', '.join(p.stem for p in REG_PACKAGES)}")
    g.parse(abox, format="turtle")
    n_loaded = len(g)
    print(f"  {n_loaded:,} triples in {time.perf_counter()-t0:.1f}s")

    n_mat = 0
    for parent, children in UNIONS.items():
        for c in children:
            for s in g.subjects(rdflib.RDF.type, c):
                if (s, rdflib.RDF.type, parent) not in g:
                    g.add((s, rdflib.RDF.type, parent))
                    n_mat += 1

    # RDFS subclass entailment on type assertions. Two questions returned
    # nothing without it: thresholds are asserted as MaximumAllowableThreshold
    # and AnnualAverageThreshold, so `?t a censo:Threshold` matched nothing.
    # Any triple store performs this; not materialising it was our omission,
    # not a limit of the ontology. It is stated rather than assumed.
    parents = {}
    for c, _, sup in g.triples((None, rdflib.RDFS.subClassOf, None)):
        if isinstance(c, rdflib.URIRef) and isinstance(sup, rdflib.URIRef):
            parents.setdefault(c, set()).add(sup)

    def ancestors(c, seen=None):
        seen = seen or set()
        for p_ in parents.get(c, ()):
            if p_ not in seen:
                seen.add(p_)
                ancestors(p_, seen)
        return seen

    n_sub = 0
    for c in list(parents):
        anc = ancestors(c)
        if not anc:
            continue
        for inst in list(g.subjects(rdflib.RDF.type, c)):
            for a_ in anc:
                if (inst, rdflib.RDF.type, a_) not in g:
                    g.add((inst, rdflib.RDF.type, a_))
                    n_sub += 1

    print(f"  materialised {n_mat:,} union memberships and {n_sub:,} rdfs:subClassOf "
          f"type entailments (the only entailment assumed)")

    meta = json.loads((Q / "_index.json").read_text(encoding="utf-8")) \
        if (Q / "_index.json").exists() else {}

    rows, empties = [], []
    L = []
    A = L.append
    A("# Competency questions\n")
    A("Generated by `scripts/17_run_competency_questions.py`, executed over the "
      "populated knowledge graph.\n")
    A(f"- graph: `{abox.relative_to(ROOT) if ROOT in abox.parents else abox.name}` plus the two ontology modules, "
      f"**{n_loaded:,} triples as loaded**, {len(g):,} after the two "
      f"entailments below are materialised")
    A(f"- entailment materialised: {n_mat:,} union memberships "
      f"(`DetectedObservation`, `AssessedObservation`). Nothing else is "
      f"assumed; every other answer comes from asserted triples.\n")

    for f in sorted(Q.glob("cq*.rq")):
        cid = f.stem
        q = f.read_text(encoding="utf-8")
        info = meta.get(cid, {})
        question = info.get("question", "")
        axiom = info.get("axiom", "")

        t1 = time.perf_counter()
        try:
            res = list(g.query(q))
            err = None
        except Exception as e:
            res, err = [], f"{type(e).__name__}: {e}"
        dt = time.perf_counter() - t1

        A(f"## {cid.upper()} — {question}\n")
        A(f"*Exercises:* `{axiom}`\n")
        if err:
            A(f"**QUERY ERROR:** `{err}`\n")
            empties.append((cid, "error"))
        elif not res:
            A("**No results.** Either the ontology cannot express this question "
              "or the data cannot support it; both need explaining.\n")
            empties.append((cid, "empty"))
        else:
            cols = [str(v) for v in res.vars] if hasattr(res, "vars") else []
            if not cols and res:
                cols = [f"c{i}" for i in range(len(res[0]))]
            A("| " + " | ".join(cols) + " |")
            A("|" + "---|" * len(cols))
            for row in res[:12]:
                A("| " + " | ".join(fmt(v) for v in row) + " |")
            if len(res) > 12:
                A(f"| … | {len(res)-12} more rows | |"[:200])
            A("")
            A(f"<sub>{len(res)} row(s), {dt:.2f}s</sub>\n")

        rows.append({"cq": cid, "question": question, "axiom": axiom,
                     "rows": len(res), "seconds": round(dt, 3),
                     "error": err or ""})

    with (PROC / "cq_results.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    answered = sum(1 for r in rows if r["rows"] and not r["error"])
    summary = [
        "## Summary\n",
        f"- questions: **{len(rows)}**",
        f"- answered with at least one row: **{answered}**",
        f"- empty or failing: **{len(empties)}**",
        f"- total query time: {sum(r['seconds'] for r in rows):.1f}s\n",
    ]
    if empties:
        summary.append("Unanswered, and why they matter:\n")
        for cid, why in empties:
            summary.append(f"- `{cid}` ({why}) — {meta.get(cid, {}).get('question','')}")
        summary.append("")
    L = L[:5] + summary + L[5:]

    text = "\n".join(L)
    (EVAL / "competency_questions.md").write_text(text, encoding="utf-8")
    print("\n".join(summary))
    print(f"\nwrote: {EVAL/'competency_questions.md'}")
    return 1 if empties else 0


if __name__ == "__main__":
    raise SystemExit(main())
