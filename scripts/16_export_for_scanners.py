#!/usr/bin/env python3
"""
Export CENSO in a form the public ontology scanners will accept.

WHY THIS IS NOT JUST A MERGE
----------------------------
OOPS! and FOOPS! parse with the OWL API / Jena, which are stricter than rdflib.
Two things in a naive rdflib merge break them:

  * `owl:versionIRI censo:2.0.0` -- a prefixed name whose local part contains
    dots is ambiguous in Turtle, because the final `.0` can be read as the
    statement terminator. rdflib round-trips its own output happily; stricter
    parsers do not. Version IRIs are therefore written as full IRIs in angle
    brackets.
  * unresolvable `owl:imports`. The scanners try to fetch them and fail, or
    silently evaluate only the fragment they could load. They are dropped here
    and the reuse is recorded with rdfs:seeAlso so the information is not lost.

RDF/XML is emitted alongside Turtle because OOPS! has historically been most
reliable with it.

Outputs: ontology/dist/censo-full.ttl
         ontology/dist/censo-full.owl   (RDF/XML)

Usage:  python scripts/16_export_for_scanners.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONTO = ROOT / "ontology"
DIST = ONTO / "dist"

try:
    import rdflib
    from rdflib import OWL, RDFS, URIRef
except ImportError:
    sys.exit("rdflib is required:  pip install rdflib")

MODULES = ["censo-core.ttl", "censo-regulation.ttl"]

# Reuse we want on record even though the imports are stripped for the scanners.
SEE_ALSO = [
    "http://www.w3.org/ns/sosa/",
    "http://www.w3.org/ns/ssn/",
    "http://www.w3.org/ns/prov#",
    "http://www.w3.org/2004/02/skos/core",
    "http://qudt.org/schema/qudt/",
]


# Terms borrowed from external vocabularies. When the imports are stripped so
# the scanners can read the file, these lose their declarations and are reported
# as "untyped class/property" (OOPS! P34/P35) and "missing annotations" (P08).
# The defect is in the standalone packaging, not in the ontology, so the
# distribution re-declares them with a note saying where they come from.
EXTERNAL_CLASSES = {
    "http://www.w3.org/ns/sosa/FeatureOfInterest": ("Feature of interest", "SOSA"),
    "http://www.w3.org/ns/sosa/ObservableProperty": ("Observable property", "SOSA"),
    "http://www.w3.org/ns/sosa/Procedure": ("Procedure", "SOSA"),
    "http://www.w3.org/ns/sosa/Sample": ("Sample", "SOSA"),
    "http://www.w3.org/ns/sosa/Observation": ("Observation", "SOSA"),
    "http://www.w3.org/ns/prov#Activity": ("Activity", "PROV-O"),
    "http://www.w3.org/ns/prov#Entity": ("Entity", "PROV-O"),
    "http://www.w3.org/2004/02/skos/core#Concept": ("Concept", "SKOS"),
    "http://qudt.org/schema/qudt/Unit": ("Unit", "QUDT"),
    "http://xmlns.com/foaf/0.1/Person": ("Person", "FOAF"),
}
EXTERNAL_PROPERTIES = {
    "http://www.w3.org/ns/prov#wasDerivedFrom": ("was derived from", "PROV-O"),
    "http://www.w3.org/ns/prov#hadPrimarySource": ("had primary source", "PROV-O"),
}


def main() -> int:
    DIST.mkdir(parents=True, exist_ok=True)

    g = rdflib.Graph()
    for m in MODULES:
        p = ONTO / m
        if not p.exists():
            sys.exit(f"missing {p}")
        g.parse(p, format="turtle")
        print(f"  + {m}")

    onts = [s for s in g.subjects(rdflib.RDF.type, OWL.Ontology)]

    # Drop imports the scanners cannot resolve; keep the fact of reuse.
    dropped = 0
    for s, p_, o in list(g.triples((None, OWL.imports, None))):
        g.remove((s, p_, o))
        dropped += 1
    for o in onts:
        for u in SEE_ALSO:
            g.add((o, RDFS.seeAlso, URIRef(u)))

    # re-declare borrowed terms so the standalone file is self-describing
    from rdflib import Literal
    n_ext = 0
    for iri, (label, src) in EXTERNAL_CLASSES.items():
        u = URIRef(iri)
        g.add((u, rdflib.RDF.type, OWL.Class))
        g.add((u, RDFS.label, Literal(label, lang="en")))
        g.add((u, RDFS.comment,
               Literal(f"Reused from {src}; declared here only so that this "
                       f"standalone distribution is self-describing.",
                       lang="en")))
        n_ext += 1
    PROV_ENTITY = URIRef("http://www.w3.org/ns/prov#Entity")
    for iri, (label, src) in EXTERNAL_PROPERTIES.items():
        u = URIRef(iri)
        g.add((u, rdflib.RDF.type, OWL.ObjectProperty))
        # PROV's own domain and range, so the standalone file does not leave
        # them undefined (OOPS! P11).
        g.add((u, RDFS.domain, PROV_ENTITY))
        g.add((u, RDFS.range, PROV_ENTITY))
        g.add((u, RDFS.label, Literal(label, lang="en")))
        g.add((u, RDFS.comment,
               Literal(f"Reused from {src}; declared here only so that this "
                       f"standalone distribution is self-describing.",
                       lang="en")))
        n_ext += 1

    ttl = g.serialize(format="turtle")

    # Rewrite prefixed version IRIs as full IRIs. rdflib emits
    # `owl:versionIRI censo:2.0.0`, which stricter parsers mis-read.
    def expand(match):
        pref, local = match.group(1), match.group(2)
        base = {"censo": "https://w3id.org/censo/",
                "cereg": "https://w3id.org/censo/reg/"}.get(pref)
        return f"owl:versionIRI <{base}{local}>" if base else match.group(0)

    ttl, n_fixed = re.subn(r"owl:versionIRI\s+(\w+):([\w.]+)", expand, ttl)

    out_ttl = DIST / "censo-full.ttl"
    out_ttl.write_text(ttl, encoding="utf-8")

    # Re-read the corrected Turtle and emit RDF/XML from it, so both files are
    # generated from the same corrected graph rather than diverging.
    g2 = rdflib.Graph()
    g2.parse(data=ttl, format="turtle")
    out_owl = DIST / "censo-full.owl"
    g2.serialize(destination=str(out_owl), format="xml")

    print(f"\n  external terms re-declared       : {n_ext}")
    print(f"  imports dropped for the scanners : {dropped}")
    print(f"  version IRIs rewritten as full   : {n_fixed}")
    print(f"  triples                          : {len(g2)}")
    print(f"\n  {out_ttl.relative_to(ROOT)}  ({out_ttl.stat().st_size/1024:.0f} KB)")
    print(f"  {out_owl.relative_to(ROOT)}  ({out_owl.stat().st_size/1024:.0f} KB)")

    # sanity checks a scanner would also perform
    problems = []
    if re.search(r"owl:versionIRI\s+\w+:", ttl):
        problems.append("a prefixed versionIRI survived")
    if "owl:imports" in ttl:
        problems.append("an owl:imports survived")
    for s in g2.subjects(rdflib.RDF.type, OWL.Class):
        if isinstance(s, URIRef) and not list(g2.objects(s, RDFS.label)):
            problems.append(f"class without label: {s}")
    print("\n  checks: " + ("OK" if not problems else "; ".join(problems[:5])))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
