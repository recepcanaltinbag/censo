#!/usr/bin/env python3
"""Check the vocabulary against the OWL 2 RL grammar, and name what fails.

WHY THIS EXISTS
---------------
The manuscript claims the vocabulary stays inside OWL 2 RL. That claim was
asserted and never checked, and it was false: sixteen axioms sat outside the
profile while the pipeline ran correctly anyway, because owlrl applies rules
beyond RL. A reasoner being more capable than the profile is exactly what hides
a profile violation, so the claim needs a checker rather than a reasoner.

WHAT IS CHECKED
---------------
The three class-expression positions OWL 2 Profiles section 4.3 constrains:

  subClassExpression    left of rdfs:subClassOf
  superClassExpression  right of rdfs:subClassOf
  equivClassExpression  either side of owl:equivalentClass

with the grammar RL gives each. The constructs this vocabulary uses and RL
restricts are unions, someValuesFrom, allValuesFrom, complements and the
cardinality family; each is resolved to its position and reported with the
class it belongs to, so a violation is actionable rather than a count.

An owl:equivalentClass is not one axiom for this purpose. It entails a subclass
axiom in BOTH directions, and RL usually permits one and forbids the other --
which is why the repair is nearly always to write the direction that does the
work and drop the one that does not.

Outputs : eval/owl_profile.md
Usage:  python scripts/12_owl_profile.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONTO = ROOT / "ontology"
EVAL = ROOT / "eval"

try:
    import rdflib
    from rdflib.namespace import OWL, RDF, RDFS
except ImportError:                                          # pragma: no cover
    sys.exit("rdflib is required")

CARD = {OWL.cardinality: "exact cardinality",
        OWL.qualifiedCardinality: "exact qualified cardinality",
        OWL.minCardinality: "min cardinality",
        OWL.minQualifiedCardinality: "min qualified cardinality"}
MAXC = (OWL.maxCardinality, OWL.maxQualifiedCardinality)


def describe(g, node):
    """A short human name for a class expression."""
    if isinstance(node, rdflib.URIRef):
        return g.qname(node)
    for p, kind in ((OWL.unionOf, "union"),
                    (OWL.intersectionOf, "intersection"),
                    (OWL.complementOf, "complement"),
                    (OWL.oneOf, "enumeration")):
        if (node, p, None) in g:
            return kind
    if (node, RDF.type, OWL.Restriction) in g:
        for p in (OWL.someValuesFrom, OWL.allValuesFrom, OWL.hasValue):
            if (node, p, None) in g:
                prop = g.value(node, OWL.onProperty)
                return (f"{p.split('#')[1]} on "
                        f"{g.qname(prop) if prop else '?'}")
        for p in list(CARD) + list(MAXC):
            if (node, p, None) in g:
                prop = g.value(node, OWL.onProperty)
                n = g.value(node, p)
                return (f"{p.split('#')[1]} {n} on "
                        f"{g.qname(prop) if prop else '?'}")
    return "anonymous class"


def violations_in(g, node, position, seen=None):
    """RL grammar for one class expression in one position."""
    seen = seen or set()
    if node in seen:
        return []
    seen = seen | {node}
    out = []
    if isinstance(node, rdflib.URIRef):
        if node == OWL.Thing:
            out.append("owl:Thing is not a class expression in any RL position")
        return out

    if (node, OWL.unionOf, None) in g:
        # union is a subClassExpression only
        if position != "sub":
            out.append(f"union is not permitted in {position}ClassExpression")
        for m in g.items(g.value(node, OWL.unionOf)):
            out += violations_in(g, m, "sub" if position == "sub" else position,
                                 seen)
        return out

    if (node, OWL.intersectionOf, None) in g:
        for m in g.items(g.value(node, OWL.intersectionOf)):
            out += violations_in(g, m, position, seen)
        return out

    if (node, OWL.complementOf, None) in g:
        if position != "super":
            out.append(f"complement is not permitted in "
                       f"{position}ClassExpression")
        else:
            out += violations_in(g, g.value(node, OWL.complementOf), "sub", seen)
        return out

    if (node, OWL.oneOf, None) in g:
        if position != "sub":
            out.append(f"enumeration is not permitted in "
                       f"{position}ClassExpression")
        return out

    if (node, RDF.type, OWL.Restriction) in g:
        if (node, OWL.someValuesFrom, None) in g:
            if position != "sub":
                out.append(f"someValuesFrom is not permitted in "
                           f"{position}ClassExpression")
            else:
                f = g.value(node, OWL.someValuesFrom)
                if f != OWL.Thing:
                    out += violations_in(g, f, "sub", seen)
        if (node, OWL.allValuesFrom, None) in g:
            if position != "super":
                out.append(f"allValuesFrom is not permitted in "
                           f"{position}ClassExpression")
            else:
                out += violations_in(g, g.value(node, OWL.allValuesFrom),
                                     "super", seen)
        for p, name in CARD.items():
            if (node, p, None) in g:
                out.append(f"{name} is not in OWL 2 RL at all")
        for p in MAXC:
            v = g.value(node, p)
            if v is not None:
                if position != "super":
                    out.append(f"max cardinality is not permitted in "
                               f"{position}ClassExpression")
                elif str(v) not in ("0", "1"):
                    out.append(f"max cardinality {v} exceeds the 0 or 1 RL "
                               f"permits")
    return out


def owner(g, node):
    """The named class an anonymous expression hangs off, for the report."""
    for s, p in ((s, p) for p in (RDFS.subClassOf, OWL.equivalentClass)
                 for s in g.subjects(p, node)):
        if isinstance(s, rdflib.URIRef):
            return g.qname(s)
    return "—"


def main() -> int:
    g = rdflib.Graph()
    files = [ONTO / "censo-core.ttl", ONTO / "censo-regulation.ttl"]
    for f in files:
        if f.exists():
            g.parse(f, format="turtle")

    found = []
    for s, o in g.subject_objects(RDFS.subClassOf):
        for v in violations_in(g, o, "super"):
            found.append((owner(g, o) if not isinstance(s, rdflib.URIRef)
                          else g.qname(s), "rdfs:subClassOf",
                          describe(g, o), v))
    for s, o in g.subject_objects(OWL.equivalentClass):
        # an equivalence is checked in the equiv position, and separately as
        # the superClassExpression it entails -- the direction that usually
        # fails, and the one the repair drops
        name = g.qname(s) if isinstance(s, rdflib.URIRef) else owner(g, s)
        for v in dict.fromkeys(violations_in(g, o, "equiv")
                               + violations_in(g, o, "super")):
            found.append((name, "owl:equivalentClass", describe(g, o), v))

    found.sort()
    A = ["# OWL 2 RL profile check\n",
         "Generated by `scripts/12_owl_profile.py`. The manuscript claims the "
         "vocabulary stays inside OWL 2 RL; this checks the claim against the "
         "grammar in OWL 2 Profiles §4.3 rather than against a reasoner. A "
         "reasoner cannot detect a profile violation, because applying more "
         "rules than the profile requires is precisely what hides one --- "
         "which is how these went unnoticed while the pipeline ran "
         "correctly.\n",
         f"- axioms outside the profile: **{len(found)}**\n"]
    if found:
        A += ["| class | axiom | expression | why it is outside RL |",
              "|---|---|---|---|"]
        A += [f"| `{c}` | `{ax}` | {e} | {w} |" for c, ax, e, w in found]
        A.append("")
    else:
        A.append("The vocabulary is inside the profile.\n")
    EVAL.mkdir(parents=True, exist_ok=True)
    (EVAL / "owl_profile.md").write_text("\n".join(A) + "\n", encoding="utf-8")
    print(f"  {len(found)} axiom(s) outside OWL 2 RL")
    print("  wrote eval/owl_profile.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
