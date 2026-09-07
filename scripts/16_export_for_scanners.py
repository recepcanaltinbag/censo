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
# Which external terms this file must re-declare is DERIVED, not listed.
#
# It was a hand-written dict, and it went stale the way hand-written things do:
# after censo:analysedSample was retired it still declared sosa:Sample, which
# OOPS! then reported as an unconnected element (P04) -- a class the standalone
# distribution declares and nothing uses. In the other direction it never
# listed sosa:usedProcedure, which IS referenced, in the cardinality restriction
# on censo:AssessedObservation, so OOPS! reported an untyped class (P34).
# One list, drifting in both directions at once.
#
# Note this is a DECLARATION, not an axiom about somebody else's term: OWL 2
# expects an entity used in an ontology to be declared in it or in an import,
# and the imports are stripped here precisely so a scanner can read one file.
# Re-stating "sosa:Procedure is a class" says nothing SOSA does not already say.
# Asserting a KEY on sosa:Observation would have been the other thing, and it is
# not done here -- see the note on owl:hasKey in censo-core.ttl.
SOURCE_OF = {
    "http://www.w3.org/ns/sosa/": "SOSA",
    "http://www.w3.org/ns/ssn/": "SSN",
    "http://www.w3.org/ns/prov#": "PROV-O",
    "http://www.w3.org/2004/02/skos/core#": "SKOS",
    "http://qudt.org/schema/qudt/": "QUDT",
    "http://xmlns.com/foaf/0.1/": "FOAF",
}


def _external(u):
    from rdflib import URIRef
    return (isinstance(u, URIRef)
            and not str(u).startswith("https://w3id.org/censo")
            and any(str(u).startswith(k) for k in SOURCE_OF))


def _label(iri):
    """A human label from the local name: Observable property, was derived from."""
    import re
    local = str(iri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    words = re.sub(r"(?<!^)(?=[A-Z])", " ", local).split()
    return " ".join([words[0].capitalize()] + [w.lower() for w in words[1:]]) \
        if words else local


def referenced_externals(g):
    """{iri: (label, source)} for every external term the modules actually use."""
    from rdflib import RDF, RDFS, OWL
    cls, prop = set(), set()
    for pred in (RDFS.subClassOf, RDFS.domain, RDFS.range, OWL.onClass):
        for _, o in g.subject_objects(pred):
            if _external(o):
                cls.add(o)
    for pred in (OWL.members, OWL.unionOf):
        for _, o in g.subject_objects(pred):
            for it in g.items(o):
                if _external(it):
                    cls.add(it)
    for _, o in g.subject_objects(RDF.type):
        if _external(o):
            cls.add(o)
    for pred in (OWL.onProperty, RDFS.subPropertyOf):
        # subPropertyOf matters: cereg:sourceDocument is a subproperty of
        # prov:hadPrimarySource, which appears nowhere else, so scanning only
        # predicates left it undeclared and OOPS! reported P35.
        for _, o in g.subject_objects(pred):
            if _external(o):
                prop.add(o)
    for _, o in g.subject_objects(OWL.hasKey):
        for it in g.items(o):
            if _external(it):
                prop.add(it)
    for s_, p_, _ in g:
        if str(s_).startswith("https://w3id.org/censo") and _external(p_):
            prop.add(p_)
    # ANNOTATION or OBJECT, inferred from how we use it rather than assumed.
    # Typing everything owl:ObjectProperty declared skos:definition,
    # skos:example and skos:scopeNote as object properties, which then drew
    # OOPS! P11 (missing domain or range) -- a complaint that is correct for an
    # object property and meaningless for an annotation property. A property we
    # only ever give literals to is an annotation property.
    from rdflib import Literal
    kind = {}
    for x in prop:
        objs = [o for _, o in g.subject_objects(x)]
        kind[x] = (OWL.AnnotationProperty
                   if objs and all(isinstance(o, Literal) for o in objs)
                   else OWL.ObjectProperty)

    src = lambda u: next(v for k, v in SOURCE_OF.items() if str(u).startswith(k))
    return ({str(c): (_label(c), src(c)) for c in cls},
            {str(x): (_label(x), src(x), kind[x]) for x in prop})

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
    ext_cls, ext_prop = referenced_externals(g)
    for iri, (label, src) in sorted(ext_cls.items()):
        u = URIRef(iri)
        g.add((u, rdflib.RDF.type, OWL.Class))
        g.add((u, RDFS.label, Literal(label, lang="en")))
        g.add((u, RDFS.comment,
               Literal(f"Reused from {src}; declared here only so that this "
                       f"standalone distribution is self-describing.",
                       lang="en")))
        n_ext += 1
    for iri, (label, src, ptype) in sorted(ext_prop.items()):
        u = URIRef(iri)
        g.add((u, rdflib.RDF.type, ptype))
        g.add((u, RDFS.label, Literal(label, lang="en")))
        g.add((u, RDFS.comment,
               Literal(f"Reused from {src}; declared here only so that this "
                       f"standalone distribution is self-describing. Its "
                       f"domain and range are {src}'s to state, not ours.",
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
