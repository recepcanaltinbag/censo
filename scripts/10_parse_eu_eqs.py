#!/usr/bin/env python3
"""
Parse EU Annex I environmental quality standards from the CONSOLIDATED text of
Directive 2008/105/EC (version in force 10 May 2026), and assess the
survey against them.

WHY THE CONSOLIDATED TEXT
-------------------------
It is the current law with every amendment already merged, including the 2026
update that brings PFAS, bisphenols, pharmaceuticals and pesticide metabolites
into scope. Parsing it gives a regulation package that is current rather than a
snapshot of 2013.

TWO THINGS THIS UNLOCKS
-----------------------
1. A second, independent regulation package. The same measurements can be
   assessed under Turkish YSKY *and* EU EQS, and the DIVERGENCE between them is
   itself a result -- exactly what pluggable regulation packages are for.

2. An AUTHORITATIVE use classification. Column (3), "Category of substances",
   carries entries such as "Pharmaceuticals - anti-inflammatory" and
   "Pesticides - neonicotinoid". Coming from the legislator, it is citable and
   cannot be accused of circularity in the way an analyst-authored mapping can.

CAVEAT
------
The layout wraps one logical row over many physical lines, and several entries
list multiple CAS numbers (substance groups) or several values (cadmium's five
hardness classes). Rows that cannot be parsed unambiguously are reported as
unparsed rather than guessed -- the count is printed so the coverage is visible.

Inputs  : refs/legal/EU-2008-105_consolidated-2026-05-10.pdf
Outputs : derived/processed/eu_eqs.csv
          eval/eu_eqs_assessment.md

Usage:  python scripts/10_parse_eu_eqs.py
"""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "refs" / "legal" / "EU-2008-105_consolidated-2026-05-10.pdf"
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        sys.exit("pypdf is required:  pip install pypdf")

# Column separator sentinel. U+001F is a unit separator: it cannot occur in the
# PDF text, so it marks a boundary the later collapse of single spaces cannot
# destroy.
COL = "\x1f"

# Annex I writes very small standards as "4,6 x 10 -4". The exponent is ALWAYS a
# single digit, and it has to be matched as one: several rows run together with
# no separator at all -- chlorpyrifos extracts as "4,6 x 10 -44,6 x 10 -5..." --
# so a greedy exponent swallows the next mantissa and yields 10^-44.
SCI_ONE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[×x]\s*1\s*0\s*[-−–]\s*(\d)")

# The already-folded form, written by page_entries before column boundaries are
# marked. It exists because the two fixes collided: the extraction renders
# dichlorvos as "6  ×  1 0 -4", with the DOUBLE spaces sitting around the
# multiplication sign -- so marking column boundaries at double spaces cut the
# value into three pieces, and dichlorvos came out as 6.0 instead of 0.0006.
# Folding the notation into a compact token first removes the double spaces from
# inside a value, and leaves them only where a column really ends.
SCI_TOKEN = re.compile(r"(?i)(\d+(?:[.,]\d+)?)E([-+])(\d)")
STASH = "\x1e"          # placeholder delimiter: never in the PDF text

# POSITIVE exponents exist too, and only one row uses one: carbamazepine's
# MAC-EQS is written "1,6 × 10 3" for 1600. Parsed as a negative-only pattern it
# yielded 1.6 and then swallowed the next column, giving a MAC of 103160.
SCI_POS = re.compile(r"(\d+(?:[.,]\d+)?)\s*[×x]\s*1\s*0\s+(\d)(?![\d,.])")

# Footnote references sit INSIDE the value area: lead's row extracts as
#     1,2 ( 12 ) 1,3  1 4  1 4
# where "( 12 )" is a pointer to footnote 12 and the four standards are
# 1,2 / 1,3 / 14 / 14. Read as a number it shifted every column by one and gave
# lead a maximum-allowable standard of 1,3 instead of 14 -- 10.8x too strict,
# and the maximum-allowable analysis is computed against exactly that column.
FOOTNOTE_REF = re.compile(r"\(\s*\d{1,2}\s*\)")


def fold_scientific(s: str) -> str:
    """'6 × 1 0 -4' -> '6E-4'; '1,6 × 10 3' -> '1,6E+3'.

    Folded before column boundaries are marked, because the extraction puts the
    DOUBLE spaces inside the value ("6  ×  1 0 -4") and a boundary marker would
    cut the value in three.
    """
    s = SCI_ONE.sub(lambda m: f"{m.group(1)}E-{m.group(2)}", s)
    return SCI_POS.sub(lambda m: f"{m.group(1)}E+{m.group(2)}", s)


def field_numbers(field: str):
    """Every number in one column field, scientific notation first.

    Digits separated by a single space belong to ONE number: the extraction
    puts a space between the glyphs of a multi-digit integer.
    """
    f = field.strip()
    if not f:
        return []                      # no column here at all
    if re.match(r"(?i)^not\s*applicable", f):
        return [None]                  # a column that is present and empty
    # Set every scientific value aside behind a placeholder BEFORE closing up
    # digits separated by a single space. Doing it the other way round joins
    # across the boundary between two of them -- "6E-4 7E-4" becomes "6E-47E-4"
    # -- which is how a greedy exponent used to swallow the next mantissa.
    vals = []

    def stash(m):
        g = m.groups()
        if len(g) == 2:                       # SCI_ONE: always a negative power
            vals.append(float(g[0].replace(",", ".")) * 10 ** -int(g[1]))
        else:                                 # SCI_TOKEN: signed
            sign = -1 if g[1] == "-" else 1
            vals.append(float(g[0].replace(",", ".")) * 10 ** (sign * int(g[2])))
        return f"{STASH}{len(vals) - 1}{STASH}"

    f = FOOTNOTE_REF.sub(" ", f)              # a pointer, never a standard
    f = SCI_ONE.sub(stash, f)
    f = SCI_TOKEN.sub(stash, f)
    f = _join_digits(f)
    out = []
    for m in re.finditer(STASH + r"(\d+)" + STASH + r"|(\d+(?:[.,]\d+)?)", f):
        if m.group(1) is not None:
            out.append(vals[int(m.group(1))])
        else:
            out.append(float(m.group(2).replace(",", ".")))
    return out


def _join_digits(s: str) -> str:
    """'1 0' is ten; '0,1 0,1' is two values. Only single spaces BETWEEN digits
    are closed up, and only where neither side carries a decimal separator."""
    return re.sub(r"(?<=\d) (?=\d)", "", s)


CAS = re.compile(r"\b\d{2,7}-\d{2}-\d\b")
ENTRY = re.compile(r"^\((\d+[a-z]?)\)\s*(.*)$")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?(?:[eE]-\d+)?"
                    r"|\d+(?:[.,]\d+)?\s*[x×]\s*10\s*-?\s*\d+")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("\xa0", " ")
    # Soft hyphen plus any following whitespace: the PDF hyphenates across line
    # breaks, so dropping only the hyphen leaves "orga nochlorine".
    s = re.sub(r"\u00ad\s*", "", s)
    return re.sub(r"\s+", " ", s).strip()


# The PDF renders scientific notation with a space INSIDE the mantissa base:
# "6 × 1 0 -4" rather than "6 x 10-4". Tokenising that yields 6, 1, 0 and 4 as
# four separate numbers, which then fill the four EQS columns with rubbish.
# Every scientific-notation threshold in Annex I was affected; SHACL caught it
# by rejecting a threshold whose value parsed as 0.
SCI = re.compile(r"(\d+(?:[.,]\d+)?)\s*[×x]\s*1\s*0\s*[-−–]\s*(\d+)")


def normalise_sci(text: str) -> str:
    """Rewrite '6 × 1 0 -4' as '6e-4' before any tokenisation."""
    return SCI.sub(lambda m: f"{m.group(1).replace(',', '.')}e-{m.group(2)}", text)


def to_float(tok: str):
    """Parse '0,0068' and '6,8 x 10 -4' style numbers."""
    t = norm(tok).replace(",", ".")
    m2 = re.match(r"^([\d.]+)[eE]-(\d+)$", t)
    if m2:
        try:
            return float(m2.group(1)) * (10 ** -int(m2.group(2)))
        except ValueError:
            return None
    m = re.match(r"^([\d.]+)\s*[x×]\s*10\s*-?\s*(\d+)$", t)
    if m:
        try:
            return float(m.group(1)) * (10 ** -int(m.group(2)))
        except ValueError:
            return None
    try:
        return float(t)
    except ValueError:
        return None


def page_entries(text: str):
    """Split one page of Annex I into logical entries keyed by '(NN)'."""
    # NOTE: soft hyphens are preserved here on purpose; join_lines needs them to
    # tell a hyphenated word-break from a real hyphen.
    # COLUMN BOUNDARIES SURVIVE AS DOUBLE SPACES, and everything downstream
    # depends on not throwing them away. Benzene's row extracts as
    #     71-43-2 200-753-7  1 0  8  5 0  5 0
    # where "1 0" is ten and the wide gaps separate the four EQS columns.
    # Collapsing all whitespace here read every digit as its own number and
    # gave benzene an annual average of 1 instead of 10 -- five entries were
    # wrong by a factor of ten, all of them high-volume industrial solvents.
    # fold_scientific FIRST: "6  ×  1 0 -4" carries its double spaces INSIDE the
    # value, so marking columns before folding splits the value across columns.
    lines = [re.sub(r"[ \t]{2,}", COL,
                    fold_scientific(l.replace("\xa0", " "))).strip()
             for l in text.splitlines()]
    lines = [re.sub(r"[ \t]+", " ", l) for l in lines]
    # drop the repeated column header block
    # The header block repeats on every page of the table, so it must be
    # dropped wherever it occurs, not once via a latch.
    body = []
    for l in lines:
        if l.startswith("(1) (2)") or l.startswith("Entry"):
            continue
        if l.startswith("AA-EQS") or l.startswith("MAC-EQS"):
            continue
        body.append(l)

    entries, cur = [], None
    for l in body:
        m = ENTRY.match(l)
        if m and not re.match(r"^\(\d+\s*\)$", l):
            if cur:
                entries.append(cur)
            cur = {"no": m.group(1), "lines": [m.group(2)]}
        elif cur is not None:
            cur["lines"].append(l)
    if cur:
        entries.append(cur)
    return entries


def join_lines(lines):
    """Join the physical lines of one entry, repairing line-break artefacts.

    Two distinct breakages occur in this PDF and both silently corrupt the parse:
      * words hyphenated across lines ("neoni-" / "cotinoid"), which a naive
        join turns into "neoni cotinoid";
      * CAS numbers split across lines ("138261-41-" / "3"), which stops the CAS
        regex matching at all -- that is why imidacloprid, whose LOQ is 300x the
        EU standard, was missing from the first run.
    """
    out = ""
    for l in lines:
        if not l:
            continue
        if out.endswith("\u00ad") or (out.endswith("-") and l[:1].isdigit()):
            out = out.rstrip("\u00ad") + l
        elif out:
            out += " " + l
        else:
            out = l
    # a CAS split as "138261-41- 3" survives as a stray space before the check digit
    out = re.sub(r"(\d{2,7}-\d{2}-)\s+(\d)\b", r"\1\2", out)
    return out


def parse_entry(e):
    """Extract name, category, CAS numbers and the four water EQS columns."""
    blob = join_lines(e["lines"])
    cas = CAS.findall(blob)
    if not cas:
        return None

    head = blob[:blob.index(cas[0])]
    # The category column always contains a dash or a known family word.
    cat = ""
    mcat = re.search(r"(Metals|Pesticides|Pharmaceuticals|Industrial|PFAS|"
                     r"Bisphenols?|Biocides?|Other)\b[^0-9]*", head)
    if mcat:
        cat = norm(mcat.group(0))
        name = norm(head[:mcat.start()])
    else:
        name = norm(head)

    tail = blob[blob.rindex(cas[-1]) + len(cas[-1]):]
    # EU numbers look like 231-152-8; strip them before reading the EQS values.
    tail = re.sub(r"\b\d{3}-\d{3}-\d\b", " ", tail)
    tail = re.sub(r"(?i)not\s*" + re.escape(COL) + r"?\s*applicable",
                  "not applicable", tail)
    # Read the columns, in order, keeping "not applicable" as a column that is
    # PRESENT AND EMPTY. Dropping it shifts every later value one column left,
    # which is how four substances with no maximum-allowable standard in Annex I
    # acquired one.
    nums = []
    for field in tail.split(COL):
        nums.extend(field_numbers(field))

    # GROUP entries state a standard for a SUM, not for each member. Annex I
    # has several: "Sum of active substances in the pesticides group" lists 75
    # CAS numbers against one aggregate limit, and the PAH entry lists nine.
    # Applying such a value to each member individually is a category error --
    # it compares one substance against a limit written for their total -- and
    # it silently affected ten measured analytes. The ontology already has the
    # right construct (cereg:GroupThreshold with requiresCompleteGroup); the
    # flag is emitted here so the analysis can honour it.
    nm = name.lower()
    is_group = (len(cas) > 1 and (
        nm.startswith("sum of") or "sum of" in nm
        or "group" in nm or "(pahs)" in nm or "cyclodiene" in nm
        or " and " in nm))

    return {
        "entry_no": e["no"],
        "name": name.rstrip(" -–,"),
        "is_group": is_group,
        "category": cat,
        "cas": cas[0],
        "all_cas": ";".join(cas),
        "n_cas": len(cas),
        "aa_inland": nums[0] if len(nums) > 0 else None,
        "aa_other": nums[1] if len(nums) > 1 else None,
        "mac_inland": nums[2] if len(nums) > 2 else None,
        "mac_other": nums[3] if len(nums) > 3 else None,
        "n_values_found": len(nums),
        "multi_valued": len(cas) > 1 or len(nums) > 6,
    }


def fold(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(s).lower())


# ===========================================================================
#  The four EQS columns are read by COLUMN POSITION, not from flattened text.
#
#  Annex I has rows whose annual-average cells are EMPTY -- mercury (21) and
#  hexachlorobenzene (16), whose standards are set on biota instead. Flattened
#  text cannot distinguish an empty cell from a missing one, so reading such a
#  row left to right put the maximum-allowable values into the annual-average
#  columns and then reached into the biota column for the maximum allowable.
#  Mercury came out with a fabricated annual average of 0.07 and a
#  maximum-allowable standard of 11; the truth is no annual average at all, and
#  0.07. No regex over flattened text can repair that: the information is
#  positional, and the position is what the flattening throws away.
#
#  pdftotext -layout keeps the columns. Every page of the table carries its own
#  index line "(1) (2) ... (13)", and pdftotext scales each page independently,
#  so the boundaries are read per page rather than assumed.
#
#  This makes poppler's pdftotext a hard dependency of THIS stage. That is the
#  right trade: the alternative is a table that is silently wrong for the
#  substances that dominate the metals record. The stage fails loudly rather
#  than falling back to the flattened guess.
# ===========================================================================

EMPTY = "\x00empty"          # a cell that is present and blank

HDR_INDEX = re.compile(r"(?m)^\s*\(1\)\s+\(2\).*\(13\)\s*$")
ROW_START = re.compile(r"^\((\d+[a-z]?)\)\s")
FOOTNOTE_IN_CELL = re.compile(r"\(\s*\d{1,2}\s*\)")
SCI_CELL = re.compile(r"(\d+(?:[.,]\d+)?)\s*[×x]\s*10\s*(-?)\s*(\d+)")

# Columns of Annex I, one-based, as the index line numbers them. The
# parenthesised numbers in the header TEXT ("AA-EQS (3)") are footnote markers,
# not column indices -- reading those as indices shifts every value by one.
COL_AA_INLAND, COL_AA_OTHER, COL_MAC_INLAND, COL_MAC_OTHER = 6, 7, 8, 9


BIOTA_TEXT = re.compile(r"(?i)see\s*footnote|fw fish|sw fish|dry weight"
                        r"|wet weight|covered by")


def _cell_value(chunks):
    """One cell's text -> float, None for 'not applicable', or EMPTY.

    Evaluated CHUNK BY CHUNK rather than on the joined text. A neighbouring
    cell can share a window when the columns are narrow -- hexachlorobenzene's
    maximum-allowable 0,05 sits beside the biota entry "8 fw fish" -- and
    judging the joined string threw the number away with the text.
    """
    pieces = [FOOTNOTE_IN_CELL.sub(" ", c).strip() for c in chunks]
    pieces = [c for c in pieces if c]
    if not pieces:
        return EMPTY
    if re.match(r"(?i)^not\s*(applicable|appli|derived)", " ".join(pieces)):
        return None
    for c in pieces:
        if BIOTA_TEXT.search(c):
            continue               # belongs to the biota column, not here
        m = SCI_CELL.search(c)
        if m:
            exp = int(m.group(3)) * (-1 if m.group(2) else 1)
            return float(m.group(1).replace(",", ".")) * 10 ** exp
        m = re.match(r"^[^\d]{0,6}(\d+(?:[.,]\d+)?)", c)
        if m:
            return float(m.group(1).replace(",", "."))
    return EMPTY


def _cell_footnotes(chunks):
    """The footnote markers a value cell cites, e.g. {"9"} or {"12"}.

    A marker inside a value cell is not decoration: footnote 9 says cadmium's
    standard varies over five water-hardness classes, footnote 12 that lead's and
    nickel's standards "refer to bioavailable concentrations of the substances".
    Those make the threshold CONDITIONAL, and the condition is a property of the
    standard that the value alone cannot carry. They are stripped before the
    number is read; they are recorded here so the package builder can attach the
    condition the Annex attaches.
    """
    out = set()
    for c in chunks:
        for m in FOOTNOTE_IN_CELL.finditer(c):
            out.add(m.group(0).strip("() "))
    return out


def layout_values(pdf):
    """{entry_no: (aa_inland, aa_other, mac_inland, mac_other, footnotes)}."""
    if not shutil.which("pdftotext"):
        sys.exit("pdftotext (poppler-utils) is required to read Annex I by "
                 "column position. Install poppler-utils. This stage will not "
                 "fall back to flattened text, which cannot tell an empty cell "
                 "from a missing one.")
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                         capture_output=True, text=True, check=True).stdout
    cells = {}
    for page in txt.split("\f"):
        m = HDR_INDEX.search(page)
        if not m:
            continue
        offs = [x.start() for x in re.finditer(r"\(\d+\)", m.group(0))]
        if len(offs) != 13:
            continue
        # ANCHOR ON THE COLUMN LABELS, not on the index line. The index numbers
        # are CENTRED over their column while the data is LEFT-ALIGNED, so on
        # the first table page the index offsets sit six characters right of the
        # values: benzene's "10" and "8" landed in the EU-number column and its
        # second "50" past the last value column, leaving benzene with an annual
        # average of 8 instead of 10. The four "AA-EQS AA-EQS MAC-EQS MAC-EQS"
        # labels sit exactly where their values begin.
        bounds = None
        for hl in page.splitlines():
            lab = [x.start() for x in re.finditer(r"AA-EQS|MAC-EQS", hl)]
            if len(lab) == 4:
                pad = 4
                width = max(lab[3] - lab[2], 8)
                e = [lab[0] - pad, lab[1] - pad, lab[2] - pad, lab[3] - pad,
                     lab[3] + width]
                bounds = ([(0, e[0])]                      # 1..5 lumped
                          + list(zip(e[:-1], e[1:]))        # 6,7,8,9
                          + [(e[4], 10 ** 6)])              # 10..13 lumped
                # index 0 -> cols 1-5, 1..4 -> cols 6..9, 5 -> cols 10-13
                break
        if bounds is None:
            edges = ([0] + [(offs[i] + offs[i + 1]) // 2 for i in range(12)]
                     + [10 ** 6])
            bounds = list(zip(edges[:-1], edges[1:]))
        cur = None
        for line in page[m.end():].splitlines():
            r = ROW_START.match(line)
            if r:
                cur = r.group(1)          # "20" or "9a"
                cells.setdefault(cur, [[] for _ in range(len(bounds))])
            if cur is None:
                continue
            # Assign whole CELLS, never character windows. A window boundary
            # that happens to fall inside a value cuts it in two: benzene's
            # "10" became "1" and "0", and anthracene's "0,1" became "0" and
            # "1". Cells are separated by two or more spaces, so each run of
            # text is taken intact and placed in the column that contains its
            # first character.
            for m2 in re.finditer(r"\S(?:[^\s]|\s(?!\s))*", line):
                start = m2.start()
                idx = next((i for i, (a, b) in enumerate(bounds)
                            if a <= start < b), None)
                if idx is not None:
                    cells[cur][idx].append(m2.group(0).strip())
    out = {}
    for no, cols in cells.items():
        if len(cols) == 6:            # label-anchored: [1-5][6][7][8][9][10-13]
            idx = (1, 2, 3, 4)
        else:                         # index-anchored: one slot per column
            idx = (COL_AA_INLAND - 1, COL_AA_OTHER - 1,
                   COL_MAC_INLAND - 1, COL_MAC_OTHER - 1)
        notes = set()
        for i in idx:
            notes |= _cell_footnotes(cols[i])
        out[no] = tuple(_cell_value(cols[i]) for i in idx) + (notes,)
    return out


def main() -> int:
    if not PDF.exists():
        sys.exit(f"missing {PDF}")
    # Every output directory this stage writes to, created here rather
    # than assumed. On a fresh clone derived/processed/ does not exist,
    # and a stage that only made eval/ died on its first write -- a
    # failure invisible for as long as anyone's tree already had the
    # directory from an earlier run.
    EVAL.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(PDF)

    # Annex I is ONE table spread over consecutive pages, and it must be parsed
    # as one stream. Two defects followed from treating each page separately:
    #
    #   * pages were skipped unless their extracted text contained the literal
    #     "AA-EQS". That string sits in the column header, which the continuation
    #     pages do not repeat, so whole pages of the table were never read;
    #   * an entry whose "(NN)" marker fell on one page and whose EQS values fell
    #     on the next lost its values, because the continuation lines arrived
    #     before any "(NN)" had been seen on that page and were discarded.
    #
    # Between them these dropped eight substances the survey actually measures,
    # including the Annex I priority pesticides atrazine, simazine, alachlor and
    # chlorfenvinphos. The table region is therefore located once and the pages
    # concatenated before splitting.
    pages = [(p.extract_text() or "") for p in reader.pages]
    first = next((i for i, t in enumerate(pages) if "AA-EQS" in t), None)
    if first is None:
        sys.exit("could not locate Annex I: no page contains 'AA-EQS'")
    last = len(pages) - 1
    for i in range(first + 1, len(pages)):
        # the table ends where the next annex or the footnote block begins
        if re.search(r"\bANNEX\s+II\b", pages[i]) or "PART B" in pages[i]:
            last = i
            break
    annex = "\n".join(pages[first:last + 1])
    n_pages = last - first + 1

    rows, unparsed, unparsed_no = [], 0, []
    for e in page_entries(annex):
        p = parse_entry(e)
        if p is None:
            unparsed += 1
            unparsed_no.append(e["no"])
            continue
        rows.append(p)

    # THE FOUR EQS COLUMNS COME FROM THE COLUMN-POSITION READER, always. The
    # flattened parse still supplies the name, category and CAS numbers, which
    # it reads well; it must not supply a standard, because it cannot see which
    # cell is empty.
    lay = layout_values(PDF)
    covered = 0
    for r in rows:
        v = lay.get(str(r["entry_no"]).strip())
        if v is None:
            r["aa_inland"] = r["aa_other"] = None
            r["mac_inland"] = r["mac_other"] = None
            r["layout_read"] = False
            r["footnotes"] = ""
            continue
        covered += 1
        r["layout_read"] = True
        # Cadmium cites footnote 9 -- the five hardness classes -- from its NAME
        # cell, not from a value cell, so the name has to be read too or the one
        # substance whose standard is explicitly conditional carries no
        # condition at all.
        notes = set(v[4]) | {m.group(1) for m in
                             re.finditer(r"\(\s*(\d{1,2})\s*\)",
                                         str(r.get("name", "")))}
        r["footnotes"] = ";".join(sorted(notes, key=int))
        for key, val in zip(("aa_inland", "aa_other",
                             "mac_inland", "mac_other"), v[:4]):
            # EMPTY (blank cell) and None ("not applicable") both mean the
            # column states no standard, and downstream treats both the same
            # way: the substance is not assessable against that standard.
            r[key] = None if (val is None or val == EMPTY) else val
    print(f"  Annex I columns read by position: {covered}/{len(rows)} entries")
    if covered < 0.9 * len(rows):
        sys.exit(f"only {covered} of {len(rows)} entries could be read by "
                 f"column position; refusing to publish a partly guessed table")

    # de-duplicate by entry number, keeping the richest parse
    best = {}
    for r in rows:
        k = r["entry_no"]
        if k not in best or r["n_values_found"] > best[k]["n_values_found"]:
            best[k] = r
    rows = [best[k] for k in sorted(best, key=lambda x: (len(x), x))]

    with (PROC / "eu_eqs.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # The single-basin survey this section used to cross-match against has
    # been withdrawn from the paper, and its inputs are retired to attic/.
    # Parsing the Annex is the whole job now: the assessment against measured
    # data happens in scripts/22 and 23, against Waterbase.

    cats = Counter(r["category"] for r in rows if r.get("category"))
    L = []
    A = L.append
    A("# EU environmental quality standards (consolidated, in force 10 May 2026)\n")
    A("Generated by `scripts/10_parse_eu_eqs.py` from the consolidated text of "
      "Directive 2008/105/EC — the current law with the 2026 update merged in.\n")
    A(f"- Annex I entries parsed: **{len(rows)}**")
    A(f"- Annex I pages read as one stream: {n_pages}")
    A(f"- entries that could not be parsed unambiguously: {unparsed} "
      f"(reported, not guessed)")
    A(f"- entries covering a substance GROUP (several CAS numbers): "
      f"{sum(1 for r in rows if r['n_cas'] > 1)}")

    A("## Official substance categories\n")
    A("Column (3) of Annex I classifies each substance by use. This is a "
      "**legislative** classification: citable, versioned, and immune to the "
      "circularity objection that an analyst-authored mapping invites.\n")
    A("| category | entries |")
    A("|---|---|")
    for c, n in cats.most_common(20):
        A(f"| {c} | {n} |")
    A("")


    A("## Caveats\n")
    A("- Cadmium carries five hardness-class values; the parser records the "
      "first. Any assessment of cadmium requires the water hardness class, "
      "which the aggregated release does not carry.\n")
    A("- Group entries (cyclodiene pesticides, PFAS sum, total pesticides) are "
      "aggregates and are handled by `cereg:GroupThreshold`, not by the "
      "per-substance rows above.\n")
    A("- Values are transcribed from the consolidated text and verified by "
      "`scripts/08_verify_thresholds.py`; the packages carry "
      "`cereg:transcriptionStatus cereg:VerifiedAgainstPrimarySource`.\n")

    text = "\n".join(L)
    (EVAL / "eu_eqs_assessment.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nwrote: {EVAL/'eu_eqs_assessment.md'}, {PROC/'eu_eqs.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
