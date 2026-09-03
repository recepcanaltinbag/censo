#!/usr/bin/env python3
"""
Validate ontology modules before they are published or cited.

Checks, in order of how badly a reviewer would react to a failure:

  1. Does it parse?
  2. Are the ontology header and metadata complete (title, licence, versionIRI,
     preferred prefix)? -- FAIR F2/R1.1
  3. Does every declared entity carry an rdfs:label? -- OOPS! P08
  4. Are imports declared?
  5. Are there any logical axioms at all (disjointness, equivalent classes,
     property characteristics)? An ontology with none is inert: a reasoner will
     report "consistent" trivially because nothing could contradict anything.
  6. Do any entity IRIs contain the Protege default pattern, a personal
     username, or the word "untitled"?
  7. Are there thresholds whose transcription status is still unverified?

Exit code 0 when no ERROR-level problem is found; 1 otherwise. WARN does not
fail the build.

Usage:  python scripts/validate_ontology.py [file.ttl ...]
        (no arguments -> validates every .ttl under ontology/)
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from rdflib import Graph, RDF, RDFS, OWL, URIRef, Namespace
    from rdflib.namespace import DCTERMS, SKOS
except ImportError:
    sys.exit("rdflib is required:  pip install rdflib")

ROOT = Path(__file__).resolve().parent.parent
ONTO = ROOT / "ontology"

VANN = Namespace("http://purl.org/vocab/vann/")
CEREG = Namespace("https://w3id.org/censo/reg/")

BAD_IRI_PATTERNS = ["untitled-ontology", "www.semanticweb.org", "ontologies/2018/0"]

ENTITY_TYPES = [OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty,
                OWL.AnnotationProperty, OWL.NamedIndividual]


class Report:
    def __init__(self, name):
        self.name = name
        self.errors = []
        self.warns = []
        self.info = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warns.append(msg)

    def note(self, msg):
        self.info.append(msg)

    def emit(self):
        status = "FAIL" if self.errors else ("WARN" if self.warns else "PASS")
        print(f"\n{'='*72}\n{status}  {self.name}\n{'='*72}")
        for m in self.info:
            print(f"  ·      {m}")
        for m in self.warns:
            print(f"  WARN   {m}")
        for m in self.errors:
            print(f"  ERROR  {m}")
        return not self.errors


def local_name(term) -> str:
    s = str(term)
    return s.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def validate(path: Path) -> bool:
    rep = Report(str(path.relative_to(ROOT)))
    g = Graph()
    try:
        g.parse(path, format="turtle")
    except Exception as e:
        rep.error(f"does not parse: {e}")
        return rep.emit()

    rep.note(f"{len(g)} triples")

    # ---- 2. ontology header ------------------------------------------------
    onts = list(g.subjects(RDF.type, OWL.Ontology))
    if not onts:
        rep.error("no owl:Ontology declaration")
        onto = None
    elif len(onts) > 1:
        rep.error(f"{len(onts)} owl:Ontology declarations; expected exactly one")
        onto = onts[0]
    else:
        onto = onts[0]

    if onto is not None:
        rep.note(f"ontology IRI: {onto}")
        required = {
            "dcterms:title": (onto, DCTERMS.title, None),
            "dcterms:license": (onto, DCTERMS.license, None),
            "owl:versionIRI": (onto, OWL.versionIRI, None),
            "owl:versionInfo": (onto, OWL.versionInfo, None),
            "vann:preferredNamespacePrefix": (onto, VANN.preferredNamespacePrefix, None),
        }
        for label, triple in required.items():
            if not list(g.triples(triple)):
                rep.error(f"missing {label} on the ontology header (FAIR F2/R1.1)")

        imports = list(g.objects(onto, OWL.imports))
        if imports:
            rep.note(f"imports: {', '.join(local_name(i) or str(i) for i in imports)}")
        else:
            rep.warn("no owl:imports — check that standard vocabularies are reused, "
                     "not re-invented")

    # ---- 6. IRI hygiene ----------------------------------------------------
    for pat in BAD_IRI_PATTERNS:
        hits = {s for s in g.subjects() if isinstance(s, URIRef) and pat in str(s)}
        if hits:
            rep.error(f"{len(hits)} IRIs contain '{pat}' — Protege default namespace "
                      f"is not publishable")

    # ---- 3. labels ---------------------------------------------------------
    entities = set()
    for t in ENTITY_TYPES:
        entities |= {s for s in g.subjects(RDF.type, t) if isinstance(s, URIRef)}
    entities -= set(onts)

    unlabelled = [e for e in entities if not list(g.objects(e, RDFS.label))]
    uncommented = [e for e in entities
                   if not list(g.objects(e, RDFS.comment))
                   and not list(g.objects(e, SKOS.definition))]

    rep.note(f"declared entities: {len(entities)}")
    if unlabelled:
        rep.error(f"{len(unlabelled)} entities without rdfs:label (OOPS! P08): "
                  + ", ".join(sorted(local_name(e) for e in unlabelled)[:8])
                  + (" …" if len(unlabelled) > 8 else ""))
    else:
        rep.note("all entities carry rdfs:label")

    if uncommented:
        rep.warn(f"{len(uncommented)} entities without rdfs:comment or skos:definition: "
                 + ", ".join(sorted(local_name(e) for e in uncommented)[:8])
                 + (" …" if len(uncommented) > 8 else ""))

    # ---- 5. logical content ------------------------------------------------
    axioms = {
        "owl:equivalentClass": len(list(g.triples((None, OWL.equivalentClass, None)))),
        "owl:disjointWith": len(list(g.triples((None, OWL.disjointWith, None)))),
        "owl:AllDisjointClasses": len(list(g.subjects(RDF.type, OWL.AllDisjointClasses))),
        "owl:inverseOf": len(list(g.triples((None, OWL.inverseOf, None)))),
        "owl:FunctionalProperty": len(list(g.subjects(RDF.type, OWL.FunctionalProperty))),
        "owl:TransitiveProperty": len(list(g.subjects(RDF.type, OWL.TransitiveProperty))),
        "owl:Restriction": len(list(g.subjects(RDF.type, OWL.Restriction))),
        # An alignment module's logical content IS its identity assertions, and
        # the census reported "no logical axioms at all" over a file whose whole
        # point is 30 of them. A warning that fires on the one module doing the
        # thing it asks about is a broken warning.
        "owl:sameAs": len(list(g.triples((None, OWL.sameAs, None)))),
        "owl:equivalentProperty": len(list(
            g.triples((None, OWL.equivalentProperty, None)))),
    }
    present = {k: v for k, v in axioms.items() if v}
    rep.note("logical axioms: " + (", ".join(f"{k}={v}" for k, v in present.items())
                                   if present else "NONE"))

    # A regulation package is a DATA module: it imports the vocabulary and
    # contributes individuals only. Having no axioms of its own is the
    # requirement, not a defect -- a package that declared classes could not be
    # swapped for another safely. Distinguish the two cases rather than warning
    # about a property the artefact is supposed to have.
    is_data_module = (not entities
                      and any("censo/reg/" in str(i) for i in
                              (g.objects(onto, OWL.imports) if onto else ()))
                      and list(g.subjects(RDF.type, URIRef(
                          "https://w3id.org/censo/reg/RegulationPackage"))))
    if is_data_module:
        n_ind = len(set(g.subjects(RDF.type, URIRef(
            "https://w3id.org/censo/Threshold"))) |
            {s for s in g.subjects() if isinstance(s, URIRef)})
        rep.note(f"regulation package: individuals only, no term declarations "
                 f"— which is what makes it swappable ({n_ind} subjects)")
    elif not present:
        rep.warn("no logical axioms at all — a reasoner will report 'consistent' "
                 "trivially, because no construct present could produce a "
                 "contradiction. Do not present that as validation.")

    # ---- domain/range coverage --------------------------------------------
    props = ({s for s in g.subjects(RDF.type, OWL.ObjectProperty)}
             | {s for s in g.subjects(RDF.type, OWL.DatatypeProperty)})
    nodomain = [p for p in props if not list(g.objects(p, RDFS.domain))]
    if nodomain:
        rep.warn(f"{len(nodomain)}/{len(props)} properties without rdfs:domain: "
                 + ", ".join(sorted(local_name(p) for p in nodomain)[:8])
                 + (" …" if len(nodomain) > 8 else ""))

    # ---- 7. unverified thresholds -----------------------------------------
    unverified = list(g.subjects(CEREG.transcriptionStatus, CEREG.Unverified))
    secondary = list(g.subjects(CEREG.transcriptionStatus,
                                CEREG.TranscribedFromSecondarySource))
    if unverified:
        rep.warn(f"{len(unverified)} thresholds still cereg:Unverified — must not be "
                 f"quoted in analysis")
    if secondary:
        rep.warn(f"{len(secondary)} thresholds from a secondary source — verify against "
                 f"the legal text")

    return rep.emit()


def main() -> int:
    args = sys.argv[1:]
    # dist/ holds generated distributions, which legitimately merge modules and
    # therefore carry more than one owl:Ontology header. They are validated by
    # scripts/16_export_for_scanners.py against its own rules, not these.
    files = ([Path(a).resolve() for a in args] if args
             else sorted(f for f in ONTO.rglob("*.ttl")
                         if "dist" not in f.parts))
    if not files:
        sys.exit("no .ttl files found under ontology/")

    results = [validate(f) for f in files]
    n_ok = sum(results)
    print(f"\n{'='*72}\n{n_ok}/{len(results)} module(s) passed\n{'='*72}")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
