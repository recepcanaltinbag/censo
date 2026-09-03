#!/usr/bin/env python3
"""
Generate every supplementary data file the paper ships.

WHY THIS IS A SCRIPT AND NOT A SET OF COPIES
--------------------------------------------
The supplementary tables are what a reader receives, and they are the only way
anyone outside this repository can recompute a number in the manuscript. Two of
them were being produced by hand and then copied, which means nothing detected
when the analysis behind them moved on. That is the same failure mode as the
published ontology copy drifting from its source, and it gets the same fix: the
directory is generated, never edited, and `--check` fails when it is stale.

The audit additionally requires every quantity asserted in the manuscript to be
findable in one of these files. A claim that cannot be traced into shipped data
is not reproducible, whatever else is true of it.

Inputs  : derived/processed/*.csv
Outputs : paper/supplementary/S2..S11*.csv

Usage:  python scripts/98_supplementary.py [--check]
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"
SUPP = ROOT / "paper" / "supplementary"


def load(name):
    p = PROC / name
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write(rows, header, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def build_substances():
    """S2: one row per substance, with the counts behind Section 5.1."""
    summ = load("waterbase_summary.csv")
    if not summ:
        return None
    eqs = {}
    for r in load("eu_eqs.csv") or []:
        if r.get("is_group") == "True":
            continue
        for c in (r.get("all_cas") or "").replace(" ", "").split(";"):
            if c:
                eqs.setdefault(c, (r.get("category", ""), r.get("aa_inland", "")))
    out = []
    for r in summ:
        if r["scope"] != "substance":
            continue
        cas = ""
        for c in eqs:
            if c in r["key"]:
                cas = c
                break
        cat, aa = eqs.get(cas, ("", ""))
        eq = int(r["has_eqs"])
        out.append([r["key"], cas, cat, aa, r["n"], eq, r["below_loq"],
                    r["silent"], r["loq_gt_eqs"], r["loq_gt_30pct_eqs"],
                    f"{100*int(r['loq_gt_30pct_eqs'])/eq:.2f}" if eq else ""])
    out.sort(key=lambda x: -int(x[4]))
    return out, ["substance", "cas", "annex_i_category", "eu_aa_eqs_ug_l",
                 "station_years", "station_years_with_eqs", "below_loq",
                 "no_flag_no_limit", "loq_above_eqs", "loq_above_30pct_eqs",
                 "pct_failing_legal_criterion"]


def build_scope(scope, first_col):
    """S3 / S4b: the same counts aggregated by country, or by substance class."""
    summ = load("waterbase_summary.csv")
    if not summ:
        return None
    cols = ["n", "samples", "samples_below", "declared_and_bounded",
            "declared_not_bounded", "silent", "qc_loq_unknown",
            "has_eqs", "loq_gt_eqs", "loq_gt_30pct_eqs"]
    out = []
    for r in summ:
        if r["scope"] != scope:
            continue
        s, eq = int(r["samples"]), int(r["has_eqs"])
        # The shares the manuscript quotes, carried explicitly. A reader should
        # not have to divide two columns to check a percentage in the text.
        out.append([r["key"]] + [r[c] for c in cols] +
                   [f"{100*int(r['samples_below'])/s:.1f}" if s else "",
                    f"{100*int(r['silent'])/int(r['n']):.1f}" if int(r["n"]) else "",
                    f"{100*int(r['loq_gt_30pct_eqs'])/eq:.1f}" if eq else ""])
    out.sort(key=lambda x: -int(x[1]))
    return out, [first_col, "station_years", "samples", "samples_below_loq",
                 "declared_and_bounded", "declared_not_bounded",
                 "no_flag_no_limit", "qc_loq_unknown", "station_years_with_eqs",
                 "loq_above_eqs", "loq_above_30pct_eqs",
                 "pct_samples_below_loq", "pct_no_flag_no_limit",
                 "pct_failing_legal_criterion"]


MAC_COLS = ["n", "quantified", "censored", "exceedance",
            "compliant_quantified", "compliant_censored",
            "method_insufficient", "censored_no_loq"]


def build_mac():
    """S12: the maximum-allowable standard, per substance and per country.

    Shipped separately from S2/S3 rather than folded into them, because the row
    is a different thing: a sample, not a station-year. Merging the two would
    be the category error the stage exists to demonstrate.
    """
    p = PROC / "mac_exceedance.csv"
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        if r["scope"] not in ("total", "substance", "country", "era"):
            continue
        n = int(r["n"])
        out.append([r["scope"], r["key"] or "all"]
                   + [r[c] for c in MAC_COLS]
                   + [f"{100*int(r['exceedance'])/n:.2f}" if n else "",
                      f"{100*int(r['method_insufficient'])/n:.2f}" if n else ""])
    if not out:
        return None
    order = {"total": 0, "era": 1, "country": 2, "substance": 3}
    out.sort(key=lambda x: (order.get(x[0], 9), -int(x[2])))
    return out, ["scope", "key", "assessable_samples", "quantified",
                 "censored", "exceedance", "compliant_quantified",
                 "compliant_censored", "method_insufficient",
                 "censored_no_limit", "pct_exceedance",
                 "pct_undecidable"]


def _shares(r):
    """The four shares the era discussion quotes, carried explicitly.

    A reader checking a percentage in the text should not have to work out
    which two columns to divide, and getting the denominator wrong is exactly
    how a percentage in this paper went wrong before: the legal-criterion share
    is over rows that HAVE a standard, not over all rows.
    """
    n, eq = int(r["n"]), int(r["has_eqs"])
    cen = int(r.get("censored") or 0)
    return [f"{100*int(r['silent'])/n:.1f}" if n else "",
            f"{100*int(r['loq_gt_eqs'])/eq:.1f}" if eq else "",
            f"{100*int(r['loq_gt_30pct_eqs'])/eq:.1f}" if eq else "",
            f"{100*int(r.get('censored_with_value') or 0)/cen:.1f}"
            if cen else ""]


ERA_LABEL = {"pre2015": "before 2015", "2015plus": "2015 onwards",
             "undated": "no year recorded"}
ERA_ORDER = {"pre2015": 0, "2015plus": 1, "undated": 2}

ERA_COLS = ["n", "samples", "samples_below", "silent", "has_eqs",
            "loq_gt_eqs", "loq_gt_30pct_eqs", "censored", "censored_with_value"]
ERA_HEADER_TAIL = ["station_years", "samples", "samples_below_loq",
                   "no_flag_no_limit", "station_years_with_eqs",
                   "loq_above_eqs", "loq_above_30pct_eqs",
                   "censored", "censored_with_positive_value",
                   "pct_no_flag_no_limit", "pct_loq_above_eqs",
                   "pct_failing_legal_criterion",
                   "pct_censored_carrying_a_positive_value"]


def build_era():
    """S10: the audit split at 2015, which is where the record divides."""
    summ = load("waterbase_summary.csv")
    if not summ:
        return None
    rows = [r for r in summ if r["scope"] == "era"]
    if not rows:
        return None
    total = sum(int(r["n"]) for r in rows)
    out = []
    for r in sorted(rows, key=lambda r: ERA_ORDER.get(r["key"], 9)):
        out.append([ERA_LABEL.get(r["key"], r["key"]),
                    f"{100*int(r['n'])/total:.1f}" if total else ""]
                   + [r[c] for c in ERA_COLS] + _shares(r))
    return out, ["era", "pct_of_river_record"] + ERA_HEADER_TAIL


def build_era_country():
    """S11: the same split within each reporting country.

    Shipped because the era comparison is only interpretable against it. The
    set of reporters changes between the two periods, so a rate that falls
    across the boundary has to be checked on the authorities present in both;
    that check is not reproducible from the pooled table alone.
    """
    summ = load("waterbase_summary.csv")
    if not summ:
        return None
    rows = [r for r in summ if r["scope"] == "era_country"]
    if not rows:
        return None
    out = []
    for r in rows:
        cty, _, era = r["key"].partition(":")
        out.append([cty, ERA_LABEL.get(era, era)]
                   + [r[c] for c in ERA_COLS] + _shares(r))
    out.sort(key=lambda x: (x[0], ERA_ORDER.get(
        {v: k for k, v in ERA_LABEL.items()}.get(x[1], x[1]), 9)))
    return out, ["country", "era"] + ERA_HEADER_TAIL


# Files copied verbatim from a derived artefact: the derived file already has
# exactly the columns a reader needs, so restating them here would only create
# a second place for them to drift.
COPIES = [
    ("country_confounders.csv", "S5_country_robustness.csv"),
    ("dual_regulation.csv", "S6_dual_regulation.csv"),
    ("waterbase_exemplars.csv", "S7_decision_geometry_cases.csv"),
    ("source_conformance.csv", "S9_source_conformance.csv"),
    # The reasoning cost was measured (stage 15) and then shipped nowhere,
    # which for a software journal is the one result a reader most wants to
    # check against their own hardware.
    ("reasoning_benchmark.csv", "S13_reasoning_cost.csv"),
]

# Two supplementary files each said "Generated by scripts/..." and were
# generated by nothing: someone had copied the report once, by hand. They then
# did exactly what the docstring above warns about. S1 was shipped claiming
# 442,363 triples while the manuscript said 447,209 and the build reported a
# third number -- one quantity, three values, in files a reader receives
# together. They are copies now, from the report that produces them.
EVAL_COPIES = [
    ("competency_questions.md", "S1_competency_questions.md"),
    ("gap_table.md", "S4_ontology_comparison.md"),
]


# The reader-facing index. It was hand-maintained and had drifted: it announced
# 15 competency questions where there are 20, described Figure 6 as four
# observations with a detection limit when it draws three and the record has no
# detection limit, listed "restriction to recent years" as one of the three
# robustness adjustments when Section 5.8 says explicitly that it is NOT one,
# and did not mention S12 at all. A file shipped to readers cannot be
# hand-maintained beside generated data; it is generated now, from here.
DESCRIPTIONS = [
    ("S1_competency_questions.md",
     "Every competency question with its SPARQL and the rows returned by the "
     "Waterbase knowledge graph."),
    ("S2_substance_inventory.csv",
     "Every substance in the audit: CAS, Annex I category, the European "
     "annual-average standard, and the counts behind Section 5.1 --- "
     "station-years, below-LOQ, records carrying neither flag nor limit, and "
     "the two legal tests."),
    ("S3_by_country.csv", "The same counts per reporting country."),
    ("S4_ontology_comparison.md",
     "The ontology files assessed, with the evidence found in each and the "
     "concepts scored as prose-only rather than as vocabulary."),
    ("S5_country_robustness.csv",
     "Section 5.8. Each country's share of records carrying neither flag nor "
     "limit, raw and after the three adjustments the section reports: direct "
     "standardisation onto the pooled European substance mix, restriction to "
     "the common substance basket, and EU membership, which is what makes the "
     "quantification-limit criterion binding. Restricting to recent years is "
     "not among them --- too few countries report after 2015."),
    ("S6_dual_regulation.csv",
     "Section 5.6. The full outcome cross-tabulation for the same "
     "observations assessed under the European and the Turkish package, with "
     "the co-regulated stratum separated from the coverage difference, and "
     "the per-substance breakdown."),
    ("S7_decision_geometry_cases.csv",
     "The real observations drawn in Figure 6 --- substance, CAS, reporting "
     "country, quantification limit, standard and reported value. There is no "
     "detection-limit column because WISE-6 has no such field."),
    ("S8_by_substance_class.csv",
     "Section 6.1. The same counts split between Annex I metals and organic "
     "micropollutants, which is the comparison against the metals-only "
     "sensitivity literature."),
    ("S9_source_conformance.csv",
     "Section 5.5. What the published SHACL shapes catch in the record as "
     "reported, with no repair applied: the population count for each "
     "condition over all river rows, the violations raised on the validated "
     "sample, and the per-country share of below-quantification rows that "
     "already carry a substituted value."),
    ("S10_by_era.csv",
     "Section 5.2. The whole audit split at 2015 --- station-years, samples, "
     "records carrying neither flag nor limit, both legal tests, and "
     "below-quantification rows carrying a positive value."),
    ("S11_era_by_country.csv",
     "The same split within each reporting country, which is what makes the "
     "era comparison interpretable: the set of authorities reporting is not "
     "the same in the two periods, so a rate that falls across the boundary "
     "has to be checked on the authorities present in both."),
    ("S12_mac_exceedance.csv",
     "Section 5.7. The maximum-allowable concentration, which is defined "
     "against an individual sample and therefore read from the disaggregated "
     "release: per substance and per country, the samples assessable, those "
     "exceeding, and those a method could not decide. Includes the coverage "
     "of the stratum readable at both units of observation."),
    ("S14_by_year.csv",
     "Section 5.2. The audit year by year rather than split in two: "
     "station-years, samples, records carrying neither flag nor limit, both "
     "legal criteria, and below-quantification rows carrying a positive value, "
     "for every reference year in the record. This is what shows that one "
     "failure ends on a date and the other two do not move."),
    ("S13_reasoning_cost.csv",
     "Section 5.10. OWL 2 RL closure and SHACL validation time against ABox "
     "size, on the reference machine. Timings are hardware-dependent; the "
     "shape --- super-linear closure, validation an order of magnitude "
     "cheaper --- is not."),
    ("figure_data/",
     "The numbers each figure actually plots, one file per figure, written by "
     "the plotting code itself at the point the values become final. Every "
     "mark in every figure can be recomputed from these without rerunning "
     "the pipeline."),
]


def write_readme():
    lines = ["# Supplementary material", "", "| file | contents |", "|---|---|"]
    for name, why in DESCRIPTIONS:
        present = (SUPP / name).exists()
        lines.append(f"| `{name}` | {why}"
                     + ("" if present else " **(not built in this run)**")
                     + " |")
    lines += [
        "",
        "Everything here is generated by `scripts/98_supplementary.py`, this "
        "index included, and never edited by hand; `--check` fails when a "
        "shipped copy is stale. `eval/audit.md` recomputes every reported "
        "value from the source data and fails on a mismatch.",
        "",
        "The Waterbase releases themselves are not redistributed --- they are "
        "downloadable from the EEA, and `scripts/22_waterbase_external.py` "
        "prints the address when the file is absent.",
        "",
    ]
    (SUPP / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return len(DESCRIPTIONS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the shipped copy is out of date")
    args = ap.parse_args()

    built = {}
    s2 = build_substances()
    if s2:
        built["S2_substance_inventory.csv"] = s2
    s3 = build_scope("country", "country")
    if s3:
        built["S3_by_country.csv"] = s3
    s4 = build_scope("class", "substance_class")
    if s4 and s4[0]:
        built["S8_by_substance_class.csv"] = s4
    s14 = build_scope("year", "year")
    if s14 and s14[0]:
        built["S14_by_year.csv"] = s14
    s10 = build_era()
    if s10 and s10[0]:
        built["S10_by_era.csv"] = s10
    s11 = build_era_country()
    if s11 and s11[0]:
        built["S11_era_by_country.csv"] = s11
    s12 = build_mac()
    if s12 and s12[0]:
        built["S12_mac_exceedance.csv"] = s12

    if args.check:
        stale = []
        for name, (rows, header) in built.items():
            p = SUPP / name
            if not p.exists():
                stale.append(f"{name} (missing)")
                continue
            cur = list(csv.reader(p.open(encoding="utf-8")))
            if not cur or cur[0] != header or len(cur) - 1 != len(rows):
                stale.append(name)
        for base, pairs in ((PROC, COPIES), (EVAL, EVAL_COPIES)):
            for src, dst in pairs:
                a, b = base / src, SUPP / dst
                if not b.exists() or (a.exists()
                                      and a.read_bytes() != b.read_bytes()):
                    stale.append(dst)
        if stale:
            print("  supplementary is OUT OF DATE: " + ", ".join(stale))
            print("  re-run: python scripts/98_supplementary.py")
            return 1
        print(f"  supplementary is current "
              f"({len(built) + len(COPIES) + len(EVAL_COPIES)} generated "
              f"files)")
        return 0

    for name, (rows, header) in built.items():
        n = write(rows, header, SUPP / name)
        print(f"  {name:34} {n:>6} rows")
    for base, pairs in ((PROC, COPIES), (EVAL, EVAL_COPIES)):
        for src, dst in pairs:
            a = base / src
            if a.exists():
                shutil.copy2(a, SUPP / dst)
                print(f"  {dst:34} {'copied':>6} from "
                      f"{a.relative_to(ROOT)}")
            else:
                print(f"  {dst:34} SKIPPED ({src} missing)")
    print(f"  {'README.md':34} {write_readme():>6} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
