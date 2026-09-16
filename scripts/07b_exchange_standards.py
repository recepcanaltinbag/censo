#!/usr/bin/env python3
"""
Censoring in water-quality EXCHANGE standards, decided from their own files.

WHY THIS IS NOT A ROW IN THE GAP TABLE
--------------------------------------
scripts/07_verify_gap_table.py decides each cell by searching an ontology's
OWL classes and properties. The standards that carry censoring in water-quality
practice are not ontologies: OGC WaterML is an XML schema, WQX an XML schema
with domain-value lists, ODM2 a relational model with SKOS vocabularies, and the
SeaDataNet L20 flags a SKOS concept scheme. Run through the gap-table method they
score ZERO entities -- L20 included, although one of its codes reads "value
below limit of quantification". Adding them there would report a blank row for
a standard that plainly carries the concept, which is the unfair comparison a
referee is right to reject.

So they get their own table, with their own method, and the same discipline:
a cell is credited only when the named field or code is FOUND in the standard's
own schema, SQL or vocabulary file, a dash means it was searched for and absent,
and a source that could not be retrieved gives `?` and no claim.

WHAT THE TABLE IS FOR
---------------------
Not to show that these standards are deficient -- they flag censoring, and WQX
attaches typed limits to the individual result, which CENSO does not. It is to
locate precisely what CENSO adds beyond them: a standard the result is compared
with, a compliance outcome with an indeterminate value, and a condition under
which the standard applies, in a form a reasoner or a shape can act on.

Outputs : eval/exchange_standards.md
          paper/tables/tab_exchange.tex
          derived/interim/exchange_cache/*   (retrieved sources)

Usage:  python scripts/07b_exchange_standards.py [--offline]
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "derived" / "interim" / "exchange_cache"
EVAL = ROOT / "eval"
TEX = ROOT / "paper" / "tables"
UA = "censo-ontology-research/1.0 (academic comparison; see repository)"

WQX_INDEX = "https://www.exchangenetwork.net/schema/WQX/3/index.xsd"

# name -> list of source URLs. WQX's schema is a tree of includes and is
# crawled from its index, so the list is extended at run time.
SOURCES = {
    "OGC WaterML 2.0": ["https://schemas.opengis.net/waterml/2.0/timeseries.xsd"],
    "CUAHSI WaterML 1.1": ["http://his.cuahsi.org/documents/cuahsiTimeSeries_v1_1.xsd"],
    # The observation model WaterML 2.0 and INSPIRE build on, and the one the
    # related-work section names: its result-quality slot is a generic ISO 19115
    # data-quality element, so it carries no censoring field of its own.
    "ISO 19156 / OGC O&M 2.0": ["http://schemas.opengis.net/om/2.0/observation.xsd"],
    "ODM2": ["http://vocabulary.odm2.org/api/v1/censorcode/?format=skos",
             "https://raw.githubusercontent.com/ODM2/ODM2/master/src/"
             "blank_schema_scripts/postgresql/ODM2_for_PostgreSQL.sql"],
    "SeaDataNet L20": ["http://vocab.nerc.ac.uk/collection/L20/current/"
                       "?_profile=nvs&_mediatype=text/turtle"],
    "US EPA WQX 3.0": [WQX_INDEX,
                       "https://cdx.epa.gov/wqx/download/DomainValues/"
                       "ResultDetectionCondition.CSV",
                       "https://cdx.epa.gov/wqx/download/DomainValues/"
                       "DetectionQuantitationLimitType.CSV"],
    "CENSO (this work)": [str(ROOT / "ontology" / "censo-core.ttl"),
                          str(ROOT / "ontology" / "censo-regulation.ttl")],
}

FORM = {"OGC WaterML 2.0": "XML Schema", "CUAHSI WaterML 1.1": "XML Schema",
        "ISO 19156 / OGC O&M 2.0": "XML Schema",
        "ODM2": "SQL + SKOS", "SeaDataNet L20": "SKOS",
        "US EPA WQX 3.0": "XML Schema + domain lists",
        "CENSO (this work)": "OWL 2 RL + SHACL"}

# Each positive cell: the label printed when found, and the patterns that must
# ALL be found in the standard's sources. Each negative cell: patterns whose
# absence is the finding. A pattern is a regular expression, case-insensitive.
CELLS = {
    "censoring": {
        "OGC WaterML 2.0": ("yes", [r"censoredReason"]),
        "CUAHSI WaterML 1.1": ("yes", [r"censorCode"]),
        "ODM2": ("yes", [r"CensorCodeCV", r"nonDetect"]),
        "SeaDataNet L20": ("yes", [r"value below detection"]),
        "US EPA WQX 3.0": ("yes", [r"ResultDetectionConditionText", r"Not Detected"]),
        "CENSO (this work)": ("yes", [r"censo:CensoredObservation a owl:Class"]),
    },
    "detected, not quantified": {
        "OGC WaterML 2.0": ("yes", [r"not\s+quantif|below\s+quantification"]),
        "CUAHSI WaterML 1.1": ("yes", [r"\bpnq\b"]),
        "ODM2": ("yes", [r"presentButNotQuantified"]),
        "SeaDataNet L20": ("yes", [r"below limit of quantification"]),
        "US EPA WQX 3.0": ("yes", [r"Present Below Quantification Limit"]),
        "CENSO (this work)": ("yes", [r"censo:EstimatedObservation a owl:Class"]),
    },
    "limit held on": {
        "OGC WaterML 2.0": ("untyped point qualifier", [r'name="qualifier"']),
        "CUAHSI WaterML 1.1": ("none", None),
        "ODM2": ("the value field", None),
        "SeaDataNet L20": ("the value field", [r"accompanying value is the"]),
        # "parameters bound to the observation act, such as ... detection
        # limits ... may augment the description of a standard procedure":
        # a generic named value, with no type and no censoring semantics
        "ISO 19156 / OGC O&M 2.0": ("untyped observation parameter",
                                    [r'name="parameter"',
                                     r"detection\s+limits"]),
        "US EPA WQX 3.0": ("the result, typed",
                           [r"ResultDetectionQuantitationLimit",
                            r"DetectionQuantitationLimitTypeName"]),
        "CENSO (this work)": ("the method; bound on the result",
                              [r"censo:limitOfQuantification a owl:DatatypeProperty",
                               r"censo:resultUpperBound a owl:DatatypeProperty"]),
    },
    "standard": {
        "US EPA WQX 3.0": ("as a limit type", [r"Water Quality Standard or Criteria"]),
        "CENSO (this work)": ("yes", [r"censo:thresholdValue a owl:DatatypeProperty"]),
    },
    "verdict": {
        "CENSO (this work)": ("three-valued",
                              [r"censo:IndeterminateCompliance a owl:Class"]),
    },
    "applicability": {
        "CENSO (this work)": ("yes", [r"censo:requiresCondition a owl:ObjectProperty"]),
    },
}
# What "absent" is searched for, per negative column. Kept narrow on purpose:
# a broad pattern would find "standard" in every schema's documentation.
ABSENT = {
    "censoring": [r"censor", r"below\s+detection", r"non-?detect"],
    "detected, not quantified": [r"not\s+quantif", r"below\s+quantification"],
    "standard": [r"quality\s+standard", r"\bEQS\b", r"regulatory\s+limit"],
    "verdict": [r"complian", r"exceedance", r"indeterminate"],
    "applicability": [r"bioavailab", r"hardness\s+class", r"applicability"],
    "limit held on": [r"detection\s*limit", r"quantitation\s*limit",
                      r"DetectionLimit", r"limit\s*of\s*quantification"],
}
# ODM2 and WaterML 1.1 hold no limit field: that is decided by the ABSENT
# patterns above over their SCHEMA files only, since the ODM2 vocabulary's
# prose mentions "the level at which the analyte can be detected".
SCHEMA_ONLY = {"ODM2": "ODM2_for_PostgreSQL.sql",
               "CUAHSI WaterML 1.1": "cuahsiTimeSeries_v1_1.xsd"}

COLUMNS = ["censoring", "detected, not quantified", "limit held on",
           "standard", "verdict", "applicability"]


def cache_name(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", url.split("://", 1)[-1])[:150]


def fetch(url: str, offline: bool):
    if not url.startswith("http"):
        p = Path(url)
        return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / cache_name(url)
    if p.exists():
        return p.read_text(encoding="utf-8", errors="replace")
    if offline:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read().decode("utf-8", errors="replace")
    except Exception as e:                                     # noqa: BLE001
        print(f"  could not retrieve {url}: {e}")
        return None
    p.write_text(data, encoding="utf-8")
    return data


def crawl_xsd(root: str, offline: bool) -> dict:
    """Every schema reachable from root through include/import."""
    seen, todo = {}, [root]
    while todo:
        u = todo.pop()
        if u in seen:
            continue
        txt = fetch(u, offline)
        seen[u] = txt
        if txt:
            for loc in re.findall(r'(?:include|import)[^>]*schemaLocation="([^"]+)"', txt):
                nxt = urllib.parse.urljoin(u, loc)
                if "exchangenetwork.net/schema/WQX" in nxt:
                    todo.append(nxt)
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    texts = {}
    for name, urls in SOURCES.items():
        got = {}
        for u in urls:
            if u == WQX_INDEX:
                got.update(crawl_xsd(u, args.offline))
            else:
                got[u] = fetch(u, args.offline)
        texts[name] = got

    table, evidence = {}, {}
    for name, got in texts.items():
        missing = [u for u, t in got.items() if t is None]
        blob = "\n".join(t for t in got.values() if t)
        row, ev = {}, {}
        for col in COLUMNS:
            spec = CELLS.get(col, {}).get(name)
            if missing and not blob:
                row[col] = "?"
                continue
            if spec:
                label, pats = spec
                if pats is None:
                    # a negative finding stated as a label: verified by absence
                    src = next((t for u, t in got.items()
                                if t and SCHEMA_ONLY.get(name, "\0") in u), None)
                    if src is None:
                        row[col] = "?"
                        continue
                    hits = [p for p in ABSENT.get(col, [])
                            if re.search(p, src, re.I)]
                    row[col] = "?" if hits else label
                    ev[col] = (f"searched the schema for {ABSENT.get(col)}; "
                               + (f"FOUND {hits}, cell withheld" if hits
                                  else "none found"))
                    continue
                found = [bool(re.search(p, blob, re.I)) for p in pats]
                row[col] = label if all(found) else ("?" if missing else "--")
                ev[col] = "; ".join(f"`{p}` {'found' if f else 'NOT found'}"
                                    for p, f in zip(pats, found))
            else:
                hits = sorted({m.group(0) for p in ABSENT.get(col, [])
                               for m in re.finditer(p, blob, re.I)})
                row[col] = "--" if not hits else "check"
                ev[col] = (f"searched for {ABSENT.get(col)}: "
                           + ("none found" if not hits else f"found {hits[:6]}"))
        table[name] = row
        evidence[name] = (ev, [u for u in got], missing)

    # ---------------------------------------------------------------- report
    L = ["# Censoring in water-quality exchange standards\n",
         "Generated by `scripts/07b_exchange_standards.py`. Each cell is decided "
         "by searching the standard's own schema, SQL definition or controlled "
         "vocabulary. A named value means the field or code was found; `--` "
         "means it was searched for and is absent; `?` means a source could not "
         "be retrieved, or a search that should have come up empty did not, and "
         "no claim is made. `check` marks an absence search that found text and "
         "has to be read by hand before the cell is published.\n",
         "These are exchange formats, not ontologies, so they are not rows of "
         "the gap table: its method scores OWL terms, and every one of them "
         "would score zero.\n",
         "| standard | form | " + " | ".join(COLUMNS) + " |",
         "|---|---|" + "---|" * len(COLUMNS)]
    for name, row in table.items():
        L.append(f"| {name} | {FORM[name]} | "
                 + " | ".join(row[c] for c in COLUMNS) + " |")
    L.append("\n## Evidence\n")
    for name, (ev, urls, missing) in evidence.items():
        L.append(f"### {name}\n")
        L.append("Sources: " + ", ".join(f"<{u}>" if u.startswith("http")
                                         else f"`{Path(u).name}`" for u in urls))
        if missing:
            L.append(f"\n**Not retrieved:** {missing}")
        L.append("")
        for c in COLUMNS:
            if c in ev:
                L.append(f"- **{c}** → `{table[name][c]}`: {ev[c]}")
        L.append("")
    EVAL.mkdir(parents=True, exist_ok=True)
    (EVAL / "exchange_standards.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    def cell(v):
        return {"yes": r"\checkmark", "--": "--"}.get(v, v)
    T = [r"% GENERATED by scripts/07b_exchange_standards.py -- do not edit.",
         r"\begin{table*}[htbp]\centering",
         r"\caption{Censoring in water-quality data-exchange standards, decided "
         r"by searching each standard's own schema, SQL definition or controlled "
         r"vocabulary for the field or code. A dash means it was searched for and "
         r"is absent. These are exchange formats rather than ontologies, so they "
         r"are assessed here and not in Table~\ref{tab:gap}, whose method scores "
         r"ontology terms and would give each of them an empty row. Every "
         r"exchange format flags a censored result except O\&M, whose generic "
         r"observation parameter can hold a detection limit but no censoring "
         r"status; none relates a result to a standard through a compliance "
         r"outcome.}",
         r"\label{tab:exchange}",
         r"\scriptsize\setlength{\tabcolsep}{3.5pt}",
         r"\begin{tabular}{l l c c l c c c}",
         r"\toprule",
         r"Standard & Form & censoring & detected, not quant. & limit held on & "
         r"standard & verdict & applic. \\",
         r"\midrule"]
    for name, row in table.items():
        tex_name = name.replace("&", r"\&")
        nm = (r"\textbf{" + tex_name + "}") if "this work" in name else tex_name
        T.append(f"{nm} & {FORM[name]} & " + " & ".join(
            cell(row[c]) for c in COLUMNS) + r" \\")
    T += [r"\bottomrule", r"\end{tabular}", r"\end{table*}"]
    TEX.mkdir(parents=True, exist_ok=True)
    (TEX / "tab_exchange.tex").write_text("\n".join(T) + "\n", encoding="utf-8")
    print("\n".join(L[:12 + len(table)]))
    bad = [(n, c) for n, r in table.items() for c, v in r.items()
           if v in ("?", "check")]
    if bad:
        print(f"\n  {len(bad)} cell(s) need reading by hand before publication: {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
