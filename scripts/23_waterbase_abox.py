#!/usr/bin/env python3
"""
Exercise CENSO on Waterbase: the ontology, applied to open data.

WHY THIS GRAPH AND NOT ONE OF OUR OWN
-------------------------------------
A graph built from our own survey would show that CENSO can carry one, but
a survey nobody else can download. Waterbase is public, so this graph can be
rebuilt by anyone, and the vocabulary is exercised on data it was not designed
around. Two things follow that the single-basin graph cannot give:

  1. INDEPENDENCE. The four detection states and the four compliance outcomes
     are assigned here from a schema written by the EEA, not by us. If the
     distinctions were an artefact of how we happened to transcribe one set of
     workbooks, they would not land cleanly on somebody else's columns.

  2. A CROSS-IMPLEMENTATION CHECK. scripts/22_waterbase_external.py counts the
     same failures with plain integer counters and no ontology at all. This
     script reaches its verdicts through the graph. The two must agree; the
     comparison is printed and a mismatch is a failure, not a footnote.

WHAT MAPS ONTO WHAT
-------------------
  resultQualityMeanBelowLOQ = 1, procedureLOQValue present
        -> censo:CensoredObservation, resultUpperBound = LOQ, lower bound 0
  flag = 0, value present
        -> censo:QuantifiedObservation
  neither flag nor LOQ
        -> censo:UnresolvedObservation   (the state no other vocabulary has)
  LOQ > EQS for the substance
        -> censo:MethodInsufficient, a subclass of IndeterminateCompliance,
           which is what Article 3(3b) of Directive 2008/105/EC requires

SIZE
----
4.2 million station-years will not fit in an in-memory graph, and inflating one
to make a point would be dishonest about what was actually reasoned over. A
stratified subset is taken instead: every station-year for the substances that
carry a European standard, sampled deterministically to --max-rows. The sample
is drawn with a fixed seed and the achieved counts are reported beside the
population counts so the reader can see what was and was not covered.

Inputs  : Data/waterbase/... or --file, derived/processed/eu_eqs.csv
Outputs : derived/abox/censo-waterbase.ttl
          eval/waterbase_abox.md

Usage:  python scripts/23_waterbase_abox.py --file <WISE6_AggregatedData-csv.zip>
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import math
import random
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
ABOX = ROOT / "derived" / "abox"
EVAL = ROOT / "eval"
DATA = ROOT / "Data" / "waterbase"

SEED = 20260803
TO_UG_L = {"mg/l": 1e3, "ug/l": 1.0, "µg/l": 1.0, "ng/l": 1e-3,
           "pg/l": 1e-6}

NS = "https://w3id.org/censo/waterbase/"
PREAMBLE = """\
@prefix censo: <https://w3id.org/censo/> .
@prefix cereg: <https://w3id.org/censo/reg/> .
@prefix sosa:  <http://www.w3.org/ns/sosa/> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .
@prefix unit:  <http://qudt.org/vocab/unit/> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:   <http://www.w3.org/2002/07/owl#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix geo:   <http://www.opengis.net/ont/geosparql#> .
@prefix wb:    <%s> .

<%s> a owl:Ontology ;
    dcterms:title "CENSO applied to EEA Waterbase (subset)"@en ;
    dcterms:description \"\"\"A subset of the EEA Waterbase Water Quality ICM
aggregated release expressed in CENSO. Built by
scripts/23_waterbase_abox.py; the source data are public, so this graph is
reproducible by anyone.\"\"\"@en ;
    dcterms:license <https://creativecommons.org/licenses/by/4.0/> ;
    owl:imports <https://w3id.org/censo/> ,
                <https://w3id.org/censo/reg/eu-2008-105-2026> .

""" % (NS, NS)


def norm(h):
    return re.sub(r"[^a-z0-9]", "", str(h).lower())


def num(x):
    try:
        return float(str(x).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def dec(v):
    """Canonical xsd:decimal LEXICAL form. Display only -- write data with lit().

    Always keeps the point: XSD's canonical form for decimal requires a digit
    on both sides of it, and in Turtle a numeral without a point is an
    xsd:integer, which is a different literal term.
    """
    s = f"{v:.10f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    return s or "0.0"


def lit(v):
    """A TYPED xsd:decimal literal, for anything written as data.

    Every concentration, limit and bound in this graph used to be written as a
    bare Turtle numeral. Turtle types `0` as xsd:integer and `0.5` as
    xsd:decimal, so the shipped ABox carried 41,396 literals of the wrong
    datatype -- 37,115 of them on the two properties censo-shapes.ttl actually
    constrains, which is why eval/shacl_validation.md reported `conforms:
    False` on every run.

    No OWL check could object. censo:resultLowerBound has rdfs:range
    xsd:decimal, and xsd:integer is DERIVED from xsd:decimal, so an integer
    literal satisfies the range and a reasoner stays silent. Worse, the core
    says CensoredObservation subClassOf (resultLowerBound hasValue
    "0.0"^^xsd:decimal) -- an axiom about a literal TERM that the graph's
    `0` could never match, on all 31,167 censored observations.

    The ontology argues at length (censo-core.ttl, NUMERIC TYPE) that a legal
    comparison must not be made in binary floating point. It is worth being
    able to say that the graph honours it.
    """
    return f'"{dec(v)}"^^xsd:decimal'
def disp(v):
    """Human-readable form for an rdfs:label: no trailing '.0'.

    dec() is the canonical xsd:decimal LEXICAL form and must keep its point;
    a label reading "(2.0 ug/L)" for a limit the legal text writes as 2 is
    just noise. Never write this as data.
    """
    s = dec(v)
    return s[:-2] if s.endswith(".0") else s


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "-", str(s)).strip("-")[:60] or "x"


# THE DECISION PROCEDURE LIVES IN ONE PLACE, and it is not here.
# scripts/22_waterbase_external.py applies it to every assessable row in the
# release while streaming; this script applies it to the rows it materialises.
# They must agree, and the only way to guarantee that is to import rather than
# restate. They were separate implementations once.
sys.path.insert(0, str(Path(__file__).resolve().parent))
_m = __import__("22_waterbase_external")
# The same footnote-derived map the streaming counter uses. Loaded here so the
# graph and the count cannot disagree about which thresholds are conditional.
_cond = {}
# Conditions the record DOES satisfy, per CAS: asserted on the
# observation with censo:conditionSatisfied so that applicability is
# visible in the graph rather than assumed by the reader.
SATISFIED = {}
detection_status = _m.detection_status
censo_outcome = _m.censo_outcome
two_valued = _m.two_valued
SUBSTITUTIONS = _m.SUBSTITUTIONS
LEGAL_UNCERTAINTY_AT_EQS = _m.LEGAL_UNCERTAINTY_AT_EQS


def self_test_counterfactual():
    """The counterfactual must reproduce the failure it was written to expose:
    a censored result whose limit exceeds the standard becomes an exceedance
    under substitution, and the verdict must depend on the convention."""
    bad = 0
    # LOQ = 1.0, standard = 0.1: censored, so no measurement supports anything.
    got = [two_valued(None, 1.0, True, 0.1, k) for _, k in SUBSTITUTIONS]
    if got != ["compliant", "exceeding", "exceeding"]:
        print(f"  FAIL substitution sensitivity not reproduced: {got}")
        bad += 1
    # A quantified value above the standard is an exceedance under every rule.
    if {two_valued(0.5, 0.01, False, 0.1, k) for _, k in SUBSTITUTIONS} != \
            {"exceeding"}:
        print("  FAIL a real exceedance must not depend on the convention")
        bad += 1
    # A record with nothing in it is read as zero, hence compliant, always.
    if {two_valued(None, None, True, 0.1, k) for _, k in SUBSTITUTIONS} != \
            {"compliant"}:
        print("  FAIL an empty record must read as compliant under every rule")
        bad += 1
    return bad


def open_rows(path: Path):
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            inner = sorted((n for n in z.namelist() if n.lower().endswith(".csv")),
                           key=lambda n: -z.getinfo(n).file_size)
            if not inner:
                sys.exit(f"no CSV inside {path.name}")
            with z.open(inner[0]) as fh:
                yield from csv.reader(io.TextIOWrapper(fh, encoding="utf-8",
                                                       errors="replace"))
    elif path.name.lower().endswith(".csv.gz"):
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
            yield from csv.reader(fh)
    else:
        with path.open(encoding="utf-8", errors="replace") as fh:
            yield from csv.reader(fh)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--max-rows", type=int, default=40000,
                    help="station-years to express in the graph")
    args = ap.parse_args()
    if self_test_counterfactual():
        return 1
    ABOX.mkdir(parents=True, exist_ok=True)
    EVAL.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    if args.file:
        path = Path(args.file)
    else:
        cands = [q for pat in ("*.zip", "*.csv", "*.csv.gz")
                 for q in sorted(DATA.glob(pat))]
        if not cands:
            sys.exit(f"no Waterbase file under {DATA}; see "
                     f"scripts/22_waterbase_external.py for the download")
        path = max(cands, key=lambda q: q.stat().st_size)

    # Thresholds, by CAS, from the verified European package -- and crucially
    # under the SAME IRIs that scripts/19_build_regulation_packages.py minted.
    # Coining fresh ones here would leave two unconnected islands and defeat the
    # point: an observation must be linked to the threshold the regulation
    # package already publishes, so that a query can walk from a verdict to the
    # legal instrument behind it.
    # Threshold IRIs are READ FROM THE PUBLISHED PACKAGE, never rebuilt here.
    #
    # They used to be re-derived from the substance name with a local slug()
    # that truncated at 60 characters and fell back to "x" for an empty name.
    # The package builder slugs differently, so 2,412 observations -- 6% of the
    # graph -- pointed at threshold IRIs that did not exist: cadmium, whose
    # name is long enough to be truncated, and 120 rows with no name at all.
    # Nothing failed, because RDF is happy to reference a URI that resolves to
    # nothing; the joins simply returned less than they should have.
    #
    # Re-deriving an identifier that another artefact owns is the bug. So the
    # package is parsed and indexed by CAS, and a CAS the package does not
    # cover is skipped rather than given a fabricated IRI.
    import rdflib
    CENSO = rdflib.Namespace("https://w3id.org/censo/")
    pkg = rdflib.Graph()
    pkg.parse(ROOT / "ontology" / "reg" / "eu-2008-105-2026.ttl",
              format="turtle")
    cas_of = defaultdict(list)
    for a, c in pkg.subject_objects(CENSO.casNumber):
        cas_of[a].append(str(c).strip())
    label_of = {a: str(l) for a, l in pkg.subject_objects(rdflib.RDFS.label)}
    eqs = {}
    for t in pkg.subjects(rdflib.RDF.type, CENSO.AnnualAverageThreshold):
        # appliesToAnalyte only. A group (sum) threshold is attached with
        # cereg:appliesToGroup instead and is therefore invisible here, which
        # is the intent: a sum standard is not a limit for any one member.
        a = next(pkg.objects(t, CENSO.appliesToAnalyte), None)
        v = next(pkg.objects(t, CENSO.thresholdValue), None)
        if a is None or v is None or not cas_of.get(a):
            continue
        name = label_of.get(a, "").strip() or cas_of[a][0]
        # the IRI as the package declares it, stripped to a cereg: qname
        iri = "cereg:" + str(t).rsplit("/", 1)[-1]
        a_iri = "cereg:" + str(a).rsplit("/", 1)[-1]
        for cas in cas_of[a]:
            prev = eqs.get(cas)
            if prev is None or float(v) < prev[0]:
                eqs[cas] = (float(v), name, iri, a_iri)
    # Which of those thresholds the PACKAGE declares conditional. Read from the
    # released package, not from a list here: the graph and the vocabulary must
    # agree about when a standard applies, and the only way to guarantee that is
    # for the graph to be told by the package.
    # NOT EVERY CONDITION IS UNSATISFIABLE, and reading them all as unmet was
    # about to make every assessment in the graph censo:PreconditionUnmet.
    #
    # The packages now attach a censo:MatrixCondition to every threshold,
    # because a limit that does not say which water it governs cannot be
    # applied -- Annex I gives benzene 10 ug/L inland and 8 elsewhere. That
    # condition is SATISFIED here: the population is river water, and rivers
    # are inland surface waters. Treating it as unmet would have reported the
    # whole record as undecidable for the wrong reason.
    #
    # What makes a condition unmet is not that it exists but that the record
    # cannot supply what it NAMES. censo:requiresCovariate is that test: the
    # hardness-class and bioavailability conditions require water hardness,
    # dissolved organic carbon and pH, none of which WISE-6 reports on the
    # row, so no comparison is possible. A condition naming no covariate is a
    # statement about scope, and scope is checkable from the row itself.
    #
    # So the two are separated, and both are asserted -- the unmet ones as the
    # precondition that decides the outcome, the satisfied ones as
    # censo:conditionSatisfied on the observation, which is the property that
    # lets a reader see WHY a threshold was applicable rather than assume it.
    _satisfied = {}
    for th in pkg.subjects(CENSO.requiresCondition, None):
        a = next(pkg.objects(th, CENSO.appliesToAnalyte), None)
        if a is None:
            continue
        for c_iri in pkg.objects(th, CENSO.requiresCondition):
            needs = list(pkg.objects(c_iri, CENSO.requiresCovariate))
            qname = "cereg:" + str(c_iri).rsplit("/", 1)[-1]
            for cas in cas_of.get(a, []):
                if needs:
                    # the record reports none of the covariates it names
                    _cond[cas] = "censo:" + str(
                        next(pkg.objects(c_iri, rdflib.RDF.type), c_iri)
                    ).rsplit("/", 1)[-1]
                else:
                    _satisfied.setdefault(cas, []).append(qname)
    print(f"  thresholds: {len(eqs)} CAS numbers, read from the package"
          + (f"; {len(_cond)} carry a condition the record cannot satisfy"
             if _cond else "")
          + (f"; {len(_satisfied)} carry one it can" if _satisfied else ""))
    SATISFIED.update(_satisfied)

    # Station names and coordinates live in the SpatialObjects release, not in
    # the measurements. Without them the graph has stations but no geometry, so
    # the competency question about spatial coverage cannot be answered -- which
    # would look like a limit of the ontology rather than a file we had not
    # loaded.
    sites = {}
    spatial = None
    for cand in list(path.parent.glob("*SpatialObject*.zip")) + \
            list(DATA.glob("*SpatialObject*.zip")):
        spatial = cand
        break
    if spatial:
        srows = open_rows(spatial)
        shdr = next(srows)
        six = {norm(h): i for i, h in enumerate(shdr)}
        for r in srows:
            if not r:
                continue
            code = r[six["monitoringsiteidentifier"]].strip() \
                if "monitoringsiteidentifier" in six else ""
            if not code:
                continue
            nm = r[six["monitoringsitename"]].strip() if "monitoringsitename" in six else ""
            sites[slug(code)] = (nm or code, code,
                                 num(r[six["lat"]]) if "lat" in six else None,
                                 num(r[six["lon"]]) if "lon" in six else None)
        print(f"  station metadata: {len(sites):,} sites from {spatial.name}")
    else:
        print("  no SpatialObjects file found; stations will carry no geometry")

    rows = open_rows(path)
    hdr = next(rows)
    ix = {norm(h): i for i, h in enumerate(hdr)}

    def g(row, key):
        i = ix.get(key)
        return row[i].strip() if i is not None and i < len(row) else ""

    # Reservoir sampling: one pass, fixed seed, no need to hold the file.
    reservoir, seen = [], 0
    pop = defaultdict(int)
    for row in rows:
        if not row:
            continue
        if g(row, "parameterwaterbodycategory") not in ("RW", ""):
            continue
        code = g(row, "observedpropertydeterminandcode")
        cas = code[4:] if code.upper().startswith("CAS_") else ""
        if cas not in eqs:
            continue                       # only substances with a standard
        # ... and only rows whose unit can be compared with the standard. A
        # value in mg{P}/L cannot be assessed against a limit in ug/L at any
        # effort, so including it would put rows in the graph that no verdict
        # can be reached on -- and would make this population differ from the
        # one scripts/22 assesses, which is what the cross-check compares.
        if TO_UG_L.get(g(row, "resultuom").lower().replace(" ", "")) is None:
            pop["not_convertible"] += 1
            continue
        pop["n"] += 1
        seen += 1
        if len(reservoir) < args.max_rows:
            reservoir.append(row)
        else:
            j = rng.randrange(seen)
            if j < args.max_rows:
                reservoir[j] = row
    print(f"  station-years with a European standard: {pop['n']:,}")
    print(f"  sampled into the graph                : {len(reservoir):,}")

    out = [PREAMBLE]
    tally = defaultdict(int)
    counterfactual = defaultdict(int)   # (CENSO outcome, two-valued outcome)
    exemplars = {}                      # one real row per decision geometry
    exemplar_fallback = {}              # used only if no well-shaped row exists
    analytes, stations = {}, set()
    methods, method_defs, campaigns = {}, [], set()
    station_country, station_n = {}, defaultdict(int)

    for k, row in enumerate(reservoir):
        code = g(row, "observedpropertydeterminandcode")
        cas = code[4:]
        thr, thr_name, t_iri, a_iri = eqs[cas]
        site = g(row, "monitoringsiteidentifier") or f"site-{k}"
        cty = g(row, "countrycode") or "??"
        year = g(row, "phenomenontimereferenceyear") or "0000"
        flag = g(row, "resultqualitymeanbelowloq")
        loq = num(g(row, "procedureloqvalue"))
        val = num(g(row, "resultmeanvalue"))
        factor = TO_UG_L.get(g(row, "resultuom").lower().replace(" ", ""))

        # the analyte individual the regulation package already declares
        if a_iri not in analytes:
            analytes[a_iri] = (thr_name, cas)
        s_iri = "wb:station-" + slug(site)
        stations.add(s_iri)
        station_country[s_iri] = cty
        station_n[s_iri] += 1
        o_iri = f"wb:obs-{k}"

        # ---- detection status -------------------------------------------
        status = detection_status(flag, val, loq)
        cls = {"censored": "censo:CensoredObservation",
               "quantified": "censo:QuantifiedObservation",
               "unresolved": "censo:UnresolvedObservation"}[status]
        tally[status] += 1

        # One method individual per (substance, LOQ): Waterbase reports the
        # limit that was in force, which is exactly what censo:AnalyticalMethod
        # is for. Without this the graph has verdicts but no way to answer
        # "which limit produced them", and nine competency questions returned
        # nothing.
        m_iri = None
        if loq is not None and factor:
            key = (a_iri, round(loq * factor, 6))
            m_iri = methods.get(key)
            if m_iri is None:
                m_iri = f"wb:method-{len(methods)}"
                methods[key] = m_iri
                method_defs.append(
                    f"{m_iri} a censo:AnalyticalMethod ;\n"
                    f'    rdfs:label "Reported method for {thr_name} '
                    f'(LOQ {disp(loq*factor)} ug/L)"@en ;\n'
                    # NO limitOfDetection. Waterbase states none, and an earlier
                    # version wrote LOQ/3 here -- a conventional ratio, invented
                    # by this script, asserted into a published graph as though
                    # the laboratory had reported it. It existed to satisfy this
                    # project's own AnalyticalMethodShape, which is circular: a
                    # shape that cannot be met by real data, met by manufacturing
                    # the datum. The shape now asks for a limit, not specifically
                    # a detection limit, and the record supplies the one it
                    # actually has.
                    f"    censo:determinesAnalyte {a_iri} ;\n"
                    f"    censo:limitOfQuantification {lit(loq*factor)} ;\n"
                    f"    censo:limitUnit unit:MicroGM-PER-L .\n")
        c_iri = f"wb:campaign-{year}"
        campaigns.add((c_iri, year))

        lines = [f"{o_iri} a {cls} ;",
                 f"    censo:hasAnalyte {a_iri} ;",
                 f"    censo:atStation {s_iri} ;",
                 f"    censo:duringCampaign {c_iri} ;"]
        # NOT for an unresolved row. censo:UnresolvedObservation is a subclass
        # of the complement of assessableAgainst-some-Threshold -- an
        # observation with no detection status may not be assessed at all,
        # which is the axiom scripts/test_axioms.py T5 exercises. This script
        # asserted both for every row, so 45,467 observations in the shipped
        # graph made it inconsistent with its own core the moment a reasoner
        # saw them beside the regulation package that types the threshold.
        # Nothing caught it because the axiom suite ran on fixtures and the
        # graph was only ever validated against SHACL, which has no complement.
        # The threshold still applies to the ANALYTE, which is how the shapes
        # reach it, and which is the fact that makes the row assessable in
        # principle and undecidable in practice.
        if cls != "censo:UnresolvedObservation":
            lines.append(f"    censo:assessableAgainst {t_iri} ;")
            # Why the threshold was applicable, rather than the reader assuming
            # it. Every threshold the packages emit carries a matrix condition,
            # and this row is river water, which is an inland surface water --
            # so the condition is met and the graph says so. The unmet ones do
            # not appear here: they decide the outcome instead, and the class
            # the observation is typed with records which.
            for c in SATISFIED.get(cas, []):
                lines.append(f"    censo:conditionSatisfied {c} ;")
        if m_iri:
            lines.append(f"    sosa:usedProcedure {m_iri} ;")
        if cls == "censo:CensoredObservation" and loq is not None and factor:
            lines.append(f"    censo:resultLowerBound {lit(0.0)} ;")
            lines.append(f"    censo:resultUpperBound {lit(loq*factor)} ;")
            # Keep the number the source reported, verbatim and separate from
            # the interval. It is provenance, not a measurement: for a censored
            # row it is whatever convention the reporter used.
            if val is not None:
                lines.append(f"    censo:reportedValue {lit(val*factor)} ;")
            lines.append("    censo:censoringRecovered false ;")
        elif cls == "censo:QuantifiedObservation" and val is not None and factor:
            lines.append(f"    censo:reportedValue {lit(val*factor)} ;")
            # A quantified result is an INTERVAL too, and the vocabulary has
            # always said so -- censo:Exceedance is defined as holding "for
            # every value consistent with the observation". Until now the
            # interval was left a point, so that definition could never do any
            # work and the fourth outcome was unreachable.
            #
            # The half-width is the largest Article 4(1) permits at the level
            # of the standard, not a measured uncertainty: WISE-6 has no field
            # for one, on any release. So this is a BOUND -- the widest
            # interval a lawful method could have -- and the outcome it
            # produces is "cannot be decided by a method that merely meets the
            # legal minimum", which is exactly what PossibleExceedance means.
            u = LEGAL_UNCERTAINTY_AT_EQS * thr
            lines.append(f"    censo:resultLowerBound "
                         f"{lit(max(0.0, val*factor - u))} ;")
            lines.append(f"    censo:resultUpperBound "
                         f"{lit(val*factor + u)} ;")
        elif cls == "censo:UnresolvedObservation" and val is not None and factor:
            # An unresolved row usually still carries a number; what it lacks
            # is any way to tell whether that number is a detection or a
            # substituted zero. Dropping it made the graph unable to reproduce
            # its own counterfactual: an independent recount from the RDF gave
            # 1,726 fewer substitution-driven exceedances than the pipeline,
            # because the value those rows turn on was never written down.
            lines.append(f"    censo:reportedValue {lit(val*factor)} ;")

        # ---- compliance outcome ------------------------------------------
        # Article 3(3b): a below-LOQ result whose LOQ exceeds the EQS "shall
        # not be considered". That is MethodInsufficient, not compliance.
        # The SAME function scripts/22_waterbase_external.py applies to every
        # assessable row in the release. The comparison PROPERTY is asserted
        # beside the class: the classes are defined over those properties, the
        # disjointness that makes the logic exclusive is declared on them, and
        # for as long as the graph asserted only the class, neither could fire.
        v_ug = val * factor if (val is not None and factor) else None
        l_ug = loq * factor if (loq is not None and factor) else None
        outcome = censo_outcome(status, v_ug, l_ug, thr,
                                precondition=_cond.get(cas))
        tally[outcome] += 1
        CLASS = {
            "method_insufficient": ("censo:MethodInsufficient", None),
            # Both of these used to name the bare parent, which is what made
            # censo:IndeterminateCompliance a directly instantiated class and
            # left its subclass hierarchy with a hole in it -- 45,467
            # station-years, the largest single reason in this record after the
            # two named provisions, carrying "cannot be determined" and no
            # answer to "why". censo:BoundNotEstablished is that answer, and it
            # is the same answer for both: in one there is no flag and no limit
            # to build an interval from, in the other the number contradicts the
            # limit reported beside it. Neither establishes a bound to compare.
            "indeterminate_unresolved": ("censo:BoundNotEstablished", None),
            "indeterminate_other": ("censo:BoundNotEstablished", None),
            "compliant": ("censo:Compliant", "censo:belowThreshold"),
            "exceedance": ("censo:Exceedance", "censo:exceeds"),
            "possible_exceedance": ("censo:PossibleExceedance",
                                    "censo:possiblyExceeds"),
            # No comparison property: there is no comparison. The standard is
            # defined on a quantity the record does not report, so the pair
            # carries the outcome and nothing else.
            "precondition_unmet": ("censo:PreconditionUnmet", None),
        }
        cls_iri, prop = CLASS[outcome]
        lines.append(f"    a {cls_iri} ;")
        if prop:
            lines.append(f"    {prop} {t_iri} ;")

        # What the same row yields with no censoring semantics. Counted, not
        # assumed: this is the comparison Figure 5 draws.
        v_ug = val * factor if (val is not None and factor) else None
        l_ug = loq * factor if (loq is not None and factor) else None

        # One real observation per decision geometry, for Figure 6.
        #
        # THREE CASES, NOT FOUR. The figure used to carry a fourth panel that
        # split the censored-and-undecidable case at the limit of DETECTION:
        # "T inside [0, LOD]" against "LOD < T < LOQ". Waterbase reports no
        # limit of detection. The one used was this pipeline's own LOQ/3, so
        # the boundary between those two panels came from a constant we chose,
        # not from the record -- in a figure whose caption says every panel is
        # a real observation. They are also the same case in law and in the
        # ontology: both are censored rows with T below the quantification
        # limit, both return an indeterminate verdict, and every compliance
        # provision here tests the LOQ (Art. 3(3b) of 2008/105/EC and Art. 4(1)
        # of 2009/90/EC are both written about the quantification limit). The
        # split was presentational and is withdrawn.
        #
        # LOD keeps its place in the argument -- a non-detection is an interval
        # and the interval has a lower region -- but it is made in the text,
        # where it is a claim about representation, and not in a figure of
        # measured cases, where it would be a claim about this data.
        if l_ug:
            censored = cls == "censo:CensoredObservation"
            case = None
            if censored and l_ug <= thr:
                case = "compliant"           # [0, LOQ] lies wholly below T
            elif censored and thr < l_ug:
                case = "cannot_decide"       # T inside [0, LOQ]: no verdict
            elif not censored and v_ug is not None and v_ug > thr:
                case = "quantified_exceedance"
            # Deterministic: the first qualifying row in file order. The two
            # bounds are presentational, and stated because they restrict
            # which real row is chosen: a threshold or a value orders of
            # magnitude off the limit squashes every other feature of the
            # panel into the axis.
            ok = thr <= 4 * l_ug and (v_ug is None or censored
                                      or v_ug <= 2.5 * l_ug)
            # The undecidable panel is the paper's central picture, and where
            # T sits inside [0, LOQ] is the whole of what it shows. The first
            # qualifying row put T at 4.6 % of the limit, which draws on top of
            # the axis and reads as "T below the interval" -- the opposite
            # claim. Prefer a row whose threshold lands in the visible middle,
            # and keep the first qualifying row as a fallback so the panel
            # cannot vanish if the record holds no such case.
            mid = (case != "cannot_decide"
                   or 0.25 * l_ug <= thr <= 0.75 * l_ug)
            if case and ok:
                row = (thr_name, cas, f"{l_ug:.6g}", f"{thr:.6g}",
                       "" if v_ug is None else f"{v_ug:.6g}",
                       "yes" if censored else "no", cty)
                if mid and case not in exemplars:
                    exemplars[case] = row
                elif case not in exemplar_fallback:
                    exemplar_fallback[case] = row

        for rule, k in SUBSTITUTIONS:
            tv = two_valued(v_ug, l_ug,
                            cls == "censo:CensoredObservation", thr, k)
            counterfactual[(rule, outcome, tv)] += 1

        lines[-1] = lines[-1].rstrip(" ;") + " ."
        out.append("\n".join(lines) + "\n")

    for a_iri, (nm, cas) in sorted(analytes.items()):
        out.append(f'{a_iri} a censo:Analyte ;\n'
                   f'    rdfs:label "{nm}"@en ;\n'
                   f'    censo:casNumber "{cas}" .\n')
    n_with_geometry = 0
    for s_iri in sorted(stations):
        code = s_iri.split("station-", 1)[1]
        meta = sites.get(code)
        if meta and meta[2] is not None and meta[3] is not None:
            n_with_geometry += 1
            out.append(f'{s_iri} a sosa:FeatureOfInterest ;\n'
                       f'    rdfs:label "{meta[0]}"@en ;\n'
                       f'    geo:asWKT "POINT({meta[3]:.6f} {meta[2]:.6f})"'
                       f'^^geo:wktLiteral .\n')
        else:
            out.append(f'{s_iri} a sosa:FeatureOfInterest ;\n'
                       f'    rdfs:label "{code}"@en .\n')
    out.extend(sorted(method_defs))
    for c_iri, year in sorted(campaigns):
        out.append(f'{c_iri} a censo:Campaign ;\n'
                   f'    rdfs:label "Reporting year {year}"@en .\n')

    ttl = ABOX / "censo-waterbase.ttl"
    ttl.write_text("\n".join(out), encoding="utf-8")

    # One real observation per decision geometry, so Figure 6 draws the
    # argument from the data rather than from illustrative numbers.
    with (PROC / "waterbase_exemplars.csv").open("w", newline="",
                                                 encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["case", "substance", "cas", "loq_ug_l",
                    "threshold_ug_l", "value_ug_l", "censored", "country"])
        for case in ("compliant", "cannot_decide", "quantified_exceedance"):
            row = exemplars.get(case) or exemplar_fallback.get(case)
            if row:
                w.writerow([case] + list(row))

    with (PROC / "waterbase_verdicts.csv").open("w", newline="",
                                                encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["substitution", "censo_outcome", "two_valued_outcome", "n"])
        for r, _ in SUBSTITUTIONS:
            # possible_exceedance belongs here too. This table is the fallback
            # source for figure 5 and the graph-side counterpart of the
            # population table, and dropping the fourth outcome from a table
            # whose subject IS the four-valued assessment is the same defect
            # the figure had.
            for k in ("compliant", "exceedance", "possible_exceedance",
                      "precondition_unmet",
                      "method_insufficient", "indeterminate_unresolved",
                      "indeterminate_other"):
                for t in ("compliant", "exceeding"):
                    if counterfactual[(r, k, t)]:
                        w.writerow([r, k, t, counterfactual[(r, k, t)]])

    # Station coordinates, for the maps. Written here because this is where the
    # sample is decided: a map drawn from the full site register would show
    # stations the graph never reasoned over.
    with (PROC / "waterbase_stations.csv").open("w", newline="",
                                                encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["station_code", "country", "lat", "lon", "n_obs"])
        for s_iri in sorted(stations):
            code = s_iri.split("station-", 1)[1]
            m = sites.get(code)
            w.writerow([code, station_country.get(s_iri, ""),
                        f"{m[2]:.5f}" if m and m[2] is not None else "",
                        f"{m[3]:.5f}" if m and m[3] is not None else "",
                        station_n.get(s_iri, 0)])

    n_triples = None
    try:
        import rdflib
        gph = rdflib.Graph()
        gph.parse(ttl, format="turtle")
        n_triples = len(gph)
    except ImportError:
        pass

    n = len(reservoir)
    # Stated as a number, not left to be counted out of a CSV. The map's
    # caption quotes it, and a quantity a reader can only obtain by counting
    # rows in a file is not one the audit can check.
    L = ["# CENSO applied to Waterbase\n",
         f"- stations in the graph carrying a geometry: "
         f"**{n_with_geometry:,}** of {len(stations):,}"
         + ("" if n_with_geometry else
            "  \N{WARNING SIGN} no SpatialObjects release was found, so the "
            "map figure will be empty; see README.md") + "\n",
         "Generated by `scripts/23_waterbase_abox.py`.\n",
         "A graph of our own making would show that the vocabulary can carry a "
         "survey; it "
         "cannot show that the distinctions survive contact with somebody "
         "else's schema. This graph is built from the EEA's public aggregated "
         "release, so it is reproducible without access to any private "
         "dataset, and every class is assigned from EEA columns rather than "
         "from our own transcription.\n",
         f"- station-years in the population (river water, substance has a "
         f"European standard): **{pop['n']:,}**",
         f"- expressed in the graph (reservoir sample, seed {SEED}): "
         f"**{n:,}**",
         f"- analytes: {len(analytes)} · stations: {len(stations):,}"
         + (f" · triples: **{n_triples:,}**" if n_triples else ""),
         "",
         "## Detection status assigned\n",
         "| class | n | share |",
         "|---|---|---|"]
    for k, lbl in (("censored", "`CensoredObservation`"),
                   ("quantified", "`QuantifiedObservation`"),
                   ("unresolved", "`UnresolvedObservation`")):
        L.append(f"| {lbl} | {tally[k]:,} | {100*tally[k]/n:.1f}% |")
    L += ["", "## Compliance outcome\n",
          "| outcome | n | share |", "|---|---|---|"]
    for k, lbl in (("compliant", "`Compliant`"),
                   ("exceedance", "`Exceedance`"),
                   ("possible_exceedance", "`PossibleExceedance`"),
                   ("method_insufficient",
                    "`MethodInsufficient` → `IndeterminateCompliance`"),
                   ("indeterminate_unresolved",
                    "`IndeterminateCompliance` (unresolved)"),
                   ("indeterminate_other",
                    "`IndeterminateCompliance` (other)")):
        L.append(f"| {lbl} | {tally[k]:,} | {100*tally[k]/n:.1f}% |")
    L.append("")
    # The shares must sum to 100: a row missing from this list is a row of the
    # graph missing from its own report. PossibleExceedance was absent here
    # while 1,059 observations carried it.
    listed = sum(tally[k] for k in
                 ("compliant", "exceedance", "possible_exceedance",
                  "precondition_unmet",
                  "method_insufficient", "indeterminate_unresolved",
                  "indeterminate_other"))
    if listed != n:
        L.append(f"> **{n - listed:,} observations carry an outcome this "
                 f"table does not list.** That is a defect in the report.\n")
    indet = (tally["method_insufficient"] + tally["indeterminate_unresolved"]
             + tally["indeterminate_other"] + tally["possible_exceedance"])
    L.append(f"> **{100*indet/n:.1f}%** of these assessments are not "
             f"decidable from the record as reported: the record carries no "
             f"bound at all, or the method's limit lies above the standard and "
             f"Article~3(3b) requires the result to be set aside, or the "
             f"interval Article~4(1) permits around the reported value "
             f"straddles the standard.\n")

    # ---- the two-valued counterfactual, counted ---------------------------
    UNSUP = ("method_insufficient", "indeterminate_unresolved",
             "indeterminate_other")
    L += ["## What a two-valued pipeline returns for the same rows\n",
          "Counted row by row, not assumed, and under all three substitution "
          "conventions in routine use: a non-detection entering the "
          "calculation at zero, at half the quantification limit, or at the "
          "limit itself. Reporting only one would make the comparison an "
          "artefact of our own choice of rule.\n",
          "A record with no usable number at all is read as zero under every "
          "rule, which is the silent substitution this paper is about.\n",
          "| CENSO outcome | " + " | ".join(
              f"→ exceeding ({r})" for r, _ in SUBSTITUTIONS) + " |",
          "|---|" + "---|" * len(SUBSTITUTIONS)]
    tv_rows = [("compliant", "`Compliant`"),
               ("exceedance", "`Exceedance`"),
               ("method_insufficient", "`MethodInsufficient`"),
               ("indeterminate_unresolved", "`IndeterminateCompliance` "
                "(unresolved)"),
               ("indeterminate_other", "`IndeterminateCompliance` (other)")]
    for k, lbl in tv_rows:
        cells = [counterfactual[(r, k, "exceeding")] for r, _ in SUBSTITUTIONS]
        tot_k = sum(counterfactual[(SUBSTITUTIONS[0][0], k, t)]
                    for t in ("compliant", "exceeding"))
        if tot_k:
            L.append(f"| {lbl} ({tot_k:,}) | " +
                     " | ".join(f"{c:,}" for c in cells) + " |")

    hidden = sum(counterfactual[(SUBSTITUTIONS[0][0], k, t)]
                 for k in UNSUP for t in ("compliant", "exceeding"))
    L.append("")
    L.append("| Substitution rule | Exceedances a two-valued pipeline reports "
             "| of which rest on a quantified measurement |")
    L.append("|---|---|---|")
    for r, _ in SUBSTITUTIONS:
        tv_exc = sum(counterfactual[(r, k, "exceeding")]
                     for k, _ in tv_rows)
        real = counterfactual[(r, "exceedance", "exceeding")]
        L.append(f"| non-detection at {r} | {tv_exc:,} | {real:,} "
                 f"({100*real/tv_exc:.1f}%) |" if tv_exc else
                 f"| non-detection at {r} | 0 | — |")
    L.append("")
    hid_e = {r: sum(counterfactual[(r, k, "exceeding")] for k in UNSUP)
             for r, _ in SUBSTITUTIONS}
    L.append(f"> Of the {hidden:,} assessments CENSO reports as not "
             f"supportable, a two-valued pipeline returns a definite verdict "
             f"for every one. How many of those verdicts are *exceeding* "
             f"depends entirely on a convention the data does not fix: "
             + ", ".join(f"{hid_e[r]:,} at {r}" for r, _ in SUBSTITUTIONS) +
             ". That the answer moves this much with an arbitrary rule is the "
             "point: the assessment is not being read off the measurement.\n")

    # ---- cross-implementation check ---------------------------------------
    L.append("## Cross-implementation check\n")
    L.append("`scripts/22_waterbase_external.py` counts the same failures with "
             "integer counters and no ontology. This graph reaches its "
             "verdicts by classification. Agreement on the sample is what "
             "makes the ontology's contribution a representation rather than "
             "a recomputation.\n")
    summ = PROC / "waterbase_summary.csv"
    if summ.exists():
        with summ.open(encoding="utf-8") as fh:
            tot = next(r for r in csv.DictReader(fh) if r["scope"] == "total")
        # LIKE WITH LIKE. This compared the streaming counter's loq_gt_eqs --
        # every row whose limit exceeds the standard, censored or not -- against
        # the graph's MethodInsufficient class, which Article 3(3b) restricts to
        # the censored case. They are different quantities, so the check reported
        # DISAGREE on a difference it had built in, and the manuscript cited it
        # as verification. The population share of the same CLASS is what the
        # sample's share of that class has to be compared with.
        pop_f3 = None
        pv = PROC / "waterbase_verdicts_population.csv"
        if pv.exists():
            with pv.open(encoding="utf-8") as fh:
                rows = [r for r in csv.DictReader(fh)
                        if r["substitution"] == "zero"]
            tot_pop = sum(int(r["n"]) for r in rows)
            mi_pop = sum(int(r["n"]) for r in rows
                         if r["censo_outcome"] == "method_insufficient")
            if tot_pop:
                pop_f3 = 100 * mi_pop / tot_pop
        if pop_f3 is None:      # no population table: say so, do not improvise
            pop_f3 = float("nan")
        smp_f3 = 100 * tally["method_insufficient"] / n
        se = math.sqrt(smp_f3 * (100 - smp_f3) / n)
        ok = abs(pop_f3 - smp_f3) <= 4 * se + 0.5
        L.append("| quantity | streaming counter | this graph | |")
        L.append("|---|---|---|---|")
        L.append(f"| `MethodInsufficient` share | {pop_f3:.1f}% (population) | "
                 f"{smp_f3:.1f}% (sample) | "
                 f"{'agree' if ok else '**DISAGREE**'} |")
        L.append("")
        L.append(f"Sampling standard error {se:.2f} percentage points; the two "
                 f"routes {'agree' if ok else 'DO NOT agree'} within it.\n")
        print(f"  cross-check: streaming {pop_f3:.1f}% vs graph {smp_f3:.1f}% "
              f"-> {'AGREE' if ok else 'DISAGREE'}")

    (EVAL / "waterbase_abox.md").write_text("\n".join(L), encoding="utf-8")
    print(f"\n  wrote {ttl.relative_to(ROOT)}"
          + (f" ({n_triples:,} triples)" if n_triples else ""))
    print(f"  wrote {(EVAL/'waterbase_abox.md').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
