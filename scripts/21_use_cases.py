#!/usr/bin/env python3
"""
What the vocabulary is FOR: seven questions, asked by whoever asks them.

WHY THIS IS NOT A LIST OF FEATURES
----------------------------------
The competency questions in queries/ are tied to axioms: each one exists to show
that a particular construct does work. That is the right test and it is the
wrong document to hand somebody deciding whether to adopt this. What they want
to know is which question they can ask on Monday that they cannot ask now.

So each scenario below is a real question, with the person who asks it, the
query that answers it, the answer from the shipped graph -- and, in every case,
WHAT A TWO-VALUED SCHEMA RETURNS INSTEAD. The last part is the point. A feature
list says CENSO has a class for undecidability; a scenario says the compliance
report a regulator signs off contains 304,836 verdicts that no measurement
supports, and here is the query that finds them.

Every number in the output is produced by running the query, not by quoting the
manuscript.

Inputs  : derived/abox/censo-waterbase.ttl, ontology/*.ttl, ontology/reg/*.ttl
Outputs : eval/use_cases.md

Usage:  python scripts/21_use_cases.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONTO = ROOT / "ontology"
ABOX = ROOT / "derived" / "abox" / "censo-waterbase.ttl"
EVAL = ROOT / "eval"

PREFIXES = """
PREFIX censo: <https://w3id.org/censo/>
PREFIX cereg: <https://w3id.org/censo/reg/>
PREFIX sosa:  <http://www.w3.org/ns/sosa/>
PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:   <http://www.w3.org/2002/07/owl#>
PREFIX xsd:   <http://www.w3.org/2001/XMLSchema#>
"""

# (id, who asks, the question, what a two-valued schema does instead, query,
#  how to read the answer)
CASES = [
    ("verdicts",
     "A competent authority preparing a status report",
     "How many of the verdicts in this report are not actually supportable, "
     "and for which reason each?",
     "Returns two columns, compliant and exceeding, and every undecidable row "
     "lands in one of them. Which one depends on the substitution constant the "
     "pipeline happened to use, and nothing in the output records that a "
     "choice was made.",
     """SELECT ?outcome (COUNT(?o) AS ?n) WHERE {
          ?o a ?outcome .
          VALUES ?outcome { censo:Compliant censo:Exceedance
                            censo:MethodInsufficient censo:PreconditionUnmet
                            censo:PossibleExceedance censo:BoundNotEstablished }
        } GROUP BY ?outcome ORDER BY DESC(?n)""",
     "Every row that is not Compliant or Exceedance is a verdict the record "
     "cannot support, and the class says why. That column does not exist in a "
     "two-valued schema, so those rows are silently counted as one of the "
     "other two."),

    ("undecidable_substances",
     "A laboratory manager choosing which methods to upgrade",
     "For which substances is my quantification limit above the legal "
     "standard, so that a clean 'not detected' still decides nothing?",
     "Reports these as compliant. The laboratory looks efficient and the "
     "substance looks clean, and the two facts have the same cause.",
     """SELECT ?substance (COUNT(?o) AS ?n) WHERE {
          ?o a censo:MethodInsufficient ;
             censo:hasAnalyte ?a .
          ?a rdfs:label ?substance .
        } GROUP BY ?substance ORDER BY DESC(?n) LIMIT 12""",
     "Ranked by how much of the record the defect costs. This is the list a "
     "method-development budget should be spent against, and it cannot be "
     "produced from a table of concentrations because the rows it names look "
     "like compliance."),

    ("affirmable",
     "An enforcement lawyer",
     "Show me only the exceedances I could defend: a quantified value above "
     "the standard, from a method that meets the legal performance criterion, "
     "with an interval that does not straddle the limit.",
     "Cannot express the question. Its exceedance count depends on the "
     "substitution rule, and it has no way to mark which exceedances rest on a "
     "measurement and which on a convention.",
     """SELECT (COUNT(?o) AS ?affirmable) WHERE {
          ?o a censo:Exceedance ; a censo:QuantifiedObservation .
        }""",
     "The affirmable count. A pipeline substituting half the limit reports "
     "many times this number over the same rows, and the difference is not "
     "measurement but convention."),

    ("substituted",
     "A data steward receiving a national submission",
     "Which rows tell me the result was below the limit and give me a positive "
     "number for it anyway?",
     "Sees only the number. The flag and the value sit in different columns "
     "and nothing relates them, so the contradiction is invisible unless "
     "somebody writes a bespoke script to look for it.",
     """SELECT (COUNT(?o) AS ?substituted) WHERE {
          ?o a censo:CensoredObservation ;
             censo:reportedValue ?v .
          FILTER (?v > 0)
        }""",
     "The substitution has already happened before anyone downloads the data. "
     "censo:CensoredObservationShape catches this as a published constraint "
     "rather than a one-off script, which is what makes it checkable by the "
     "party receiving the submission."),

    ("applicability",
     "An assessor asked whether a limit even applies here",
     "For this assessment, which conditions of the standard are satisfied, and "
     "which cannot be evaluated from what was reported?",
     "Has a threshold column with a number in it. There is nowhere to record "
     "that the standard is defined on a quantity nobody measured, so an "
     "inapplicable limit is applied and the verdict looks like any other.",
     """SELECT ?condition (COUNT(?o) AS ?n) WHERE {
          ?o censo:conditionSatisfied ?condition .
        } GROUP BY ?condition""",
     "Applicability is asserted, not assumed: the graph says which condition "
     "was met. Where a condition names a covariate the record does not report, "
     "the observation is censo:PreconditionUnmet instead, and the count above "
     "for that class is the size of that stratum."),

    ("why_this_one",
     "Anyone reading a single row and asking why it is undecidable",
     "Take one assessment that cannot be decided. What is the reason, in the "
     "graph, without reading the pipeline's source?",
     "Offers a verdict and no reason. To find out why, you read the code that "
     "produced it, if you have it.",
     """SELECT ?substance ?reason ?upper ?limit WHERE {
          ?o a censo:MethodInsufficient ;
             a censo:CensoredObservation ;
             censo:hasAnalyte ?a ;
             censo:resultUpperBound ?upper ;
             censo:assessableAgainst ?t .
          ?a rdfs:label ?substance .
          ?t censo:thresholdValue ?limit .
          BIND("the quantification limit exceeds the standard (Art. 3(3b))"
               AS ?reason)
        } LIMIT 5""",
     "The reason travels with the row. The upper bound is what the "
     "non-detection established and the threshold is what it had to decide; "
     "the first being above the second is the whole finding, and it is legible "
     "from the graph alone."),

    ("two_jurisdictions",
     "A basin authority on a border, or anyone comparing regimes",
     "The same measurement, under two regulations. Are they even talking about "
     "the same substance, and do they agree?",
     "Needs a name-matching script, and gets one verdict per run because the "
     "threshold is a column rather than a citable object.",
     """SELECT ?eu ?tr ?cas WHERE {
          { ?eu owl:sameAs ?tr } UNION { ?tr owl:sameAs ?eu }
          ?eu censo:casNumber ?cas .
          FILTER (STRSTARTS(STR(?eu), "https://w3id.org/censo/reg/analyte-eu-"))
          FILTER (STRSTARTS(STR(?tr), "https://w3id.org/censo/reg/analyte-tr-"))
        } ORDER BY ?cas LIMIT 8""",
     "The substances are reconciled by owl:sameAs in "
     "ontology/censo-alignment.ttl, so the comparison is an entailment rather "
     "than a string join across two spellings. Both packages can be loaded at "
     "once because each threshold cites the regulation that defines it, and "
     "two verdicts about two jurisdictions' thresholds are not a "
     "contradiction -- the disjointness is per observation-threshold pair."),
]


def main() -> int:
    try:
        import rdflib
    except ImportError:
        sys.exit("rdflib is required")
    if not ABOX.exists():
        sys.exit(f"missing {ABOX}; run scripts/23_waterbase_abox.py first")

    g = rdflib.Graph()
    t0 = time.time()
    files = [ONTO / "censo-core.ttl", ONTO / "censo-regulation.ttl", ABOX]
    files += sorted((ONTO / "reg").glob("*.ttl"))
    align = ONTO / "censo-alignment.ttl"
    if align.exists():
        files.append(align)
    for f in files:
        g.parse(f, format="turtle")
    load_s = time.time() - t0
    print(f"  loaded {len(g):,} triples in {load_s:.0f}s")

    A = ["# Seven questions the vocabulary exists to answer\n",
         "Generated by `scripts/21_use_cases.py`, by running each query "
         "against the shipped graph: `derived/abox/censo-waterbase.ttl` plus "
         "the vocabulary, both regulation packages and the alignment "
         f"({len(g):,} triples).\n",
         "**The counts are of the materialised graph, not of the "
         "population.** The knowledge graph is a 40,000-row reservoir sample "
         "with a fixed seed, because a pure-Python triple store cannot hold "
         "4.19 million station-years; the manuscript's headline figures are "
         "computed over every assessable row by "
         "`scripts/22_waterbase_external.py` and are larger. What these "
         "queries demonstrate is that the question is *askable* and what the "
         "answer looks like, not the size of the finding.\n",
         "The competency questions in `queries/` are tied to axioms — each "
         "shows that a construct works. This document answers a different "
         "question, the one somebody deciding whether to adopt this actually "
         "has: **what can I ask on Monday that I cannot ask now?** So every "
         "scenario names who asks it, and every scenario says what a "
         "two-valued schema returns instead. That contrast is the "
         "contribution; the class hierarchy is only how it is delivered.\n",
         "---\n"]

    for i, (cid, who, question, twovalued, q, reading) in enumerate(CASES, 1):
        print(f"  [{i}/{len(CASES)}] {cid} …", flush=True)
        t0 = time.time()
        try:
            rows = list(g.query(PREFIXES + q))
            err = None
        except Exception as e:                      # noqa: BLE001
            rows, err = [], f"{type(e).__name__}: {e}"
        dt = time.time() - t0

        A.append(f"## {i}. {question}\n")
        A.append(f"**Asked by:** {who}\n")
        A.append("```sparql")
        A.append(q.strip())
        A.append("```\n")
        if err:
            A.append(f"> query failed: `{err}`\n")
        elif not rows:
            A.append("> no rows. This is reported rather than hidden: a "
                     "scenario whose query returns nothing on the shipped "
                     "graph is a scenario the artefact does not yet "
                     "demonstrate.\n")
        else:
            vars_ = [str(v) for v in rows[0].labels] if hasattr(rows[0], "labels") \
                else [f"c{i}" for i in range(len(rows[0]))]
            A.append("| " + " | ".join(vars_) + " |")
            A.append("|" + "---|" * len(vars_))
            for r in rows[:12]:
                cells = []
                for v in r:
                    s = str(v) if v is not None else ""
                    s = s.rsplit("/", 1)[-1].rsplit("#", 1)[-1]
                    cells.append(s[:60])
                A.append("| " + " | ".join(cells) + " |")
            if len(rows) > 12:
                A.append(f"| … | {len(rows) - 12} more rows |"
                         + " |" * (len(vars_) - 2))
            A.append("")
        A.append(f"*{dt:.1f}s*\n")
        A.append(f"**What a two-valued schema returns instead.** {twovalued}\n")
        A.append(f"**Reading it.** {reading}\n")
        A.append("---\n")

    A.append("## What these have in common\n")
    A.append("None of the seven is answered by adding a column. Each needs the "
             "record to carry something a table of concentrations throws away: "
             "that a number is a bound rather than a measurement, that a "
             "threshold has conditions, that a verdict has a reason, or that "
             "two regulations name one substance. Where the information is "
             "gone, no estimator and no substitution rule recovers it — which "
             "is why the argument is about representation and not about "
             "statistics.\n")

    EVAL.mkdir(parents=True, exist_ok=True)
    (EVAL / "use_cases.md").write_text("\n".join(A) + "\n", encoding="utf-8")
    print("  wrote eval/use_cases.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
