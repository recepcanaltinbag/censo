#!/usr/bin/env python3
"""
The fourth detection status, populated from a record that can supply it.

WHY A SECOND SOURCE
-------------------
censo:EstimatedObservation -- detected, but below the limit of quantification --
is declared and has never been populated. That is not an oversight: WISE-6 has
one below-limit flag, so a true non-detection and a detection too small to
quantify arrive identically and both become censo:CensoredObservation. A
referee is nonetheless right that one of four statuses has never been tested
against real data, and that a vocabulary evaluated on a single release has not
shown that it generalises.

The US Water Quality Portal can supply the distinction. WQX records a detection
condition on every result ("Not Detected", "Present Below Quantification
Limit", ...) and, in a separate profile, every detection and quantitation limit
the laboratory attached to it. So this stage takes a bounded, citable slice of
it -- California streams, 2022-2023, trace metals and pesticides -- and maps
each result to one of the four statuses, with the interval the record actually
supports.

WHAT IT FINDS THAT A SINGLE FLAG CANNOT
---------------------------------------
Two things are counted, because they are what the fourth status is for.

  * How many below-limit results were in fact DETECTIONS. Under a one-flag
    schema that share is invisible.
  * How many estimated results carry only a DETECTION limit. Collapsed into a
    censored result against the only limit reported, such a result becomes the
    interval [0, LOD] -- which excludes every concentration the laboratory said
    it found. A single flag does not merely lose information there; it asserts
    the wrong interval.

And one thing is reported because it is true of the record: no estimated
result in this slice carries both a detection and a quantitation limit, so the
closed interval [LOD, LOQ] the vocabulary can hold is never fully supplied.
The graph writes the half it has and leaves the other bound absent.

WHAT IS NOT DONE
----------------
No compliance verdict is computed. These are US waters and no European standard
applies to them; the point here is the detection layer, which is independent of
any regulation, and the three-valued verdict is exercised on Waterbase.

Inputs  : Data/wqp/wqp_06_{metals,pest}_{2022,2023}_Result.zip
          Data/wqp/wqp_06_{metals,pest}_{2022,2023}_ResultDetectionQuantitationLimit.zip
          (each with a .url file holding the exact request)
Outputs : derived/abox/censo-wqp.ttl              (validated sample graph)
          derived/processed/wqp_statuses.csv
          eval/wqp_estimated.md

Usage:  python scripts/31_wqp_estimated.py [--sample 1500]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import random
import sys
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WQP = ROOT / "Data" / "wqp"
ABOX = ROOT / "derived" / "abox"
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

sys.path.insert(0, str(Path(__file__).resolve().parent))
_22 = __import__("22_waterbase_external")
_23 = __import__("23_waterbase_abox")
TO_UG_L, lit, slug = _22.TO_UG_L, _23.lit, _23.slug

SEED = 20260915

# WQX detection conditions, grouped by what they assert about the true value.
# The domain list is https://cdx.epa.gov/wqx/download/DomainValues/
# ResultDetectionCondition.CSV; only conditions whose meaning is unambiguous for
# a below-limit result are mapped, and everything else is Unresolved.
CENSORED = {"Not Detected", "Not Detected at Reporting Limit",
            "Not Detected at Detection Limit", "Below Detection Limit",
            "Below Method Detection Limit", "Below Reporting Limit",
            "Below Sample-specific Detect Limit"}
ESTIMATED = {"Present Below Quantification Limit", "Detected Not Quantified",
             "Between Inst Detect and Quant Limit", "Trace"}


def limit_kind(type_name: str):
    """'lod', 'loq' or None, from a WQX DetectionQuantitationLimitTypeName.

    Read by what the name says it is. A reporting level is not the IUPAC limit
    of quantification -- a USGS laboratory reporting level is twice the
    long-term method detection level -- but it is the level below which the
    laboratory declines to report a number, which is the role the
    quantification limit plays in a censoring statement. An UPPER quantitation
    limit bounds the other end and is not used.
    """
    t = type_name.lower()
    if "upper" in t:
        return None
    if "detect" in t:
        return "lod"
    if "quantitation" in t or "reporting" in t:
        return "loq"
    return None


def read_zip_csv(path: Path):
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(name) as fh:
            yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8",
                                                       errors="replace"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def to_ug(value: str, unit: str):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    f = TO_UG_L.get((unit or "").strip().lower().replace(" ", ""))
    return v * f if f is not None else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=1500,
                    help="censored and quantified results written to the "
                         "graph, each; every estimated and unresolved result "
                         "is written")
    args = ap.parse_args()

    result_files = sorted(WQP.glob("wqp_06_*_Result.zip"))
    limit_files = sorted(WQP.glob("wqp_06_*_ResultDetectionQuantitationLimit.zip"))
    if not result_files or len(result_files) != len(limit_files):
        print(f"  WQP slice incomplete under {WQP.relative_to(ROOT)}/: "
              f"{len(result_files)} result and {len(limit_files)} limit files. "
              f"The request URLs are in the .url files beside them.")
        return 0

    provenance = []
    for p in result_files + limit_files:
        u = p.with_suffix(".url")
        provenance.append((p.name, sha256(p),
                           u.read_text().strip() if u.exists() else ""))

    limits = defaultdict(lambda: {"lod": [], "loq": []})
    lim_types = Counter()
    for p in limit_files:
        for r in read_zip_csv(p):
            k = limit_kind(r["DetectionQuantitationLimitTypeName"])
            lim_types[(r["DetectionQuantitationLimitTypeName"], k)] += 1
            v = to_ug(r["DetectionQuantitationLimitMeasure/MeasureValue"],
                      r["DetectionQuantitationLimitMeasure/MeasureUnitCode"])
            if k and v is not None and v >= 0:
                limits[r["ResultIdentifier"]][k].append(
                    (v, r["DetectionQuantitationLimitTypeName"]))

    excluded = Counter()
    obs = []
    for p in result_files:
        group = "metals" if "_metals_" in p.name else "pesticides"
        for r in read_zip_csv(p):
            if r.get("ResultStatusIdentifier") == "Rejected":
                excluded["result rejected by the provider"] += 1
                continue
            if "sediment" in (r.get("ResultSampleFractionText") or "").lower():
                excluded["sediment, not a water concentration"] += 1
                continue
            cond = (r.get("ResultDetectionConditionText") or "").strip()
            val = to_ug(r.get("ResultMeasureValue"),
                        r.get("ResultMeasure/MeasureUnitCode"))
            raw_val = (r.get("ResultMeasureValue") or "").strip()
            if raw_val and val is None:
                excluded["value in a unit that is not a water concentration"] += 1
                continue
            lim = limits.get(r["ResultIdentifier"], {"lod": [], "loq": []})
            # Several limits of one kind on one result: the largest bounds what
            # the result can mean, so it is the one a bound may rest on.
            lod_t = max(lim["lod"]) if lim["lod"] else None
            loq_t = max(lim["loq"]) if lim["loq"] else None
            lod = lod_t[0] if lod_t else None
            loq = loq_t[0] if loq_t else None
            if lod is None and loq is None:
                excluded["no limit of either kind attached"] += 1
                continue

            # THE CONDITION FIELD IS NOT THE WHOLE RECORD. A first pass read only
            # ResultDetectionConditionText and typed 952 results "quantified"
            # whose value sits below a limit attached to them. 891 are USGS
            # results with the condition left blank and the status carried
            # elsewhere: ResultValueTypeName "Estimated", or a laboratory
            # comment in free text -- "below the reporting level but at or
            # above the detection level" is an estimated value by definition,
            # and "below the detection level" beside a number is a result whose
            # two statements contradict each other. Both are read here, and
            # the route each status was read by is counted, because a status
            # recovered from free text is weaker evidence than a coded one.
            lab = (r.get("ResultLaboratoryCommentText") or "").lower()
            vtype = (r.get("ResultValueTypeName") or "").strip()
            if cond in CENSORED:
                status, route = "censored", "condition code"
                lo, hi = 0.0, (lod if lod is not None else loq)
            elif cond in ESTIMATED:
                status, route = "estimated", "condition code"
                lo, hi = (lod if lod is not None else 0.0), loq
            elif cond == "" and val is not None and "below the detection level" in lab:
                status, route = "unresolved", "value beside 'below the detection level'"
                lo, hi = None, None
            elif cond == "" and val is not None and (
                    "below the reporting level but at or above the detection level"
                    in lab or vtype == "Estimated"):
                status = "estimated"
                route = ("laboratory comment" if "at or above the detection level"
                         in lab else "value type 'Estimated'")
                lo, hi = (lod if lod is not None else 0.0), loq
            elif cond == "" and val is not None:
                status, route, lo, hi = "quantified", "numeric value", val, val
            else:
                status, route = "unresolved", f"condition '{cond or '(none)'}'"
                lo, hi = None, None
            # an estimated value outside the interval its own limits give is
            # not an estimate the record supports
            if status == "estimated" and val is not None and (
                    (lod is not None and val < lod) or
                    (loq is not None and val > loq)):
                status, route, lo, hi = ("unresolved",
                                         "estimated value outside its limits",
                                         None, None)
            obs.append({
                "group": group, "status": status, "route": route,
                "cond": cond or "(none)",
                "lod": lod, "loq": loq, "val": val, "lo": lo, "hi": hi,
                # the laboratory's own name for each limit, kept verbatim
                "lod_def": lod_t[1] if lod_t else None,
                "loq_def": loq_t[1] if loq_t else None,
                "rid": r["ResultIdentifier"],
                "char": r["CharacteristicName"],
                "fraction": r.get("ResultSampleFractionText") or "",
                "method": r.get("ResultAnalyticalMethod/MethodIdentifier") or "",
                "site": r["MonitoringLocationIdentifier"],
                "year": (r.get("ActivityStartDate") or "")[:4],
                "org": r["OrganizationIdentifier"],
            })

    # ---------------------------------------------------------- the counts ---
    by_status = Counter(o["status"] for o in obs)
    by_group = Counter((o["group"], o["status"]) for o in obs)
    est = [o for o in obs if o["status"] == "estimated"]
    cen = by_status["censored"]
    est_lod_only = sum(1 for o in est if o["lod"] is not None and o["loq"] is None)
    est_loq_only = sum(1 for o in est if o["loq"] is not None and o["lod"] is None)
    est_both = sum(1 for o in est if o["lod"] is not None and o["loq"] is not None)
    est_bad = sum(1 for o in est if o["lod"] is not None and o["loq"] is not None
                  and o["lod"] > o["loq"])
    q_below = sum(1 for o in obs if o["status"] == "quantified"
                  and o["loq"] is not None and o["val"] < o["loq"])
    est_orgs = Counter(o["org"] for o in est)
    est_chars = Counter(o["char"] for o in est)
    routes = Counter((o["status"], o["route"]) for o in obs)
    free_text = sum(n for (s, rt), n in routes.items()
                    if s in ("estimated", "unresolved") and rt != "condition code"
                    and not rt.startswith("condition '"))

    # ------------------------------------------------------------ the graph --
    rng = random.Random(SEED)
    chosen = [o for o in obs if o["status"] in ("estimated", "unresolved")]
    for s in ("censored", "quantified"):
        pool = sorted((o for o in obs if o["status"] == s), key=lambda o: o["rid"])
        chosen += rng.sample(pool, min(args.sample, len(pool)))

    CLS = {"censored": "censo:CensoredObservation",
           "estimated": "censo:EstimatedObservation",
           "quantified": "censo:QuantifiedObservation",
           "unresolved": "censo:UnresolvedObservation"}
    out = ["@prefix censo: <https://w3id.org/censo/> .",
           "@prefix sosa:  <http://www.w3.org/ns/sosa/> .",
           "@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .",
           "@prefix unit:  <http://qudt.org/vocab/unit/> .",
           "@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .",
           "@prefix dcterms: <http://purl.org/dc/terms/> .",
           "@prefix wqp:   <https://w3id.org/censo/data/wqp/> .", "",
           "<https://w3id.org/censo/data/wqp/> dcterms:source "
           "<https://www.waterqualitydata.us/> ;",
           '    rdfs:comment "California stream results 2022-2023, trace metals '
           'and pesticides, from the US Water Quality Portal, expressed in CENSO '
           'by scripts/31_wqp_estimated.py. Every estimated and unresolved result '
           'in the slice, and a seeded sample of the censored and quantified '
           'ones."@en .', ""]
    methods, analytes, stations, campaigns = {}, {}, set(), set()
    for o in sorted(chosen, key=lambda o: o["rid"]):
        a_iri = f"wqp:analyte-{slug(o['char'])}"
        analytes[a_iri] = o["char"]
        s_iri = f"wqp:station-{slug(o['site'])}"
        stations.add((s_iri, o["site"]))
        c_iri = f"wqp:campaign-{o['year']}"
        campaigns.add((c_iri, o["year"]))
        mkey = (o["char"], o["fraction"], o["method"], o["lod"], o["loq"],
                o["lod_def"], o["loq_def"])
        m_iri = methods.get(mkey)
        if m_iri is None:
            m_iri = methods[mkey] = f"wqp:method-{len(methods)}"
        L = [f"wqp:obs-{slug(o['rid'])} a {CLS[o['status']]} ;",
             f"    censo:hasAnalyte {a_iri} ;",
             f"    censo:atStation {s_iri} ;",
             f"    censo:duringCampaign {c_iri} ;",
             f"    sosa:usedProcedure {m_iri} ;"]
        if o["val"] is not None and o["val"] >= 0:
            L.append(f"    censo:reportedValue {lit(o['val'])} ;")
        if o["lo"] is not None:
            L.append(f"    censo:resultLowerBound {lit(o['lo'])} ;")
        if o["hi"] is not None:
            L.append(f"    censo:resultUpperBound {lit(o['hi'])} ;")
        L[-1] = L[-1].rstrip(" ;") + " ."
        out.append("\n".join(L) + "\n")
    for (char, fraction, method, lod, loq, lod_def, loq_def), m_iri in sorted(
            methods.items(), key=lambda kv: int(kv[1].rsplit("-", 1)[1])):
        L = [f"{m_iri} a censo:AnalyticalMethod ;",
             f'    rdfs:label "{method or "unstated method"} for {char}'
             f'{" (" + fraction + ")" if fraction else ""}"@en ;',
             f"    censo:determinesAnalyte wqp:analyte-{slug(char)} ;"]
        if lod is not None:
            L.append(f"    censo:limitOfDetection {lit(lod)} ;")
        if loq is not None:
            L.append(f"    censo:limitOfQuantification {lit(loq)} ;")
        # Not converted into one another: a method detection level and a
        # laboratory reporting level are different definitions, and the record
        # says which one it used.
        if lod_def:
            L.append(f'    censo:limitDefinition "detection limit: '
                     f'{lod_def.replace(chr(34), "")}" ;')
        if loq_def:
            L.append(f'    censo:limitDefinition "quantification limit: '
                     f'{loq_def.replace(chr(34), "")}" ;')
        L.append("    censo:limitUnit unit:MicroGM-PER-L .")
        out.append("\n".join(L) + "\n")
    for a_iri, char in sorted(analytes.items()):
        out.append(f'{a_iri} a censo:Analyte ;\n    rdfs:label "{char}"@en .\n')
    for s_iri, site in sorted(stations):
        out.append(f'{s_iri} a sosa:FeatureOfInterest ;\n'
                   f'    rdfs:label "{site}"@en .\n')
    for c_iri, year in sorted(campaigns):
        out.append(f'{c_iri} a censo:Campaign ;\n'
                   f'    censo:reportingYear "{year}"^^xsd:gYear ;\n'
                   f'    rdfs:label "Sampling year {year}"@en .\n')
    ABOX.mkdir(parents=True, exist_ok=True)
    ttl = ABOX / "censo-wqp.ttl"
    ttl.write_text("\n".join(out), encoding="utf-8")
    graph_status = Counter(o["status"] for o in chosen)

    # ----------------------------------------------------------- validation --
    import rdflib
    import pyshacl
    d = rdflib.Graph()
    d.parse(ttl, format="turtle")
    d.parse(ROOT / "ontology" / "censo-core.ttl", format="turtle")
    for t in list(d.triples((None, rdflib.OWL.imports, None))):
        d.remove(t)
    sweep = True
    while sweep:            # the same fixed-point closure as scripts/18
        sweep = False
        for sub, _, sup in list(d.triples((None, rdflib.RDFS.subClassOf, None))):
            if isinstance(sup, rdflib.term.BNode):
                continue
            for s_ in set(d.subjects(rdflib.RDF.type, sub)):
                if (s_, rdflib.RDF.type, sup) not in d:
                    d.add((s_, rdflib.RDF.type, sup))
                    sweep = True
    shapes = rdflib.Graph()
    shapes.parse(ROOT / "ontology" / "censo-shapes.ttl", format="turtle")
    C = "https://w3id.org/censo/"
    seen = {n: len(set(d.subjects(rdflib.RDF.type, rdflib.URIRef(C + n))))
            for n in ("AssessedObservation", "EstimatedObservation",
                      "DetectedObservation", "CensoredObservation",
                      "AnalyticalMethod")}
    t0 = time.perf_counter()
    conforms, _, txt = pyshacl.validate(d, shacl_graph=shapes, advanced=True,
                                        inplace=False)
    dt = time.perf_counter() - t0
    msgs = Counter(l.split("Message:", 1)[1].strip()
                   for l in txt.splitlines() if "Message:" in l)

    # --------------------------------------------------------------- output --
    PROC.mkdir(parents=True, exist_ok=True)
    with (PROC / "wqp_statuses.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["group", "status", "n"])
        for (g, s), n in sorted(by_group.items()):
            w.writerow([g, s, n])

    R = []
    a = R.append
    a("# The fourth detection status, on a record that can supply it\n")
    a("Generated by `scripts/31_wqp_estimated.py`. Source: US Water Quality "
      "Portal, California streams, 2022–2023, trace metals and pesticides; "
      "result and detection-limit profiles joined on `ResultIdentifier`.\n")
    a("| file | sha256 |")
    a("|---|---|")
    for name, h, _ in provenance:
        a(f"| `{name}` | `{h[:16]}…` |")
    a("\nThe exact request for each file is kept beside it as a `.url` file.\n")
    a("## Detection status over the whole slice\n")
    a("| status | metals | pesticides | total |")
    a("|---|---|---|---|")
    for s in ("quantified", "censored", "estimated", "unresolved"):
        a(f"| `{CLS[s]}` | {by_group[('metals', s)]:,} | "
          f"{by_group[('pesticides', s)]:,} | **{by_status[s]:,}** |")
    a("")
    a("Not written, and why: " + "; ".join(f"{k} {v:,}" for k, v in
                                           excluded.most_common()) + ".\n")
    a("### How each status was read\n")
    a("| status | read from | n |")
    a("|---|---|---|")
    for (s, rt), n in sorted(routes.items(), key=lambda kv: (kv[0][0], -kv[1])):
        a(f"| {s} | {rt} | {n:,} |")
    a("")
    a(f"**{free_text:,} statuses could not be read from the coded detection "
      f"condition** and were recovered from the value type or a free-text "
      f"laboratory comment. The exchange standard that carries the most about "
      f"censoring still leaves part of it where no query over coded fields "
      f"reaches it.\n")
    share = 100 * len(est) / (len(est) + cen) if (len(est) + cen) else 0
    mshare_e = by_group[("metals", "estimated")]
    mshare_c = by_group[("metals", "censored")]
    a("## What one below-limit flag would hide\n")
    a(f"- **{len(est):,} of {len(est) + cen:,} below-limit results "
      f"({share:.1f} %) were detections**, not non-detections"
      + (f"; for the trace metals alone {mshare_e:,} of {mshare_e + mshare_c:,} "
         f"({100 * mshare_e / (mshare_e + mshare_c):.1f} %)"
         if mshare_e + mshare_c else "") + ". WISE-6 records all of them "
      "with the same flag.")
    a(f"- **{est_lod_only:,} estimated results carry a detection limit and no "
      f"quantification limit.** Collapsed into a censored result against the "
      f"only limit reported, each becomes [0, LOD], an interval that excludes "
      f"every concentration the laboratory reported finding.")
    a(f"- {est_loq_only:,} carry a quantification or reporting limit only, and "
      f"are written as [0, LOQ] with the detection recorded by the class.")
    a(f"- **{est_both:,} carry both**, so the closed interval [LOD, LOQ] is "
      f"never supplied by this record" +
      (f" ({est_bad:,} with LOD above LOQ)" if est_bad else "") + ".")
    a(f"- {q_below:,} quantified results report a value below a quantification "
      f"or reporting limit attached to them — the self-contradicting row the "
      f"Waterbase assessment types `BoundNotEstablished`.\n")
    a("Reported by: " + ", ".join(f"{k} {v:,}" for k, v in est_orgs.most_common(6))
      + ". Most frequent analytes: " + ", ".join(
          f"{k} {v:,}" for k, v in est_chars.most_common(8)) + ".\n")
    a("## The graph, and what the shapes saw\n")
    a(f"- `derived/abox/censo-wqp.ttl`: "
      + ", ".join(f"{s} {graph_status[s]:,}" for s in
                  ("estimated", "censored", "quantified", "unresolved"))
      + f"; {len(methods):,} method individuals "
      f"(seed {SEED}, {args.sample:,} per sampled status)")
    a("- shape targets after closure: " + ", ".join(
        f"{k} {v:,}" for k, v in seen.items()))
    a(f"- SHACL conforms: **{conforms}** ({dt:.1f} s); "
      f"{sum(msgs.values()):,} result message(s)\n")
    if msgs:
        a("| message | n |")
        a("|---|---|")
        for m, n in msgs.most_common():
            a(f"| {m} | {n:,} |")
        a("")
        if any("below the limit of detection" in m for m in msgs):
            a("The inverted-limit violations are the source's, not the "
              "mapping's: the laboratory attached a detection limit above the "
              "quantitation or reporting limit on the same result. They are left "
              "in the graph so that the shape is seen to catch them.\n")
    a("## Limit types, as read\n")
    a("| WQX limit type | read as | n |")
    a("|---|---|---|")
    for (t, k), n in sorted(lim_types.items(), key=lambda kv: -kv[1]):
        a(f"| {t} | {k or 'not used'} | {n:,} |")
    a("")
    a("No compliance verdict is computed: no European standard applies to these "
      "waters, and the detection layer is independent of any regulation.")
    (EVAL / "wqp_estimated.md").write_text("\n".join(R) + "\n", encoding="utf-8")
    print("\n".join(R))
    return 0


if __name__ == "__main__":
    sys.exit(main())
