#!/usr/bin/env python3
"""
Emit the pluggable regulation packages the paper claims to offer.

WHY THIS EXISTS
---------------
`paper/sections/04-methods.tex` says regulations are "pluggable, versioned
packages", and `ontology/censo-regulation.ttl` defines the vocabulary for them
-- but `ontology/reg/` shipped only a README. A reviewer downloading the
artefact would have found nothing to plug in, and the modularity claim would
have rested entirely on prose. This script produces the packages themselves,
from the transcriptions that were verified against the primary legal texts:

  * `tr-ysky-2016.ttl`      from derived/processed/eqs_official.csv
                            (Table 4, Yerüstü Su Kalitesi Yönetmeliği)
  * `eu-2008-105-2026.ttl`  from derived/processed/eu_eqs.csv
                            (Directive 2008/105/EC consolidated 10 May 2026)

Each package is self-contained: it imports the vocabulary, declares its own
`cereg:RegulationPackage` with jurisdiction, dates, legal citation and source
document, and contributes ONLY threshold and analyte individuals. Nothing in a
package redefines a class or a property, which is what makes swapping one for
another safe.

That is the claim made testable: the same observations can be assessed under
either package by loading a different file, and the two answers can be held at
once because the thresholds carry different IRIs and different `definedBy`
links.

Every threshold carries `cereg:transcriptionStatus
cereg:VerifiedAgainstPrimarySource`, because both CSVs are produced by scripts
that parse the legal PDFs directly. Values from the project's working
spreadsheet are deliberately NOT emitted: seven of its ten metal values and a
further eleven organics disagree with the law.

Inputs  : derived/processed/{eqs_official,eu_eqs}.csv
Outputs : ontology/reg/tr-ysky-2016.ttl
          ontology/reg/eu-2008-105-2026.ttl
          eval/regulation_packages.md

Usage:  python scripts/19_build_regulation_packages.py
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
REG = ROOT / "ontology" / "reg"
EVAL = ROOT / "eval"


def slug(s: str) -> str:
    s = str(s)
    for a, b in (("ı", "i"), ("İ", "i"), ("ş", "s"), ("Ş", "s"), ("ğ", "g"),
                 ("Ğ", "g"), ("ç", "c"), ("Ç", "c"), ("ö", "o"), ("Ö", "o"),
                 ("ü", "u"), ("Ü", "u")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    return s or "unnamed"


def esc(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def num(x):
    try:
        v = float(str(x).strip())
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def dec(v: float) -> str:
    """Canonical xsd:decimal LEXICAL form. Display only -- write data with lit()."""
    s = f"{v:.10f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    return s or "0.0"


def lit(v: float) -> str:
    """A TYPED xsd:decimal literal.

    The docstring above used to read "xsd:decimal, not double: thresholds are
    compared exactly" -- and then returned a bare numeral, which Turtle types as
    xsd:integer whenever the value is whole. Sixteen thresholds in the released
    EU package shipped as `censo:thresholdValue 10`, an xsd:integer, in a file
    whose whole purpose is to be the citable exact limit.

    rdfs:range xsd:decimal cannot object, because xsd:integer is derived from
    xsd:decimal and satisfies it. The constraint that can object is
    censo:ThresholdShape in censo-shapes.ttl, which now carries
    sh:datatype xsd:decimal.
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


PREAMBLE = """\
@prefix censo:   <https://w3id.org/censo/> .
@prefix cereg:   <https://w3id.org/censo/reg/> .
@prefix owl:     <http://www.w3.org/2002/07/owl#> .
@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix prov:    <http://www.w3.org/ns/prov#> .
@prefix qudt:    <http://qudt.org/schema/qudt/> .
@prefix unit:    <http://qudt.org/vocab/unit/> .
@prefix vann:    <http://purl.org/vocab/vann/> .
@prefix sosa:    <http://www.w3.org/ns/sosa/> .
"""


def emit_package(*, pkg_id, iri_base, title, description, jurisdiction,
                 jurisdiction_label, in_force_from, legal_reference,
                 source_url, source_local, version, rows, analyte_prefix,
                 matrix, matrix_label, matrix_note, transposes=None):
    """rows: list of dicts with name, cas, aa, mac, note."""
    L = [f"# GENERATED by scripts/19_build_regulation_packages.py -- "
         f"do not edit by hand.",
         f"# Values transcribed from the primary legal text; see "
         f"{source_local}.",
         "",
         PREAMBLE,
         f"<{iri_base}> a owl:Ontology ;",
         f'    dcterms:title "{esc(title)}"@en ;',
         f'    dcterms:description """{esc(description)}"""@en ;',
         "    dcterms:license <https://creativecommons.org/licenses/by/4.0/> ;",
         f"    owl:versionIRI <{iri_base}/{version}> ;",
         f'    owl:versionInfo "{version}" ;',
         # A package contributes into the cereg: namespace rather than opening
         # one of its own; stating that is what keeps it FAIR-complete without
         # pretending it is a separate vocabulary.
         '    vann:preferredNamespacePrefix "cereg" ;',
         '    vann:preferredNamespaceUri "https://w3id.org/censo/reg/" ;',
         "    owl:imports <https://w3id.org/censo/reg/> ;",
         f"    rdfs:comment \"Contributes individuals only. It declares no "
         f"class and no property, which is what makes it safe to load "
         f"alongside, or in place of, another package.\"@en .",
         "",
         f"cereg:{jurisdiction} a cereg:Jurisdiction ;",
         f'    rdfs:label "{esc(jurisdiction_label)}"@en .',
         "",
         f"cereg:{pkg_id}-source a prov:Entity ;",
         f'    rdfs:label "{esc(title)} (primary text)"@en ;',
         f"    prov:value <{source_url}> .",
         "",
         f"cereg:{pkg_id} a cereg:RegulationPackage ;",
         f'    rdfs:label "{esc(title)}"@en ;',
         f"    cereg:jurisdiction cereg:{jurisdiction} ;",
         f'    cereg:inForceFrom "{in_force_from}"^^xsd:date ;',
         f'    cereg:legalReference "{esc(legal_reference)}" ;',
         f"    cereg:sourceDocument cereg:{pkg_id}-source ;"]
    if transposes:
        # cereg:transposes was declared and never emitted. The Turkish
        # regulation transposes the European directive -- that is the whole
        # reason two packages are comparable at all, and section 5.7 rests on
        # it -- so the relation belongs in the package rather than in prose.
        L.append(f"    cereg:transposes cereg:{transposes} ;")

    thresholds = []
    analytes = {}
    groups = {}
    n_aa = n_mac = n_grp = 0
    # Annex I makes some thresholds CONDITIONAL, and says so in a footnote
    # attached to the value or the name. Those footnotes are the reason
    # censo:requiresCondition exists, and until now the packages emitted none of
    # them -- so one of the four commitments the paper claims for the vocabulary
    # was declared in the TBox and never exercised. The mapping is hand-read
    # from the consolidated text and quoted here:
    #
    #   (9)  "For Cadmium and its compounds (No 6) the EQS values vary depending
    #         on the hardness of the water as specified in five class
    #         categories (Class 1: < 40 mg CaCO3/l ... Class 5: >= 200 mg
    #         CaCO3/l)."
    #   (12) "These EQS refer to bioavailable concentrations of the substances."
    #
    # Only footnotes that govern WHEN the threshold applies appear here. The
    # others (isomer lists, relative potency factors, indicative parameters)
    # say what the standard covers.
    CONDITIONS = {
        "9": ("hardness-class", "censo:HardnessClassCondition",
              ["hardness"],
              "Annex I footnote 9: the EQS values vary with water hardness "
              "over five class categories, so the applicable value is unknown "
              "until the hardness is measured."),
        "12": ("bioavailability", "censo:BioavailabilityCondition",
               ["hardness", "dissolvedOrganicCarbon", "pH"],
               "Annex I footnote 12: these EQS refer to bioavailable "
               "concentrations of the substances, which requires hardness, "
               "dissolved organic carbon and pH for normalisation."),
        }
    conditions_used = {}

    for r in rows:
        s = slug(r["name"])
        notes = [x for x in str(r.get("footnotes") or "").split(";") if x]
        cond = next((CONDITIONS[x] for x in notes if x in CONDITIONS), None)
        if cond:
            conditions_used[cond[0]] = cond
        # A sum standard is NOT a standard for any one of its members. Annex I
        # entries such as the cyclodiene pesticides or the brominated
        # diphenylethers carry a single value for the sum of several
        # substances, and this builder used to emit them as ordinary
        # per-analyte thresholds -- so an observation of aldrin alone was
        # assessed against a limit defined for aldrin + dieldrin + endrin +
        # isodrin together. The vocabulary already had cereg:GroupThreshold
        # for exactly this; it simply was not being used.
        is_group = str(r.get("is_group", "")).strip().lower() in ("true", "1")
        if is_group:
            g_iri = f"cereg:{pkg_id}-group-{s}"
            groups[g_iri] = (r["name"], r.get("all_cas", ""))
            subject_iri, kind_cls = g_iri, "cereg:GroupThreshold"
        else:
            a_iri = f"{analyte_prefix}{s}"
            if a_iri not in analytes:
                # Every CAS the entry names, not just the first. Annex I lists
                # several substances under more than one registry number, and
                # a package carrying only the primary one silently fails to
                # match measurements reported under an alternate -- which is
                # how the graph and the streaming audit came to disagree.
                cas_all = [c.strip() for c in
                           str(r.get("all_cas") or r.get("cas") or "")
                           .split(";") if c.strip()]
                analytes[a_iri] = (r["name"], cas_all)
            subject_iri, kind_cls = a_iri, None
        for kind, value, cls in (("aa", r.get("aa"),
                                  "censo:AnnualAverageThreshold"),
                                 ("mac", r.get("mac"),
                                  "censo:MaximumAllowableThreshold")):
            v = num(value)
            if v is None:
                continue
            t_iri = f"cereg:{pkg_id}-{s}-{kind}"
            thresholds.append((t_iri, kind_cls or cls, v, subject_iri,
                               r.get("note", ""), r["name"], kind, is_group,
                               cond[0] if cond else None))
            if is_group:
                n_grp += 1
            elif kind == "aa":
                n_aa += 1
            else:
                n_mac += 1

    L.append("    cereg:definesThreshold")
    L.append(" ,\n".join(f"        {t[0]}" for t in thresholds) + " .")
    L.append("")

    # INDIVIDUALS THIS PACKAGE USES FROM THE VOCABULARY, typed.
    # cereg:VerifiedAgainstPrimarySource and cereg:Sum were referenced by every
    # threshold and typed nowhere, so cereg:TranscriptionStatus and
    # cereg:AggregationFunction were classes with no instances while their
    # instances were IRIs with no class. A consumer loading the package alone
    # could not tell what either individual was.
    L.append("#" * 78)
    L.append("#  Vocabulary individuals this package uses")
    L.append("#" * 78)
    L.append("")
    L.append("cereg:VerifiedAgainstPrimarySource a cereg:TranscriptionStatus ;")
    L.append('    rdfs:label "verified against the primary source"@en ;')
    L.append('    rdfs:comment "The value was parsed from the primary legal '
             'text by a script in this repository, not taken from a secondary '
             'compilation."@en .')
    L.append("")
    if any(t[7] for t in thresholds):
        L.append("cereg:Sum a cereg:AggregationFunction ;")
        L.append('    rdfs:label "sum"@en ;')
        L.append('    rdfs:comment "The aggregate is the sum of the group\'s '
                 'member concentrations."@en .')
        L.append("")

    # THE MATRIX CONDITION.
    #
    # Annex I sets four values per substance -- annual average and maximum
    # allowable, each for inland surface waters and for other surface waters --
    # and scripts/10_parse_eu_eqs.py reads all four by column position, with
    # 212 of them hand-checked against the consolidated text. This builder then
    # emitted only the inland pair and said nothing about it, so the package
    # published thresholds whose matrix was unstated. That is the bare-number
    # failure this vocabulary exists to prevent, in its own artefact: the same
    # substance has different limits in inland and in other surface waters --
    # benzene is 10 and 8 -- and a threshold that does not say which it is
    # cannot be applied.
    #
    # censo:MatrixCondition was declared for exactly this and instantiated
    # nowhere. Every threshold now carries one, so what the value applies to
    # travels with the value.
    L.append("#" * 78)
    L.append("#  The matrix this package's thresholds apply to")
    L.append("#" * 78)
    L.append("")
    L.append(f"cereg:{pkg_id}-cond-matrix a censo:MatrixCondition ;")
    L.append(f'    rdfs:label "{esc(matrix_label)}"@en ;')
    L.append(f'    rdfs:comment "{esc(matrix_note)}"@en .')
    L.append("")

    if conditions_used:
        L.append("#" * 78)
        L.append("#  Applicability conditions this package's thresholds carry")
        L.append("#")
        L.append("#  Each is quoted from the Annex I footnote that creates it.")
        L.append("#  Where the record cannot supply the covariates a condition")
        L.append("#  names, the outcome is censo:PreconditionUnmet -- not a")
        L.append("#  default pass, and not a comparison against a number that")
        L.append("#  refers to a different quantity.")
        L.append("#" * 78)
        L.append("")
        for key, (_, cls, covars, why) in sorted(conditions_used.items()):
            L.append(f"cereg:{pkg_id}-cond-{key} a {cls} ;")
            L.append(f'    rdfs:label "{esc(key.replace("-", " "))} condition '
                     f'({pkg_id})"@en ;')
            for c in covars:
                L.append(f"    censo:requiresCovariate cereg:covariate-{c} ;")
            L.append(f'    rdfs:comment "{esc(why)}"@en .')
            L.append("")
        seen = sorted({c for _, (_, _, cs, _) in conditions_used.items()
                       for c in cs})
        for c in seen:
            L.append(f"cereg:covariate-{c} a sosa:ObservableProperty ;")
            L.append(f'    rdfs:label "{esc(c)}"@en .')
            L.append("")

    L.append("#" * 78)
    L.append("#  Analytes referenced by this package")
    L.append("#" * 78)
    L.append("")
    for a_iri, (name, cas) in sorted(analytes.items()):
        cas = [cas] if isinstance(cas, str) else list(cas)
        cas = [c for c in cas if c]
        L.append(f"{a_iri} a censo:Analyte ;")
        L.append(f'    rdfs:label "{esc(name)}"@en' +
                 (" ;" if cas else " ."))
        if cas:
            L.append("    censo:casNumber " +
                     " , ".join(f'"{esc(c)}"' for c in cas) + " .")
        L.append("")

    group_members = {}
    if groups:
        L.append("#" * 78)
        L.append("#  Substance groups")
        L.append("#")
        L.append("#  A group carries ONE standard for an aggregate over its")
        L.append("#  members. It is deliberately not an censo:Analyte: nothing")
        L.append("#  in this file lets a single measurement be compared to a")
        L.append("#  sum standard, because that comparison is not valid.")
        L.append("#" * 78)
        L.append("")
        for g_iri, (name, all_cas) in sorted(groups.items()):
            L.append(f"{g_iri} a cereg:SubstanceGroup ;")
            L.append(f'    rdfs:label "{esc(name)}"@en' +
                     (" ;" if all_cas else " ."))
            if all_cas:
                members = [c.strip() for c in str(all_cas).split(";")
                           if c.strip()]
                L.append('    rdfs:comment "Members, by CAS: ' +
                         esc("; ".join(members)) + '"@en .')
                group_members[g_iri] = members
            L.append("")

        # MEMBERSHIP, as triples. The group used to carry
        # cereg:groupCoverage <count>, which was declared as the FRACTION of
        # the group actually measured and emitted as the COUNT of its declared
        # members -- so the one number in the package about groups meant
        # something other than what its own definition said. The membership it
        # was standing in for is asserted directly now, which is strictly more
        # information: the count is COUNT(?a) over these, and the question that
        # decides an aggregate verdict -- was every member measured -- becomes
        # answerable by query instead of only in Python.
        by_cas = {}
        for a_iri, (_, cs) in analytes.items():
            for c in ([cs] if isinstance(cs, str) else list(cs)):
                if c:
                    by_cas.setdefault(c.strip(), a_iri)
        minted = []
        for g_iri, members in sorted(group_members.items()):
            for c in members:
                a_iri = by_cas.get(c)
                if a_iri is None:
                    # A member the regulation names only inside the group.
                    # CAS is the join key the vocabulary prefers, so the
                    # individual is minted from it rather than left implicit.
                    # analyte_prefix already carries the cereg: prefix and a
                    # trailing hyphen, as line 232 uses it.
                    a_iri = f"{analyte_prefix}cas-{slug(c)}"
                    if a_iri not in by_cas.values() and a_iri not in minted:
                        minted.append((a_iri, c))
                        by_cas[c] = a_iri
                    else:
                        a_iri = by_cas[c]
                L.append(f"{a_iri} cereg:memberOfGroup {g_iri} .")
        L.append("")
        for a_iri, c in minted:
            L.append(f"{a_iri} a censo:Analyte ;")
            L.append(f'    rdfs:label "CAS {esc(c)}"@en ;')
            L.append(f'    censo:casNumber "{esc(c)}" ;')
            L.append('    rdfs:comment "Named by the regulation only as a '
                     'member of a group standard; no individual limit is set '
                     'for it, so it carries a CAS and nothing more."@en .')
            L.append("")

    L.append("#" * 78)
    L.append("#  Thresholds")
    L.append("#" * 78)
    L.append("")
    for (t_iri, cls, v, a_iri, note, a_name, kind, is_group,
         cond_key) in thresholds:
        L.append(f"{t_iri} a {cls} ;")
        # A threshold with no label is not citable in a report and cannot be
        # shown to a regulator. The omission also made the competency question
        # "which regulation establishes this threshold" return nothing, which
        # looked like a gap in the ontology rather than in the data.
        kind_label = ("annual average" if kind == "aa"
                      else "maximum allowable concentration")
        L.append(f'    rdfs:label "{esc(a_name)} \u2014 {kind_label} '
                 f'({disp(v)} \u00b5g/L)"@en ;')
        L.append(f"    censo:thresholdValue {lit(v)} ;")
        L.append("    censo:thresholdUnit unit:MicroGM-PER-L ;")
        if is_group:
            # appliesToGroup, NOT appliesToAnalyte: the distinction is the
            # whole point, and it is what stops a consumer joining a single
            # measurement to a sum standard by following one property.
            L.append(f"    cereg:appliesToGroup {a_iri} ;")
            L.append("    cereg:aggregationFunction cereg:Sum ;")
            L.append("    cereg:requiresCompleteGroup true ;")
        else:
            L.append(f"    censo:appliesToAnalyte {a_iri} ;")
        L.append(f"    censo:requiresCondition "
                 f"cereg:{pkg_id}-cond-matrix ;")
        if cond_key:
            L.append(f"    censo:requiresCondition "
                     f"cereg:{pkg_id}-cond-{cond_key} ;")
        L.append(f"    censo:definedBy cereg:{pkg_id} ;")
        line = ("    cereg:transcriptionStatus "
                "cereg:VerifiedAgainstPrimarySource")
        if note:
            L.append(line + " ;")
            L.append(f'    rdfs:comment "{esc(note)}"@en .')
        else:
            L.append(line + " .")
        L.append("")

    out = REG / f"{pkg_id}.ttl"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    if n_grp:
        print(f"  {pkg_id}: {n_grp} group (sum) standards held apart from "
              f"{n_aa + n_mac} per-analyte thresholds")
    return out, len(analytes), n_aa, n_mac


def main() -> int:
    REG.mkdir(parents=True, exist_ok=True)
    EVAL.mkdir(parents=True, exist_ok=True)
    report = []

    # ---- Turkish package ---------------------------------------------------
    p = PROC / "eqs_official.csv"
    if not p.exists():
        sys.exit(f"missing {p}; run scripts/08_verify_thresholds.py first")
    with p.open(encoding="utf-8") as fh:
        rows = []
        for r in csv.DictReader(fh):
            rows.append({
                "name": r["name_tr"], "cas": r["cas"],
                "aa": r["aa_river"], "mac": r["mac_river"],
                # The regulation marks eight metals with an asterisk whose
                # meaning is given nowhere in the published text. Recording the
                # ambiguity is the honest option; asserting a basis is not.
                "note": ("Marked with an asterisk in Table 4 whose meaning is "
                         "not defined in the published text; the applicability "
                         "basis is therefore unresolved."
                         if r.get("asterisk_unexplained") == "True" else ""),
            })
    out, n_a, n_aa, n_mac = emit_package(
        pkg_id="tr-ysky-2016",
        iri_base="https://w3id.org/censo/reg/tr-ysky-2016",
        matrix="inland-surface-water",
        matrix_label="inland surface water, rivers (Table 4, YSKY 2016)",
        matrix_note=("Table 4 sets separate columns for rivers and for coastal "
                     "and transitional waters. The values emitted here are the "
                     "river columns, so every threshold in this package "
                     "applies to river water and to nothing else. The coastal "
                     "columns are parsed and verified by "
                     "scripts/08_verify_thresholds.py and not emitted, because "
                     "the record this work assesses is river water; emitting a "
                     "value without saying which water it governs is the "
                     "failure this vocabulary exists to prevent."),
        transposes="eu-2008-105-2026",
        title="Turkish Surface Water Quality Regulation, Table 4 (2016)",
        description=("Environmental quality standards for inland surface "
                     "waters, transcribed from Table 4 of the Yerustu Su "
                     "Kalitesi Yonetmeligi as amended in 2016. Values were "
                     "parsed from the official text by "
                     "scripts/08_verify_thresholds.py, not from any secondary "
                     "compilation."),
        jurisdiction="TR", jurisdiction_label="Türkiye",
        in_force_from="2016-08-10",
        legal_reference="Yerüstü Su Kalitesi Yönetmeliği, Tablo 4 (2016)",
        source_url="https://www.mevzuat.gov.tr/",
        source_local="refs/legal/YSKY.pdf",
        version="2.0.0", rows=rows,
        analyte_prefix="cereg:analyte-tr-")
    report.append(("tr-ysky-2016", out, n_a, n_aa, n_mac))
    print(f"  {out.relative_to(ROOT)}: {n_a} analytes, "
          f"{n_aa} AA + {n_mac} MAC thresholds")

    # ---- European package --------------------------------------------------
    p = PROC / "eu_eqs.csv"
    if p.exists():
        with p.open(encoding="utf-8") as fh:
            rows = []
            for r in csv.DictReader(fh):
                rows.append({
                    "name": r["name"],
                    "cas": (r.get("cas") or "").strip(),
                    "is_group": r.get("is_group", ""),
                    "all_cas": r.get("all_cas", ""),
                    "aa": r.get("aa_inland"), "mac": r.get("mac_inland"),
                    # the footnote markers the parse captured: they are what
                    # makes a threshold conditional
                    "footnotes": r.get("footnotes", ""),
                    "note": (f"Annex I entry {r.get('entry_no','')}, "
                             f"category: {r.get('category','')}."
                             if r.get("entry_no") else ""),
                })
        out, n_a, n_aa, n_mac = emit_package(
            pkg_id="eu-2008-105-2026",
            iri_base="https://w3id.org/censo/reg/eu-2008-105-2026",
            matrix="inland-surface-water",
            matrix_label="inland surface water (Annex I, column 1)",
            matrix_note=("Annex I sets four values per substance: an annual "
                         "average and a maximum allowable concentration, each "
                         "for inland surface waters and for other surface "
                         "waters. Inland surface waters are rivers and lakes "
                         "and the artificial or heavily modified bodies "
                         "related to them. The two matrices differ -- benzene "
                         "is 10 ug/L inland and 8 elsewhere -- so a threshold "
                         "that does not say which water it governs cannot be "
                         "applied. The inland values are emitted, the other "
                         "surface water values are parsed and verified by "
                         "scripts/10_parse_eu_eqs.py and not emitted, and this "
                         "condition records which of the two this package "
                         "carries."),
            title=("Directive 2008/105/EC, Annex I, consolidated text in force "
                   "10 May 2026"),
            description=("Environmental quality standards for priority "
                         "substances in inland surface waters, from the "
                         "consolidated text of Directive 2008/105/EC as "
                         "amended, in force on 10 May 2026. Parsed from the "
                         "EUR-Lex primary text by scripts/10_parse_eu_eqs.py."),
            jurisdiction="EU", jurisdiction_label="European Union",
            in_force_from="2026-05-10",
            legal_reference=("Directive 2008/105/EC as amended by Directive "
                             "2013/39/EU, Annex I (consolidated)"),
            source_url=("https://eur-lex.europa.eu/legal-content/EN/TXT/"
                        "?uri=CELEX:02008L0105-20260510"),
            source_local="refs/legal/EU-2008-105_consolidated-2026-05-10.pdf",
            # 2.0.0. This used to say "stays at 1.0.0 -- no DOI, the
            # permanent-identifier request is still open, so there is no 1.0.0
            # in anyone's hands to invalidate". That reasoning stopped holding
            # when the packages went up at the IRI w3id.org redirects to: they
            # ARE dereferenceable, and this release removes cereg:groupCoverage
            # from every group and adds a censo:MatrixCondition to every
            # threshold. A consumer who read the 1.0.0 files would break on
            # both. The old files stay reachable under releases/1.0.0/.
            version="2.0.0", rows=rows,
            analyte_prefix="cereg:analyte-eu-")
        report.append(("eu-2008-105-2026", out, n_a, n_aa, n_mac))
        print(f"  {out.relative_to(ROOT)}: {n_a} analytes, "
              f"{n_aa} AA + {n_mac} MAC thresholds")

    # ---- validate what we just wrote --------------------------------------
    parsed = []
    try:
        import rdflib
        for _, out, *_ in report:
            g = rdflib.Graph()
            g.parse(out, format="turtle")
            # a package must contribute individuals only
            declared = set(g.subjects(rdflib.RDF.type, rdflib.OWL.Class)) | \
                set(g.subjects(rdflib.RDF.type, rdflib.OWL.ObjectProperty)) | \
                set(g.subjects(rdflib.RDF.type, rdflib.OWL.DatatypeProperty))
            parsed.append((out.name, len(g), len(declared)))
    except ImportError:
        print("  (rdflib not available; packages not re-parsed)")

    L = ["# Regulation packages\n",
         "Generated by `scripts/19_build_regulation_packages.py`.\n",
         "The paper claims regulations are pluggable, versioned packages. "
         "These are the packages. Each imports the vocabulary and contributes "
         "**individuals only** -- no class, no property -- which is what makes "
         "it safe to load one in place of another and to hold both answers at "
         "once.\n",
         "| package | analytes | AA thresholds | MAC thresholds | file |",
         "|---|---|---|---|---|"]
    for pkg, out, n_a, n_aa, n_mac in report:
        L.append(f"| `{pkg}` | {n_a} | {n_aa} | {n_mac} | "
                 f"`{out.relative_to(ROOT)}` |")
    L.append("")
    if parsed:
        L.append("## Re-parsed after writing\n")
        L.append("| file | triples | classes/properties declared |")
        L.append("|---|---|---|")
        for name, n_t, n_d in parsed:
            flag = "**0 — individuals only, as required**" if n_d == 0 \
                else f"**{n_d} — a package must not declare terms**"
            L.append(f"| `{name}` | {n_t:,} | {flag} |")
        L.append("")
    L.append("Every threshold carries "
             "`cereg:transcriptionStatus cereg:VerifiedAgainstPrimarySource`, "
             "because both sources are parsed from the legal PDFs. The "
             "project's working spreadsheet is deliberately not emitted: seven "
             "of its ten metal values, and a further eleven organics, disagree "
             "with the law.\n")
    L.append("## Using a different jurisdiction\n")
    L.append("```bash")
    L.append("# assess the same observations under the Turkish package")
    L.append("python scripts/17_run_competency_questions.py \\")
    L.append("    --abox derived/abox/censo-waterbase.ttl")
    L.append("```")
    L.append("Load `ontology/reg/tr-ysky-2016.ttl` or "
             "`ontology/reg/eu-2008-105-2026.ttl` alongside the ABox. The "
             "thresholds carry different IRIs and different `censo:definedBy` "
             "links, so both assessments can coexist in one graph.\n")
    (EVAL / "regulation_packages.md").write_text("\n".join(L), encoding="utf-8")
    print(f"\n  wrote {(EVAL / 'regulation_packages.md').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
