#!/usr/bin/env python3
"""
Show, mechanically, that the surveyed vocabularies cannot SEPARATE the readings
that the record leaves open -- and that CENSO does.

WHY THIS EXISTS
---------------
The gap table (scripts/07_verify_gap_table.py) is a presence/absence matrix: it
says which vocabulary declares a term for censoring, for a limit, for an
undecidable verdict. A referee is entitled to answer "so what -- a missing term
is a missing convenience, not a missing capability; anyone can mint a subclass."

That objection is answerable, and the answer is a logical one rather than a
feature count. A vocabulary distinguishes two situations only if some sentence
it can write is true of one and false of the other. So take one REAL record,
write down the readings it admits, and ask of each vocabulary whether the
readings it can express still differ. Where they do not, no reasoner, query or
pipeline built on that vocabulary can return different answers for them --
whatever it is later extended with.

THE WITNESS
-----------
One row of the EEA record, the same row Figure 6(b) is drawn from: imidacloprid
at a Spanish river station, reported below a quantification limit of
0.01 ug/L, carrying the number 0.01 as its value, against an annual-average
standard of 0.0068 ug/L. Nothing about it is constructed: the threshold lies
inside the censored interval, and the reported value is the limit itself, which
is what substitution at source looks like in this release.

Three readings of those same four numbers:

  R1  the censoring is honoured -- the number is a BOUND, the result is the
      interval [0, 0.01], the standard lies inside it, and Article 3(3b)
      applies: no verdict is supportable.
  R2  the flag is dropped and the number is taken at face value -- a measured
      0.01 ug/L against a standard of 0.0068, which any numeric comparison
      calls an exceedance.
  R3  the number arrives with neither flag nor limit -- 25.5 % of this record.
      Nothing is known about whether it is a measurement.

R1 and R2 are the pair that matters: the SAME four numbers, and the whole
argument of the paper is that they are different claims.

WHAT IS COMPUTED
----------------
1. For each vocabulary in derived/processed/gap_matrix.csv, the translation of
   each reading into that vocabulary -- the set of facts it has any term to
   carry. The translation is deliberately GENEROUS: a fact survives if the
   vocabulary has ANY term in the concept family the fact needs, and every
   vocabulary is granted the two families (an observation, a reported number)
   without checking, since all of them are observation vocabularies. Being
   generous is the point: the vocabularies still fail.
2. Whether the translations of two readings coincide. Where they do, the
   vocabularies cannot separate the readings -- reported as a collapse.
3. For CENSO, the same readings run through owlrl, reporting the outcome class
   each entails, and a merge test showing the readings are not merely labelled
   differently but logically incompatible.

WHAT THIS DOES NOT CLAIM
------------------------
Not that the vocabularies are wrong, and not that they could not be extended.
Any vocabulary can be given a censoring class tomorrow. The claim is about
reuse as published, which is what a comparison table is for, and about where
the distinction has to live once it is added: on the result, not the device.

Inputs  : derived/processed/gap_matrix.csv        (scripts/07_verify_gap_table.py)
          paper/supplementary/figure_data/fig06_decision_geometry.csv
          ontology/censo-core.ttl
Outputs : eval/separation.md

Usage:  python scripts/13_separation.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
PROC = ROOT / "derived" / "processed"
ONTO = ROOT / "ontology"
CORE = ONTO / "censo-core.ttl"
FIGDATA = (ROOT / "paper" / "supplementary" / "figure_data"
           / "fig06_decision_geometry.csv")
MATRIX = PROC / "gap_matrix.csv"
OUT = EVAL / "separation.md"

try:
    import rdflib
    import owlrl
except ImportError:
    sys.exit("rdflib and owlrl are required:  pip install rdflib owlrl")


# ---------------------------------------------------------------------------
# The facts, and the concept family each one needs a term for.
#
# The families are the gap table's own columns, so nothing is decided here that
# was not already decided by parsing the ontology files. Two families are
# granted to every vocabulary without checking -- `observation` and `result` --
# because every entry in the comparison set is an observation or measurement
# vocabulary and refusing them would manufacture the conclusion.
#
# `detection_limit_on_result` is the one family the gap table records as a
# BINDING rather than a presence: SSN-system has a detection limit and binds it
# to the sensor, so it can say what the instrument can do and cannot say that
# THIS result fell below it. That distinction is the whole of why a limit
# declared as a SystemProperty does not help here, and it is why the column
# exists in the table.
# ---------------------------------------------------------------------------
GRANTED = {"observation", "result"}

FACTS = {
    "identity":   ("the observation exists, with its analyte, station and year",
                   "observation"),
    "value":      ("the number 0.01 ug/L is reported for it", "result"),
    "limit":      ("a quantification limit of 0.01 ug/L is stated",
                   "detection_limit"),
    "limit_here": ("that limit qualifies THIS result, not the device that "
                   "produced it", "detection_limit_on_result"),
    "censored":   ("the number is a bound, not a measurement", "censoring"),
    # The interval is not an independent fact: without the censoring statement
    # there is no ground on which to assert that the result is an interval at
    # all. A vocabulary with interval-valued results and no censoring term can
    # hold the interval only if something else tells it the result is one --
    # which is the distinction at issue. The sensitivity below reports what
    # happens if this is granted anyway.
    "interval":   ("the result is the interval [0, 0.01], not the point 0.01",
                   "censoring+interval_result"),
    "threshold":  ("an annual-average standard of 0.0068 ug/L applies",
                   "threshold"),
    "no_verdict": ("the verdict is that no verdict is supportable",
                   "undecidable"),
}

READINGS = {
    "R1": ("censoring honoured",
           ["identity", "value", "limit", "limit_here", "censored",
            "interval", "threshold", "no_verdict"]),
    "R2": ("number taken at face value",
           ["identity", "value", "limit", "limit_here", "threshold"]),
    "R3": ("neither flag nor limit reported",
           ["identity", "value", "threshold"]),
}

PAIRS = [("R1", "R2"), ("R1", "R3"), ("R2", "R3")]

# Vocabularies allowed to separate R1 from R2, each with the reason. A
# separation NOT listed here fails the build: that is where a real competitor
# capability would surface, and it is the reason this file can afford to have
# generous concept patterns at all.
#
# Every entry has to say why the separation is an artefact, and be checkable by
# reading the named term's own superclass in the cached file. "It would be
# inconvenient" is not a reason.
KNOWN_SEPARATORS = {
    "CHMO (chemical methods)":
        "credited with the `undecidable` family on two terms that are not "
        "assessment outcomes: `ambiguous synonym` (OMO_0003001), an OBO "
        "annotation property describing the quality of a SYNONYM, and `double "
        "quantum transitions for finding unresolved lines` (CHMO_0001861), an "
        "NMR technique in which the unresolved things are spectral lines. R1 "
        "therefore gains `no_verdict` and R2 does not. CHMO declares no "
        "censoring term at all, so it cannot separate a bound from a "
        "measurement -- which is the distinction that matters -- and read "
        "strictly it collapses with the rest.",
}


def families_of(row: dict) -> set:
    """Concept families a vocabulary can carry, read off the gap matrix."""
    fams = set(GRANTED)
    for col in ("detection_limit", "censoring", "undecidable", "threshold",
                "interval_result", "applicability"):
        if row.get(col) == "1":
            fams.add(col)
    if (row.get("lod_bound_to") or "").strip() == "result":
        fams.add("detection_limit_on_result")
    return fams


def translate(reading: str, fams: set, grant_interval: bool = False) -> set:
    """The facts of a reading a vocabulary has any term to carry."""
    kept = set()
    for fid in READINGS[reading][1]:
        need = FACTS[fid][1]
        if "+" in need:
            parts = set(need.split("+"))
            ok = parts <= fams
            if grant_interval and "interval_result" in parts:
                ok = "interval_result" in fams
        else:
            ok = need in fams
        if ok:
            kept.add(fid)
    return kept


# ---------------------------------------------------------------------------
# The positive half: CENSO run through a reasoner on the same three readings.
# ---------------------------------------------------------------------------
PREFIX = """@prefix censo: <https://w3id.org/censo/> .
@prefix ex:    <https://example.org/witness/> .
@prefix owl:   <http://www.w3.org/2002/07/owl#> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .
@prefix sosa:  <http://www.w3.org/ns/sosa/> .
@prefix qudt:  <http://qudt.org/schema/qudt/> .
"""

# The threshold, the analyte and the station are IDENTICAL across the three
# readings. Only the observation differs, which is the point: the readings are
# not three records, they are three readings of one.
FIXTURE = """
ex:imidacloprid a censo:Analyte ; censo:casNumber "138261-41-3" .
ex:stationES    a sosa:FeatureOfInterest .
ex:campaign     a censo:Campaign .
ex:eu2026       a censo:Regulation .
ex:ugPerL       a qudt:Unit .

ex:eqs a censo:AnnualAverageThreshold ;
    censo:thresholdValue "0.0068"^^xsd:decimal ;
    censo:thresholdUnit  ex:ugPerL ;
    censo:definedBy      ex:eu2026 ;
    censo:appliesToAnalyte ex:imidacloprid .

ex:method a censo:AnalyticalMethod ;
    censo:determinesAnalyte ex:imidacloprid ;
    censo:limitOfQuantification "0.01"^^xsd:decimal ;
    censo:limitUnit ex:ugPerL .
"""

# R1. Censored, the standard inside [0, LOQ]. The comparison properties are NOT
# asserted: Article 3(3b) sets the result aside, which is a regulatory verdict
# and not a comparison, and censo:MethodInsufficient is what the shape layer
# materialises for it. See the Limitations subsection of the manuscript.
R1_TTL = """
ex:obs a sosa:Observation , censo:CensoredObservation , censo:MethodInsufficient ;
    censo:hasAnalyte ex:imidacloprid ;
    censo:atStation  ex:stationES ;
    censo:duringCampaign ex:campaign ;
    sosa:usedProcedure ex:method ;
    censo:resultLowerBound "0"^^xsd:decimal ;
    censo:resultUpperBound "0.01"^^xsd:decimal ;
    censo:reportedValue "0.01"^^xsd:decimal ;
    censo:censoringRecovered false ;
    censo:assessableAgainst ex:eqs .
"""

# R2. The flag is gone and the number is a measurement. A two-valued pipeline
# compares 0.01 against 0.0068 and calls it an exceedance; censo:exceeds is
# what that comparison materialises, and censo:Exceedance follows from the
# equivalent-class axiom without being asserted.
R2_TTL = """
ex:obs a sosa:Observation , censo:QuantifiedObservation ;
    censo:hasAnalyte ex:imidacloprid ;
    censo:atStation  ex:stationES ;
    censo:duringCampaign ex:campaign ;
    sosa:usedProcedure ex:method ;
    censo:resultLowerBound "0.01"^^xsd:decimal ;
    censo:resultUpperBound "0.01"^^xsd:decimal ;
    censo:reportedValue "0.01"^^xsd:decimal ;
    censo:exceeds ex:eqs .
"""

# R3. A number and nothing that says what it is. UnresolvedObservation is
# subclass of the complement of assessableAgainst-some-Threshold, so asserting
# a verdict here is an inconsistency rather than a default pass.
R3_TTL = """
ex:obs a sosa:Observation , censo:UnresolvedObservation ;
    censo:hasAnalyte ex:imidacloprid ;
    censo:atStation  ex:stationES ;
    censo:duringCampaign ex:campaign ;
    censo:reportedValue "0.01"^^xsd:decimal .
"""

READING_TTL = {"R1": R1_TTL, "R2": R2_TTL, "R3": R3_TTL}

OUTCOME_CLASSES = [
    "Exceedance", "PossibleExceedance", "Compliant",
    "IndeterminateCompliance", "MethodInsufficient", "CensoredAmbiguous",
    "NoThresholdDefined", "PreconditionUnmet",
]
STATUS_CLASSES = ["CensoredObservation", "QuantifiedObservation",
                  "EstimatedObservation", "UnresolvedObservation"]

CENSO = "https://w3id.org/censo/"
ERR_PRED = rdflib.URIRef(
    "http://www.daml.org/2002/03/agents/agent-ont#error")


def build(snippets) -> "rdflib.Graph":
    g = rdflib.Graph()
    g.parse(CORE, format="turtle")
    g.parse(data=PREFIX + FIXTURE + "".join(snippets), format="turtle")
    for t in list(g.triples((None, rdflib.OWL.imports, None))):
        g.remove(t)
    return g


def close(g):
    """OWL 2 RL closure. Returns (inconsistent, first message)."""
    try:
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics,
                               axiomatic_triples=False,
                               datatype_axioms=False).expand(g)
    except Exception as e:                       # noqa: BLE001
        return True, f"reasoner raised {type(e).__name__}: {e}"
    msgs = sorted({str(o) for _, _, o in g.triples((None, ERR_PRED, None))})
    if list(g.triples((None, rdflib.RDF.type, rdflib.OWL.Nothing))):
        msgs.append("an individual was entailed to be owl:Nothing")
    return bool(msgs), (msgs[0] if msgs else "")


def entailed(g, names):
    obs = rdflib.URIRef("https://example.org/witness/obs")
    types = {str(o) for o in g.objects(obs, rdflib.RDF.type)}
    return [n for n in names if CENSO + n in types]


def main() -> int:
    if not MATRIX.exists():
        sys.exit(f"{MATRIX} is missing — run scripts/07_verify_gap_table.py")
    rows = list(csv.DictReader(MATRIX.open(encoding="utf-8")))
    # The witness is a REAL row and there is no substitute for it: inventing
    # one would make the whole argument a construction. So the stage skips
    # rather than fabricates when the figure data is absent, which is what a
    # run without the Waterbase download looks like.
    if not FIGDATA.exists():
        print(f"  {FIGDATA.relative_to(ROOT)} absent — skipped "
              f"(run scripts/90_figures.py first)")
        return 0
    witness = next((r for r in csv.DictReader(FIGDATA.open(encoding="utf-8"))
                    if r["case"] == "cannot_decide"), None)
    if witness is None:
        print("  the figure data holds no undecidable case — skipped")
        return 0

    # ---- the negative half: what the vocabularies can separate -------------
    others, collapses = [], {p: [] for p in PAIRS}
    generous_separators = []
    for r in rows:
        name = r["ontology"]
        if r["status"] != "OK" or name.startswith("CENSO"):
            continue
        fams = families_of(r)
        tr = {k: translate(k, fams) for k in READINGS}
        gen = {k: translate(k, fams, grant_interval=True) for k in READINGS}
        row = {"name": name, "fams": fams, "tr": tr}
        for a, b in PAIRS:
            if tr[a] == tr[b]:
                collapses[(a, b)].append(name)
        if gen["R1"] != gen["R2"]:
            generous_separators.append(name)
        others.append(row)

    # ---- the positive half: what CENSO separates --------------------------
    censo_rows, censo_bad = [], []
    for k in ("R1", "R2", "R3"):
        g = build([READING_TTL[k]])
        inc, msg = close(g)
        if inc:
            censo_bad.append((k, msg))
        censo_rows.append((k, READINGS[k][0],
                           entailed(g, STATUS_CLASSES),
                           entailed(g, OUTCOME_CLASSES)))

    # Not merely different labels: incompatible descriptions. Merging any two
    # readings of the same individual must be an inconsistency, or "different
    # outcome" would only mean "we chose to write something else".
    merges = []
    for a, b in PAIRS:
        g = build([READING_TTL[a], READING_TTL[b]])
        inc, msg = close(g)
        merges.append((a, b, inc, msg))

    # ---- report -----------------------------------------------------------
    A, add = [], None
    add = A.append
    add("# What the other vocabularies cannot separate\n")
    add("Generated by `scripts/13_separation.py`. The gap table records which "
        "vocabulary declares which term; this asks the question a term list "
        "cannot answer — whether the readings a record admits stay different "
        "once written in that vocabulary.\n")

    add("## The witness\n")
    add(f"One row of the EEA record, the same one Figure 6(b) is drawn from: "
        f"**{witness['substance']}** (CAS {witness['cas']}) at a river "
        f"station in {witness['country']}, reported below a quantification "
        f"limit of **{witness['loq_ug_l']} µg/L**, carrying "
        f"**{witness['value_ug_l']}** as its value, against an annual-average "
        f"standard of **{witness['threshold_ug_l']} µg/L**. The standard lies "
        f"inside the censored interval and the reported value is the limit "
        f"itself, which is what substitution at source looks like in this "
        f"release.\n")
    add("Three readings of those same four numbers:\n")
    add("| reading | what it says | facts asserted |")
    add("|---|---|---|")
    for k, (label, fids) in READINGS.items():
        add(f"| **{k}** | {label} | {', '.join(f'`{f}`' for f in fids)} |")
    add("")
    add("`R1` and `R2` are the pair the paper turns on: identical numbers, "
        "different claims.\n")

    add("## The facts, and the concept family each needs a term for\n")
    add("| fact | statement | family required |")
    add("|---|---|---|")
    for fid, (stmt, fam) in FACTS.items():
        add(f"| `{fid}` | {stmt} | `{fam}` |")
    add("")
    add("`observation` and `result` are granted to every vocabulary without "
        "checking, since all of them are observation vocabularies. Every "
        "other family is decided by `scripts/07_verify_gap_table.py` parsing "
        "the ontology file. The translation is generous by construction: a "
        "fact survives if the vocabulary has **any** term in its family.\n")

    add("## Translations\n")
    add("| vocabulary | τ(R1) | τ(R2) | τ(R3) | R1 vs R2 |")
    add("|---|---|---|---|---|")
    for o in others:
        cells = []
        for k in ("R1", "R2", "R3"):
            s = sorted(o["tr"][k])
            cells.append(", ".join(f"`{x}`" for x in s) if s else "∅")
        verdict = ("**collapse**" if o["tr"]["R1"] == o["tr"]["R2"]
                   else "separated")
        add(f"| {o['name']} | {cells[0]} | {cells[1]} | {cells[2]} "
            f"| {verdict} |")
    add("")

    n = len(others)
    r1r2 = len(collapses[("R1", "R2")])
    add("## Result\n")
    add(f"- vocabularies assessed: **{n}**")
    for a, b in PAIRS:
        c = len(collapses[(a, b)])
        add(f"- {a} and {b} translate to the same facts in: "
            f"**{c} of {n}**")
    add("")
    if r1r2 == n:
        add("**Every vocabulary in the comparison set collapses R1 into R2.** "
            "The censoring statement, the interval that follows from it and "
            "the verdict that no verdict is supportable each need a family no "
            "vocabulary declares, so all three are dropped from both readings "
            "and what remains is literally the same set of facts.\n")
        add("The consequence is not a matter of convenience. If two readings "
            "translate to the same theory, then for every sentence φ in that "
            "vocabulary the first entails φ exactly when the second does. No "
            "query, rule or reasoner over these vocabularies returns a "
            "different answer for a non-detection than for a measurement at "
            "the same number — not because none has been written, but "
            "because none can be.\n")
    else:
        sep = sorted(set(o["name"] for o in others
                         if o["tr"]["R1"] != o["tr"]["R2"]))
        add(f"**{n - r1r2} of {n} vocabularies separate R1 from R2**: "
            + ", ".join(sep or ["—"]) + ".\n")
        for name in sep:
            why = KNOWN_SEPARATORS.get(name)
            add(f"- **{name}** — "
                + (why if why else
                   "NOT a documented exception. This vocabulary separates the "
                   "two readings, so the novelty claim is false as written and "
                   "must be narrowed. The build fails on this."))
        add("")
        add("A separation listed above as a documented exception is an artefact "
            "of the matcher, not a capability: the concept patterns are "
            "deliberately generous, so a vocabulary can be credited with a "
            "family on a term that means something else, and the fact it then "
            "gains in one reading is enough to break the collapse. The cells "
            "are left standing and the discrepancy published, because "
            "narrowing a pattern until a competitor loses one would make the "
            "comparison an assertion again.\n")

    if collapses[("R1", "R3")] != [o["name"] for o in others]:
        sep13 = [o["name"] for o in others if o["tr"]["R1"] != o["tr"]["R3"]]
        add(f"R1 and R3 are separated by {', '.join(sep13)} — but only by the "
            "presence or absence of a limit somewhere in the record, not by "
            "what the number means. A vocabulary can notice that a limit was "
            "stated; none can say that this result fell below it.\n")

    add("### Sensitivity: granting the interval without the censoring term\n")
    add("`interval` is written above as needing both a censoring term and an "
        "interval-valued result, because without the first there is no ground "
        "on which to assert that the result is an interval. Granting it on "
        "the interval family alone — the most favourable reading available to "
        "a vocabulary with interval results and no censoring class — "
        + (f"separates R1 from R2 in: **{', '.join(generous_separators)}**. "
           "Even there the interval must be asserted by hand from a flag the "
           "vocabulary has no term for, which is the distinction at issue "
           "rather than a counter-example to it.\n"
           if generous_separators else
           "changes nothing: no vocabulary separates the readings even then.\n"))

    add("## The same three readings in CENSO\n")
    add("| reading | detection status entailed | compliance outcome entailed |")
    add("|---|---|---|")
    for k, label, st, out in censo_rows:
        add(f"| **{k}** ({label}) | "
            f"{', '.join('`censo:' + x + '`' for x in st) or '—'} | "
            f"{', '.join('`censo:' + x + '`' for x in out) or '—'} |")
    add("")
    if censo_bad:
        add("**A reading was inconsistent on its own, which is a defect:** "
            + "; ".join(f"{k}: {m}" for k, m in censo_bad) + "\n")

    add("Outcome classes are entailed, not asserted: `censo:Exceedance` is an "
        "equivalent class of an observation bearing `censo:exceeds` to a "
        "threshold, so R2's verdict follows from the comparison the rule "
        "layer materialises. R1 carries no comparison property at all — "
        "Article 3(3b) sets the result aside, which is a regulatory verdict "
        "and not a comparison.\n")

    add("### The readings are incompatible, not merely differently labelled\n")
    add("A vocabulary that only wrote a different word for each reading would "
        "leave a graph free to hold both at once. Merging any two readings of "
        "the same individual must therefore be an inconsistency.\n")
    add("| merged | inconsistent | what the reasoner reports |")
    add("|---|---|---|")
    for a, b, inc, msg in merges:
        add(f"| {a} + {b} | {'**yes**' if inc else 'no'} "
            f"| {(msg[:110] + '…') if len(msg) > 110 else (msg or '—')} |")
    add("")
    if all(inc for _, _, inc, _ in merges):
        add("All three merges are contradictions, from the "
            "`owl:AllDisjointClasses` axiom over the detection statuses. The "
            "separation is therefore a property of the vocabulary and not of "
            "the pipeline that populates it: a loader cannot quietly hold two "
            "readings of one record.\n")

    add("## What this does not claim\n")
    add("Not that these vocabularies are wrong, and not that they could not "
        "be extended — any of them could be given a censoring class tomorrow. "
        "The claim is about reuse as published, which is what a comparison "
        "table is for, and about where the distinction has to live once it is "
        "added. A limit declared as a property of the sensor, as SSN-system "
        "declares it, describes what an instrument can do; separating these "
        "readings needs a limit bound to the result and a status on the "
        "observation.\n")

    OUT.write_text("\n".join(A) + "\n", encoding="utf-8")
    print(f"  {n} vocabularies assessed; R1/R2 collapse in {r1r2}")
    print(f"  CENSO: " + "; ".join(
        f"{k}→{','.join(out) or '—'}" for k, _, _, out in censo_rows))
    print(f"  merges inconsistent: "
          f"{sum(1 for _, _, i, _ in merges if i)}/{len(merges)}")
    print(f"  wrote {OUT.relative_to(ROOT)}")
    # THE INVARIANTS, and what is no longer one.
    #
    # `r1r2 == n` used to be the exit condition. It stopped being defensible
    # when the concept patterns were widened to admit other people's spellings
    # rather than only ours: a generous matcher can credit a vocabulary with a
    # family on a term that means something else, that reading then gains a
    # fact the other lacks, and the collapse breaks without any competitor
    # gaining a capability. Making that fail the build would create pressure to
    # narrow the patterns until the answer came out right, which is the one
    # thing this comparison must never do.
    #
    # So the exit condition is now: every separation must be a DECLARED
    # exception. A vocabulary that separates the two readings for a reason not
    # written down in KNOWN_SEPARATORS fails the build, which is the behaviour
    # the universal was there to provide -- if a competitor ever declares a
    # censoring status, this is what says so.
    undeclared = sorted(o["name"] for o in others
                        if o["tr"]["R1"] != o["tr"]["R2"]
                        and o["name"] not in KNOWN_SEPARATORS)
    if undeclared:
        print(f"  FAIL undeclared separation: {', '.join(undeclared)}")
        print("       A vocabulary separates the two readings for a reason "
              "that is not documented. Either it has genuinely gained the "
              "capability -- in which case the novelty claim must be narrowed "
              "-- or the matcher credited it wrongly and the reason belongs in "
              "KNOWN_SEPARATORS. Do not narrow a pattern to make this pass.")
        return 1
    if not all(i for _, _, i, _ in merges):
        print("  FAIL a merged reading came back CONSISTENT. The disjointness "
              "that makes the readings incompatible rather than differently "
              "labelled has been lost.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
