#!/usr/bin/env python3
"""
Verify the novelty claim against the ACTUAL ontology files, not against prose.

The paper's contribution rests on a gap table asserting that no existing water
or observation ontology represents detection limits, censoring status, or an
"undecidable" compliance state. That claim is worthless if it was derived from
reading abstracts. This script downloads each ontology and searches its own
vocabulary.

Method
------
For each comparison ontology, fetch the RDF, parse it, and search every entity
IRI, rdfs:label, rdfs:comment and skos:definition for concept families:

  detection_limit  - LOD/LOQ, reporting limit, quantification limit
  censoring        - non-detect, below limit, censored, left-censored
  undecidable      - indeterminate, undetermined, not assessable, unknown state
  threshold        - EQS, standard, limit value, guideline
  interval_result  - lower/upper bound, interval, range-valued result
  applicability    - precondition, applicability, bioavailable, dissolved fraction

A hit is reported with the exact entity so a reviewer can check it. A miss is
only claimed when the ontology was actually parsed -- a download failure is
reported as UNKNOWN, never silently as absence.

Outputs: eval/gap_table.md  (paste-ready Table 1)
         derived/interim/ontology_cache/*  (downloaded sources, for reproducibility)

Usage:  python scripts/07_verify_gap_table.py [--offline]
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "derived" / "interim" / "ontology_cache"
EVAL = ROOT / "eval"

try:
    import rdflib
    from rdflib import RDF, RDFS, OWL, URIRef
    from rdflib.namespace import SKOS, DCTERMS
except ImportError:
    sys.exit("rdflib is required:  pip install rdflib")

UA = "censo-ontology-research/1.0 (academic comparison; see repository)"

# Comparison set. Local files are used where the ontology is one of ours.
TARGETS = [
    ("SOSA/SSN", "http://www.w3.org/ns/ssn/", "ssn.ttl", None),
    ("SOSA core", "http://www.w3.org/ns/sosa/", "sosa.ttl", None),
    ("GeoSPARQL", "http://www.opengis.net/ont/geosparql", "geosparql.ttl", None),
    ("QUDT schema", "http://qudt.org/schema/qudt/", "qudt.ttl", None),
    ("SAREF core", "https://saref.etsi.org/core/v3.1.1/saref.ttl", "saref.ttl", None),
    # v2.1.1 is the current release; comparing against a superseded version
    # would understate what the competitor actually offers.
    ("SAREF4WATR v2.1.1", None, None,
     ROOT / "derived" / "interim" / "ontology_cache" / "saref4watr-v2.ttl"),
    ("SSN-system", "http://www.w3.org/ns/ssn/systems/", "ssn-systems.ttl", None),
    # Included so the temporal-Interval exclusion is documented rather than
    # merely asserted: OWL-Time is where that Interval comes from.
    ("OWL-Time", None, None,
     ROOT / "derived" / "interim" / "ontology_cache" / "owl-time.ttl"),
    # WHOW: Water Health Open Knowledge Graph. Published at a w3id IRI with
    # content negotiation, so unlike WaWO+ and OPO it can be checked directly.
    ("WHOW water-monitoring", "https://w3id.org/whow/onto/water-monitoring",
     "whow-water-monitoring.ttl", None),
    # Domain ontologies that DO publish a dereferenceable file. Adding these is
    # what turns the novelty claim from an assertion into a test.
    ("DoCE (Rio Doce WQ)", "https://nemo-ufes.github.io/doce/doce.ttl",
     "doce.ttl", None),
    ("InWaterSense core", None, None,
     ROOT / "derived" / "interim" / "ontology_cache" / "inws-core.owl"),
    ("InWaterSense regulations", None, None,
     ROOT / "derived" / "interim" / "ontology_cache" / "inws-regulations.owl"),
    ("InWaterSense pollutants", None, None,
     ROOT / "derived" / "interim" / "ontology_cache" / "inws-pollutants.owl"),
    ("WAM-ONTO", None, None,
     ROOT / "derived" / "interim" / "ontology_cache" / "wam-onto.owl"),
    ("SewerNet", None, None,
     ROOT / "derived" / "interim" / "ontology_cache" / "sewernet.owl"),
    # ANALYTICAL-CHEMISTRY AND STATISTICS VOCABULARIES.
    #
    # Added because the comparison set was otherwise entirely water and sensor
    # domain, while censo-core.ttl claims applicability to "food safety
    # residues, clinical assays, soil contaminants, occupational exposure". A
    # domain-independence claim tested inside one domain is not tested, and the
    # first referee who works on laboratory semantics would say so.
    #
    # These three are where the concepts would live if they lived anywhere:
    #
    #   CHMO  - the OBO Chemical Methods Ontology. It DOES declare
    #           `limit of detection` (CHMO:0002801) and `limit of quantification`
    #           (CHMO:0002802), both defined from the IUPAC Gold Book. This is
    #           the hardest test the novelty claim has, and it is the reason to
    #           run it rather than argue about it.
    #   AFO   - the Allotrope Foundation Ontology, built by a pharmaceutical
    #           consortium specifically for analytical laboratory data.
    #   STATO - the OBO statistics ontology, where censoring is a standard
    #           concept in survival analysis.
    #
    # Their false positives need the same care as ENVO's *indeterminate root
    # nodule*, and are recorded in the prose-only section rather than scored:
    # AFO's `lower bound` and `upper bound` are subclasses of `bound role`, a
    # BFO role and not a value on a result; its `precondition` is a subclass of
    # `at start`, a temporal relation and not an applicability condition on a
    # threshold; and the `threshold` hits in both AFO and STATO are instrument
    # settings -- `cycle threshold (qPCR)`, `peak integration area threshold` --
    # not regulatory limits.
    ("CHMO (chemical methods)", "http://purl.obolibrary.org/obo/chmo.owl",
     "chmo.owl", None),
    ("AFO (Allotrope)",
     "http://purl.allotrope.org/voc/afo/merged/REC/2025/06/"
     "merged-without-qudt-and-inferred", "afo.ttl", None),
    ("STATO (statistics)", "http://purl.obolibrary.org/obo/stato.owl",
     "stato.owl", None),
    # OBO Foundry environment ontologies. Not measurement vocabularies, but a
    # reviewer will expect ENVO to be addressed, so it is checked rather than
    # asserted about.
    ("ENVO", None, None,
     ROOT / "derived" / "interim" / "ontology_cache" / "envo.owl"),
    ("ExO (exposure)", None, None,
     ROOT / "derived" / "interim" / "ontology_cache" / "exo.owl"),
    # Ours, for contrast.
    ("CENSO (this work)", None, None, ROOT / "ontology" / "censo-core.ttl"),
    ("CENSO-REG (this work)", None, None, ROOT / "ontology" / "censo-regulation.ttl"),
    # The 2018 project ontology, as a further contrast point.
    ("Project ontology 2018", None, None, ROOT / "TheOntologyGISDSS.owl"),
]

# Cells the stated method scores **yes** where reading the term's own superclass
# shows it is a different concept. The cell is NOT adjusted: a pattern tweaked
# until a competitor scores the way we want would make the whole table an
# assertion again. The discrepancy is published beside it instead, and each of
# these was checked by following rdfs:subClassOf in the cached file.
CAVEATS = {
    "CHMO (chemical methods)": [
        ("undecidable",
         "both hits are artefacts of the widened patterns and are reported "
         "rather than removed: `ambiguous synonym` (OMO_0003001) is an OBO "
         "metadata annotation property describing the quality of a SYNONYM, "
         "and `double quantum transitions for finding unresolved lines` "
         "(CHMO_0001861) is an NMR technique, where the unresolved things are "
         "spectral lines. Neither is an assessment outcome."),
        ("interval_result",
         "`confidence interval` (OBCS_0000070), imported from OBCS. A "
         "confidence interval is an interval ESTIMATE of a parameter from a "
         "sample; the interval CENSO needs is the set of concentrations a "
         "single non-detection leaves possible. Related, and not the same: no "
         "amount of sampling narrows the second."),
    ],
    "STATO (statistics)": [
        ("interval_result",
         "nine hits, all confidence or credible intervals. As above these are "
         "interval estimates of a parameter. STATO is also the sharpest "
         "negative result in the table: censoring is a routine concept in "
         "survival analysis, the patterns here match `censor`, `left-censor` "
         "and `right-censor` bare, and STATO declares no term for it and does "
         "not mention it in a single definition."),
    ],
    "AFO (Allotrope)": [
        ("interval_result",
         "seventeen hits, of two kinds. `lower bound` (AFRL_0000041), "
         "`upper bound` (AFRL_0000042), `minimum value role` and `maximum "
         "value role` are subclasses of `bound role` — BFO roles borne by a "
         "participant, not values on a result. `minimum value` (AFR_0002440) "
         "and `maximum value` (AFX_0000674) are genuine data properties, so "
         "AFO can bound a quantity; what it has no way to say is that the "
         "bound exists BECAUSE the analyte was sought and not found."),
        ("applicability",
         "`precondition` (AFRL_0000059) is a subclass of `at start`, a "
         "temporal relation about when something holds in a process — not a "
         "condition governing whether a threshold may lawfully be applied."),
        ("threshold",
         "the eight hits are instrument settings: `cycle threshold (qPCR)`, "
         "`area threshold for peak integration (chromatography)`, "
         "`fluorescence intensity threshold setting`. None is a limit a result "
         "is assessed against."),
    ],
    "STATO (statistics)": [
        ("threshold",
         "the single hit is `threshold cycle`, the qPCR quantity, not a limit "
         "value. Note also what STATO does NOT have: censoring is a standard "
         "concept in survival analysis, and it appears in STATO only in prose, "
         "with no term."),
    ],
}

# Concept families, matched against an entity's IRI local name and its labels.
#
# DELIBERATELY OVER-GENEROUS, and the asymmetry is the point. Every pattern here
# can only ADD a "yes" to a competitor's row; CENSO's own cells are already yes,
# so no widening can flatter this work. A novelty claim that survives a matcher
# tuned in the competitors' favour is worth something; one that depends on
# spelling is not.
#
# The lists were widened after the first version was found to match on OUR
# vocabulary's spellings and miss other people's. Every one of these was a real
# miss, checked by running the pattern against the phrase:
#
#   detection_limit  "limit of quantitation" -- the US and pharmacopoeial
#                    spelling, which is what a laboratory vocabulary is most
#                    likely to use; also LLOQ, ULOQ, decision limit (CCalpha).
#   censoring        "below detection limit" -- the most ordinary phrasing there
#                    is. The old pattern required the word "limit" to follow
#                    "below" immediately, so it matched "below limit" and missed
#                    "below reporting limit".
#   undecidable      "undetermined", "unresolved" -- bare, without the
#                    compliance/status qualifier the old pattern demanded.
#   interval_result  "minimum value" -- the old "min ?value" matched "minvalue"
#                    and "min value" but not the word spelled out.
#   applicability    "validity condition", "context of use".
#   threshold        "maximum residue level", "action level" -- the food-safety
#                    and occupational-exposure equivalents of an EQS, which is
#                    precisely the neighbouring domain the set now reaches into.
#
# Where a widened pattern credits an ontology with a concept it does not really
# carry, the cell stands and the discrepancy goes in CAVEATS above. Narrowing a
# pattern until a competitor loses a cell is the one move forbidden here.
CONCEPTS = {
    "detection_limit": [
        r"\blod\b", r"\bloq\b", r"\blloq\b", r"\buloq\b",
        r"limit of detection", r"detection limit", r"detection threshold",
        r"limit of quantifi", r"limit of quantitat", r"quantification limit",
        r"quantitation limit", r"reporting limit", r"reporting level",
        r"decision limit", r"minimum detectable", r"detectable limit",
        r"detection capabilit",
        # camelCase and concatenated forms: our own limitOfDetection was missed
        # by the spaced patterns, which would have put a wrong "-" in this
        # work's own row.
        r"detectionlimit", r"quantificationlimit", r"quantitationlimit",
        r"limitofdetection", r"limitofquantif", r"limitofquantitat",
    ],
    "censoring": [
        r"censor", r"left[- ]?censor", r"right[- ]?censor", r"left[- ]?truncat",
        r"non[- ]?detect", r"nondetect", r"not detected", r"no[nt][- ]detection",
        r"below\s+\w*\s*limit", r"under\s+the\s+limit", r"less than the limit",
        r"not quantifi", r"unquantifi", r"non[- ]?quantifi",
        r"below\s+\w*\s*threshold",
    ],
    # The concept is an ASSESSMENT OUTCOME. The qualifier requirement is kept
    # for "indeterminate" alone, because a bare "indetermin" matched ENVO's
    # *indeterminate root nodule*, a plant-biology class -- but the other
    # spellings are now admitted bare, which is the generous direction.
    "undecidable": [
        r"undecid", r"unresolved", r"undetermined", r"not determined",
        r"not assessable", r"unassessable", r"not evaluable", r"inconclusive",
        r"cannot be determined", r"ambiguous", r"insufficient evidence",
        r"indetermin\w*\s+(compliance|status|result|assessment|outcome)",
        r"undetermin\w*\s+(compliance|status|result|assessment|outcome)",
    ],
    "threshold": [
        r"threshold", r"quality standard", r"\beqs\b", r"limit value",
        r"guideline value", r"permissible", r"exceedance",
        r"maximum residue", r"\bmrl\b", r"action level", r"tolerance limit",
        r"specification limit", r"acceptance criteri", r"reference value",
        r"regulatory limit", r"maximum allowable",
    ],
    # A bare "interval" matches OWL-Time's temporal Interval, which has nothing
    # to do with a value range: SewerNet and SAREF4WATR were scored "yes" on
    # that false positive alone. So the interval must still be about a VALUE --
    # but every spelling of that is now admitted.
    "interval_result": [
        r"lower ?bound", r"upper ?bound", r"lowerbound", r"upperbound",
        r"lower ?limit", r"upper ?limit", r"lower ?value", r"upper ?value",
        r"min(imum)? ?value", r"max(imum)? ?value", r"low ?value", r"high ?value",
        r"rangemin", r"rangemax", r"range of value", r"value range",
        r"value interval", r"interval of value", r"confidence interval",
        r"uncertainty interval", r"credible interval", r"interval[- ]valued",
    ],
    "applicability": [
        r"applicab", r"precondition", r"pre[- ]condition",
        r"validity condition", r"valid(ity)? for", r"usage condition",
        r"context of use", r"qualifying condition", r"condition of use",
        r"bioavailab", r"dissolved fraction", r"hardness class",
        r"matrix condition",
    ],
}

COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in CONCEPTS.items()}


def fetch(name: str, url: str, fname: str, offline: bool):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / fname
    if path.exists() and path.stat().st_size > 0:
        return path
    if offline:
        return None
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/turtle, application/rdf+xml;q=0.9, */*;q=0.5"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except Exception as e:
        print(f"  ! {name}: download failed ({type(e).__name__})")
        return None
    path.write_bytes(data)
    return path


def parse(path: Path):
    g = rdflib.Graph()
    for fmt in ("turtle", "xml", "n3", "nt"):
        try:
            g.parse(path, format=fmt)
            return g
        except Exception:
            g = rdflib.Graph()
            continue
    return None


def scan(g):
    """Return {concept: [evidence]} found in the ontology's own vocabulary.

    Evidence is graded, because the two kinds are not comparable:

      TERM  - the concept appears in an entity's IRI local name or rdfs:label.
              The ontology has a term for it. This is what the gap table scores.
      PROSE - it appears only inside a comment or definition. In a large
              ontology this is mostly noise: ENVO yielded "undecidable" from
              *indeterminate root nodule*, a plant-biology class, and
              "threshold" from a remark that the definition of a rainy day is
              arbitrary. Scoring prose as presence would have credited ENVO
              with four concepts it does not model.
    """
    found = defaultdict(list)
    prose = defaultdict(list)
    seen = set()

    def consider(entity, text, is_term):
        if not text:
            return
        for concept, pats in COMPILED.items():
            for p in pats:
                if p.search(text):
                    ev = f"{entity} :: {text[:90]}"
                    if ev not in seen:
                        seen.add(ev)
                        (found if is_term else prose)[concept].append(ev)
                    break

    entity_types = [OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty,
                    OWL.AnnotationProperty, RDFS.Class, RDF.Property]
    entities = set()
    for t in entity_types:
        entities |= {s for s in g.subjects(RDF.type, t) if isinstance(s, URIRef)}

    for e in entities:
        local = str(e).rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        consider(local, local, True)
        for p in (RDFS.label, SKOS.prefLabel):
            for o in g.objects(e, p):
                consider(local, str(o), True)
        for p in (RDFS.comment, SKOS.definition):
            for o in g.objects(e, p):
                consider(local, str(o), False)
    return found, len(entities), prose


# The discriminating question is NOT "does the term exist" but "is it attached
# to an individual observation's result".
#
# SSN's Systems module does define ssn-system:DetectionLimit -- but as a
# subclass of ssn-system:SystemProperty, i.e. metadata about what a SENSOR can
# do. It is never linked to a sosa:Observation or its result, so nothing in
# SOSA/SSN can say that a particular measurement fell below it. The limit is
# known about the instrument and forgotten about the measurement.
# Split out of the old OBS_TERMS, which lumped method and result together and
# so could not tell "the limit is a property of the assay" from "the limit
# reaches this measurement". See detection_limit_binding().
RESULT_TERMS = re.compile(r"observation|\bresult\b|sosa|hasSimpleResult|"
                          r"measurement datum|measured value", re.I)
METHOD_TERMS = re.compile(r"AnalyticalMethod|Procedure|\bmethod\b|\bassay\b|"
                          r"figure of merit|technique|protocol", re.I)
SYSTEM_TERMS = re.compile(r"SystemProperty|SystemCapability|Sensor|Device|"
                          r"Platform|Actuator", re.I)


SOSA_NS = "http://www.w3.org/ns/sosa/"
SAMPLING_TERMS = re.compile(r"Sampling|Sampler|\bSample\b|specimen|laboratory|"
                            r"analytical|assay", re.I)
SENSING_TERMS = re.compile(r"Sensor|Sensing|Device|Platform|Actuator|"
                           r"measurement capability", re.I)


def profile(g):
    """Characterise an ontology beyond keyword presence.

    Three dimensions a reviewer actually cares about:
      * FAIR    - is it citable and reusable (licence, versionIRI, labels)?
      * reuse   - does it build on SOSA/SSN or reinvent an observation model?
      * modality- does its vocabulary describe SENSING (device observes in situ)
                  or SAMPLING (specimen taken, analysed later)? Trace organic
                  monitoring is the second, and the field's detection-limit gap
                  follows directly from having inherited the first.
    """
    names = []
    for t_ in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty):
        for s in g.subjects(RDF.type, t_):
            if isinstance(s, URIRef):
                names.append(str(s).rsplit("#", 1)[-1].rsplit("/", 1)[-1])
    for _, _, o in g.triples((None, RDFS.label, None)):
        names.append(str(o))
    blob = " ".join(names)

    onts = list(g.subjects(RDF.type, OWL.Ontology))
    o0 = onts[0] if onts else None
    imports = [str(i) for i in g.objects(o0, OWL.imports)] if o0 else []
    has_sosa = any(SOSA_NS in i for i in imports) or SOSA_NS in blob or \
        any(SOSA_NS in str(s) for s in list(g.subjects())[:2000])

    # Count ENTITIES THAT HAVE at least one label, not label triples: a
    # multilingual ontology has several labels per entity and would otherwise
    # score above 100%.
    ents = {s for t_ in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty)
            for s in g.subjects(RDF.type, t_) if isinstance(s, URIRef)}
    labelled = {s for s in ents if list(g.objects(s, RDFS.label))
                or list(g.objects(s, SKOS.prefLabel))}
    n_lab, n_ent = len(labelled), len(ents)

    return {
        "licence": bool(o0 and list(g.objects(o0, DCTERMS.license))),
        "versionIRI": bool(o0 and list(g.objects(o0, OWL.versionIRI))),
        "imports": len(imports),
        "reuses_sosa": has_sosa,
        "label_coverage": (n_lab / n_ent) if n_ent else 0.0,
        "sampling_terms": len(SAMPLING_TERMS.findall(blob)),
        "sensing_terms": len(SENSING_TERMS.findall(blob)),
    }


def _names(g, e):
    """Every string that names an entity: its IRI local part and its labels.

    OBO ontologies mint opaque numeric IRIs -- CHMO's limit of detection is
    CHMO_0002801 -- so an IRI-only match finds nothing in them. This function is
    why the comparison can include an OBO vocabulary at all.
    """
    out = [str(e).rsplit("#", 1)[-1].rsplit("/", 1)[-1]]
    for p in (RDFS.label, SKOS.prefLabel):
        out += [str(o) for o in g.objects(e, p)]
    return out


def detection_limit_binding(g):
    """Classify what a detection-limit concept is attached TO, if anything.

    Returns 'result', 'method', 'sensor', 'unclear', or '' (absent). This is
    the discriminating column of the gap table, so each value has to be earned.

    THREE DEFECTS THIS REPLACES, all of which would have put a wrong cell in the
    table the moment an OBO vocabulary entered the comparison set:

      1. Detection-limit entities were found by matching the IRI's local name
         only. Against CHMO -- the one competitor that genuinely declares
         `limit of detection` and `limit of quantification`, both from the IUPAC
         Gold Book -- that finds nothing, because the IRIs are CHMO_0002801 and
         CHMO_0002802. The row would have said the concept is present and its
         binding unknown, in the same row.
      2. The default was 'system'. An ontology whose limit had no informative
         superclass was reported as binding it to a SENSOR even when, as in
         CHMO, the vocabulary contains no sensor concept at all. A default is
         not a finding; unclear is now its own value.
      3. OBS_TERMS included AnalyticalMethod and Procedure, so a limit declared
         on a METHOD scored as bound to the RESULT. Those are different claims,
         and the difference is the paper's whole argument: a limit belongs to
         the method, and what matters is whether anything carries it onto an
         individual result. They are separate values now.

    'result' is therefore earned in one of two ways: the limit itself is
    attached to an observation or a result, OR -- the CENSO case -- the limit is
    declared on the method AND the vocabulary has an interval bound whose domain
    is an observation, which is what carries it onto the measurement.
    """
    dl_entities = [s for s in set(g.subjects())
                   if isinstance(s, URIRef)
                   and any(p.search(n) for n in _names(g, s)
                           for p in COMPILED["detection_limit"])]
    if not dl_entities:
        return ""

    def linked(e, pat):
        for p in (RDFS.domain, RDFS.range, RDFS.subClassOf):
            for o in g.objects(e, p):
                if isinstance(o, URIRef) and any(pat.search(n)
                                                 for n in _names(g, o)):
                    return True
        return False

    on_result = any(linked(e, RESULT_TERMS) for e in dl_entities)
    on_method = any(linked(e, METHOD_TERMS) for e in dl_entities)
    on_system = any(linked(e, SYSTEM_TERMS) for e in dl_entities)

    # Does anything carry a value bound onto an individual observation? This is
    # the property CENSO adds and the reason its limit reaches the measurement.
    carries = False
    for s in g.subjects(RDF.type, OWL.DatatypeProperty):
        if not isinstance(s, URIRef):
            continue
        if not any(p.search(n) for n in _names(g, s)
                   for p in COMPILED["interval_result"]):
            continue
        for o in g.objects(s, RDFS.domain):
            if isinstance(o, URIRef) and any(RESULT_TERMS.search(n)
                                             for n in _names(g, o)):
                carries = True

    if on_result or (on_method and carries):
        return "result"
    if on_method:
        return "method"
    if on_system:
        return "sensor"
    return "unclear"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    EVAL.mkdir(parents=True, exist_ok=True)

    results = {}
    prose_only = {}
    profiles = {}
    for name, url, fname, local in TARGETS:
        print(f"{name} …")
        path = local if local else fetch(name, url, fname, args.offline)
        if path is None or not Path(path).exists():
            results[name] = ("UNKNOWN", {}, 0, "")
            continue
        g = parse(Path(path))
        if g is None:
            print(f"  ! {name}: could not parse")
            results[name] = ("UNPARSED", {}, 0, "")
            continue
        found, n_ent, prose = scan(g)
        binding = detection_limit_binding(g)
        results[name] = ("OK", found, n_ent, binding)
        profiles[name] = profile(g)
        if prose:
            prose_only[name] = {k: v for k, v in prose.items() if k not in found}
        hits = ", ".join(sorted(found)) or "none"
        print(f"  {n_ent} entities · concepts present: {hits}")

    order = list(CONCEPTS)
    L = []
    A = L.append
    A("# Gap table, verified against the ontology files themselves\n")
    A("Generated by `scripts/07_verify_gap_table.py`. Each cell is decided by "
      "searching the ontology's own entity names, labels, comments and "
      "definitions -- not by reading its documentation. Sources are cached under "
      "`derived/interim/ontology_cache/` so any cell can be re-checked.\n")
    A("A blank cell means the ontology parsed and the concept was absent. "
      "`?` means the file could not be retrieved or parsed, and **no claim is "
      "made** about it.\n")

    A("| Ontology | entities | LOD bound to | "
      + " | ".join(c.replace("_", " ") for c in order) + " |")
    A("|---" * (len(order) + 3) + "|")
    BIND = {"result": "**the result**", "method": "the method",
            "sensor": "the sensor", "unclear": "unclear", "": "—"}
    for name, (status, found, n_ent, binding) in results.items():
        if status != "OK":
            A(f"| {name} | ? | ? | " + " | ".join("?" for _ in order) + " |")
            continue
        cells = ["**yes**" if found.get(c) else "—" for c in order]
        A(f"| {name} | {n_ent} | {BIND[binding]} | " + " | ".join(cells) + " |")
    A("")
    A("**The `LOD bound to` column is the discriminating one.** A detection "
      "limit declared as a sensor capability describes what an instrument can "
      "do; it says nothing about whether a particular measurement fell below "
      "it. Only a limit bound to the result supports a censoring statement. "
      "CHMO is the sharpest case in the table: it declares `limit of detection` "
      "and `limit of quantification` from the IUPAC Gold Book, and binds them "
      "to the METHOD, as a `figure of merit` of an assay. That is a better "
      "place than a sensor and still not a place from which any particular "
      "result can be called censored.\n")

    if CAVEATS:
        A("## Scored **yes**, but not the same concept\n")
        A("Every cell above is decided by the stated method: does the ontology "
          "have a TERM whose name or label matches the concept family. Where "
          "that method credits an ontology with a concept it does not really "
          "carry, the cell is left standing -- demoting a competitor by "
          "adjusting a pattern until it scores the way we want is exactly the "
          "move this table exists to avoid -- and the discrepancy is recorded "
          "here instead. Each was checked by reading the term's own superclass "
          "in the file.\n")
        for name, notes in CAVEATS.items():
            if name not in results or results[name][0] != "OK":
                continue
            A(f"- **{name}**")
            for concept, note in notes:
                if results[name][1].get(concept):
                    A(f"    - `{concept}` — {note}")
        A("")

    if any(prose_only.values()):
        A("## Prose-only mentions — NOT scored\n")
        A("These concepts appear in a comment or definition but the ontology has "
          "no term for them. In large ontologies this is noise: ENVO's "
          "\"undecidable\" hit is *indeterminate root nodule*.\n")
        for name, d in prose_only.items():
            hits = {k: v for k, v in d.items() if v}
            if not hits:
                continue
            A(f"- **{name}**: " + ", ".join(f"{k} ({len(v)})" for k, v in hits.items()))
        A("")

    A("## Profile: reuse, FAIR and measurement modality\n")
    A("Keyword presence is only half the comparison. This table asks whether an "
      "ontology is reusable at all, whether it builds on SOSA/SSN, and whether "
      "its vocabulary describes **sensing** (a device observing in situ) or "
      "**sampling** (a specimen taken and analysed later). Trace organic "
      "monitoring is the second; the detection-limit gap follows from a field "
      "that inherited the first.\n")
    A("| Ontology | entities | labels | licence | versionIRI | imports | "
      "reuses SOSA | sampling terms | sensing terms |")
    A("|---|---|---|---|---|---|---|---|---|")
    for name, pr in profiles.items():
        A(f"| {name} | {results[name][2]} | {pr['label_coverage']:.0%} | "
          f"{'yes' if pr['licence'] else '—'} | "
          f"{'yes' if pr['versionIRI'] else '—'} | {pr['imports']} | "
          f"{'yes' if pr['reuses_sosa'] else '—'} | "
          f"{pr['sampling_terms']} | {pr['sensing_terms']} |")
    A("")

    A("## Evidence\n")
    for name, (status, found, n_ent, binding) in results.items():
        if status != "OK" or not found:
            continue
        A(f"### {name}\n")
        for c in order:
            if not found.get(c):
                continue
            A(f"**{c.replace('_', ' ')}**")
            for ev in found[c][:6]:
                A(f"- `{ev}`")
            if len(found[c]) > 6:
                A(f"- … and {len(found[c]) - 6} more")
            A("")

    A("## How to read this\n")
    A("The novelty claim, stated precisely after this check:\n")
    A("1. SSN's Systems module **does** define `ssn-system:DetectionLimit`, but "
      "as a subclass of `ssn-system:SystemProperty` -- metadata about a sensor's "
      "capability. It is never attached to a `sosa:Observation` or its result, "
      "so nothing in SOSA/SSN can state that a given measurement fell below it.\n")
    A("2. No comparison ontology represents a **censoring status** on a result, "
      "an **interval-valued** result arising from censoring, or an "
      "**undecidable** compliance outcome.\n")
    A("3. Thresholds are represented by several vocabularies, so thresholds are "
      "explicitly **not** claimed as novel here.\n")
    A("The original claim -- that SOSA/SSN has no notion of a detection limit -- "
      "was too strong and is withdrawn. What survives is sharper: the limit is "
      "known about the instrument and forgotten about the measurement.\n")
    A("If any cell above contradicts the claim, the claim is revised — that is "
      "what this script is for.\n")

    text = "\n".join(L)
    (EVAL / "gap_table.md").write_text(text, encoding="utf-8")

    # ---- LaTeX for the manuscript ------------------------------------------
    # Emitted from the same `results` dict that produced the Markdown, so the
    # table in the paper cannot drift from the table that was verified. It is
    # \input by paper/sections/05-results.tex; nothing is transcribed by hand.
    TEX = ROOT / "paper" / "tables"
    TEX.mkdir(parents=True, exist_ok=True)
    SHORT = {"detection_limit": "det.\\ limit", "censoring": "censoring",
             "undecidable": "undecid.", "threshold": "threshold",
             "interval_result": "interval", "applicability": "applic."}
    BIND_TEX = {"result": "\\textbf{the result}", "method": "the method",
                "sensor": "the sensor", "unclear": "unclear", "": "--"}
    T = []
    B = T.append
    B("% GENERATED by scripts/07_verify_gap_table.py -- do not edit.")
    B("\\begin{table*}[htbp]\\centering")
    B("\\caption{Concepts present in published water and observation "
      "ontologies, decided by parsing each ontology file rather than its "
      "documentation. A dash means the file parsed and the concept was absent; "
      "\\texttt{?} means it could not be retrieved, and no claim is made. The "
      "\\emph{LOD bound to} column is the discriminating one: a detection limit "
      "declared as a sensor capability cannot state that a given measurement "
      "fell below it. The two rows marked \\emph{this work} are CENSO's own "
      "modules and are not among the assessed vocabularies, which is why the "
      "text counts eighteen where the table has twenty rows.}")
    B("\\label{tab:gap}")
    # Nine columns overran the measure by 24 mm at \\footnotesize with the
    # default 6 pt gutters. Tightening the gutters and dropping one size step
    # fits it without \\resizebox, which would scale the rules and the text by
    # different amounts and print at a size no reader chose.
    B("\\scriptsize\\setlength{\\tabcolsep}{3.5pt}")
    B("\\begin{tabular}{l r l " + "c" * len(order) + "}")
    B("\\toprule")
    B("Ontology & Ent. & LOD bound to & "
      + " & ".join(SHORT.get(c, c.replace("_", " ")) for c in order)
      + " \\\\")
    B("\\midrule")
    for name, (status, found, n_ent, binding) in results.items():
        nm = name.replace("&", "\\&").replace("_", "\\_")
        if status != "OK":
            B(f"{nm} & ? & ? & " + " & ".join("?" for _ in order) + " \\\\")
            continue
        cells = ["\\checkmark" if found.get(c) else "--" for c in order]
        if "this work" in name:
            nm = f"\\textbf{{{nm}}}"
        B(f"{nm} & {n_ent} & {BIND_TEX[binding]} & "
          + " & ".join(cells) + " \\\\")
    B("\\bottomrule")
    B("\\end{tabular}")
    B("\\end{table*}")
    tex_path = TEX / "tab_gap.tex"
    tex_path.write_text("\n".join(T) + "\n", encoding="utf-8")

    # ---- machine-readable form, for the capability figure ------------------
    import csv as _csv
    PROCD = ROOT / "derived" / "processed"
    PROCD.mkdir(parents=True, exist_ok=True)
    with (PROCD / "gap_matrix.csv").open("w", newline="",
                                         encoding="utf-8") as fh:
        w = _csv.writer(fh)
        w.writerow(["ontology", "status", "entities", "lod_bound_to"] + order)
        for name, (status, found, n_ent, binding) in results.items():
            w.writerow([name, status, n_ent, binding]
                       + [("1" if found.get(c) else "0") if status == "OK"
                          else "?" for c in order])

    print("\n" + text[:2500])
    print(f"\nwrote: {EVAL/'gap_table.md'}")
    print(f"wrote: {tex_path.relative_to(ROOT)}  "
          f"({len(results)} ontologies x {len(order)} concepts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
