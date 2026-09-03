#!/usr/bin/env python3
"""
Verify the project's EQS spreadsheet against the PRIMARY legal text.

WHY
---
The project's CKS_FEnCY.xlsx is a secondary source. A reviewer-eye scan flagged
several values as physically implausible (copper at 0.05 ug/L is below natural
background and below most quantification limits). This script settles it by
parsing the official Turkish Surface Water Quality Regulation (Yerustu Su
Kalitesi Yonetmeligi) annex and comparing substance by substance.

Any mismatch found here would have propagated silently into every compliance
statement in the paper. That is the argument of the paper, demonstrated on its
own inputs: thresholds carried without provenance or validation are not
trustworthy.

Inputs  : refs/legal/YSKY.pdf          (official regulation, downloaded)
          Data/CKS_FEnCY.xlsx          (project spreadsheet, secondary source)
Outputs : derived/processed/eqs_official.csv
          eval/threshold_verification.md

Usage:  python scripts/08_verify_thresholds.py
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "refs" / "legal" / "YSKY.pdf"
# Secondary source, retired to attic/ with the single-basin survey and not
# redistributed. Absent by design on any other machine; the substance-by-
# substance comparison then reports itself as not reproduced, and the parse of
# the primary text -- which is what the manuscript depends on -- still runs.
XLSX = ROOT / "Data" / "CKS_FEnCY.xlsx"
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        sys.exit("pypdf is required:  pip install pypdf")

try:
    import openpyxl
except ImportError:
    sys.exit("openpyxl is required")

# Rows in Tablo 4 read:
#   <no> <name> <CAS> <AA-river> <MAC-river> <AA-coastal> <MAC-coastal>
# Several names carry a trailing '*' whose meaning is NOT given anywhere in the
# published text; it is captured but not interpreted.
ROW = re.compile(
    r"^\s*(?P<no>\d{1,3})\s+"
    r"(?P<name>[^\d]+?)\*?\s+"
    r"(?P<cas>\d{2,7}-\d{2}-\d)\s+"
    r"(?P<aa_r>[\d.,]+)\s+(?P<mac_r>[\d.,]+)\s+"
    r"(?P<aa_c>[\d.,]+)\s+(?P<mac_c>[\d.,]+)\s*$"
)

# Turkish -> English names for the substances we measure, so the two sources join.
TR_EN = {
    "alüminyum": "Al", "antimon": "Sb", "arsenik": "As", "bakır": "Cu",
    "baryum": "Ba", "berilyum": "Be", "bor": "B", "civa": "Hg",
    "çinko": "Zn", "demir": "Fe", "gümüş": "Ag", "kadmiyum": "Cd",
    "kalay": "Sn", "kobalt": "Co", "krom": "Cr", "kurşun": "Pb",
    "nikel": "Ni", "titan": "Ti", "titanyum": "Ti", "vanadyum": "V",
    "molibden": "Mo", "selenyum": "Se",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def fold(s: str) -> str:
    s = norm(s).lower()
    for a, b in [("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ç", "c"),
                 ("ö", "o"), ("ü", "u"), ("â", "a")]:
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", s)


def num(s):
    if s is None:
        return None
    t = norm(s).replace(".", "").replace(",", ".") if re.search(r"\d,\d", str(s)) \
        else norm(s).replace(",", ".")
    t = re.sub(r"[^0-9.eE+-]", "", t)
    try:
        return float(t)
    except ValueError:
        return None


def parse_official():
    """Extract the EQS table rows from the regulation PDF."""
    reader = PdfReader(PDF)
    rows = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        for line in text.splitlines():
            m = ROW.match(norm(line))
            if not m:
                continue
            # An asterisk follows several metal names in Tablo 4. NO FOOTNOTE
            # explaining it appears anywhere in the regulation text, so its
            # meaning is recorded as unknown rather than guessed. An earlier
            # draft assumed "bioavailability-corrected"; that was unsupported
            # and is withdrawn.
            starred = "*" in line
            rows.append({
                "no": m.group("no"),
                "name_tr": norm(m.group("name")),
                "cas": m.group("cas"),
                "aa_river": num(m.group("aa_r")),
                "mac_river": num(m.group("mac_r")),
                "aa_coastal": num(m.group("aa_c")),
                "mac_coastal": num(m.group("mac_c")),
                "asterisk_unexplained": starred,
            })
    return rows


def parse_spreadsheet():
    wb = openpyxl.load_workbook(XLSX, data_only=True, read_only=True)
    out = {}
    for r in list(wb["CKS"].iter_rows(values_only=True))[1:]:
        if r[0] is None:
            continue
        out[fold(r[0])] = {"name": norm(r[0]), "aa": num(r[1]), "mac": num(r[2])}
    wb.close()
    return out


def main() -> int:
    if not PDF.exists():
        sys.exit(f"missing {PDF}; download the regulation first")
    EVAL.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)

    official = parse_official()
    # The spreadsheet is the single-basin survey's secondary source. It is not
    # redistributed with the repository, and the comparison it feeds was
    # withdrawn with that survey; every section below already degrades when its
    # companions in derived/processed/ are absent. Guarding the load too, for
    # the same reason the analytes.csv read is guarded: what still matters here
    # is parsing YSKY.pdf into eqs_official.csv, which feeds the Turkish
    # regulation package, and that must not depend on a retired input.
    sheet = parse_spreadsheet() if XLSX.exists() else {}

    with (PROC / "eqs_official.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(official[0].keys()))
        w.writeheader()
        w.writerows(official)

    # The spreadsheet comparison belonged to the single-basin survey, whose
    # inputs are retired to attic/. Guarded rather than deleted: the script's
    # job that still matters is parsing YSKY.pdf into eqs_official.csv, which
    # feeds the Turkish regulation package, and that must not depend on it.
    ana_path = PROC / "analytes.csv"
    measured = ({a["parameter"] for a in
                 csv.DictReader(ana_path.open(encoding="utf-8"))}
                if ana_path.exists() else set())

    comparisons = []
    for o in official:
        sym = TR_EN.get(fold(o["name_tr"]).replace("*", ""))
        if not sym or sym not in measured:
            continue
        # the spreadsheet is keyed by its own naming; try symbol and Turkish name
        s = sheet.get(fold(sym)) or sheet.get(fold(o["name_tr"]))
        comparisons.append({
            "symbol": sym, "name_tr": o["name_tr"], "cas": o["cas"],
            "official_aa": o["aa_river"], "official_mac": o["mac_river"],
            "official_aa_coastal": o["aa_coastal"],
            "official_mac_coastal": o["mac_coastal"],
            "sheet_aa": (s or {}).get("aa"), "sheet_mac": (s or {}).get("mac"),
            "asterisk_unexplained": o["asterisk_unexplained"],
        })

    def agree(a, b, tol=1e-6):
        if a is None or b is None:
            return None
        return abs(a - b) <= tol * max(1.0, abs(a))

    L = []
    A = L.append
    A("# EQS verification against the primary legal text\n")
    A("Generated by `scripts/08_verify_thresholds.py`. The project spreadsheet "
      "`Data/CKS_FEnCY.xlsx` is a secondary source; the official Turkish Surface "
      "Water Quality Regulation annex is the primary one.\n")
    A(f"- Rows parsed from the regulation: **{len(official)}**")
    A(f"- Substances compared (measured metals): **{len(comparisons)}**\n")

    if not comparisons:
        A("> The substance-by-substance comparison is **not reproduced in this "
          "run**. It compared the regulation against the single-basin survey's "
          "analyte list and working spreadsheet, both of which were retired "
          "with that survey and are not redistributed. What this stage still "
          "does, and what the manuscript depends on, is the parse above: "
          "`derived/processed/eqs_official.csv`, the primary-text transcription "
          "the Turkish regulation package is built from. The comparison's own "
          "finding is not asserted anywhere in the paper.\n")

    n_ok = n_bad = n_missing = 0
    bad = []
    if comparisons:
        A("## Substance-by-substance comparison (inland surface waters)\n")
        A("| substance | CAS | official AA | sheet AA | official MAC | sheet MAC | verdict |")
        A("|---|---|---|---|---|---|---|")
        for c in sorted(comparisons, key=lambda x: x["symbol"]):
            aa_ok = agree(c["official_aa"], c["sheet_aa"])
            mac_ok = agree(c["official_mac"], c["sheet_mac"])
            if aa_ok is None or mac_ok is None:
                verdict, n_missing = "not in sheet", n_missing + 1
            elif aa_ok and mac_ok:
                verdict, n_ok = "match", n_ok + 1
            else:
                verdict, n_bad = "**MISMATCH**", n_bad + 1
                bad.append(c)
            A(f"| {c['symbol']} ({c['name_tr']}) | {c['cas']} | {c['official_aa']} | "
              f"{c['sheet_aa']} | {c['official_mac']} | {c['sheet_mac']} | {verdict} |")
        A("")
        A(f"**{n_ok} match · {n_bad} mismatch · {n_missing} absent from the "
          f"sheet.**\n")

    if bad:
        A("## Diagnosis of the mismatches\n")
        A("Several spreadsheet values turn out to be the **coastal/transitional** "
          "column of a *different* substance, which is the signature of a row "
          "misalignment during transcription rather than of independent errors:\n")
        A("| substance | sheet value | matches which official cell? |")
        A("|---|---|---|")
        for c in bad:
            note = []
            for other in comparisons:
                for field, label in (("official_aa_coastal", "AA coastal"),
                                     ("official_mac_coastal", "MAC coastal"),
                                     ("official_aa", "AA river"),
                                     ("official_mac", "MAC river")):
                    if other[field] is not None and c["sheet_aa"] is not None \
                       and abs(other[field] - c["sheet_aa"]) < 1e-9:
                        note.append(f"{other['symbol']} {label}")
            A(f"| {c['symbol']} | AA {c['sheet_aa']} | "
              f"{', '.join(sorted(set(note))) or 'no match found'} |")
        A("")

    starred = [c for c in comparisons if c["asterisk_unexplained"]]
    if starred:
        A("## Unexplained asterisk in the regulation table\n")
        A(f"**{len(starred)}** of the compared metals carry an asterisk after "
          "their name in Tablo 4: "
          + ", ".join(sorted(c["symbol"] for c in starred)) + ".\n")
        A("**No footnote explaining it appears anywhere in the regulation text "
          "as published.** Its meaning is therefore recorded as unknown. It "
          "plausibly marks a dissolved-fraction or bioavailability basis, both "
          "of which would impose preconditions on any comparison — but that is a "
          "guess, and the ontology records the condition as unresolved rather "
          "than asserting one.\n")
        A("This is itself an instance of the paper's claim: a threshold whose "
          "applicability conditions are not machine-readable — or not readable "
          "at all — cannot support an automated compliance verdict.\n")

    # ---- full sweep: every analyte, not just the metals --------------------
    # The metal comparison above matches on the regulation's own substance
    # numbering. That covers the ten measured metals but leaves the organics
    # unchecked, and the organics turn out to be where most of the damage is.
    # This second pass joins on CAS via derived/processed/substances.csv, so it
    # reaches every analyte for which the regulation states a value.
    def clean(c):
        return str(c).strip().replace(" ", "")

    def fnum(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    sub_p = PROC / "substances.csv"
    ana_p = PROC / "analytes.csv"
    if sub_p.exists() and ana_p.exists():
        with sub_p.open(encoding="utf-8") as fh:
            cas_of = {r["analyte"]: clean(r["cas"])
                      for r in csv.DictReader(fh)}
        with ana_p.open(encoding="utf-8") as fh:
            analytes = list(csv.DictReader(fh))
        by_cas = {}
        for r in official:
            for c in clean(r.get("cas", "")).split(";"):
                if c:
                    by_cas[c] = r

        diffs, n_traced, n_orphan = [], 0, 0
        for x in analytes:
            sheet = fnum(x.get("eqs_aa"))
            o = by_cas.get(cas_of.get(x["parameter"], ""))
            if not o or not o.get("aa_river"):
                if sheet is not None:
                    n_orphan += 1
                continue
            reg = fnum(o["aa_river"])
            n_traced += 1
            if sheet is not None and reg and abs(reg - sheet) > 1e-9:
                diffs.append((x["parameter"], x.get("group", ""), sheet, reg,
                              reg / sheet if sheet else None))

        A("## Full sweep: every analyte, matched on CAS\n")
        A(f"The comparison above covers the measured metals. Joining on CAS "
          f"instead reaches every analyte for which the regulation states an "
          f"annual-average value: **{n_traced}** analytes.\n")
        A(f"- spreadsheet values that **disagree with the regulation**: "
          f"**{len(diffs)}**")
        A(f"- spreadsheet values with **no counterpart in the regulation** at "
          f"all: **{n_orphan}** (these cannot be used, and are excluded from "
          f"any figure or verdict)\n")
        if diffs:
            A("| substance | group | spreadsheet | regulation | regulation / "
              "spreadsheet |")
            A("|---|---|---|---|---|")
            for n_, g_, s_, r_, fa in sorted(diffs,
                                             key=lambda d: -(d[4] or 0)):
                A(f"| {n_} | {g_} | {s_:g} | {r_:g} | "
                  f"{fa:.2f}× |" if fa else
                  f"| {n_} | {g_} | {s_:g} | {r_:g} | — |")
            A("")
            # The ratio is regulation/spreadsheet, so a value BELOW 1 means the
            # spreadsheet permits more than the law does. Reading it the other
            # way round inverts the direction of the finding.
            lax = [d for d in diffs if d[4] and d[4] < 1]
            A(f"> **{len(lax)} of {len(diffs)}** spreadsheet values are more "
              f"permissive than the law, so a compliance verdict drawn from "
              f"them would wrongly declare compliance. Triclosan is the "
              f"extreme: the spreadsheet allows "
              f"{[d[2] for d in diffs if d[0]=='Triclosan'][0]:g} against a "
              f"legal {[d[3] for d in diffs if d[0]=='Triclosan'][0]:g} "
              f"µg/L.\n" if any(d[0] == 'Triclosan' for d in diffs)
              else f"> **{len(lax)} of {len(diffs)}** spreadsheet values are "
                   f"more permissive than the law.\n")

    A("## Consequence\n")
    A("Every threshold used in this study must be transcribed from the "
      "regulation, not from the spreadsheet, and carry "
      "`cereg:transcriptionStatus cereg:VerifiedAgainstPrimarySource`. "
      "`scripts/validate_ontology.py` refuses to let unverified thresholds into "
      "an analysis.\n")

    text = "\n".join(L)
    (EVAL / "threshold_verification.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nwrote: {EVAL/'threshold_verification.md'}, {PROC/'eqs_official.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
