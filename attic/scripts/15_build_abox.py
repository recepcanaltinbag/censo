#!/usr/bin/env python3
"""
Populate CENSO with the survey: build the knowledge graph.

WHY THIS SCRIPT EXISTS
----------------------
Until now every analysis in this project ran over CSV in plain Python, and the
ontology stood beside the work rather than carrying it. A referee is entitled to
ask whether the vocabulary was ever actually used. This script answers that by
expressing the survey AS CENSO: analytes, analytical methods with their limits,
campaigns, stations, thresholds with their regulation, and one
sosa:Observation per measurement, typed by its detection status and carrying the
interval its result establishes.

WHAT IS ASSERTED, AND WHAT IS DERIVED
-------------------------------------
Asserted here: identity, structure, the reported value, and the detection status
where it can be established from a published limit.
NOT asserted here: the compliance verdict. That is left to the rule layer and
SHACL, so the graph can be shipped without prejudging the assessment.

DETECTION STATUS
----------------
  reported 0, LOD known        -> CensoredObservation,  bounds [0, LOD]
  reported 0, LOD unknown      -> UnresolvedObservation, no bounds asserted
  0 < value < LOQ              -> EstimatedObservation,  bounds [LOD, LOQ]
  value >= LOQ (or no LOQ)     -> QuantifiedObservation, bounds [v(1-u), v(1+u)]
A reported zero is never written as a measured zero; censo:reportedValue keeps
the source number verbatim for provenance and censo:censoringRecovered records
that the status was reconstructed rather than recorded at source.

SCALE
-----
The full graph is ~76k observations. Turtle output is streamed rather than built
in memory. OWL RL closure over the whole graph is impractical in pure Python
(see eval/reasoning_benchmark.md), so --campaign emits one campaign for
reasoning experiments while the full file remains available for SPARQL.

Inputs  : derived/processed/{measurements,analytes,stations_snapped,eu_eqs,
                             substances}.csv
Outputs : derived/abox/censo-ergene[-Cn].ttl
          eval/abox_build.md

Usage:  python scripts/15_build_abox.py [--campaign C3] [--limit N]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
OUT = ROOT / "derived" / "abox"
EVAL = ROOT / "eval"

EX = "https://w3id.org/censo/ergene/"
REL_UNCERTAINTY = 0.20      # combined relative analytical uncertainty, conservative

HEADER = f"""@prefix censo:   <https://w3id.org/censo/> .
@prefix cereg:   <https://w3id.org/censo/reg/> .
@prefix ex:      <{EX}> .
@prefix owl:     <http://www.w3.org/2002/07/owl#> .
@prefix rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .
@prefix skos:    <http://www.w3.org/2004/02/skos/core#> .
@prefix sosa:    <http://www.w3.org/ns/sosa/> .
@prefix geo:     <http://www.opengis.net/ont/geosparql#> .
@prefix qudt:    <http://qudt.org/schema/qudt/> .
@prefix prov:    <http://www.w3.org/ns/prov#> .
@prefix dcterms: <http://purl.org/dc/terms/> .

<{EX}> a owl:Ontology ;
    dcterms:title "Ergene River Basin micropollutant survey, expressed in CENSO"@en ;
    dcterms:source <https://doi.org/10.1016/j.scitotenv.2020.143656> ;
    dcterms:description \"\"\"Four seasonal campaigns, 75 stations. Detection status
is reconstructed from published limits of detection where available and marked
as reconstructed; it was not recorded at source.\"\"\"@en ;
    owl:imports <https://w3id.org/censo/> , <https://w3id.org/censo/reg/> .

ex:ugPerL a qudt:Unit ; rdfs:label "microgram per litre"@en .
ex:m3PerS a qudt:Unit ; rdfs:label "cubic metre per second"@en .

ex:eu-eqs-consolidated-2026 a cereg:RegulationPackage ;
    rdfs:label "Directive 2008/105/EC, consolidated text in force 10 May 2026"@en ;
    censo:regulationVersion "consolidated 2026-05-10" ;
    cereg:jurisdiction "EU" ;
    cereg:legalReference "Directive 2008/105/EC as amended" ;
    cereg:sourceDocument <https://eur-lex.europa.eu/eli/dir/2008/105/oj> .
"""

CAMPAIGN_LABEL = {"C1": ("summer", "2017-08"), "C2": ("autumn", "2017-11"),
                  "C3": ("winter", "2018-02"), "C4": ("spring", "2018-05")}


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    return s[:70] or "x"


def num(x):
    if x in ("", None):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def dec(x) -> str:
    """xsd:decimal literal. Decimal, not double: thresholds are exact."""
    return f'"{x:.10g}"^^xsd:decimal'


def load(name):
    p = PROC / name
    if not p.exists():
        sys.exit(f"missing {p}; run the earlier scripts first")
    return list(csv.DictReader(p.open(encoding="utf-8")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", help="emit only this campaign (C1..C4)")
    ap.add_argument("--limit", type=int, help="cap the number of observations")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    EVAL.mkdir(parents=True, exist_ok=True)

    analytes = {a["parameter"]: a for a in load("analytes.csv")}
    stations = {s["station"]: s for s in load("stations_snapped.csv")}
    measurements = load("measurements.csv")

    cas_of = {}
    chebi_of = {}
    if (PROC / "substances.csv").exists():
        for r in load("substances.csv"):
            if r.get("cas"):
                cas_of[r["analyte"]] = r["cas"]
            if r.get("chebi_id"):
                chebi_of[r["analyte"]] = r["chebi_id"]

    eu_by_cas = {}
    if (PROC / "eu_eqs.csv").exists():
        for r in load("eu_eqs.csv"):
            for c in (r.get("all_cas") or "").split(";"):
                if c.strip():
                    eu_by_cas.setdefault(c.strip(), r)

    suffix = f"-{args.campaign}" if args.campaign else ""
    path = OUT / f"censo-ergene{suffix}.ttl"
    stats = Counter()

    with path.open("w", encoding="utf-8") as fh:
        fh.write(HEADER)

        # ---- campaigns ----
        fh.write("\n# --- campaigns ---\n")
        for cid, (season, period) in CAMPAIGN_LABEL.items():
            if args.campaign and cid != args.campaign:
                continue
            fh.write(f'ex:campaign-{cid} a censo:Campaign ;\n'
                     f'    rdfs:label "{season} {period}"@en .\n')
            stats["campaigns"] += 1

        # ---- stations ----
        fh.write("\n# --- stations ---\n")
        for sid, s in sorted(stations.items(), key=lambda kv: int(kv[0])):
            lat, lon = num(s.get("lat")), num(s.get("lon"))
            fh.write(f'ex:station-{sid} a sosa:FeatureOfInterest ;\n'
                     f'    rdfs:label "Ergene station {sid}"@en')
            if lat is not None and lon is not None:
                fh.write(f' ;\n    geo:asWKT "POINT({lon:.6f} {lat:.6f})"'
                         f'^^geo:wktLiteral')
            if s.get("seg_id"):
                fh.write(f' ;\n    ex:onSegment "{s["seg_id"]}"')
            fh.write(" .\n")
            stats["stations"] += 1

        # ---- analytes, methods, thresholds ----
        fh.write("\n# --- analytes, analytical methods and thresholds ---\n")
        for name, a in sorted(analytes.items()):
            if a["group"] not in ("micropollutant", "metal", "conventional"):
                continue
            an = f"ex:analyte-{slug(name)}"
            fh.write(f'{an} a censo:Analyte ;\n'
                     f'    rdfs:label {csv_str(name)}@en')
            if cas_of.get(name):
                fh.write(f' ;\n    censo:casNumber "{cas_of[name]}"')
            if chebi_of.get(name):
                fh.write(f' ;\n    skos:exactMatch '
                         f'<http://purl.obolibrary.org/obo/{chebi_of[name].replace(":", "_")}>')
            fh.write(" .\n")
            stats["analytes"] += 1

            lod, loq = num(a.get("lod")), num(a.get("loq"))
            if lod is not None:
                m = f"ex:method-{slug(name)}"
                fh.write(f'{m} a censo:AnalyticalMethod ;\n'
                         f'    rdfs:label "LC-MS/MS determination of {name}"@en ;\n'
                         f'    censo:determinesAnalyte {an} ;\n'
                         f'    censo:limitOfDetection {dec(lod)} ;\n'
                         f'    censo:limitUnit ex:ugPerL')
                if loq is not None:
                    fh.write(f' ;\n    censo:limitOfQuantification {dec(loq)}')
                if num(a.get("r2")) is not None:
                    fh.write(f' ;\n    censo:calibrationR2 {dec(num(a["r2"]))}')
                fh.write(" .\n")
                stats["methods"] += 1

            eu = eu_by_cas.get(cas_of.get(name, ""))
            if eu:
                for col, cls, lab in (("mac_inland", "MaximumAllowableThreshold",
                                       "MAC-EQS"),
                                      ("aa_inland", "AnnualAverageThreshold",
                                       "AA-EQS")):
                    v = num(eu.get(col))
                    if v is None:
                        continue
                    t = f"ex:threshold-{slug(name)}-{col}"
                    fh.write(f'{t} a censo:{cls} ;\n'
                             f'    rdfs:label "{lab} for {name}, inland surface waters"@en ;\n'
                             f'    censo:thresholdValue {dec(v)} ;\n'
                             f'    censo:thresholdUnit ex:ugPerL ;\n'
                             f'    censo:definedBy ex:eu-eqs-consolidated-2026 ;\n'
                             f'    censo:appliesToAnalyte {an} ;\n'
                             f'    cereg:transcriptionStatus '
                             f'cereg:TranscribedFromSecondarySource .\n')
                    stats["thresholds"] += 1

        # ---- observations ----
        fh.write("\n# --- observations ---\n")
        n = 0
        for m in measurements:
            if args.campaign and m["campaign"] != args.campaign:
                continue
            p = m["parameter"]
            a = analytes.get(p)
            if not a or a["group"] not in ("micropollutant", "metal",
                                           "conventional"):
                continue
            v = num(m["value_num"])
            if v is None:
                continue
            if args.limit and n >= args.limit:
                break
            n += 1

            lod, loq = num(a.get("lod")), num(a.get("loq"))
            an = f"ex:analyte-{slug(p)}"
            oid = f"ex:obs-{m['campaign']}-{m['station']}-{slug(p)}"
            is_nd = (v == 0.0)

            if is_nd and lod is None:
                cls, lo, hi = "UnresolvedObservation", None, None
                stats["unresolved"] += 1
            elif is_nd:
                cls, lo, hi = "CensoredObservation", 0.0, lod
                stats["censored"] += 1
            elif loq is not None and v < loq:
                cls, lo, hi = "EstimatedObservation", (lod or 0.0), loq
                stats["estimated"] += 1
            else:
                cls = "QuantifiedObservation"
                lo, hi = v * (1 - REL_UNCERTAINTY), v * (1 + REL_UNCERTAINTY)
                stats["quantified"] += 1

            fh.write(f'{oid} a sosa:Observation , censo:{cls} ;\n'
                     f'    censo:hasAnalyte {an} ;\n'
                     f'    censo:atStation ex:station-{m["station"]} ;\n'
                     f'    censo:duringCampaign ex:campaign-{m["campaign"]} ;\n'
                     f'    censo:reportedValue {dec(v)}')
            if lod is not None:
                fh.write(f' ;\n    sosa:usedProcedure ex:method-{slug(p)}')
            if lo is not None:
                fh.write(f' ;\n    censo:resultLowerBound {dec(lo)} ;\n'
                         f'    censo:resultUpperBound {dec(hi)}')
            if is_nd:
                # the status was reconstructed, not recorded at source
                fh.write(' ;\n    censo:censoringRecovered true')
            fh.write(" .\n")
            stats["observations"] += 1

    size_mb = path.stat().st_size / 1e6
    # Report the triple count: it is quoted in the paper and every quoted number
    # must come from a generated artefact, not from a console line.
    n_triples = None
    try:
        import rdflib
        _g = rdflib.Graph()
        _g.parse(path, format="turtle")
        n_triples = len(_g)
    except Exception:
        pass

    L = []
    A = L.append
    A("# Knowledge graph build\n")
    A("Generated by `scripts/15_build_abox.py`. The survey expressed in CENSO, "
      "so the vocabulary carries the data rather than standing beside it.\n")
    A(f"- output: `{path.relative_to(ROOT)}` ({size_mb:.1f} MB)")
    if n_triples is not None:
        A(f"- triples: **{n_triples:,}**")
    if args.campaign:
        A(f"- restricted to campaign **{args.campaign}**")
    A("")
    A("| entity | count |")
    A("|---|---|")
    for k in ("campaigns", "stations", "analytes", "methods", "thresholds",
              "observations"):
        A(f"| {k} | {stats[k]:,} |")
    A("")
    A("## Detection status assigned\n")
    A("| status | n | share |")
    A("|---|---|---|")
    tot = sum(stats[k] for k in ("censored", "estimated", "quantified",
                                 "unresolved"))
    for k in ("censored", "estimated", "quantified", "unresolved"):
        A(f"| `{k}` | {stats[k]:,} | {100*stats[k]/tot:.1f}% |")
    A("")
    A(f"**{stats['unresolved']:,} observations ({100*stats['unresolved']/tot:.1f}%) "
      f"are `UnresolvedObservation`**: a zero was reported but no limit of "
      f"detection is published for the analyte, so the status cannot be "
      f"established. The graph says so rather than guessing, and those "
      f"observations are excluded from assessment by the axiom "
      f"`UnresolvedObservation ⊑ ¬∃assessableAgainst.Threshold`.\n")
    A("## What is deliberately not asserted\n")
    A("No compliance verdict appears in this graph. Verdicts are materialised "
      "by the rule layer and SHACL, so the published knowledge graph does not "
      "prejudge an assessment that depends on which regulation is applied.\n")
    A("Every reported zero is kept verbatim in `censo:reportedValue`, and every "
      "reconstructed status carries `censo:censoringRecovered true`, so a "
      "consumer can distinguish what was measured from what was inferred.\n")

    text = "\n".join(L)
    (EVAL / "abox_build.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nwrote: {path}")
    return 0


def csv_str(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


if __name__ == "__main__":
    raise SystemExit(main())
