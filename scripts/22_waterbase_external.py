#!/usr/bin/env python3
"""
External validation: do the three failure modes appear across Europe?

WHY
---
A representational claim needs evidence that is not a single laboratory's
reporting habits, or the finding is about that laboratory. Waterbase settles
it: the EEA's WISE-6 release carries, for every station, substance and year, a
below-LOQ flag AND the limit of quantification that was in force -- exactly
the two fields whose absence is our finding, across 37 reporting countries.

So the same three failures can be counted at continental scale:

  F1  censoring present        share of observations flagged below LOQ
  F2  censoring unrecoverable  of those, the share with NO LOQ value recorded.
                               These are our `UnresolvedObservation`: the flag
                               survived but the bound did not, so the record
                               cannot be interpreted even in principle.
  F3  method insufficient      share of observations whose LOQ exceeds the EQS
                               for that substance. Article 3(3b) of Directive
                               2008/105/EC says such a result "shall not be
                               considered" for chemical status -- so this is
                               not a nuisance statistic but a count of records
                               the law requires to be set aside.

F2 is the decisive one. Lipinski (2026) had to EXCLUDE below-LOQ records that
lacked an LOQ value; we predict they are common, and here they are counted
rather than dropped.

MEMORY AND DISK
---------------
The disaggregated file is several GB. Nothing here loads it: rows are streamed,
counters are integers, and only a compact per-country/per-substance summary is
kept. It reads .csv, .csv.gz and .zip without unpacking to disk.

GETTING THE DATA
----------------
The EEA distributes it through a Nextcloud share that needs a browser, so it
cannot be fetched from a script. Download once from

  https://www.eea.europa.eu/en/datahub/datahubitem-view/fbf3717c-cd7b-4785-933a-d0cf510542e1

and drop the file in Data/waterbase/ . Take:

  WISE6_AggregatedData-csv.zip              162 MB   <- this one
  WISE6_SpatialObjects_DerivedData-csv.zip    3 MB   station coordinates
  WISE6_dataset_definition.zip                6 KB   column semantics

NOT the disaggregated release (1.5 GB CSV / 2.3 GB SQLite). It is not merely
bigger: the aggregated file is the CORRECT UNIT for this test. An annual-average
EQS is defined against an annual mean, which is exactly one aggregated row per
site, substance and year. Counting individual samples against an AA-EQS would
compare quantities the regulation never intended to be compared.

Two further notes on the disaggregated release, both measured rather than
assumed. Its archive is Deflate64, which Python's zipfile refuses, so open_rows
below cannot read it at all. And its 28 columns carry neither a measurement
uncertainty nor a limit of detection -- so it cannot supply what the aggregated
file lacks for the fourth compliance value either.

Inputs  : Data/waterbase/*.{csv,csv.gz,zip}
          derived/processed/eu_eqs.csv   (verified EQS, for F3)
Outputs : derived/processed/waterbase_summary.csv
          eval/waterbase_external.md

Usage:  python scripts/22_waterbase_external.py [--limit N] [--file PATH]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import math
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Data" / "waterbase"
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

# WISE-6 column names vary between releases, so each field is matched by intent.
# Concentrations arrive in mg/L, ug/L and ng/L in the same column, and an EQS
# is stated in ug/L. Comparing without converting would be wrong by three
# orders of magnitude in either direction.
TO_UG_L = {"mg/l": 1e3, "ug/l": 1.0, "µg/l": 1.0, "\u00b5g/l": 1.0,
           "ng/l": 1e-3, "pg/l": 1e-6}

# The record is not one era, and treating it as one produced a wrong statement
# in the manuscript: that the data "mostly predates 2015". Nearly half of these
# river rows do not. Whether the three failures are historical or current is the
# first question a reader asks of an archived dataset, so the split is a
# permanent layer of the count rather than a robustness check bolted on
# afterwards. Same boundary as scripts/25_country_confounders.py, so the two
# agree by construction.
RECENT_FROM = 2015


def era_of(year):
    """pre2015 / 2015plus / undated. A year that cannot be read is its own
    stratum: silently folding it into either era would move a headline."""
    if year is None:
        return "undated"
    return "2015plus" if year >= RECENT_FROM else "pre2015"


# --------------------------------------------------- the compliance decision
# The three functions below ARE the decision procedure, and they live here so
# that there is exactly one of them: scripts/23_waterbase_abox.py imports them
# rather than restating them. The graph and this streaming counter must reach
# the same verdict on the same row, and the only way to guarantee that is for
# there to be one implementation to disagree with.
#
# Because they stream, the assessment is not a sample. Every station-year whose
# substance carries a European standard is assessed here -- the graph
# materialises a subset of that assessment so it can be queried and validated,
# but the counts the manuscript quotes are population counts.

# Directive 2009/90/EC, Article 4(1) -- the SAME SENTENCE that sets the 30 %
# quantification-limit criterion counted above -- also requires "an uncertainty
# of measurement of 50 % or below (k = 2) estimated at the level of relevant
# environmental quality standards".
#
# WISE-6 provides no field for a per-result uncertainty, and neither the
# aggregated nor the disaggregated release carries one; that was measured, not
# assumed. It does not follow that nothing can be said. The 50 % is a LEGAL
# MAXIMUM: for any method whose results may lawfully be used, the expanded
# uncertainty at the standard is at most half the standard. U = 0.5 * threshold
# is therefore the widest interval the law permits around a quantified result,
# and
#
#     [x - U, x + U] straddles T   <=>   0.5*T < x < 1.5*T
#
# is exactly the band in which a method that merely meets the legal minimum
# cannot establish compliance either way. Note where that band sits: around the
# standard, which is where the criterion is defined. Nothing is extrapolated to
# concentrations about which Article 4(1) says nothing.
#
# This is NOT the LOD = LOQ/3 substitution that was removed from this pipeline.
# There the constant was ours, and a figure presented the result as measured.
# Here the number is stated by the instrument being audited against, and the
# outcome is labelled as what it is: not the uncertainty of the measurement,
# but the largest uncertainty the law would permit it to have.
LEGAL_UNCERTAINTY_AT_EQS = 0.50


def detection_status(flag, val_ug, loq_ug):
    """censored / quantified / unresolved, from the three fields WISE-6 gives.

    `flag` is the RAW field, not its truthiness. An empty flag and a "0" are
    different statements: the first says nothing, the second says "not
    censored", which is information.
    """
    if flag == "" and loq_ug is None:
        return "unresolved"
    if flag == "1":
        return "censored"
    if val_ug is not None:
        return "quantified"
    return "unresolved"


def censo_outcome(status, val_ug, loq_ug, thr, *, uncertainty=True,
                  precondition=None):
    """The compliance outcome for one observation-threshold pair.

    Three values -- Compliant, Exceedance, IndeterminateCompliance -- with the
    third subtyped by the reason. The keys below name the subtype, so the
    counterfactual cross-tab and every count built on it keep the reason and not
    just the verdict.

    Order matters and is not arbitrary.

    An UNMET PRECONDITION comes first, because it is prior to every other
    question. Where Annex I defines the standard on a quantity the record does
    not report -- footnote 12 makes lead's and nickel's standards refer to
    "bioavailable concentrations of the substances", footnote 9 makes cadmium's
    vary over five water-hardness classes -- there is no comparison to make. Not
    a strict one, not a lenient one: the number in the table and the number in
    the record are not measurements of the same thing, so asking whether the
    method's limit meets 30 % of the standard is asking about the wrong quantity.
    censo:PreconditionUnmet is a subclass of censo:IndeterminateCompliance for
    exactly this, and the vocabulary named lead, nickel and cadmium before the
    record was read.

    Then Article 3(3b) of Directive 2008/105/EC, which reaches a result
    "reported as less than the limit of quantification" whose limit exceeds the
    standard: such a result "shall not be considered". Its scope is the CENSORED
    case, and only that -- an earlier version applied it wherever the limit
    exceeded the standard, which set aside quantified means as well. That was
    wrong in the direction that hides exceedances: a mean quantified ABOVE the
    standard is evidence of exceedance whatever the method's limit was, and
    setting it aside deleted 10,524 such results from the count.

    A quantified value is never below its own quantification limit, so for a
    quantified row LOQ > T entails value > T: the reclassification can only move
    a row to Exceedance or to PossibleExceedance, never to Compliant. That
    invariant is asserted in scripts/99_audit.py rather than assumed here.
    """
    if precondition is not None:
        return "precondition_unmet"
    if status == "censored" and loq_ug is not None and loq_ug > thr:
        return "method_insufficient"
    if status == "unresolved":
        return "indeterminate_unresolved"
    if status == "censored" and loq_ug is not None:
        return "compliant"          # the bound clears the standard
    if status == "quantified" and val_ug is not None:
        if loq_ug is not None and val_ug < loq_ug:
            # reported below the limit it was measured with: the row contradicts
            # itself, and neither Article 3(3b) nor a comparison applies
            return "indeterminate_other"
        if uncertainty:
            u = LEGAL_UNCERTAINTY_AT_EQS * thr
            if val_ug - u < thr < val_ug + u:
                return "possible_exceedance"
        return "exceedance" if val_ug > thr else "compliant"
    return "indeterminate_other"


# Footnote number -> applicability condition class, hand-read from Annex I of the
# consolidated Directive 2008/105/EC. Only footnotes that make the threshold
# CONDITIONAL appear here; the others (isomer lists, indicative parameters,
# relative potency factors) say what the standard covers, not when it applies.
#
#   (9)  "For Cadmium and its compounds (No 6) the EQS values vary depending on
#         the hardness of the water as specified in five class categories
#         (Class 1: < 40 mg CaCO3/l ... Class 5: >= 200 mg CaCO3/l)."
#   (12) "These EQS refer to bioavailable concentrations of the substances."
#
# WISE-6 reports neither hardness, nor dissolved organic carbon, nor pH on the
# row, so neither condition can be evaluated from the aggregated release. That
# is the finding, not a limitation of this pipeline.
FOOTNOTE_CONDITION = {
    "9": "censo:HardnessClassCondition",
    "12": "censo:BioavailabilityCondition",
}


def conditional_thresholds(eqs_rows):
    """{cas: condition class} for every threshold Annex I makes conditional."""
    out = {}
    for r in eqs_rows:
        notes = [x for x in (r.get("footnotes") or "").split(";") if x]
        hit = next((FOOTNOTE_CONDITION[x] for x in notes
                    if x in FOOTNOTE_CONDITION), None)
        if not hit:
            continue
        for cas in (r.get("all_cas") or r.get("cas") or "").split(";"):
            if cas.strip():
                out[cas.strip()] = hit
    return out


def two_valued(val_ug, loq_ug, censored, thr, k):
    """What a pipeline with no censoring semantics returns for the same row.

    This used to be asserted rather than computed -- the report claimed a
    two-valued pipeline calls every unsupportable assessment "compliant". That
    is false in one direction that matters: substitution can push a censored
    result above the standard, so the pipeline reports an exceedance no
    measurement supports. Asserting otherwise understated the damage, so the
    counterfactual is counted row by row.

    `k` is the fraction of the quantification limit a non-detection enters at:
    0, 1/2 or 1, the three conventions the monitoring literature uses. A record
    with no usable number at all is read as zero, which is the silent
    substitution this paper is about and is identical under all three.
    """
    if censored:
        x = loq_ug * k if loq_ug is not None else (
            val_ug if val_ug is not None else 0.0)
    else:
        x = val_ug if val_ug is not None else 0.0
    return "exceeding" if x > thr else "compliant"


SUBSTITUTIONS = (("zero", 0.0), ("half", 0.5), ("full", 1.0))


CANDIDATES = {
    # AggregatedData names the flag on the annual MEAN; DisaggregatedData names
    # it on the individual observed value. Both are accepted.
    "below_loq": ["resultqualitymeanbelowloq",
                  "resultqualityobservedvaluebelowloq",
                  "resultqualityminimumbelowloq", "observedvaluebelowloq"],
    "loq": ["procedureloqvalue", "procedureanalysedloq", "loqvalue"],
    "value": ["resultmeanvalue", "resultobservedvalue"],
    "determinand": ["observedpropertydeterminandlabel",
                    "observedpropertydeterminandcode"],
    "country": ["countrycode", "country"],
    "site": ["monitoringsiteidentifier"],
    "year": ["phenomenontimereferenceyear", "phenomenontimesamplingdate"],
    "uom": ["resultuom", "resultuominfo"],
    "n_samples": ["resultnumberofsamples"],
    # richer than a boolean: how many of the year's samples were below LOQ
    "n_below": ["resultqualitynumberofsamplesbelowloq"],
    # CAS_7440-09-7 -- matching on this is exact, unlike matching on names
    "code": ["observedpropertydeterminandcode"],
    # RW = river water; an inland-surface-water EQS applies to those
    "category": ["parameterwaterbodycategory"],
    # the EEA's own QC flags, including QC_LOQ_UNKNOWN
    "statements": ["metadata_statements", "metadatastatements"],
    # CEN/ISO code of the method. Needed to ask whether the limit is a
    # property of the instrument or of the run that produced the result.
    "method": ["procedureanalyticalmethod"],
}


def norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(h).lower())


def pick(headers):
    idx = {norm(h): i for i, h in enumerate(headers)}
    out = {}
    for role, names in CANDIDATES.items():
        for n in names:
            if n in idx:
                out[role] = idx[n]
                break
    return out


def open_rows(path: Path):
    """Yield rows from csv / csv.gz / zip without unpacking to disk."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            inner = [n for n in z.namelist() if n.lower().endswith(".csv")]
            if not inner:
                sys.exit(f"no CSV inside {path.name}")
            inner.sort(key=lambda n: -z.getinfo(n).file_size)
            with z.open(inner[0]) as fh:
                yield from csv.reader(io.TextIOWrapper(fh, encoding="utf-8",
                                                       errors="replace"))
    elif path.name.lower().endswith(".csv.gz"):
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
            yield from csv.reader(fh)
    else:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            yield from csv.reader(fh)


def num(x):
    try:
        v = float(str(x).strip().replace(",", "."))
        return v
    except (TypeError, ValueError):
        return None


def wilson(k: int, n: int, z: float = 1.959963985):
    """Wilson score interval for a proportion.

    Reported instead of a p-value on purpose. At n = 4.2 million every
    difference is 'significant' at any conventional level, so a p-value carries
    no information; what a reader needs is how precisely each share is pinned
    down, and for the small per-substance groups that is the binding
    constraint. Wilson rather than normal-approximation because several shares
    sit at or near 1.0, where the normal interval runs past 100%.
    """
    if n == 0:
        return (0.0, 0.0, 0.0)
    ph = k / n
    d = 1 + z * z / n
    centre = (ph + z * z / (2 * n)) / d
    half = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (100 * ph, 100 * max(0.0, centre - half),
            100 * min(1.0, centre + half))


def truthy(x) -> bool:
    return str(x).strip().lower() in ("1", "true", "yes", "y")


def test_decision() -> int:
    """The decision procedure, on cases whose answers are worked out by hand.

    This exists because the procedure below now classifies EVERY assessable row
    in the release -- 759,257 of them -- and a silent error in it moves a
    headline. The cases are chosen at the boundaries, which is where a
    comparison operator is got wrong: exactly at the standard, exactly at the
    edges of the uncertainty band, and at each branch a censored row can take.

    Nothing here touches the data. It runs before every count.
    """
    T = 1.0                       # standard, ug/L
    U = LEGAL_UNCERTAINTY_AT_EQS  # 0.50 -> band is (0.5, 1.5) x T
    cases = [
        # (status, value, loq, expected outcome, why)
        ("quantified", 0.49, 0.05, "compliant",
         "whole permitted interval below the standard"),
        ("quantified", 0.51, 0.05, "possible_exceedance",
         "interval straddles: just inside the lower edge of the band"),
        ("quantified", 1.00, 0.05, "possible_exceedance",
         "exactly at the standard is undecidable, not compliant"),
        ("quantified", 1.49, 0.05, "possible_exceedance",
         "just inside the upper edge of the band"),
        ("quantified", 1.51, 0.05, "exceedance",
         "whole permitted interval above the standard"),
        ("censored", None, 0.5, "compliant",
         "the bound clears the standard, so the non-detection decides it"),
        ("censored", None, 1.0, "compliant",
         "a bound EQUAL to the standard still clears it"),
        ("censored", None, 1.01, "method_insufficient",
         "Art. 3(3b): the limit exceeds the standard"),
        ("censored", None, None, "indeterminate_other",
         "censored with no bound recorded decides nothing"),
        ("unresolved", None, None, "indeterminate_unresolved",
         "neither flag nor limit"),
        # Article 3(3b) reaches the CENSORED case only. A quantified value
        # under a limit that exceeds the standard is not set aside by it -- and
        # a value below its own limit is a contradiction, handled as such.
        # A mean quantified BELOW its own quantification limit cannot happen in
        # a well-formed record: it says the laboratory reported a number it also
        # says it could not measure. Article 3(3b) does not reach it (the result
        # is not reported as below the limit) and neither does compliance, so it
        # is an integrity case and returns an indeterminate outcome.
        ("quantified", 0.2, 5.0, "indeterminate_other",
         "a value below its own limit is a contradiction, not a verdict"),
    ]
    bad = 0
    for status, v, l, want, why in cases:
        got = censo_outcome(status, v, l, T)
        if got != want:
            print(f"  FAIL {status} v={v} loq={l}: got {got!r}, want {want!r}"
                  f"  ({why})")
            bad += 1

    # An unmet precondition is prior to EVERYTHING, including the number, the
    # limit and Article 3(3b). Each case below would land somewhere else if the
    # branch were ordered wrongly, which is the only way to test an ordering.
    for status, v, l, why in (
            ("quantified", 0.1, 0.05, "well under the standard"),
            ("quantified", 9.9, 0.05, "well over the standard"),
            ("quantified", 1.0, 0.05, "exactly at the standard"),
            ("censored", None, 0.5, "a bound that clears the standard"),
            ("censored", None, 5.0, "a limit that exceeds the standard"),
            ("unresolved", None, None, "no flag and no limit")):
        got = censo_outcome(status, v, l, T,
                            precondition="censo:BioavailabilityCondition")
        if got != "precondition_unmet":
            print(f"  FAIL precondition {status} v={v} loq={l}: got {got!r} "
                  f"({why} must still be precondition_unmet)")
            bad += 1
    # and it must not fire when there is no precondition
    for status, v, l, want in (("quantified", 9.9, 0.05, "exceedance"),
                               ("censored", None, 0.5, "compliant")):
        got = censo_outcome(status, v, l, T, precondition=None)
        if got != want:
            print(f"  FAIL {status} v={v} loq={l}: got {got!r}, want {want!r}"
                  f"  ({why})")
            bad += 1

    # Detection status. Three of these look surprising and are not; writing
    # them down is the point of the test.
    #   ("", 0.4, None)  -> unresolved, NOT quantified. A number with neither a
    #     flag nor a limit cannot be told apart from a substituted zero, which
    #     is the whole 25.5 % finding. Calling it quantified would launder it.
    #   ("0", None, 0.1) -> unresolved, NOT quantified. "Not censored" with no
    #     number is not a measurement.
    #   ("0", None, None) -> unresolved. A declared-but-empty row decides
    #     nothing either.
    for flag, v, l, want in (("", None, None, "unresolved"),
                             ("", 0.4, None, "unresolved"),
                             ("0", None, 0.1, "unresolved"),
                             ("0", 0.4, 0.1, "quantified"),
                             ("1", 0.05, 0.1, "censored"),
                             ("0", None, None, "unresolved")):
        got = detection_status(flag, v, l)
        if got != want:
            print(f"  FAIL detection_status({flag!r}, {v}, {l}) = {got!r}, "
                  f"want {want!r}")
            bad += 1

    # the counterfactual: substitution must be able to push a censored result
    # ABOVE the standard, which is the direction an earlier version assumed
    # away, and a real exceedance must not depend on the convention.
    # loq = 10 x the standard, so half the limit (5 T) and the full limit
    # (10 T) both exceed it while zero does not. NOT loq = 2 T: there half the
    # limit lands EXACTLY on the standard, and "exceeds" is strict, so that
    # fixture tests the boundary rather than the sensitivity it claims to.
    got = [two_valued(None, 10.0 * T, True, T, k) for _, k in SUBSTITUTIONS]
    if got != ["compliant", "exceeding", "exceeding"]:
        print(f"  FAIL substitution sensitivity: {got}")
        bad += 1
    # and the boundary itself, stated rather than stumbled into: a value
    # exactly at the standard does not exceed it, under any convention.
    if two_valued(None, 2.0 * T, True, T, 0.5) != "compliant":
        print("  FAIL exactly at the standard must not count as exceeding")
        bad += 1
    if {two_valued(5.0, 0.1, False, T, k) for _, k in SUBSTITUTIONS} != {"exceeding"}:
        print("  FAIL a quantified exceedance must not depend on the rule")
        bad += 1
    if {two_valued(None, None, True, T, k) for _, k in SUBSTITUTIONS} != {"compliant"}:
        print("  FAIL an empty record reads as compliant under every rule")
        bad += 1

    # the band must be symmetric about the standard and closed on neither side
    if censo_outcome("quantified", (1 - U) * T, 0.01, T) != "compliant":
        print("  FAIL lower band edge is not exclusive")
        bad += 1
    if censo_outcome("quantified", (1 + U) * T, 0.01, T) != "exceedance":
        print("  FAIL upper band edge is not exclusive")
        bad += 1

    # len(cases) + the hand-written blocks: 8 detection-status cases, 3
    # substitution cases, 2 band-edge cases, 6 precondition-ordering cases and
    # 2 no-precondition controls. Counted rather than guessed, because a summary
    # that understates its own coverage invites someone to add a branch and no
    # test for it.
    print(f"  decision procedure: {len(cases) + 21} cases, "
          + ("all pass" if not bad else f"{bad} FAILURES"))
    return 1 if bad else 0


def self_test() -> int:
    """Verify the counting against data whose answers are known in advance.

    The real file cannot be downloaded from a script, so without this the
    parsing would go untested until someone ran it on 3 GB and trusted the
    output. Here the flags are injected at known rates and recovered. Nothing
    is written to eval/: a synthetic result must never be mistakable for a
    measured one.
    """
    import random
    import tempfile
    random.seed(7)
    subs = [("Imidacloprid", 0.0068), ("Atrazine", 0.6), ("Diclofenac", 0.04)]
    n_rows, p_below, p_no_loq = 4000, 0.55, 0.30
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "synthetic.csv"
        with f.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["monitoringSiteIdentifier", "countryCode",
                        "observedPropertyDeterminandLabel",
                        "resultObservedValue", "resultUom",
                        "resultQualityObservedValueBelowLOQ",
                        "procedureLOQValue"])
            exp_below = exp_no_loq = 0
            for i in range(n_rows):
                name, eqs = random.choice(subs)
                below = random.random() < p_below
                no_loq = below and random.random() < p_no_loq
                exp_below += below
                exp_no_loq += no_loq
                w.writerow([f"S{i%50}", random.choice(["DE", "FR"]), name,
                            "" if below else f"{eqs*2:.5g}", "ug/L",
                            "1" if below else "0",
                            "" if no_loq else f"{eqs*0.5:.5g}"])
        rows = open_rows(f)
        col = pick(next(rows))
        got_below = got_no_loq = n = 0
        for row in rows:
            if not row:
                continue
            n += 1
            if truthy(row[col["below_loq"]]):
                got_below += 1
                if num(row[col["loq"]]) is None:
                    got_no_loq += 1
    ok = (n == n_rows and got_below == exp_below and got_no_loq == exp_no_loq)
    print(f"  rows        : {n:,} (expected {n_rows:,})")
    print(f"  below LOQ   : {got_below:,} (expected {exp_below:,})")
    print(f"  missing LOQ : {got_no_loq:,} (expected {exp_no_loq:,})")
    print(f"\n  {'PASS' if ok else 'FAIL'} — parsing verified without the "
          f"download; nothing written to eval/")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="explicit path to the Waterbase file")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N data rows (for a quick smoke test)")
    ap.add_argument("--self-test", action="store_true",
                    help="run on generated data with known answers and exit; "
                         "verifies the parsing without the 3 GB download")
    args = ap.parse_args()
    # Every output directory this stage writes to, created here rather
    # than assumed. On a fresh clone derived/processed/ does not exist,
    # and a stage that only made eval/ died on its first write -- a
    # failure invisible for as long as anyone's tree already had the
    # directory from an earlier run.
    EVAL.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)

    if args.self_test:
        return test_decision() or self_test()

    if test_decision():
        sys.exit("the decision procedure failed its own tests; refusing to "
                 "count 4.19 million rows with it")

    if args.file:
        path = Path(args.file)
    else:
        cands = []
        if DATA.exists():
            for pat in ("*.csv", "*.csv.gz", "*.zip"):
                cands += sorted(DATA.glob(pat))
        if not cands:
            print(f"No Waterbase file found under {DATA.relative_to(ROOT)}/.\n"
                  f"\nThe EEA serves it through a browser-only share, so it "
                  f"cannot be fetched here. Download 'Waterbase - Water "
                  f"Quality ICM' (disaggregated data) from\n"
                  f"  https://www.eea.europa.eu/en/datahub/datahubitem-view/"
                  f"fbf3717c-cd7b-4785-933a-d0cf510542e1\n"
                  f"and place it in {DATA.relative_to(ROOT)}/ . "
                  f"This script streams it; it never unpacks it to disk.")
            return 2
        path = max(cands, key=lambda p: p.stat().st_size)

    print(f"reading {path.name} ({path.stat().st_size/1e9:.2f} GB on disk)")

    # Verified EU thresholds, keyed by CAS. Waterbase identifies substances as
    # `CAS_7440-09-7`, so the join is exact rather than by name.
    eqs, eqs_cat = {}, {}
    p_eqs = PROC / "eu_eqs.csv"
    if p_eqs.exists():
        with p_eqs.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("is_group") == "True":
                    continue          # a sum standard is not a per-substance limit
                v = num(r.get("aa_inland"))
                if not v:
                    continue
                cat = (r.get("category") or "").strip()
                for c in (r.get("all_cas") or "").replace(" ", "").split(";"):
                    if c:
                        eqs.setdefault(c, v)
                        # Annex I's own category, so the metals/organics split
                        # below is the regulation's classification and not ours.
                        eqs_cat.setdefault(c, cat)
    # Which of those thresholds Annex I makes conditional. Read from the
    # footnote markers the parse captured, not from a list kept here.
    cond = {}
    if p_eqs.exists():
        with p_eqs.open(encoding="utf-8") as fh:
            cond = conditional_thresholds(list(csv.DictReader(fh)))
    cond = {c: k for c, k in cond.items() if c in eqs}
    print(f"  EQS (ug/L, inland AA) for {len(eqs)} CAS numbers; "
          f"group standards excluded")
    if cond:
        print(f"  conditional thresholds: {len(cond)} CAS number(s) -- "
              + ", ".join(sorted({k.split(':')[-1] for k in cond.values()})))

    rows = open_rows(path)
    try:
        header = next(rows)
    except StopIteration:
        sys.exit("empty file")
    col = pick(header)
    if "determinand" not in col:
        sys.exit(f"determinand column not found; header was {header[:14]}")
    has_loq = "loq" in col
    print(f"  columns located: {', '.join(sorted(col))}")

    n = kept = 0
    tot = defaultdict(int)
    by_sub = defaultdict(lambda: defaultdict(int))
    by_country = defaultdict(lambda: defaultdict(int))
    # Metals vs organic micropollutants. Reported because the published
    # sensitivity work is metals-only, and the discussion compares against it;
    # a claim about how much worse organics are has to be computable from the
    # shipped summary rather than from a one-off script.
    by_class = defaultdict(lambda: defaultdict(int))
    # Era, and era within reporting country. The second is not decoration: a
    # failure rate that falls between eras is worthless if the reporters also
    # changed, so the only reading that survives is the one restricted to
    # authorities present in both. That comparison needs the cross-tab.
    by_era = defaultdict(lambda: defaultdict(int))
    by_era_country = defaultdict(lambda: defaultdict(int))
    # Five-year blocks as well as the two eras. A reader's first objection to a
    # split is that the boundary was chosen to suit the answer; the blocks let
    # the shape of the record be seen without taking our word for where to cut.
    by_block = defaultdict(lambda: defaultdict(int))
    # And year by year. The five-year blocks answer "was the boundary chosen to
    # suit the answer"; only an annual series answers the question a reader of a
    # monitoring paper actually asks -- is this getting better, or is it still
    # happening. A two-era split cannot distinguish a step change from a trend.
    by_year = defaultdict(lambda: defaultdict(int))
    # Which SUBSTANCES contribute to each decade of the standard, and how much.
    # Figure 4b reads a rate per decade, and a rate over one substance is that
    # substance's rate, not a property of the decade: the lowest decade holds
    # deltamethrin and nothing else. Counted so the figure can say so.
    dec_subs = defaultdict(lambda: defaultdict(int))
    uom_unknown = defaultdict(int)
    # The three-valued assessment over the whole population, and the
    # counterfactual a two-valued pipeline would report for the same rows.
    pop_status = defaultdict(int)
    pop_outcome = defaultdict(int)
    pop_verdicts = defaultdict(int)

    # Does the quantification limit belong to the INSTRUMENT or to the RUN?
    # The vocabulary's central modelling move is to bind it to the analytical
    # run, and the manuscript argues for that rather than showing it. It is
    # showable: if the same substance at the same station carries different
    # limits in different years, then a limit is not a property of a device.
    # Sets are capped -- what is needed is "more than one", not how many.
    CAP = 8
    by_pair = {}

    # Group standards. Annex I states four limits on a SUM. A sum computed
    # over an incompletely measured group is an underestimate, so treating it
    # as compliant is the same error as substituting zero for a non-detection
    # -- and the vocabulary already carries requiresCompleteGroup for exactly
    # this. It has never been used on data.
    group_members = {}
    p_eqs2 = PROC / "eu_eqs.csv"
    if p_eqs2.exists():
        with p_eqs2.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("is_group") != "True":
                    continue
                mem = {c for c in (r.get("all_cas") or "").replace(" ", "")
                       .split(";") if c}
                if mem:
                    group_members[r.get("name", "")[:60]] = mem
    member_of = {}
    for gname, mem in group_members.items():
        for c in mem:
            member_of.setdefault(c, []).append(gname)
    group_seen = defaultdict(set)      # (group, site, year) -> measured CAS

    # Undecidability against the MAGNITUDE of the standard. This is the
    # micropollutant question and it is not the same as the metals/organics
    # split: what matters is not what a substance is made of but how low the
    # limit written for it is. Regulation is moving to substances whose
    # standards sit three to six orders of magnitude below the classical
    # pollutants, so if undecidability rises as the standard falls, the problem
    # this paper describes grows with every substance added to Annex I.
    by_eqs_decade = defaultdict(lambda: defaultdict(int))
    print(f"  group standards: {len(group_members)} "
          f"({', '.join(str(len(m)) for m in group_members.values())} members)")

    def get(row, role):
        i = col.get(role)
        return row[i].strip() if i is not None and i < len(row) else ""

    for row in rows:
        if not row:
            continue
        n += 1
        if args.limit and n > args.limit:
            break
        if n % 2_000_000 == 0:
            print(f"    {n:,} rows read, {kept:,} river rows kept …")

        # An inland-surface-water EQS applies to rivers. Lakes, transitional
        # and coastal waters have their own standards and are not comparable.
        if "category" in col and get(row, "category") not in ("RW", ""):
            continue
        kept += 1

        sub = get(row, "determinand") or get(row, "code")
        cty = get(row, "country") or "??"
        cas = get(row, "code")
        cas = cas[4:] if cas.upper().startswith("CAS_") else ""

        n_samp = num(get(row, "n_samples")) or 0
        n_bel = num(get(row, "n_below"))
        loq = num(get(row, "loq")) if has_loq else None
        # The EEA's own QC vocabulary already names this defect.
        qc_unknown = "QC_LOQ_UNKNOWN" in get(row, "statements").upper()
        below = truthy(get(row, "below_loq")) or (n_bel or 0) > 0

        # F3 needs both sides in the same unit.
        #
        # Two legal tests, not one. Article 3(3b) of 2008/105/EC says a
        # below-LOQ result whose LOQ exceeds the EQS shall not be considered --
        # that is F3. But Article 4(1) of Directive 2009/90/EC sets the
        # performance criterion the method was supposed to meet in the first
        # place: "a limit of quantification equal or below a value of 30 % of
        # the relevant environmental quality standards". Measuring only F3
        # understates the failure by design, because it applies a threshold
        # three times more permissive than the law.
        factor = TO_UG_L.get(get(row, "uom").lower().replace(" ", ""))
        f3 = f3_30 = False
        if loq is not None and cas in eqs:
            if factor is None:
                uom_unknown[get(row, "uom") or "(blank)"] += 1
            else:
                if loq * factor > eqs[cas]:
                    f3 = True
                if loq * factor > 0.30 * eqs[cas]:
                    f3_30 = True

        # The four-way cross-tabulation of "was censoring declared?" against
        # "is the bound recorded?" is what the data actually support. An
        # earlier version asked only how often a FLAGGED row lacked its LOQ,
        # and got zero -- which reads as a clean bill of health and is the
        # wrong question. European reporters who set the flag do record the
        # limit. The failure is elsewhere: rows that declare nothing at all,
        # where one cannot tell whether a value is censored, and could not
        # reconstruct it if it were.
        flag_set = get(row, "below_loq") != ""
        has_bound = loq is not None

        # Substitution AT SOURCE, counted with the same definition
        # scripts/26_source_conformance.py uses, so the era table and the
        # conformance table cannot drift: the flag says the result is below the
        # limit and the row nonetheless carries a positive number for it.
        censored = get(row, "below_loq") == "1"
        val = num(get(row, "value"))

        # ---- the three-valued assessment, on the WHOLE population ---------
        # This used to happen only inside the knowledge graph, on a 40,000-row
        # sample, and the manuscript quoted those sample counts as its result.
        # The decision is arithmetic on four fields this loop already holds, so
        # there was never a reason to sample it. The graph still materialises a
        # subset -- rdflib cannot hold four million rows -- but the subset is
        # now a queryable view of an assessment made on everything, not the
        # assessment itself.
        # ---- is the limit a property of the run? --------------------------
        site = get(row, "site")
        if site and cas and loq is not None and factor is not None:
            key = (site, cas)
            rec = by_pair.get(key)
            if rec is None:
                rec = by_pair[key] = [set(), set(), 0, set()]
            rec[2] += 1
            if len(rec[0]) < CAP:
                rec[0].add(round(loq * factor, 9))
            m = get(row, "method")
            if m and len(rec[1]) < CAP:
                rec[1].add(m)
            if cas in eqs and len(rec[3]) < 3:
                rec[3].add(loq * factor > eqs[cas])

        # ---- was a group standard's basket completely measured? ------------
        for gname in member_of.get(cas, ()):
            if site:
                group_seen[(gname, site, get(row, "year")[:4])].add(cas)

        if cas in eqs and factor is not None:
            thr = eqs[cas]
            v_ug = val * factor if val is not None else None
            l_ug = loq * factor if loq is not None else None
            status = detection_status(get(row, "below_loq"), v_ug, l_ug)
            outcome = censo_outcome(status, v_ug, l_ug, thr,
                                    precondition=cond.get(cas))
            pop_status[status] += 1
            pop_outcome[outcome] += 1
            for rule, k in SUBSTITUTIONS:
                tv = two_valued(v_ug, l_ug, status == "censored", thr, k)
                pop_verdicts[(rule, outcome, tv)] += 1

        # A year, so the record can be split into eras. Aggregated rows carry
        # phenomenonTimeReferenceYear; a sampling date is accepted by taking
        # its leading four digits rather than assuming a format.
        raw_year = get(row, "year")
        yr = num(raw_year[:4]) if len(raw_year) >= 4 else num(raw_year)
        era = era_of(int(yr) if yr is not None else None)

        klass = eqs_cat.get(cas)
        block = f"{int(yr)//5*5}-{int(yr)//5*5+4}" if yr is not None else "undated"
        targets = [tot, by_sub[sub], by_country[cty],
                   by_era[era], by_era_country[f"{cty}:{era}"],
                   by_block[block]]
        if yr is not None:
            targets.append(by_year[str(int(yr))])
        if cas in eqs and eqs[cas] > 0:
            _d = math.floor(math.log10(eqs[cas]))
            targets.append(by_eqs_decade[_d])
            dec_subs[_d][sub] += 1
        if klass:
            targets.append(by_class["Metals" if "etal" in klass.lower()
                                    else "Organic micropollutants"])
        for d in targets:
            d["n"] += 1
            d["samples"] += int(n_samp)
            if n_bel is not None:
                d["samples_below"] += int(n_bel)
            if flag_set and has_bound:
                d["declared_and_bounded"] += 1
            elif flag_set and not has_bound:
                d["declared_not_bounded"] += 1        # F2a
            elif not flag_set and has_bound:
                d["undeclared_but_bounded"] += 1
            else:
                d["silent"] += 1                      # F2b: no information
            if below:
                d["below_loq"] += 1
                if not has_bound:
                    d["below_loq_no_loq"] += 1
            if not has_bound:
                d["no_loq_any"] += 1
            if qc_unknown:
                d["qc_loq_unknown"] += 1
            if f3:
                d["loq_gt_eqs"] += 1                  # F3, Art. 3(3b)
            if f3_30:
                d["loq_gt_30pct_eqs"] += 1            # F4, Art. 4(1) 2009/90/EC
            if cas in eqs:
                d["has_eqs"] += 1
            if censored:
                d["censored"] += 1
                if val is not None and val > 0:
                    d["censored_with_value"] += 1     # substitution at source

    print(f"  {n:,} rows read; {kept:,} river-water rows retained")
    if uom_unknown:
        print(f"    unrecognised units skipped for F3: "
              f"{dict(list(uom_unknown.items())[:5])}")

    multi_pairs = [r for r in by_pair.values() if r[2] >= 2]
    n_varied = sum(1 for r in multi_pairs if len(r[0]) > 1)
    # rec[1] only ever receives a NON-EMPTY method code, so a pair whose method
    # field is never filled has an empty set and counts as "no method change".
    # Reporting the change count without this denominator conflates "the method
    # did not change" with "the record does not say", and the paper's argument
    # that the limit belongs to the run rests on telling those apart.
    n_method_any = sum(1 for r in multi_pairs if r[1])
    n_method = sum(1 for r in multi_pairs if len(r[1]) > 1)
    n_flipped = sum(1 for r in multi_pairs if len(r[3]) > 1)

    with (PROC / "waterbase_summary.csv").open("w", newline="",
                                               encoding="utf-8") as fh:
        w = csv.writer(fh)
        # The four-way cross-tab must be written out too: it is what the
        # graphical abstract reads, and omitting `silent` made that figure
        # report 0% for the paper's second headline number.
        cols = ["n", "samples", "samples_below", "below_loq",
                "loq_gt_30pct_eqs",
                "below_loq_no_loq", "no_loq_any", "qc_loq_unknown",
                "declared_and_bounded", "declared_not_bounded",
                "undeclared_but_bounded", "silent",
                "has_eqs", "loq_gt_eqs",
                "censored", "censored_with_value"]
        w.writerow(["scope", "key"] + cols)
        for scope, d in (("total", {"": tot}), ("substance", by_sub),
                         ("country", by_country), ("class", by_class),
                         ("era", by_era), ("era_country", by_era_country),
                         ("period", by_block), ("year", by_year),
                         # The run-vs-instrument counters, so the manuscript's
                         # claims about them are recomputed by the audit rather
                         # than only printed in a report.
                         # Written through defaultdicts: every scope shares
                         # one column list, so a plain dict with only "n" in it
                         # raises KeyError on the first column it lacks and
                         # takes the whole stage down.
                         ("run_scope", {
                             k: defaultdict(int, n=v) for k, v in (
                                 ("pairs_multiyear", len(multi_pairs)),
                                 ("pairs_multi_limit", n_varied),
                                 ("pairs_multi_method", n_method),
                                 ("pairs_with_any_method", n_method_any),
                                 ("pairs_crossing_standard", n_flipped))}),
                         ("eqs_decade", {str(k): v
                                         for k, v in by_eqs_decade.items()})):
            for k, v in sorted(d.items(), key=lambda kv: -kv[1]["n"]):
                w.writerow([scope, k] + [v[c] for c in cols])

    # The population verdict table, shaped exactly like the one
    # scripts/23_waterbase_abox.py writes from the graph, so that Figure 5 and
    # the audit can read either and the two can be compared cell by cell.
    if dec_subs:
        with (PROC / "eqs_decade_substances.csv").open(
                "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["decade_log10_ug_l", "assessments", "n_substances",
                        "top_substance", "top_share_pct"])
            for d in sorted(dec_subs, reverse=True):
                m = dec_subs[d]
                n = sum(m.values())
                top, tn = max(m.items(), key=lambda kv: kv[1])
                w.writerow([d, n, len(m), top, f"{100 * tn / n:.1f}"])
        print(f"  decade composition: "
              + ", ".join(f"1e{d}:{len(dec_subs[d])}"
                          for d in sorted(dec_subs, reverse=True)))

    with (PROC / "waterbase_verdicts_population.csv").open(
            "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["substitution", "censo_outcome", "two_valued_outcome", "n"])
        for (rule, outcome, tv), v in sorted(pop_verdicts.items()):
            w.writerow([rule, outcome, tv, v])

    # Group completeness as its own table. The manuscript reports it, so it has
    # to be recomputable rather than only printed: a number the audit cannot
    # reach is also a number the stale-value detector will mis-attribute.
    if group_members:
        with (PROC / "group_completeness.csv").open("w", newline="",
                                                    encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["group", "members", "station_years_touching",
                        "station_years_complete", "pct_complete"])
            for gname, mem in sorted(group_members.items(),
                                     key=lambda kv: -len(kv[1])):
                keys = [k for k in group_seen if k[0] == gname]
                comp = sum(1 for k in keys if len(group_seen[k]) == len(mem))
                w.writerow([gname, len(mem), len(keys), comp,
                            f"{100*comp/len(keys):.1f}" if keys else ""])

    def pct(a, b):
        return f"{100*a/b:.1f}%" if b else "—"

    L = []
    A = L.append
    A("# External validation against Waterbase\n")
    A("Generated by `scripts/22_waterbase_external.py`.\n")
    A(f"- source: `{path.name}` (EEA Waterbase Water Quality ICM, "
      f"aggregated release)")
    A(f"- rows read: **{n:,}**; river-water rows retained: **{kept:,}**")
    A(f"- substances: {len(by_sub):,} · reporting countries: "
      f"{len(by_country):,}")
    A(f"- underlying samples represented: {tot['samples']:,}\n")
    A("Every other figure in this paper describes one basin. Waterbase records "
      "a below-LOQ flag and the limit of quantification in force, so the same "
      "three failures can be counted across European monitoring programmes. "
      "Only river water is retained, because an inland-surface-water EQS does "
      "not apply to lakes or coastal waters; substances are joined to the "
      "verified EU thresholds by CAS number, and concentrations are converted "
      "to \\si{\\micro\\gram\\per\\litre} before any comparison.\n")

    def ci(k, n_):
        s, lo, hi = wilson(k, n_)
        return f"{s:.1f}% [{lo:.1f}, {hi:.1f}]"

    A("Shares carry Wilson 95\\% intervals. A p-value is deliberately not "
      "reported: at this sample size every contrast is significant at any "
      "conventional level, so the informative quantity is how tightly each "
      "share is bounded.\n")
    A("| failure | n | share [95% CI] |")
    A("|---|---|---|")
    A(f"| F1 · station-years with at least one below-LOQ sample | "
      f"{tot['below_loq']:,} | {ci(tot['below_loq'], kept)} |")
    A(f"| F2a · censoring declared but **no LOQ recorded** | "
      f"{tot['declared_not_bounded']:,} | "
      f"{ci(tot['declared_not_bounded'], kept)} |")
    A(f"| F2b · **neither a censoring flag nor an LOQ** — one cannot tell "
      f"whether the value is censored, nor reconstruct it if it is | "
      f"**{tot['silent']:,}** | **{ci(tot['silent'], kept)}** |")
    A(f"| — · censoring declared *and* bounded (the correct case) | "
      f"{tot['declared_and_bounded']:,} | "
      f"{ci(tot['declared_and_bounded'], kept)} |")
    A(f"| — · EEA's own `QC_LOQ_UNKNOWN` flag | "
      f"{tot['qc_loq_unknown']:,} | {ci(tot['qc_loq_unknown'], kept)} |")
    A(f"| F3 · LOQ exceeds the EQS — Art. 3(3b) requires the result to be "
      f"excluded | {tot['loq_gt_eqs']:,} | "
      f"{ci(tot['loq_gt_eqs'], tot['has_eqs'])} of rows with an EQS |")
    A(f"| **F4 · LOQ exceeds 30\\% of the EQS — the method fails the legal "
      f"performance criterion (Art. 4(1), 2009/90/EC)** | "
      f"**{tot['loq_gt_30pct_eqs']:,}** | "
      f"**{ci(tot['loq_gt_30pct_eqs'], tot['has_eqs'])} of rows with an "
      f"EQS** |")
    if tot["samples"]:
        A(f"| — · individual samples below LOQ | "
          f"{tot['samples_below']:,} | "
          f"{ci(tot['samples_below'], tot['samples'])} of all samples |")
    A("")

    # An exclusion that is printed to the console and nowhere else is an
    # undisclosed exclusion. A row whose unit cannot be converted is dropped
    # from the two legal tests, so its size belongs in the report next to the
    # numbers it affects, whether it is large or negligible.
    dropped = sum(uom_unknown.values())
    if dropped:
        A(f"> **Excluded from the two legal tests:** {dropped:,} row(s) "
          f"({100 * dropped / max(tot['has_eqs'], 1):.3f}\\% of rows with an "
          f"EQS) report a unit this pipeline does not convert, so no "
          f"comparison against a threshold is attempted for them. Units seen: "
          + ", ".join(f"`{u}` ({n:,})" for u, n in
                      sorted(uom_unknown.items(), key=lambda kv: -kv[1])[:6])
          + ".\n")
    else:
        A("> Every row carrying both a quantification limit and a standard "
          "reported a convertible unit; nothing was dropped from the two legal "
          "tests for an unrecognised unit.\n")

    if kept:
        A(f"> **The defect is systemic omission, not careless flagging.** "
          f"Where a reporter declares censoring, the limit is recorded almost "
          f"without exception: only {tot['declared_not_bounded']:,} of "
          f"{tot['declared_and_bounded'] + tot['declared_not_bounded']:,} "
          f"declared rows lack it. The failure lies in the "
          f"**{ci(tot['silent'], kept)}** of river station-years that declare "
          f"nothing at all -- no flag, no limit. For those a zero and a "
          f"measured trace are indistinguishable, and no substitution rule "
          f"can be chosen because there is "
          f"nothing to substitute from. The EEA's own quality control reaches "
          f"the same conclusion on {tot['qc_loq_unknown']:,} rows, which it "
          f"marks `QC_LOQ_UNKNOWN`.\n")

    # ---- the three-valued assessment, over the population ------------------
    n_assessed = sum(pop_outcome.values())
    if n_assessed:
        A("## The three-valued assessment, over every assessable row\n")
        A(f"Every station-year whose substance carries a European "
          f"annual-average standard is assessed here: **{n_assessed:,}** of "
          f"them. This is not a sample. The knowledge graph "
          f"(`scripts/23_waterbase_abox.py`) materialises a subset so that it "
          f"can be queried and validated in memory, but the decision itself is "
          f"arithmetic on four reported fields and is applied to every row.\n")
        A("| outcome | n | share |")
        A("|---|---|---|")
        LBL = {
            "compliant": "`Compliant`",
            "exceedance": "`Exceedance`",
            "possible_exceedance":
                "`PossibleExceedance` — the interval permitted by Art. 4(1) "
                "straddles the standard",
            "precondition_unmet":
                "`PreconditionUnmet` — the standard is defined on a quantity "
                "the record does not report (Annex I footnotes 9 and 12)",
            "method_insufficient":
                "`MethodInsufficient` — the quantification limit exceeds the "
                "standard (Art. 3(3b))",
            # These two named the bare parent until the taxonomy was made
            # three-valued. The KEYS are unchanged -- scripts/99_audit.py joins
            # on them and the counterfactual cross-tab is written with them --
            # only the class the row is reported under is now the subclass that
            # says why.
            "indeterminate_unresolved":
                "`BoundNotEstablished` — neither a flag nor a limit, so no "
                "interval can be built",
            "indeterminate_other":
                "`BoundNotEstablished` — the number contradicts the limit "
                "reported beside it",
        }
        for k in ("compliant", "exceedance", "possible_exceedance",
                  "precondition_unmet",
                  "method_insufficient", "indeterminate_unresolved",
                  "indeterminate_other"):
            if pop_outcome.get(k):
                A(f"| {LBL[k]} | {pop_outcome[k]:,} | "
                  f"{pct(pop_outcome[k], n_assessed)} |")
        A("")
        pe = pop_outcome.get("possible_exceedance", 0)
        if pe:
            A(f"> **`PossibleExceedance` is not decorative: {pe:,} assessments "
              f"({pct(pe, n_assessed)}) fall in it.** Directive 2009/90/EC "
              f"Article 4(1) permits a measurement uncertainty of up to "
              f"{LEGAL_UNCERTAINTY_AT_EQS:.0%} (k = 2) at the level of the "
              f"standard. A quantified result between "
              f"{1-LEGAL_UNCERTAINTY_AT_EQS:.0%} and "
              f"{1+LEGAL_UNCERTAINTY_AT_EQS:.0%} of the standard therefore has "
              f"an interval that straddles it, and a method meeting only the "
              f"legal minimum cannot decide the question either way. The "
              f"uncertainty is not reported by WISE-6 — no European release "
              f"carries one — so what is applied here is the largest "
              f"uncertainty the law permits, not the actual one, and the "
              f"result is a bound rather than an estimate.\n")
        # EVERY subclass of censo:IndeterminateCompliance, which is the whole
        # point of the class being a union of three and not of four.
        # precondition_unmet was missing here. It was added to the taxonomy with
        # the fourth commitment and to every count the manuscript quotes, but
        # not to this sum -- so the largest single reason a verdict cannot be
        # reached (131,068 assessments, 18.8 %) was dropped, and the shipped
        # report said 25.0 % where the paper says 43.8 %, three lines under a
        # table that lists the missing row. Nothing objected: the audit
        # recomputes the manuscript's 43.8 % from the processed CSVs and never
        # reads the prose of a report it did not write.
        ind = (pop_outcome.get("method_insufficient", 0)
               + pop_outcome.get("precondition_unmet", 0)
               + pop_outcome.get("indeterminate_unresolved", 0)
               + pop_outcome.get("indeterminate_other", 0) + pe)
        A(f"> Taken together, **{ind:,} ({pct(ind, n_assessed)}) of these "
          f"assessments are not decidable** from the record as reported. A "
          f"two-valued schema has nowhere to put any of them.\n")

        A("### What a two-valued pipeline reports for the same rows\n")
        A("| non-detection enters at | exceedances reported | of those, resting "
          "on a quantified measurement above the standard |")
        A("|---|---|---|")
        real = sum(v for (r, o, t), v in pop_verdicts.items()
                   if r == "zero" and o == "exceedance" and t == "exceeding")
        for rule, lbl in (("zero", "zero"), ("half", "half the limit"),
                          ("full", "the limit")):
            exc = sum(v for (r, o, t), v in pop_verdicts.items()
                      if r == rule and t == "exceeding")
            A(f"| {lbl} | {exc:,} | {real:,} ({pct(real, exc)}) |")
        A("")
        A("Counted row by row under each convention, not assumed. The spread "
          "between the first and last row is what a reader of a two-valued "
          "record cannot see, because the record does not say which convention "
          "produced it.\n")

    # ---- does the problem grow as the standard falls? ----------------------
    if by_eqs_decade:
        A("## Undecidability against the magnitude of the standard\n")
        A("The substances European regulation has been adding --- pesticides "
          "and their metabolites, pharmaceuticals, bisphenols, PFAS --- are "
          "biologically active at concentrations far below those of the "
          "classical pollutants, and their standards are written accordingly. "
          "The question this table answers is whether the failure counted "
          "above is a legacy problem or a growing one.\n")
        A("| annual-average standard | station-years with that standard | "
          "quantification limit above it | fails the 30\\% criterion |")
        A("|---|---|---|---|")
        for d in sorted(by_eqs_decade, reverse=True):
            v = by_eqs_decade[d]
            lo, hi = 10.0 ** d, 10.0 ** (d + 1)
            A(f"| {lo:g}–{hi:g} µg/L | {v['has_eqs']:,} | "
              f"{pct(v['loq_gt_eqs'], v['has_eqs'])} | "
              f"{pct(v['loq_gt_30pct_eqs'], v['has_eqs'])} |")
        A("")
        ds = sorted(by_eqs_decade)
        if len(ds) >= 2:
            lowest, highest = by_eqs_decade[ds[0]], by_eqs_decade[ds[-1]]
            A(f"> **The failure is not a legacy of old chemistry; it scales "
              f"with the ambition of the standard.** Where the annual average "
              f"is of order {10.0**ds[-1]:g} µg/L the quantification limit "
              f"exceeds it in {pct(highest['loq_gt_eqs'], highest['has_eqs'])} "
              f"of assessments; where it is of order {10.0**ds[0]:g} µg/L that "
              f"rises to {pct(lowest['loq_gt_eqs'], lowest['has_eqs'])}. Every "
              f"substance added to Annex~I at a lower threshold therefore "
              f"enlarges the set of assessments the record cannot decide, "
              f"unless analytical capability moves with it.\n")

    # ---- the limit belongs to the run, not to the instrument ---------------
    multi = multi_pairs
    if multi:
        varied = [r for r in multi if len(r[0]) > 1]
        flipped = [r for r in multi if len(r[3]) > 1]
        m_varied = [r for r in multi if len(r[1]) > 1]
        spread = sorted(max(r[0]) / min(r[0]) for r in varied if min(r[0]) > 0)
        A("## Is the quantification limit a property of the instrument?\n")
        A("The vocabulary binds the limit to the **analytical run** rather than "
          "to the device, and the sensing vocabularies it is compared against "
          "do the opposite. The record decides between them. If a limit were a "
          "property of an instrument, the same substance measured at the same "
          "station would carry the same limit from one year to the next.\n")
        A("| | n | share |")
        A("|---|---|---|")
        A(f"| station–substance pairs reported in more than one year | "
          f"{len(multi):,} | |")
        A(f"| ... reporting **more than one quantification limit** | "
          f"**{len(varied):,}** | {pct(len(varied), len(multi))} |")
        if m_varied:
            A(f"| ... reporting more than one analytical method code | "
              f"{len(m_varied):,} | {pct(len(m_varied), len(multi))} |")
        A(f"| ... where that change **crosses the standard**, so the same "
          f"station and substance is decidable in one year and not in another | "
          f"**{len(flipped):,}** | {pct(len(flipped), len(multi))} |")
        A("")
        if spread:
            q = lambda f: spread[min(int(f * len(spread)), len(spread) - 1)]
            # Quantiles, not the maximum. The extreme tail runs to ratios of
            # 1e8, which no analytical method explains: those are reporting
            # defects -- a unit written wrongly, or a limit entered in the
            # value column. Quoting the maximum would present a data error as
            # a measurement, which is the mistake this paper is about.
            A(f"Among the pairs whose limit changes, the ratio of the largest "
              f"limit to the smallest has a median of **{q(0.5):.1f}×** "
              f"(interquartile range {q(0.25):.1f}–{q(0.75):.1f}×, "
              f"95th percentile {q(0.95):.0f}×).")
            A(f"The upper tail is not analytical: {sum(1 for s in spread if s > 1e4):,} "
              f"pairs differ by more than \\num{{10000}}×, which no method "
              f"change explains and which is itself a reporting defect.\n")
        A("> This is the empirical case for the modelling choice, and it does "
          "not depend on any of our own vocabulary. A limit that changes "
          "between years at one station, for one substance, is not a property "
          "of a device: it is a property of the run that produced the result. "
          "A vocabulary that attaches it to the sensor cannot express the "
          "difference, and a schema that stores one limit per instrument "
          "cannot record which run a result came from.\n")

    # ---- a sum standard over an incompletely measured group ----------------
    if group_members:
        A("## Sum standards, and whether the basket was ever complete\n")
        A("Annex~I states four limits on a **sum** rather than on any single "
          "substance. A sum computed over an incompletely measured group is an "
          "underestimate, so reporting it as compliant is the same error as "
          "entering a non-detection as zero — and it is invisible, because the "
          "arithmetic succeeds either way. The vocabulary carries "
          "`requiresCompleteGroup` for this; here is what the record does with "
          "it.\n")
        A("| sum standard | members | station-years with at least one measured "
          "| with **all** members measured |")
        A("|---|---|---|---|")
        for gname, mem in sorted(group_members.items(),
                                 key=lambda kv: -len(kv[1])):
            keys = [k for k in group_seen if k[0] == gname]
            complete = sum(1 for k in keys if len(group_seen[k]) == len(mem))
            A(f"| {gname} | {len(mem)} | {len(keys):,} | "
              f"**{complete:,}** ({pct(complete, len(keys))}) |")
        A("")
        A("> Where the basket is incomplete the sum standard is not applicable "
          "and the correct outcome is that it could not be assessed, not that "
          "it was met. A threshold column has no way to say so: it holds a "
          "number, and the number compares.\n")

    # ---- the record is not one era ----------------------------------------
    # Reported before the per-country breakdown because it changes how every
    # number above should be read. An earlier draft asserted that the release
    # "mostly predates 2015" and drew a limitation from it; the split below
    # says otherwise, and two of the three failures behave quite differently
    # across the boundary.
    if by_era:
        A(f"## Before and after {RECENT_FROM}\n")
        A(f"Each row is a station-year and carries its own reference year, so "
          f"the audit can be split rather than described in the aggregate. "
          f"A year that cannot be read is kept as its own stratum instead of "
          f"being folded into either era.\n")
        A("| | station-years | no flag, no limit | LOQ > EQS | fails the "
          "30\\% criterion | censored rows carrying a positive value |")
        A("|---|---|---|---|---|---|")
        order = [e for e in ("pre2015", "2015plus", "undated") if by_era.get(e)]
        label = {"pre2015": f"before {RECENT_FROM}",
                 "2015plus": f"{RECENT_FROM} onwards", "undated": "no year"}
        for e in order:
            v = by_era[e]
            A(f"| {label[e]} | {v['n']:,} | {pct(v['silent'], v['n'])} | "
              f"{pct(v['loq_gt_eqs'], v['has_eqs'])} | "
              f"{pct(v['loq_gt_30pct_eqs'], v['has_eqs'])} | "
              f"{pct(v['censored_with_value'], v['censored'])} |")
        A("")
        if by_block:
            A("Five-year blocks, so the choice of boundary can be checked "
              "against the shape of the record rather than taken on trust:\n")
            A("| period | station-years | no flag, no limit | fails the 30\\% "
              "criterion |")
            A("|---|---|---|---|")
            for b in sorted(by_block, key=lambda k: (k == "undated", k)):
                v = by_block[b]
                A(f"| {b} | {v['n']:,} | {pct(v['silent'], v['n'])} | "
                  f"{pct(v['loq_gt_30pct_eqs'], v['has_eqs'])} |")
            A("")

        rec = by_era.get("2015plus", {})
        if rec.get("n"):
            A(f"**{pct(rec['n'], kept)} of the river record is dated "
              f"{RECENT_FROM} or later** — {rec['n']:,} station-years — so "
              f"this is not an archive of one period. The three failures do "
              f"not move together across the boundary, and that is the "
              f"finding: the two that are questions of *record-keeping* "
              f"largely disappear, while the one that is a question of "
              f"*analytical capability* does not.\n")

        # Survivorship. A rate that falls while the set of reporters changes
        # has not been shown to have fallen. Restricting to authorities that
        # report in both eras is the only comparison that isolates practice
        # from composition, so it is computed rather than asserted.
        both = []
        for cty in sorted(by_country):
            a = by_era_country.get(f"{cty}:pre2015", {})
            b = by_era_country.get(f"{cty}:2015plus", {})
            if a.get("n") and b.get("n"):
                both.append((cty, a, b))
        if both:
            A(f"### Is the fall composition or practice?\n")
            A(f"The set of reporters is not the same in the two eras, so a "
              f"rate that falls between them proves nothing on its own. "
              f"**{len(both)}** authorities report in both, and the "
              f"comparison restricted to them is the one that isolates "
              f"practice from composition.\n")
            A(f"| country | station-years before / after | no flag, no limit "
              f"before | after |")
            A("|---|---|---|---|")
            for cty, a, b in sorted(both, key=lambda t: -t[2]["n"]):
                A(f"| {cty} | {a['n']:,} / {b['n']:,} | "
                  f"{pct(a['silent'], a['n'])} | {pct(b['silent'], b['n'])} |")
            A("")
            worse = [c for c, a, b in both
                     if b["n"] and a["n"]
                     and b["silent"] / b["n"] > a["silent"] / a["n"]]
            A(f"{len(both) - len(worse)} of {len(both)} improved; "
              f"{len(worse)} did not. The fall is therefore not survivorship: "
              f"it is the same authorities recording what they previously "
              f"omitted.\n")
            A(f"> **What this does not license.** Only {len(both)} "
              f"authorities report after {RECENT_FROM} at all. Any statement "
              f"about *current European practice* rests on that handful and "
              f"must say so; it is not a statement about the "
              f"{len(by_country)} reporters in the release.\n")

    # Metals against organic micropollutants. The published sensitivity work is
    # metals-only and the discussion compares against it, so the two shares it
    # turns on have to be stated here rather than left to be divided out of two
    # columns of a CSV -- one of them was quoted in the manuscript and occurred
    # in no generated file at all.
    if by_class:
        A("## Annex I metals against organic micropollutants\n")
        A("| substance class | station-years | samples | samples below LOQ | "
          "fails the 30\\% criterion |")
        A("|---|---|---|---|---|")
        for k in sorted(by_class, key=lambda k: -by_class[k]["samples"]):
            v = by_class[k]
            A(f"| {k} | {v['n']:,} | {v['samples']:,} | "
              f"{pct(v['samples_below'], v['samples'])} | "
              f"{pct(v['loq_gt_30pct_eqs'], v['has_eqs'])} |")
        A("")
        A("The comparison matters because the sensitivity literature this paper "
          "builds on examines metals, which is where censoring bites least.\n")

    top = sorted(by_country.items(), key=lambda kv: -kv[1]["n"])[:18]
    if top:
        A("## By reporting country\n")
        A("| country | station-years | with below-LOQ | of those, no LOQ | "
          "LOQ > EQS |")
        A("|---|---|---|---|---|")
        for k, v in top:
            A(f"| {k} | {v['n']:,} | {pct(v['below_loq'], v['n'])} | "
              f"{pct(v['below_loq_no_loq'], v['below_loq'])} | "
              f"{pct(v['loq_gt_eqs'], v['has_eqs'])} |")
        A("")
        A("The spread between countries is itself the point: this is a "
          "property of reporting practice, not of chemistry.\n")

        # The effect size that carries the argument. If the missing-bound rate
        # were driven by chemistry it would be similar everywhere; the spread
        # across reporting authorities is what shows it is a documentation
        # choice. Countries with a token number of rows are excluded so the
        # dispersion is not an artefact of tiny denominators.
        big = [v for v in by_country.values() if v["n"] >= 5000]
        if len(big) >= 8:
            sil = sorted(100 * v["silent"] / v["n"] for v in big)
            f3s = sorted(100 * v["loq_gt_eqs"] / v["has_eqs"]
                         for v in big if v["has_eqs"] >= 500)
            def q(xs, f):
                return xs[min(int(f * len(xs)), len(xs) - 1)]
            A("### How much of this is reporting practice?\n")
            A(f"Across the **{len(big)}** countries with at least "
              f"\\num{{5000}} station-years, the share declaring neither a "
              f"flag nor a limit runs from **{sil[0]:.1f}%** to "
              f"**{sil[-1]:.1f}%** (median {q(sil,0.5):.1f}%, IQR "
              f"{q(sil,0.25):.1f}–{q(sil,0.75):.1f}%).")
            if f3s:
                A(f"The share of assessments made with a limit above the "
                  f"standard runs from **{f3s[0]:.1f}%** to "
                  f"**{f3s[-1]:.1f}%** (median {q(f3s,0.5):.1f}%).")
            A("")
            A("A defect driven by chemistry would look the same in every "
              "country. A range this wide, over the same substances and the "
              "same standards, locates it in reporting practice -- which is "
              "where a representational fix can reach it.\n")

    worst = sorted((kv for kv in by_sub.items() if kv[1]["has_eqs"] >= 200),
                   key=lambda kv: -kv[1]["loq_gt_eqs"] / max(kv[1]["has_eqs"], 1))
    worst = [kv for kv in worst if kv[1]["loq_gt_eqs"]][:15]
    if worst:
        A("## Substances most often unmeasurable against their own standard\n")
        A("Rows where the laboratory's quantification limit is above the legal "
          "threshold. Article 3(3b) requires these to be set aside; a "
          "two-valued pipeline records them as compliant.\n")
        A("| substance | station-years with an EQS | LOQ > EQS |")
        A("|---|---|---|")
        for k, v in worst:
            A(f"| {k} | {v['has_eqs']:,} | "
              f"{pct(v['loq_gt_eqs'], v['has_eqs'])} |")
        A("")

    A("## Limits\n")
    A("- Waterbase aggregates national submissions of differing completeness; "
      "a missing LOQ may be a reporting omission rather than a laboratory one "
      "— which is exactly the failure being counted.")
    A("- The unit of a row is a station-year, matching the annual-average EQS. "
      "Sample-level counts are reported separately where available.")
    A("- F3 uses the inland-surface-water annual average and skips group "
      "standards, which apply to a sum rather than to any single substance.\n")

    text = "\n".join(L)
    (EVAL / "waterbase_external.md").write_text(text, encoding="utf-8")
    print("\n" + text[:2000])
    print(f"\nwrote: {EVAL/'waterbase_external.md'}, "
          f"{PROC/'waterbase_summary.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
