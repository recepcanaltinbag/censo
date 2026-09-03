#!/usr/bin/env python3
"""
What the shapes catch in the record as it was actually reported.

WHY THIS IS DIFFERENT FROM scripts/18
-------------------------------------
Script 18 validates the graph this project builds, and that graph conforms by
construction: the builder repairs what it can and types the rest as
UnresolvedObservation. Zero violations there says the builder is correct. It
says nothing about the data.

This script does the opposite. It expresses Waterbase rows AS REPORTED, with no
repair, and runs the same published shapes over them. That is the operation a
reporting authority would perform on its own submission before sending it, so
the output is the answer to a question the audit alone cannot pose: how much of
what is about to be published cannot afterwards be interpreted?

The one substantive difference from scripts/23 is the interval. There, a
censored observation gets resultLowerBound 0, because that is what a
non-detection actually establishes. Here it gets the number the reporter wrote,
because that is what the reporter asserted -- and censo:CensoredObservationShape
exists precisely to say that a non-detect with a positive lower bound is a
substituted value rather than a measurement.

SCALE
-----
pyshacl materialises as well as validates, so the whole record is impractical.
A deterministic sample is validated to prove the shapes fire, and the
population counts for the same conditions are obtained by streaming every row.
Both are reported; neither is presented as the other.

Inputs  : Data/waterbase/... or --file, ontology/censo-shapes.ttl
Outputs : derived/abox/censo-waterbase-asreported.ttl
          derived/processed/source_conformance.csv
          eval/source_conformance.md

Usage:  python scripts/26_source_conformance.py --file <zip> [--max-rows N]
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
ABOX = ROOT / "derived" / "abox"
EVAL = ROOT / "eval"
DATA = ROOT / "Data" / "waterbase"

sys.path.insert(0, str(Path(__file__).resolve().parent))
_m = __import__("22_waterbase_external")
open_rows, pick, num, wilson = _m.open_rows, _m.pick, _m.num, _m.wilson
TO_UG_L = _m.TO_UG_L

SEED = 20260803

PREAMBLE = """\
@prefix censo: <https://w3id.org/censo/> .
@prefix cereg: <https://w3id.org/censo/reg/> .
@prefix sosa:  <http://www.w3.org/ns/sosa/> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .
@prefix unit:  <http://qudt.org/vocab/unit/> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:   <http://www.w3.org/2002/07/owl#> .
@prefix wb:    <https://w3id.org/censo/waterbase-asreported/> .

"""

# Each condition names the shape that fires on it, so the report can be read
# against the published shapes file rather than against this script.
CONDITIONS = {
    "censored_with_positive_value":
        ("censo:CensoredObservationShape",
         "a below-LOQ result carrying a positive value: the number is a "
         "substitution, not a measurement"),
    "censored_without_loq":
        ("censo:ObservationShape / usedProcedure",
         "censoring declared with no limit, so the interval cannot be "
         "reconstructed"),
    "nonpositive_loq":
        ("censo:AnalyticalMethodShape",
         "a quantification limit of zero or less, which is not a limit"),
    "negative_value":
        ("censo:ObservationShape / reportedValue",
         "a negative concentration, physically impossible"),
    "silent":
        ("censo:ObservationShape / usedProcedure",
         "neither a flag nor a limit, so the record cannot be interpreted "
         "even in principle"),
}


def dec(v):
    """Canonical xsd:decimal LEXICAL form -- always a point. Display only."""
    s = f"{v:.10f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    return s or "0.0"


def lit(v):
    """A TYPED xsd:decimal literal, for anything written as data.

    Same defect, same fix as scripts/23_waterbase_abox.py: a bare Turtle
    numeral is typed by its lexical form, so `censo:resultLowerBound 0` is an
    xsd:integer and violates sh:datatype xsd:decimal. This is the graph
    validated against the published shapes to show that the substitution has
    already happened at source; it should not itself be failing them on
    datatypes while making that point.
    """
    return f'"{dec(v)}"^^xsd:decimal'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path)
    ap.add_argument("--max-rows", type=int, default=20000,
                    help="rows to express and validate with SHACL")
    args = ap.parse_args()

    src = args.file
    if src is None:
        cand = [p for p in sorted(DATA.glob("*"))
                if p.suffix.lower() in (".csv", ".zip", ".gz")]
        agg = [p for p in cand if "aggregated" in p.name.lower()]
        cand = agg or cand
        if not cand:
            sys.exit(f"no Waterbase file in {DATA.relative_to(ROOT)}")
        src = cand[0]
    print(f"  source: {src.name}")

    rows = open_rows(src)
    header = next(rows)
    col = pick(header)

    def g(row, role):
        i = col.get(role)
        return row[i].strip() if i is not None and i < len(row) else ""

    pop = defaultdict(int)          # population counts, every river row
    n_river = 0
    out = []                        # the sampled graph
    kept = 0
    n_cand = 0
    by_cty = defaultdict(lambda: defaultdict(int))
    reservoir = []
    rng = random.Random(SEED)

    for row in rows:
        if not row:
            continue
        if "category" in col and g(row, "category") not in ("RW", ""):
            continue
        n_river += 1
        if n_river % 2_000_000 == 0:
            print(f"    {n_river:,} river rows …")

        val = num(g(row, "value"))
        loq = num(g(row, "loq"))
        flag = g(row, "below_loq")
        uom = g(row, "uom").strip().lower()
        factor = TO_UG_L.get(uom)

        cty = (g(row, "country") or "??").upper()
        censored = flag == "1"
        if censored:
            by_cty[cty]["censored"] += 1
        if censored and val is not None and val > 0:
            pop["censored_with_positive_value"] += 1
            by_cty[cty]["substituted"] += 1
        if censored and loq is None:
            pop["censored_without_loq"] += 1
        if loq is not None and loq <= 0:
            pop["nonpositive_loq"] += 1
        if val is not None and val < 0:
            pop["negative_value"] += 1
        if flag == "" and loq is None:
            pop["silent"] += 1
        if factor is None:
            # conventional determinands (pH, temperature, mg{P}/L …) are not
            # micropollutants and carry no inland-water EQS in ug/L. Excluded
            # here for the same reason as in the audit, and counted so the
            # exclusion is visible rather than silent.
            pop["not_a_concentration_in_ug_l"] += 1
            continue

        # ---- keep the row for the sample ----------------------------------
        # Reservoir sampling, not the first N rows. Taking the head gave a
        # sample containing no censored observation at all -- Waterbase is
        # ordered, so the opening block is one reporter's conventional
        # determinands -- and the shapes then found nothing to fire on. That
        # was a property of the sample, not of the data.
        rec = (censored, val, loq, factor)
        n_cand += 1
        if len(reservoir) < args.max_rows:
            reservoir.append(rec)
        else:
            j = rng.randrange(n_cand)
            if j < args.max_rows:
                reservoir[j] = rec

    for kept, (censored, val, loq, factor) in enumerate(reservoir, 1):
        o = f"wb:obs-{kept}"
        cls = ("censo:CensoredObservation" if censored else
               "censo:QuantifiedObservation" if val is not None else
               "censo:UnresolvedObservation")
        L = [f"{o} a {cls} ;",
             f"    censo:hasAnalyte wb:analyte-{kept} ;",
             f"    censo:atStation wb:station-{kept} ;",
             f"    censo:duringCampaign wb:campaign-{kept} ;"]
        if loq is not None and factor:
            L.append(f"    sosa:usedProcedure wb:method-{kept} ;")
        if val is not None and factor:
            L.append(f"    censo:reportedValue {lit(val * factor)} ;")
        if censored:
            # THE POINT: the source's own number becomes the lower bound,
            # because that is what the source asserts the concentration to be.
            lo = val * factor if (val is not None and factor) else 0.0
            L.append(f"    censo:resultLowerBound {lit(lo)} ;")
            if loq is not None and factor:
                L.append(f"    censo:resultUpperBound {lit(loq * factor)} ;")
        L[-1] = L[-1].rstrip(" ;") + " ."
        out.append("\n".join(L))
        out.append(f"wb:analyte-{kept} a censo:Analyte .")
        out.append(f"wb:station-{kept} a sosa:FeatureOfInterest .")
        if loq is not None and factor:
            out.append(f"wb:method-{kept} a censo:AnalyticalMethod ;\n"
                       f"    censo:limitOfQuantification {lit(loq * factor)} ;\n"
                       f"    censo:limitUnit unit:MicroGM-PER-L .")

    ABOX.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)
    EVAL.mkdir(parents=True, exist_ok=True)
    ttl = ABOX / "censo-waterbase-asreported.ttl"
    ttl.write_text(PREAMBLE + "\n".join(out) + "\n", encoding="utf-8")
    print(f"  expressed {kept:,} rows as reported -> {ttl.name}")

    # ---- run the published shapes over it ---------------------------------
    conforms, n_viol, by_shape = None, None, {}
    try:
        import rdflib
        from pyshacl import validate
        data = rdflib.Graph()
        data.parse(ttl, format="turtle")
        shapes = rdflib.Graph()
        shapes.parse(ROOT / "ontology" / "censo-shapes.ttl", format="turtle")
        print(f"  validating {len(data):,} triples against the published shapes …")
        conforms, rg, _ = validate(data, shacl_graph=shapes,
                                   advanced=True, inference="none",
                                   abort_on_first=False)
        SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
        n_viol = 0
        for r in rg.subjects(rdflib.RDF.type, SH.ValidationResult):
            n_viol += 1
            src_shape = next(rg.objects(r, SH.sourceShape), None)
            msg = next(rg.objects(r, SH.resultMessage), None)
            key = str(msg)[:90] if msg else str(src_shape)
            by_shape[key] = by_shape.get(key, 0) + 1
        print(f"  conforms: {conforms}; {n_viol:,} violation(s), "
              f"{len(by_shape)} distinct message(s)")
    except ImportError as e:
        print(f"  (pyshacl/rdflib absent: {e}); population counts only")

    with (PROC / "source_conformance.csv").open("w", newline="",
                                                encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scope", "condition", "shape", "n", "share_of_river_rows"])
        w.writerow(["total", "river_rows", "", n_river, ""])
        for k, v in sorted(pop.items(), key=lambda kv: -kv[1]):
            shape = CONDITIONS.get(k, ("", ""))[0]
            w.writerow(["population", k, shape, v, f"{100*v/n_river:.3f}"])
        for msg, v in sorted(by_shape.items(), key=lambda kv: -kv[1]):
            w.writerow(["shacl_sample", msg, "", v, ""])
        for c, d in sorted(by_cty.items(),
                           key=lambda kv: -kv[1]["censored"]):
            if d["censored"]:
                w.writerow(["country", c, "censored_with_positive_value",
                            d["substituted"],
                            f"{100*d['substituted']/d['censored']:.1f}"])

    L = ["# What the shapes catch in the record as reported", "",
         "Generated by `scripts/26_source_conformance.py`. Rows are expressed "
         "**without repair**: a below-LOQ result keeps the number the reporter "
         "wrote as its lower bound, because that is what the reporter "
         "asserted. This is the check a reporting authority would run on its "
         "own submission before publishing it.", "",
         f"- river rows examined: **{n_river:,}**",
         f"- rows expressed and validated with SHACL: **{len(reservoir):,}**, "
         f"drawn by reservoir sampling with a fixed seed from the "
         f"**{n_cand:,}** rows reporting a concentration in a convertible "
         f"unit (the sample is therefore of concentration rows, not of all "
         f"river rows)", ""]
    if conforms is not None:
        L += [f"- SHACL conforms: **{conforms}**",
              f"- violations on the sample: **{n_viol:,}**", ""]
        if by_shape:
            L += ["| Violation reported by the shape | n |", "|---|---|"]
            for msg, v in sorted(by_shape.items(), key=lambda kv: -kv[1])[:10]:
                L.append(f"| {msg} | {v:,} |")
            L.append("")

    L += ["## The same conditions over every river row", "",
          "| Condition | Shape that fires | n | % of river rows |",
          "|---|---|---|---|"]
    for k, v in sorted(pop.items(), key=lambda kv: -kv[1]):
        shape, _desc = CONDITIONS.get(k, ("—", ""))
        L.append(f"| {k.replace('_', ' ')} | `{shape}` | {v:,} | "
                 f"{100*v/n_river:.2f}\\% |")
    # This section described TWO violation types and told the reader that "our
    # own pipeline fills the gap with the conventional LOD = LOQ/3". Both
    # statements were superseded when the fabricated detection limit was removed
    # from the ABox and the shape was relaxed to require *a* limit: the table
    # above now reports one violation type, and the pipeline invents nothing.
    # The report is generated, but its prose is not, so it outlived the change
    # it was describing -- in a file that ships with the repository and is cited
    # by the manuscript.
    L += ["", "## Reading the violation", "",
          "**A non-detect carrying a positive number** is an assertion the "
          "reporter made: the record says the concentration is below the "
          "quantification limit and simultaneously states a value for it. "
          "Substitution has already been applied at source. Where the flag "
          "survives this is visible and reversible; where it does not, it is "
          "neither.",
          "",
          "An earlier version of the shapes required every method to state a "
          "limit of *detection*, and so fired on every row: WISE-6 has no "
          "field for one, and both provisions at issue --- Article 3(3b) of "
          "Directive 2008/105/EC and Article 4(1) of Directive 2009/90/EC --- "
          "are written about the quantification limit. This pipeline satisfied "
          "that constraint by manufacturing the datum at LOQ/3, which is why "
          "the constraint was wrong and the manufactured value is gone: the "
          "shapes now require *a* limit and the ABox states the one the source "
          "reports. The distinction the old constraint reached for is real and "
          "is made in the manuscript rather than here: a non-detection "
          "establishes $[0,\\mathrm{LOD}]$, and this record supports at best "
          "$[0,\\mathrm{LOQ}]$ --- a weaker and different claim.",
          "", "## Reading", ""]
    sub = pop.get("censored_with_positive_value", 0)
    cen = sub + pop.get("censored_without_loq", 0)
    if sub:
        L.append(
            f"The dominant finding is not a data-entry error. **{sub:,} rows "
            f"({100*sub/n_river:.1f}\\% of the river record) declare a result "
            f"below the quantification limit and carry a positive number for "
            f"it.** The substitution this paper is about has therefore already "
            f"been performed, by the reporting authority, before anyone "
            f"downloads the data. Where the flag survives, as here, the "
            f"substitution is visible and can be undone. Where it does not, "
            f"it cannot.\n")
    top = sorted((d for d in by_cty.items() if d[1]["censored"] >= 5000),
                 key=lambda kv: -kv[1]["censored"])[:10]
    if top:
        L += ["## Substitution at source, by reporting country", "",
              "Countries with at least \\num{5000} below-quantification "
              "station-years.", "",
              "| Country | below-LOQ rows | of which carry a positive value | "
              "share |", "|---|---|---|---|"]
        for c, d in top:
            L.append(f"| {c} | {d['censored']:,} | {d['substituted']:,} | "
                     f"{100*d['substituted']/d['censored']:.1f}\\% |")
        L.append("")
    L.append("Every condition above is expressed by a shape published with the "
             "ontology, so a reporting authority can run this check on its own "
             "submission without adopting anything else from this work.\n")
    (EVAL / "source_conformance.md").write_text("\n".join(L) + "\n",
                                                encoding="utf-8")
    print(f"  wrote {(EVAL/'source_conformance.md').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
