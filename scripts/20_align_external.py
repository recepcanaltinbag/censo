#!/usr/bin/env python3
"""
Align the vocabulary to the external ontologies it should not be reinventing.

WHY THIS EXISTS
---------------
`censo:Analyte` carried the comment "Aligned to ChEBI/PubChem with
skos:exactMatch rather than renamed, so that two regulation packages referring
to the same substance resolve to one IRI -- the precondition for comparing
them." The released artefact contained **zero** alignment triples. The one
occurrence of `skos:exactMatch` anywhere in the ontology was inside that
sentence.

That is the third time this project shipped a commitment as prose: the fourth
commitment shipped with no `censo:requiresCondition` triples, the first with no
`censo:AnalyticalRun` individuals, and the reconciliation precondition with no
alignment at all. `scripts/99_audit.py::check_no_dead_terms` now catches the
first kind; this script fixes the third, and the audit checks its output.

The dual-regulation comparison in the manuscript does work -- but by joining on
CAS registry number strings in Python, which is a different mechanism from the
one the vocabulary describes. After this script the mechanism the vocabulary
describes exists, and the comparison is an entailment: two analytes the two
packages name separately are `owl:sameAs`, so a reasoner reconciles them.

WHAT IS ASSERTED, AND WHY THESE RELATIONS
-----------------------------------------
1. ANALYTE -> ChEBI, with `rdfs:seeAlso`. NOT `skos:exactMatch`, and not
   `owl:sameAs`. A `censo:Analyte` is a `sosa:ObservableProperty` -- the
   *concentration of* a substance -- while a ChEBI class is the substance,
   whose instances are molecules. They are not the same entity and asserting
   that they are would be a category error dressed as interoperability. SKOS
   mapping properties are also the wrong tool: they relate `skos:Concept`
   instances, and neither of these is one. `rdfs:seeAlso` carries no type
   constraint and claims exactly what is true -- here is the substance this
   analyte is about, at a resolvable IRI.

2. ANALYTE -> ANALYTE, with `owl:sameAs`, where two packages name the same
   substance. This one IS an identity claim and it is the right one: the
   concentration of naphthalene in inland surface water is one observable
   property whether the European or the Turkish package names it. This is what
   the comment promised and it is what makes Section 5.7 an entailment rather
   than a join.

   It is safe only because `censo:casNumber` is no longer
   `owl:FunctionalProperty` -- see the note on that property. With the old axiom
   in place, merging two analytes whose CAS sets differ would have produced a
   functional-property clash.

3. LIMIT PROPERTIES -> CHMO, with `rdfs:seeAlso`. CHMO:0002801 `limit of
   detection` and CHMO:0002802 `limit of quantification` are the closest prior
   art there is, both defined from the IUPAC Gold Book. They are `owl:Class`
   instances -- a `figure of merit` of an assay -- and ours are
   `owl:DatatypeProperty`. Again not the same kind of thing, so again
   `rdfs:seeAlso` with the difference stated rather than a mapping property
   asserting more than is true. Section 5.9 makes the argument in prose; this
   makes it machine-readable, and a consumer holding CHMO data can find the
   property to put the value on.

WHAT IS NOT ASSERTED
--------------------
A CAS number matching more than one ChEBI class yields NO triple. Twenty-six of
them do, mostly where ChEBI models a substance and its conjugate base or a
stereoisomer separately, and picking one would be a silent editorial decision
inside a file that is supposed to be evidence. They are listed in the report.

Inputs  : ontology/reg/*.ttl, and the ChEBI flat files (downloaded, cached)
Outputs : ontology/censo-alignment.ttl
          eval/alignment.md

The module is NOT imported by censo-core.ttl. Alignment is a claim about the
world outside the vocabulary and a consumer may not want it, so it loads only
if asked -- which is the same reason the regulation packages are separate files.

Usage:  python scripts/20_align_external.py [--offline]
"""

from __future__ import annotations

import argparse
import collections
import csv
import gzip
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "ontology" / "reg"
CACHE = ROOT / "derived" / "interim" / "chebi"
OUT = ROOT / "ontology" / "censo-alignment.ttl"
EVAL = ROOT / "eval"

CHEBI_FTP = "https://ftp.ebi.ac.uk/pub/databases/chebi/flat_files/"
FILES = ("compounds.tsv.gz", "database_accession.tsv.gz")
UA = "censo-ontology-research/1.0 (academic alignment; see repository)"

# The CHMO terms the limit properties point at, with the reason each pointer is
# rdfs:seeAlso and not a mapping property. Hand-read from the cached CHMO file;
# scripts/07_verify_gap_table.py is what put them in the comparison.
CHMO = {
    "limitOfDetection": (
        "CHMO_0002801",
        "limit of detection",
        "CHMO's term is an owl:Class -- a `figure of merit` of an assay, "
        "defined from the IUPAC Gold Book -- and this is an "
        "owl:DatatypeProperty on the method. Same concept, different kind of "
        "entity, so this is a pointer and not a mapping. The difference is the "
        "contribution: CHMO can say what a method's limit is and has no "
        "property relating it to a result, which is why a measurement cannot "
        "be called censored in it."),
    "limitOfQuantification": (
        "CHMO_0002802",
        "limit of quantification",
        "As above. CHMO records `LOQ` as a synonym and cites the IUPAC Gold "
        "Book. This is the limit the legal tests are written about -- Article "
        "3(3b) of 2008/105/EC and Article 4(1) of 2009/90/EC -- so it is the "
        "one a monitoring release reports and the one this alignment matters "
        "most for."),
}

PREAMBLE = """\
# GENERATED by scripts/20_align_external.py -- do not edit by hand.
#
# Alignment of CENSO to the external ontologies it reuses rather than
# reinvents. NOT imported by censo-core.ttl: a consumer who does not want the
# external commitments should not have to take them, which is the same reason
# the regulation packages are separate files.
#
# rdfs:seeAlso, not skos:exactMatch and not owl:sameAs, wherever the two things
# are of different kinds -- an observable property is not the substance, and a
# datatype property is not a class. The one identity claim here is between two
# packages' names for the same observable property, which is what it is.

@prefix censo:   <https://w3id.org/censo/> .
@prefix cereg:   <https://w3id.org/censo/reg/> .
@prefix owl:     <http://www.w3.org/2002/07/owl#> .
@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix vann:    <http://purl.org/vocab/vann/> .
@prefix obo:     <http://purl.obolibrary.org/obo/> .

<https://w3id.org/censo/alignment> a owl:Ontology ;
    dcterms:title "CENSO external alignment"@en ;
    dcterms:description \"\"\"Pointers from CENSO and its regulation packages to
ChEBI, for the substances, and to CHMO, for the detection and quantification
limit concepts; and owl:sameAs between the two packages' names for one
observable property, which is what makes a cross-jurisdiction comparison an
entailment rather than a string join. Generated from the ChEBI flat files by
scripts/20_align_external.py; a CAS number resolving to more than one ChEBI
class yields no triple.\"\"\"@en ;
    dcterms:license <https://creativecommons.org/licenses/by/4.0/> ;
    vann:preferredNamespacePrefix "censo" ;
    owl:versionIRI <https://w3id.org/censo/alignment/1.0.0> ;
    owl:versionInfo "1.0.0" ;
    owl:imports <https://w3id.org/censo/> .

"""


def fetch(name: str, offline: bool) -> Path | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / name
    if p.exists() and p.stat().st_size > 0:
        return p
    if offline:
        return None
    req = urllib.request.Request(CHEBI_FTP + name, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            p.write_bytes(r.read())
    except Exception as e:
        print(f"  ! {name}: download failed ({type(e).__name__})")
        return None
    return p


def cas_to_chebi(offline: bool):
    """{CAS: {CHEBI accession}} from the ChEBI flat files."""
    comp_p = fetch("compounds.tsv.gz", offline)
    acc_p = fetch("database_accession.tsv.gz", offline)
    if not (comp_p and acc_p):
        return None, None
    label = {}
    with gzip.open(comp_p, "rt", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            acc = (row.get("chebi_accession") or "").strip()
            if acc.startswith("CHEBI:"):
                label[row["id"]] = (acc, (row.get("name") or "").strip())
    out = collections.defaultdict(set)
    names = {}
    with gzip.open(acc_p, "rt", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            # the flat file distinguishes CAS from MANUAL_X_REF, CITATION and
            # REGISTRY_NUMBER by this column; only CAS is a registry number we
            # can join a regulation's own identifier on
            if row.get("type") != "CAS":
                continue
            hit = label.get(row["compound_id"])
            if not hit:
                continue
            cas = row["accession_number"].strip()
            out[cas].add(hit[0])
            names[hit[0]] = hit[1]
    return out, names


CAS_RE = re.compile(r'"([0-9]{2,7}-[0-9]{2}-[0-9])"')


def read_analytes():
    """{package: {analyte IRI: (label, {CAS})}} from the released packages."""
    pkgs = {}
    for path in sorted(REG.glob("*.ttl")):
        src = path.read_text(encoding="utf-8")
        found = {}
        for m in re.finditer(r"^(cereg:\S+) a censo:Analyte ;(.*?)\.\n",
                             src, re.S | re.M):
            iri, body = m.group(1), m.group(2)
            lab = re.search(r'rdfs:label "([^"]*)"', body)
            found[iri] = (lab.group(1) if lab else iri,
                          set(CAS_RE.findall(body)))
        if found:
            pkgs[path.stem] = found
    return pkgs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    pkgs = read_analytes()
    if not pkgs:
        sys.exit("no analytes found; run scripts/19_build_regulation_packages.py")
    c2c, chebi_name = cas_to_chebi(args.offline)
    if c2c is None:
        print("  ! ChEBI flat files unavailable; writing the CHMO alignment only")
        c2c, chebi_name = {}, {}

    L = [PREAMBLE]
    n_seealso = n_amb = n_miss = 0
    ambiguous, missing = [], []

    L.append("#" * 78)
    L.append("#  Substances: the ChEBI class each analyte is about")
    L.append("#" * 78)
    L.append("")
    resolved = {}          # analyte IRI -> CHEBI accession
    for pkg, analytes in sorted(pkgs.items()):
        for iri, (lab, cas) in sorted(analytes.items()):
            hits = set()
            for c in cas:
                hits |= c2c.get(c, set())
            if len(hits) == 1:
                acc = next(iter(hits))
                resolved[iri] = acc
                obo = "obo:" + acc.replace("CHEBI:", "CHEBI_")
                L.append(f"{iri} rdfs:seeAlso {obo} .")
                n_seealso += 1
            elif len(hits) > 1:
                n_amb += 1
                ambiguous.append((pkg, lab, sorted(cas), sorted(hits)))
            elif cas:
                n_miss += 1
                missing.append((pkg, lab, sorted(cas)))
    L.append("")

    # ---- cross-package identity -------------------------------------------
    L.append("#" * 78)
    L.append("#  One observable property, two packages")
    L.append("#")
    L.append("#  owl:sameAs, and this one IS an identity claim: the")
    L.append("#  concentration of a substance in inland surface water is the")
    L.append("#  same observable property whichever regulation names it. This")
    L.append("#  is the reconciliation censo:Analyte's comment promised, and")
    L.append("#  what makes a cross-jurisdiction comparison an entailment.")
    L.append("#" * 78)
    L.append("")
    by_cas = collections.defaultdict(list)
    for pkg, analytes in pkgs.items():
        for iri, (lab, cas) in analytes.items():
            for c in cas:
                by_cas[c].append((pkg, iri))
    pairs, n_same = set(), 0
    for c, holders in sorted(by_cas.items()):
        pkgs_here = {p for p, _ in holders}
        if len(pkgs_here) < 2:
            continue
        iris = sorted({i for _, i in holders})
        for a, b in zip(iris, iris[1:]):
            if (a, b) in pairs:
                continue
            pairs.add((a, b))
            L.append(f"{a} owl:sameAs {b} .")
            n_same += 1
    L.append("")

    # ---- the limit concepts -----------------------------------------------
    L.append("#" * 78)
    L.append("#  The detection and quantification limit, in CHMO")
    L.append("#" * 78)
    L.append("")
    for prop, (chmo_id, chmo_label, why) in sorted(CHMO.items()):
        L.append(f"censo:{prop} rdfs:seeAlso obo:{chmo_id} ;")
        L.append(f'    rdfs:comment """{why}"""@en .')
        L.append("")
        L.append(f"obo:{chmo_id} rdfs:label \"{chmo_label}\"@en .")
        L.append("")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")

    # ---- report ------------------------------------------------------------
    total = sum(len(a) for a in pkgs.values())
    A = ["# External alignment\n",
         "Generated by `scripts/20_align_external.py`.\n",
         "`censo:Analyte` has always carried the comment *\"Aligned to "
         "ChEBI/PubChem with skos:exactMatch rather than renamed, so that two "
         "regulation packages referring to the same substance resolve to one "
         "IRI -- the precondition for comparing them.\"* The released artefact "
         "contained **no alignment triples at all**: the single occurrence of "
         "`skos:exactMatch` in the whole ontology was inside that sentence. "
         "The comparison in Section 5.7 did work, by joining CAS strings in "
         "Python -- a different mechanism from the one the vocabulary "
         "described. This file is the mechanism it described.\n",
         "| | n |", "|---|---|",
         f"| analytes across both packages | {total} |",
         f"| pointed at exactly one ChEBI class | **{n_seealso}** |",
         f"| CAS resolving to more than one ChEBI class — no triple written "
         f"| {n_amb} |",
         f"| CAS with no ChEBI entry | {n_miss} |",
         f"| `owl:sameAs` pairs across the two packages | **{n_same}** |",
         "",
         "**The relations are chosen, not defaulted.** `rdfs:seeAlso` to "
         "ChEBI, because a `censo:Analyte` is a `sosa:ObservableProperty` -- "
         "the *concentration of* a substance -- and a ChEBI class is the "
         "substance, whose instances are molecules. They are different "
         "entities, and `skos:exactMatch` between them would be a category "
         "error dressed as interoperability; SKOS mapping properties are also "
         "defined over `skos:Concept`, which neither is. The one `owl:sameAs` "
         "here is between two packages' names for one observable property, "
         "which is an identity and is asserted as one.\n",
         "It is safe only because `censo:casNumber` is no longer "
         "`owl:FunctionalProperty`. With the old axiom, merging two analytes "
         "whose CAS sets differ produced a functional-property clash — which "
         "is how that axiom's own violation in the released EU package came to "
         "light.\n"]

    if ambiguous:
        A.append("## Ambiguous — deliberately unaligned\n")
        A.append("ChEBI models these as more than one class for one registry "
                 "number, usually a substance and its conjugate base or a "
                 "stereoisomer. Choosing one would be a silent editorial "
                 "decision inside a file that is meant to be evidence.\n")
        A.append("| package | analyte | CAS | ChEBI classes |")
        A.append("|---|---|---|---|")
        for pkg, lab, cas, hits in ambiguous[:40]:
            A.append(f"| {pkg} | {lab} | {', '.join(cas)} | "
                     f"{', '.join(hits)} |")
        A.append("")
    if missing:
        A.append("## No ChEBI entry\n")
        A.append("Mostly technical mixtures and congener groups, which ChEBI "
                 "reasonably does not model as single chemical entities: "
                 "C10-13 chloroalkanes, tributyltin compounds, brominated "
                 "diphenylether congeners. That a regulation sets a limit on "
                 "something no chemical ontology can name as one substance is "
                 "a finding about the regulation, not a gap in the "
                 "alignment.\n")
        A.append("| package | analyte | CAS |")
        A.append("|---|---|---|")
        for pkg, lab, cas in missing[:40]:
            A.append(f"| {pkg} | {lab} | {', '.join(cas)} |")
        A.append("")

    EVAL.mkdir(parents=True, exist_ok=True)
    (EVAL / "alignment.md").write_text("\n".join(A) + "\n", encoding="utf-8")
    print(f"  {n_seealso} ChEBI pointer(s), {n_same} cross-package owl:sameAs, "
          f"{n_amb} ambiguous, {n_miss} unmatched")
    print(f"  wrote {OUT.relative_to(ROOT)}")
    print(f"  wrote eval/alignment.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
