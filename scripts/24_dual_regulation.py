#!/usr/bin/env python3
"""
The same observations, assessed under two regulations.

WHY THIS SCRIPT EXISTS
----------------------
Section 4 claims that pluggable regulation packages let one set of observations
be assessed under several jurisdictions without reimplementation. That claim is
cheap to make and, until it is run, unfalsifiable. This script runs it: it reads
BOTH published regulation packages as data, streams the same Waterbase rows past
each of them, and reports how the four-valued verdict changes.

Nothing about the observations differs between the two passes. The value, the
limit of quantification, the unit conversion and the decision procedure are
identical; the only input that changes is which package supplies the threshold.
Every disagreement in the output is therefore attributable to the regulation
alone, which is exactly the property a threshold column in a spreadsheet cannot
demonstrate.

WHAT COUNTS AS A DISAGREEMENT
-----------------------------
Compliant and Exceeding, plus three reasons a verdict may be unavailable. The
three are kept apart because they are unavailable for different reasons and only
one of them moves when the jurisdiction changes:

  Compliant             the interval lies entirely at or below the standard
  Exceeding             the value lies above it
  MethodInsufficient    LOQ > standard, so Article 3(3b) sets the result aside
  NoThresholdDefined    that jurisdiction regulates no standard for this analyte
  BoundNotEstablished   the record establishes no bound to compare -- a
                        censoring flag with no limit, or no value

NoThresholdDefined is not a gap in the data: it is a substantive legal fact
about the jurisdiction, and a two-valued model has to record it as "compliant"
or drop the row -- both wrong in the same direction. BoundNotEstablished IS a
gap in the data, is identical under every jurisdiction, and collapsing the two
would let a
reporting defect masquerade as a regulatory difference.

TWO NUMBERS, NOT ONE
--------------------
Swapping the package changes outcomes for two quite different reasons, and a
single headline percentage would conflate them:

  COVERAGE   one jurisdiction regulates a substance the other does not. Real,
             but it says nothing about whether the numbers disagree.
  SUBSTANCE  both regulate it and still reach different verdicts. This is the
             one that tests whether pluggable thresholds matter.

The report gives both, and the co-regulated stratum is the honest headline.

A NOTE ON WHAT THIS DOES NOT SHOW
---------------------------------
Turkish standards are not in force over European rivers. The comparison is
counterfactual by construction, and it is reported as a demonstration that the
machinery is regulation-independent, never as an assessment of Türkiye. The
substantive finding is the SIZE of the divergence: if swapping the package moved
almost nothing, the pluggability would be an engineering convenience rather than
a modelling requirement.

Inputs  : Data/waterbase/*.{csv,csv.gz,zip}   or --file
          ontology/reg/eu-2008-105-2026.ttl
          ontology/reg/tr-ysky-2016.ttl
Outputs : derived/processed/dual_regulation.csv
          eval/dual_regulation.md

Usage:  python scripts/24_dual_regulation.py [--file PATH] [--limit N]
        python scripts/24_dual_regulation.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Data" / "waterbase"
REG = ROOT / "ontology" / "reg"
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

sys.path.insert(0, str(Path(__file__).resolve().parent))
_m = __import__("22_waterbase_external")
open_rows, pick, num, wilson = _m.open_rows, _m.pick, _m.num, _m.wilson
TO_UG_L = _m.TO_UG_L

# Jurisdiction label -> package file. Adding a third is one line here and
# nothing anywhere else; that is the point being demonstrated.
PACKAGES = [
    ("EU", REG / "eu-2008-105-2026.ttl", "Directive 2008/105/EC, Annex I"),
    ("TR", REG / "tr-ysky-2016.ttl", "YSKY 2016, Table 4"),
]

# The label follows the vocabulary: what these rows lack is the BOUND, not
# necessarily the limit, and censo:BoundNotEstablished is the class the graph
# now carries for them. The variable name is unchanged so the cross-tab keys,
# which scripts/99_audit.py joins on, are untouched.
COMPLIANT, EXCEEDING, INSUFFICIENT, NOTHRESHOLD, UNRESOLVED = (
    "Compliant", "Exceeding", "MethodInsufficient", "NoThresholdDefined",
    "BoundNotEstablished")
OUTCOMES = [COMPLIANT, EXCEEDING, INSUFFICIENT, NOTHRESHOLD, UNRESOLVED]


def load_package(path: Path):
    """CAS -> annual-average threshold in ug/L, read from the published file.

    Read as RDF rather than from a CSV of our own making: if the file we ship
    at w3id.org disagrees with the numbers in the paper, this is where it shows.
    """
    import rdflib
    C = rdflib.Namespace("https://w3id.org/censo/")
    g = rdflib.Graph()
    g.parse(path, format="turtle")

    cas_of = {}
    for a, _, c in g.triples((None, C.casNumber, None)):
        cas_of[a] = str(c).strip()

    out = {}
    for t in g.subjects(rdflib.RDF.type, C.AnnualAverageThreshold):
        a = next(g.objects(t, C.appliesToAnalyte), None)
        v = next(g.objects(t, C.thresholdValue), None)
        u = next(g.objects(t, C.thresholdUnit), None)
        if a is None or v is None:
            continue
        if u is not None and not str(u).endswith("MicroGM-PER-L"):
            sys.exit(f"{path.name}: unexpected threshold unit {u}")
        cas = cas_of.get(a)
        if not cas:
            continue
        val = float(v)
        # A CAS with two standards (different water categories) takes the
        # stricter: assessing against the looser one would understate exceedance.
        if cas not in out or val < out[cas]:
            out[cas] = val
    return out


def verdict(thr, value_ug, loq_ug, below_loq):
    """The four-valued outcome. Identical for every jurisdiction by construction.

    Order matters and follows the law, not convenience: Article 3(3b) is tested
    BEFORE compliance, because a below-LOQ result whose limit exceeds the
    standard is set aside whatever the reported number happens to say.
    """
    # Tested before the threshold: a record that cannot be interpreted is
    # unresolvable under EVERY jurisdiction, so calling it "no standard" would
    # charge a reporting defect to the regulation.
    if below_loq and loq_ug is None:
        return UNRESOLVED
    if not below_loq and value_ug is None:
        return UNRESOLVED
    if thr is None:
        return NOTHRESHOLD
    if loq_ug is not None and loq_ug > thr:
        return INSUFFICIENT
    if below_loq:
        # the bound clears the standard, so the non-detection decides it
        return COMPLIANT
    return EXCEEDING if value_ug > thr else COMPLIANT


def self_test() -> int:
    """Every branch of verdict(), plus the property the whole script rests on:
    the SAME observation under two thresholds may take two different outcomes."""
    cases = [
        # thr,  value, loq,  below, expected
        (None,  0.5,   0.01, False, NOTHRESHOLD),
        (0.1,   0.5,   0.01, False, EXCEEDING),
        (0.1,   0.05,  0.01, False, COMPLIANT),
        (0.1,   None,  0.5,  True,  INSUFFICIENT),   # LOQ above the standard
        (0.1,   None,  0.01, True,  COMPLIANT),      # bound clears it
        (0.1,   None,  None, True,  UNRESOLVED),     # flag without a bound
        (None,  None,  None, True,  UNRESOLVED),     # and it stays unresolved
        (0.1,   None,  0.05, False, UNRESOLVED),     # no value, not censored
        (0.1,   0.1,   0.01, False, COMPLIANT),      # equal is not exceeding
    ]
    bad = 0
    for thr, val, loq, bel, want in cases:
        got = verdict(thr, val, loq, bel)
        if got != want:
            print(f"  FAIL verdict({thr},{val},{loq},{bel}) = {got}, want {want}")
            bad += 1

    # the divergence property, on one measurement
    if verdict(0.1, 0.5, 0.01, False) == verdict(1.0, 0.5, 0.01, False):
        print("  FAIL a value between two standards must be judged differently")
        bad += 1
    # and the one that matters for Article 3(3b): the same method is adequate
    # under a loose standard and inadequate under a strict one
    if verdict(1.0, None, 0.5, True) != COMPLIANT or \
       verdict(0.1, None, 0.5, True) != INSUFFICIENT:
        print("  FAIL method adequacy must depend on the standard")
        bad += 1
    # the converse property: an uninterpretable record must NOT move when the
    # jurisdiction does, or a reporting defect would be counted as divergence
    if verdict(0.1, None, None, True) != verdict(9.9, None, None, True):
        print("  FAIL an unresolvable record must be jurisdiction-invariant")
        bad += 1

    print("  self-test passed" if not bad else f"  {bad} self-test failures")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if self_test():
        return 1

    src = args.file
    if src is None:
        cand = [p for p in sorted(DATA.glob("*"))
                if p.suffix.lower() in (".csv", ".zip", ".gz")]
        agg = [p for p in cand if "aggregated" in p.name.lower()]
        cand = agg or cand
        if not cand:
            sys.exit(f"no Waterbase file in {DATA.relative_to(ROOT)}; "
                     f"see scripts/22_waterbase_external.py for the download")
        src = cand[0]
    print(f"  source: {src.name}")

    packs = []
    for name, path, cite in PACKAGES:
        thr = load_package(path)
        packs.append((name, thr, cite))
        print(f"  {name}: {len(thr)} annual-average standards from {path.name}")

    rows = open_rows(src)
    header = next(rows)
    col = pick(header)
    if "determinand" not in col:
        sys.exit(f"determinand column not found; header was {header[:14]}")

    def get(row, role):
        i = col.get(role)
        return row[i].strip() if i is not None and i < len(row) else ""

    n = kept = scored = 0
    tally = {name: defaultdict(int) for name, _, _ in packs}
    cross = defaultdict(int)                      # (EU outcome, TR outcome)
    co_cross = defaultdict(int)                   # same, co-regulated only
    co = defaultdict(int)
    by_sub = defaultdict(lambda: defaultdict(int))
    labels = {}

    for row in rows:
        if not row:
            continue
        n += 1
        if args.limit and n > args.limit:
            break
        if n % 2_000_000 == 0:
            print(f"    {n:,} rows read, {scored:,} scored …")

        if "category" in col and get(row, "category") not in ("RW", ""):
            continue
        kept += 1

        code = get(row, "code")
        cas = code[4:] if code.upper().startswith("CAS_") else ""
        if not cas:
            continue
        # Only rows some jurisdiction regulates. A row neither regulates is
        # NoThresholdDefined under both and would inflate the agreement rate
        # with a fact about neither regulation.
        if not any(cas in thr for _, thr, _ in packs):
            continue

        factor = TO_UG_L.get(get(row, "uom").strip().lower())
        if factor is None:
            continue

        val = num(get(row, "value"))
        loq = num(get(row, "loq"))
        below = _m.truthy(get(row, "below_loq"))
        val_ug = val * factor if val is not None else None
        loq_ug = loq * factor if loq is not None else None

        scored += 1
        labels.setdefault(cas, get(row, "determinand") or code)
        vs = []
        for name, thr, _ in packs:
            v = verdict(thr.get(cas), val_ug, loq_ug, below)
            tally[name][v] += 1
            vs.append(v)
        cross[tuple(vs)] += 1
        # The stratum that actually tests the thresholds: both jurisdictions
        # regulate this substance, so any difference is about the numbers.
        if all(cas in thr for _, thr, _ in packs):
            co["n"] += 1
            co_cross[tuple(vs)] += 1
            if len(set(vs)) > 1:
                co["differ"] += 1
                by_sub[cas]["differ"] += 1
            by_sub[cas]["n"] += 1

    if not scored:
        sys.exit("no rows scored; check the source file and column mapping")

    PROC.mkdir(parents=True, exist_ok=True)
    EVAL.mkdir(parents=True, exist_ok=True)

    with (PROC / "dual_regulation.csv").open("w", newline="",
                                             encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scope", "key", "eu_outcome", "tr_outcome", "n"])
        w.writerow(["total", "rows_read", "", "", n])
        w.writerow(["total", "rows_river", "", "", kept])
        w.writerow(["total", "rows_scored", "", "", scored])
        w.writerow(["total", "rows_co_regulated", "", "", co["n"]])
        w.writerow(["total", "co_regulated_differ", "", "", co["differ"]])
        for name, _, _ in packs:
            for o in OUTCOMES:
                w.writerow(["jurisdiction", name, o, "", tally[name][o]])
        for (a, b), c in sorted(cross.items(), key=lambda kv: -kv[1]):
            w.writerow(["cross", "", a, b, c])
        for (a, b), c in sorted(co_cross.items(), key=lambda kv: -kv[1]):
            w.writerow(["cross_co_regulated", "", a, b, c])
        for cas, d in sorted(by_sub.items(),
                             key=lambda kv: -kv[1]["differ"]):
            w.writerow(["substance", f"{cas}|{labels.get(cas,'')}",
                        "", "", d["differ"]])

    differ = sum(c for (a, b), c in cross.items() if a != b)
    # wilson() returns percentages, not proportions
    _p, lo, hi = wilson(differ, scored)
    _p2, clo, chi = wilson(co["differ"], co["n"])

    L = ["# The same observations under two regulations", "",
         "Generated by `scripts/24_dual_regulation.py`. The observations, the "
         "unit conversion and the decision procedure are identical in both "
         "columns; only the regulation package differs.", "",
         f"- rows read: **{n:,}**",
         f"- river rows: **{kept:,}**",
         f"- rows regulated by at least one jurisdiction, and scored: "
         f"**{scored:,}**",
         f"- of those, regulated by **both** (the co-regulated stratum): "
         f"**{co['n']:,}**", "",
         "## Verdict distribution", "",
         "| Outcome | " + " | ".join(p[0] for p in packs) + " |",
         "|---|" + "---|" * len(packs)]
    for o in OUTCOMES:
        L.append(f"| {o} | " + " | ".join(
            f"{tally[p[0]][o]:,} ({tally[p[0]][o]/scored:.1%})"
            for p in packs) + " |")

    L += ["", "## Where they disagree, and why", "",
          "Two distinct effects, reported separately because a single figure "
          "would let the larger one hide the more interesting one.", "",
          f"**Coverage.** Over all {scored:,} scored assessments, "
          f"{differ:,} ({differ/scored:.1%}, 95% CI {lo:.1f}–{hi:.1f}%) change "
          "outcome. Most of that is one jurisdiction regulating a substance "
          "the other does not, which is a fact about the two legal instruments "
          "rather than about the measurements.", "",
          f"**Substance.** Restricting to the {co['n']:,} assessments both "
          f"jurisdictions regulate, **{co['differ']:,} "
          f"({co['differ']/co['n']:.1%}, 95% CI {clo:.1f}–{chi:.1f}%) still "
          "change outcome.** Here nothing differs but the numeric standard, so "
          "this is the figure that tests whether the threshold has to be "
          "swappable.", "",
          "| EU | TR | n (co-regulated) |", "|---|---|---|"]
    for (a, b), c in sorted(co_cross.items(), key=lambda kv: -kv[1]):
        if a != b:
            L.append(f"| {a} | {b} | {c:,} |")

    L += ["", "The two rows worth reading twice are the ones that cross the "
          "compliance boundary: an assessment that is *Exceeding* under one "
          "instrument and *Compliant* under the other, and one the EU sets "
          "aside under Article 3(3b) as method-insufficient while Türkiye's "
          "looser standard lets the same method decide it. Neither is "
          "expressible if the threshold is a column.", "",
          "## Substances driving the divergence", "",
          "Co-regulated substances only, ranked by assessments whose outcome "
          "changes.", "",
          "| Substance | CAS | differing | of | share |", "|---|---|---|---|---|"]
    for cas, d in sorted(by_sub.items(), key=lambda kv: -kv[1]["differ"])[:12]:
        if d["differ"]:
            L.append(f"| {labels.get(cas,'')} | {cas} | {d['differ']:,} | "
                     f"{d['n']:,} | {d['differ']/d['n']:.0%} |")

    L += ["", "## What this does and does not establish", "",
          "Turkish standards are not in force over European rivers, so the TR "
          "column is counterfactual. It is reported to show that the "
          "assessment machinery is regulation-independent: neither the "
          "ontology, the rule layer nor this script contains a threshold. "
          "Both columns are produced by the same code reading two published "
          "files.", ""]
    for name, thr, cite in packs:
        L.append(f"- **{name}** — {cite}; {len(thr)} annual-average standards.")

    (EVAL / "dual_regulation.md").write_text("\n".join(L) + "\n",
                                             encoding="utf-8")
    print(f"\n  scored {scored:,} assessments under {len(packs)} jurisdictions")
    print(f"  all rows        : {differ:,} ({differ/scored:.1%}) change outcome")
    print(f"  co-regulated    : {co['differ']:,} of {co['n']:,} "
          f"({co['differ']/co['n']:.1%}) change outcome")
    print(f"  wrote {(PROC/'dual_regulation.csv').relative_to(ROOT)}")
    print(f"  wrote {(EVAL/'dual_regulation.md').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
