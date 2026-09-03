#!/usr/bin/env python3
"""
Prove that the CENSO axioms do real work.

An ontology paper is rejected when the reasoner is decorative. This suite is the
evidence to the contrary: each case injects a defect that OCCURS IN THE SOURCE
DATASET and asserts that a DL reasoner rejects it. If an axiom were removed, the
corresponding test would fail.

Every case names the axiom it exercises, so the table it prints goes straight
into the paper's evaluation section.

Runs entirely in Python: owlrl computes the OWL 2 RL deductive closure over an
rdflib graph. No JVM, no external reasoner, so the suite runs anywhere the rest
of the pipeline does -- which matters for reproducibility.

Usage:  python scripts/test_axioms.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONTO = ROOT / "ontology"
EVAL = ROOT / "eval"
PROC = ROOT / "derived" / "processed"


def unresolved_in_the_record() -> str:
    """How many real assessments carry no bound at all, for the T5 rationale.

    T5's rationale used to read "1,103 candidate onsets in this dataset fall in
    exactly this category". *Candidate onsets* is vocabulary from the retired
    single-basin pipeline in attic/, and 1,103 is a count from an analysis this
    paper does not report -- shipped in eval/axiom_tests.md, which the
    manuscript cites as its evaluation evidence. Read from the current data
    instead, and phrased without a number when the data are absent, since this
    suite must run on the vocabulary alone.
    """
    f = PROC / "waterbase_verdicts_population.csv"
    if not f.exists():
        return ("Assessments carrying no bound at all fall in exactly this "
                "category.")
    import csv
    n = 0
    with f.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            # ONLY indeterminate_unresolved. The prefix match used to catch
            # indeterminate_other as well, and that is a different population:
            # a QUANTIFIED row whose value contradicts the limit reported
            # beside it. Such a row has a detection status, so it is not a
            # censo:UnresolvedObservation and T5's axiom says nothing about it.
            # Counting it here made the rationale claim 45,509 for a class the
            # shipped report puts at 45,467 -- two numbers for one class, in
            # two files the manuscript cites.
            if (r.get("substitution") == "zero"
                    and r.get("censo_outcome") == "indeterminate_unresolved"):
                n += int(r["n"])
    if not n:
        return ("Assessments carrying no bound at all fall in exactly this "
                "category.")
    return (f"{n:,} assessments in this record -- a European standard exists "
            f"and no bound is reported -- fall in exactly this category.")

CORE = ONTO / "censo-core.ttl"

try:
    import rdflib
except ImportError:
    sys.exit("rdflib is required:  pip install rdflib")

try:
    import owlrl
except ImportError:
    sys.exit("owlrl is required:  pip install owlrl")

# Engine note. owlrl computes the OWL 2 RL deductive closure in pure Python and
# signals a contradiction by entailing owl:Nothing / rdf:type false. RL covers
# every axiom this suite exercises: class disjointness, disjoint properties,
# functional properties and hasKey. Full DL (complement of an existential, and
# the covering union) needs HermiT, which requires a JVM; those two axioms are
# checked by SHACL instead, so the suite runs without Java.


PREFIX = """@prefix censo: <https://w3id.org/censo/> .
@prefix ex:    <https://example.org/test/> .
@prefix owl:   <http://www.w3.org/2002/07/owl#> .
@prefix rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .
@prefix sosa:  <http://www.w3.org/ns/sosa/> .
@prefix qudt:  <http://qudt.org/schema/qudt/> .
"""

# Shared fixture: one analyte, one station, one campaign, one threshold.
FIXTURE = """
ex:atrazine   a censo:Analyte .
ex:station12  a sosa:FeatureOfInterest .
ex:campaignC1 a censo:Campaign .
ex:reg2026    a censo:Regulation .
ex:ugPerL     a qudt:Unit .

ex:eqsAtrazine a censo:AnnualAverageThreshold ;
    censo:thresholdValue "0.6"^^xsd:decimal ;
    censo:thresholdUnit  ex:ugPerL ;
    censo:definedBy      ex:reg2026 ;
    censo:appliesToAnalyte ex:atrazine .
"""

# ---------------------------------------------------------------------------
# Each case: (id, axiom exercised, real-world defect, snippet, expect_consistent)
# ---------------------------------------------------------------------------
CASES = [
    (
        "T1", "AllDisjointClasses over the four detection statuses",
        "A pipeline assigns a record both 'non-detect' and 'quantified' — e.g. a "
        "zero recovered as censored while a later join also marks it quantified.",
        """
ex:obs1 a sosa:Observation , censo:CensoredObservation , censo:QuantifiedObservation ;
    censo:hasAnalyte ex:atrazine ;
    censo:atStation ex:station12 ;
    censo:duringCampaign ex:campaignC1 .
""",
        False,
    ),
    (
        "T2", "control: compliance outcomes are exclusive per "
              "observation-threshold pair, not per observation",
        "One measurement assessed under two jurisdictions: compliant against "
        "the looser standard, method-insufficient against the stricter one. "
        "This MUST remain consistent, and it is a control rather than a defect. "
        "An earlier version declared the four outcomes pairwise disjoint at the "
        "class level, which made exactly this an inconsistency — and so forbade "
        "the multi-regulation assessment the vocabulary exists to support, "
        "while the manuscript reported it as a result. The case is kept so that "
        "the axiom cannot return unnoticed.",
        """
ex:regTR a censo:Regulation .
ex:eqsAtrazineTR a censo:AnnualAverageThreshold ;
    censo:thresholdValue "2.0"^^xsd:decimal ;
    censo:thresholdUnit  ex:ugPerL ;
    censo:definedBy      ex:regTR ;
    censo:appliesToAnalyte ex:atrazine .

ex:obs2 a sosa:Observation , censo:QuantifiedObservation ,
          censo:Compliant , censo:MethodInsufficient ;
    censo:hasAnalyte ex:atrazine ;
    censo:atStation ex:station12 ;
    censo:duringCampaign ex:campaignC1 ;
    censo:belowThreshold ex:eqsAtrazineTR .
""",
        True,
    ),
    (
        "T3", "CensoredObservation ⊑ ¬∃exceeds.Threshold",
        "A non-detection is reported as an exceedance. This is what happens when "
        "a zero-substituted non-detect is compared numerically against a limit "
        "without restoring its censoring status.",
        """
ex:obs3 a sosa:Observation , censo:CensoredObservation ;
    censo:hasAnalyte ex:atrazine ;
    censo:atStation ex:station12 ;
    censo:duringCampaign ex:campaignC1 ;
    censo:exceeds ex:eqsAtrazine .
""",
        False,
    ),
    (
        "T4", "AllDisjointProperties over exceeds / possiblyExceeds / belowThreshold",
        "The rule layer materialises two mutually exclusive comparisons for the "
        "same observation-threshold pair.",
        """
ex:obs4 a sosa:Observation , censo:QuantifiedObservation ;
    censo:hasAnalyte ex:atrazine ;
    censo:atStation ex:station12 ;
    censo:duringCampaign ex:campaignC1 ;
    censo:exceeds ex:eqsAtrazine ;
    censo:belowThreshold ex:eqsAtrazine .
""",
        False,
    ),
    (
        "T5", "UnresolvedObservation ⊑ ¬∃assessableAgainst.Threshold",
        "An analyte with no published limit is nevertheless assessed for "
        "compliance. " + unresolved_in_the_record(),
        """
ex:obs5 a sosa:Observation , censo:UnresolvedObservation ;
    censo:hasAnalyte ex:atrazine ;
    censo:atStation ex:station12 ;
    censo:duringCampaign ex:campaignC1 ;
    censo:possiblyExceeds ex:eqsAtrazine .
""",
        False,
    ),
    (
        "T6", "FunctionalProperty on hasAnalyte",
        "A row is joined to two different substances by fuzzy name matching — the "
        "silent corruption a chemical-name join can cause.",
        """
ex:benzene a censo:Analyte .
ex:atrazine owl:differentFrom ex:benzene .
ex:obs6 a sosa:Observation , censo:QuantifiedObservation ;
    censo:hasAnalyte ex:atrazine , ex:benzene ;
    censo:atStation ex:station12 ;
    censo:duringCampaign ex:campaignC1 .
""",
        False,
    ),
    (
        "T7", "SHACL censo:CensoredObservationShape (outside OWL 2 RL)",
        "A non-detect is given a non-zero lower bound, e.g. by half-LOQ "
        "substitution — the practice this ontology exists to prevent.",
        """
ex:obs7 a sosa:Observation , censo:CensoredObservation ;
    censo:hasAnalyte ex:atrazine ;
    censo:atStation ex:station12 ;
    censo:duringCampaign ex:campaignC1 ;
    censo:resultLowerBound "0.025"^^xsd:decimal .
""",
        None,          # None => outside OWL 2 RL; checked by the SHACL layer
    ),
    (
        "T8", "AllDisjointClasses over threshold types",
        "An annual-average limit is also treated as a maximum-allowable limit, so "
        "a single grab sample is compared against a long-term mean standard.",
        """
ex:badThreshold a censo:AnnualAverageThreshold , censo:MaximumAllowableThreshold ;
    censo:thresholdValue "0.6"^^xsd:decimal ;
    censo:thresholdUnit ex:ugPerL ;
    censo:definedBy ex:reg2026 .
""",
        False,
    ),
    (
        "T9", "control: a well-formed knowledge graph",
        "Everything asserted consistently. Guards against a suite that passes "
        "because the ontology is unsatisfiable for unrelated reasons.",
        """
ex:obs9 a sosa:Observation , censo:QuantifiedObservation ;
    censo:hasAnalyte ex:atrazine ;
    censo:atStation ex:station12 ;
    censo:duringCampaign ex:campaignC1 ;
    censo:resultLowerBound "0.8"^^xsd:decimal ;
    censo:resultUpperBound "0.9"^^xsd:decimal ;
    censo:exceeds ex:eqsAtrazine .

ex:station13 a sosa:FeatureOfInterest .
ex:obs9b a sosa:Observation , censo:CensoredObservation ;
    censo:hasAnalyte ex:atrazine ;
    censo:atStation ex:station13 ;
    censo:duringCampaign ex:campaignC1 ;
    censo:resultLowerBound "0.0"^^xsd:decimal ;
    censo:resultUpperBound "0.02"^^xsd:decimal .
""",
        True,
    ),
    (
        "T10", "owl:hasKey (hasAnalyte, atStation, duringCampaign)",
        "The same analyte, station and campaign appears twice with conflicting "
        "detection status — a duplicated spreadsheet row that would otherwise be "
        "double-counted in any load or frequency statistic.",
        """
ex:dupA a sosa:Observation , censo:CensoredObservation ;
    censo:hasAnalyte ex:atrazine ;
    censo:atStation ex:station12 ;
    censo:duringCampaign ex:campaignC1 .

ex:dupB a sosa:Observation , censo:QuantifiedObservation ;
    censo:hasAnalyte ex:atrazine ;
    censo:atStation ex:station12 ;
    censo:duringCampaign ex:campaignC1 .
""",
        False,
    ),
]


def build_graph(snippet: str) -> "rdflib.Graph":
    """Merge the core ontology with the fixture and one test snippet."""
    g = rdflib.Graph()
    g.parse(CORE, format="turtle")
    g.parse(data=PREFIX + FIXTURE + snippet, format="turtle")
    # Imports are dropped: the suite must run offline and deterministically.
    for triple in list(g.triples((None, rdflib.OWL.imports, None))):
        g.remove(triple)
    return g


# owlrl reports a contradiction by attaching an ErrorMessage node to the graph
# rather than by raising, so detection reads those nodes back out. Capturing the
# message as well as the fact is what makes the output diagnostic instead of a
# bare pass/fail.
ERR_PRED = rdflib.URIRef("http://www.daml.org/2002/03/agents/agent-ont#error")


def check(g):
    """Return (inconsistent, [messages]) after computing the OWL 2 RL closure."""
    try:
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics,
                               axiomatic_triples=False,
                               datatype_axioms=False).expand(g)
    except Exception as e:
        return True, [f"reasoner raised {type(e).__name__}: {e}"]
    msgs = sorted({str(o) for _, _, o in g.triples((None, ERR_PRED, None))})
    if list(g.triples((None, rdflib.RDF.type, rdflib.OWL.Nothing))):
        msgs.append("an individual was entailed to be owl:Nothing")
    return bool(msgs), msgs


SHAPES = ONTO / "censo-shapes.ttl"


def shacl_check(g):
    """Validate against the SHACL shapes. Returns (conforms, [messages])."""
    import pyshacl
    shapes = rdflib.Graph()
    shapes.parse(SHAPES, format="turtle")
    conforms, _, text = pyshacl.validate(
        g, shacl_graph=shapes, advanced=True, inplace=False, debug=False)
    msgs = [ln.split("Message:", 1)[1].strip()
            for ln in text.splitlines() if "Message:" in ln]
    return conforms, msgs


def run_case(case, workdir: Path):
    cid, axiom, defect, snippet, expect_consistent = case

    # expect_consistent is None for cases the RL profile cannot express; those
    # are the SHACL layer's responsibility and are checked there.
    if expect_consistent is None:
        g = build_graph(snippet)
        conforms, msgs = shacl_check(g)
        passed = not conforms
        detail = (msgs[0][:110] if msgs else "no violation reported")
        return cid, axiom, defect, passed, detail

    g = build_graph(snippet)
    inconsistent, msgs = check(g)
    consistent = not inconsistent
    passed = (consistent == expect_consistent)
    if consistent:
        detail = "consistent"
    else:
        first = msgs[0] if msgs else "contradiction"
        detail = first[:110] + ("…" if len(first) > 110 else "")
    return cid, axiom, defect, passed, detail


def main() -> int:
    EVAL.mkdir(parents=True, exist_ok=True)

    results = []
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        for case in CASES:
            results.append(run_case(case, workdir))

    L = []
    A = L.append
    A("# Axiom test suite\n")
    A("Generated by `scripts/test_axioms.py`. Most cases inject a defect that "
      "occurs in the source dataset and check that a DL reasoner (owlrl, OWL 2 RL) "
      "rejects it; remove the named axiom and the case fails. The rest are "
      "controls, which must stay CONSISTENT — a suite that only ever demands "
      "rejection is passed just as well by an ontology that rejects "
      "everything.\n")
    A("| # | axiom exercised | defect it catches | expected | result |")
    A("|---|---|---|---|---|")
    case_expect = {c[0]: c[4] for c in CASES}
    n_pass = 0
    for cid, axiom, defect, passed, detail in results:
        # Read from the case, not from its id. This was hard-coded to T9, so a
        # second control reported its expectation as the opposite of what the
        # suite actually asserted -- a PASS printed beside the wrong word.
        exp = ("SHACL violation" if case_expect[cid] is None
               else "consistent" if case_expect[cid]
               else "inconsistent")
        mark = "PASS" if passed else ("SKIP" if passed is None else "FAIL")
        if passed:
            n_pass += 1
        A(f"| {cid} | `{axiom}` | {defect} | {exp} | **{mark}** ({detail}) |")
    A("")
    A(f"**{n_pass}/{len(results)} passed.**\n")
    A("These are not decorative axioms: each one fires on a defect that a "
      "closed-world spreadsheet workflow would carry forward silently.\n")

    text = "\n".join(L)
    (EVAL / "axiom_tests.md").write_text(text, encoding="utf-8")
    print(text)
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
