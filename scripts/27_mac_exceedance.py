#!/usr/bin/env python3
"""
The one legal test the aggregated release cannot run at all.

WHY THIS EXISTS
---------------
Every count in scripts/22_waterbase_external.py rests on a deliberate choice:
an annual-average environmental quality standard is defined against an annual
mean, and one aggregated Waterbase row IS an annual mean, so one row is one
assessment. That choice is correct and the headline numbers stay on it.

Annex I of Directive 2008/105/EC states a SECOND standard for most priority
substances: a maximum allowable concentration, defined against an individual
measurement. It is not a stricter version of the annual-average test. It has a
different UNIT OF OBSERVATION, and the aggregated release cannot evaluate it at
any level of effort, because the quantity it needs -- the individual sample --
was averaged away before publication.

That is why this stage exists, and it is the point:

  * The vocabulary declares censo:AnnualAverageThreshold and
    censo:MaximumAllowableThreshold, holds them disjoint, and
    scripts/test_axioms.py case T8 makes conflating them an inconsistency.
    Until now that distinction was asserted and never used: the EU package ships
    maximum-allowable thresholds that nothing in the pipeline referenced.
  * A numeric threshold column cannot carry the distinction, because it is not
    a property of the number. Two limits for the same substance in the same
    matrix differ in what they are a limit ON. Storing both as columns and
    comparing whichever is to hand is exactly the error T8 rejects.
  * And the two standards disagree on real rows. A station-year can be
    compliant on its annual mean while one of the samples behind that mean
    breaches the maximum allowable concentration. Only the record read at both
    units shows it.

WHAT IS COMPUTED
----------------
One streaming pass over the disaggregated release does two things.

  A. THE SAMPLE-LEVEL AUDIT. For every river sample of a substance carrying a
     maximum-allowable standard:
        quantified, value > MAC          -> Exceedance
        quantified, value <= MAC         -> Compliant
        censored, LOQ <= MAC             -> Compliant (the non-detection decides)
        censored, LOQ  > MAC             -> MethodInsufficient. Article 3(3b)
                                            applies to this standard too: a
                                            result whose limit exceeds the
                                            standard shall not be considered.
        censored, no LOQ                 -> Unresolved: nothing to decide with

  B. THE TWO STANDARDS ON THE SAME STATION-YEAR. The aggregated release is
     indexed first, for the substances that carry both standards. Each sample
     is then attributed to its station-year, and the annual-average verdict on
     the published mean is cross-tabulated against the maximum-allowable
     verdict on the samples behind it.

WHAT THIS DOES NOT DO
---------------------
It does not touch a single headline number. Those are annual-average
assessments on annual means and stay that way. This is a different question
asked of the same monitoring, and it is reported separately for that reason.

COVERAGE, STATED RATHER THAN ASSUMED
------------------------------------
The disaggregated release does not contain the samples behind every aggregated
station-year. The join coverage is measured and reported, because a share
computed over the covered stratum is a statement about that stratum.

THE ARCHIVE
-----------
WISE6_DisaggregatedData-csv.zip is Deflate64, which Python's zipfile refuses.
It is streamed through 7z or bsdtar instead; a plain .csv or .csv.gz is read
directly with no external tool. When neither the file nor an extractor is
present the stage SKIPS rather than fails, so the repository's documented
reproduction path -- the 165 MB aggregated download -- stays intact.

Inputs  : Data/waterbase/*Disaggregated*  (optional; the stage skips without it)
          Data/waterbase/*Aggregated*     (for the station-year comparison)
          derived/processed/eu_eqs.csv
Outputs : derived/processed/mac_exceedance.csv
          eval/mac_exceedance.md

Usage:  python scripts/27_mac_exceedance.py [--file PATH] [--limit N]
        python scripts/27_mac_exceedance.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import shutil
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Data" / "waterbase"
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

sys.path.insert(0, str(Path(__file__).resolve().parent))
_m = __import__("22_waterbase_external")
num, wilson, era_of, RECENT_FROM = _m.num, _m.wilson, _m.era_of, _m.RECENT_FROM
TO_UG_L = _m.TO_UG_L

# Extractors that handle Deflate64, in order of preference. Both are read-only
# uses on a file the user downloaded; neither is required unless the
# disaggregated release is present AND its archive defeats zipfile.
EXTRACTORS = (["7z", "e", "-so"], ["bsdtar", "-xOf"])


def find(pattern: str):
    if not DATA.exists():
        return None
    for p in sorted(DATA.iterdir()):
        if pattern.lower() in p.name.lower() and p.suffix.lower() in (
                ".zip", ".gz", ".csv"):
            return p
    return None


def stream_rows(path: Path):
    """Yield CSV rows from .csv / .csv.gz / .zip, falling back to an external
    extractor for compression methods zipfile does not implement."""
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", errors="replace") as fh:
            yield from csv.reader(fh)
        return
    if path.name.lower().endswith(".csv.gz"):
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
            yield from csv.reader(fh)
        return

    with zipfile.ZipFile(path) as z:
        inner = sorted((n for n in z.namelist() if n.lower().endswith(".csv")),
                       key=lambda n: -z.getinfo(n).file_size)
        if not inner:
            sys.exit(f"no CSV inside {path.name}")
        info = z.getinfo(inner[0])
        try:
            with z.open(info) as fh:
                yield from csv.reader(io.TextIOWrapper(fh, encoding="utf-8",
                                                       errors="replace"))
            return
        except NotImplementedError:
            # Deflate64 (method 9). Documented here because the error message
            # zipfile raises says only "That compression method is not
            # supported", which sends the reader looking in the wrong place.
            pass

    for exe in EXTRACTORS:
        if shutil.which(exe[0]):
            p = subprocess.Popen(exe + [str(path)], stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, bufsize=1 << 20)
            yield from csv.reader(line.decode("utf-8", "replace")
                                  for line in p.stdout)
            p.stdout.close()
            p.wait()
            return
    sys.exit(
        f"{path.name} uses a compression method Python cannot read "
        f"(Deflate64), and neither 7z nor bsdtar is on PATH. Install either, "
        f"or unpack the archive and leave the .csv in "
        f"{DATA.relative_to(ROOT)}/.")


# THE SAME DECISION PROCEDURE THE ANNUAL-AVERAGE ANALYSIS USES.
#
# This stage had its own verdict() function. The manuscript claimed one shared
# procedure "held in a single module precisely so the two cannot drift", and the
# two had drifted: Article 3(3b) was applied here to any row whose limit exceeded
# the standard rather than to a censored one, no applicability condition was
# consulted at all, and 49,783 of the reported exceedances were cadmium, lead and
# nickel -- substances whose standards Annex I defines on a quantity the record
# does not report. Importing removes the possibility of drift instead of
# promising its absence.
sys.path.insert(0, str(Path(__file__).resolve().parent))
_m = __import__("22_waterbase_external")
detection_status = _m.detection_status
censo_outcome = _m.censo_outcome
conditional_thresholds = _m.conditional_thresholds


def load_thresholds():
    """CAS -> (annual average, maximum allowable), inland surface water.

    Group standards are excluded from both: a sum limit is not a limit on any
    of its members, and applying it to one would be the same category error
    this stage exists to demonstrate, in the other direction.
    """
    aa, mac, cond = {}, {}, {}
    p = PROC / "eu_eqs.csv"
    if not p.exists():
        return aa, mac, cond
    with p.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    cond = conditional_thresholds(rows)
    if True:
        for r in rows:
            if r.get("is_group") == "True":
                continue
            a, m = num(r.get("aa_inland")), num(r.get("mac_inland"))
            for c in (r.get("all_cas") or "").replace(" ", "").split(";"):
                if not c:
                    continue
                if a:
                    aa.setdefault(c, a)
                if m:
                    mac.setdefault(c, m)
    return aa, mac, cond


def self_test() -> int:
    """Every branch of the verdict, on rows whose answers are known.

    Written because the interesting branch is the one that is easy to get
    backwards: a NON-DETECTION whose quantification limit sits above the
    standard is not compliant. It is undecidable, and a pipeline that reads it
    as compliant is the failure this paper is about -- reproduced here at the
    sample level, where the maximum-allowable standard lives.
    """
    cases = [
        # (censored, value, loq, mac, expected)
        (False, 2.0, 0.1, 1.0, "exceedance"),
        (False, 0.5, 0.1, 1.0, "compliant_quantified"),
        (True, None, 0.1, 1.0, "compliant_censored"),
        (True, None, 5.0, 1.0, "method_insufficient"),
        (True, None, None, 1.0, "censored_no_loq"),
        # the source's own substituted number must not decide a censored row
        (True, 5.0, 0.1, 1.0, "compliant_censored"),
    ]
    bad = 0
    for censored, val, loq, mac, want in cases:
        got = verdict(censored, val, loq, mac)
        if got != want:
            print(f"  FAIL {censored=} {val=} {loq=}: got {got}, want {want}")
            bad += 1
    print("  self-test passed" if not bad else f"  {bad} failure(s)")
    return 1 if bad else 0


def verdict(censored, val_ug, loq_ug, mac, precondition=None):
    """The verdict for one sample against a maximum-allowable standard.

    A thin adapter over censo_outcome, kept only to preserve this stage's
    reporting vocabulary (which distinguishes a compliant quantified sample from
    a compliant censored one, a split the annual-average tables do not need).
    Every decision is the shared one.

    A censored row is decided by its BOUND, never by the number the reporter
    wrote in place of the non-detection. That number is a substitution; using it
    here would import into the maximum-allowable test exactly the artefact the
    annual-average analysis spends its length demonstrating -- so a censored row
    is passed with val_ug=None.
    """
    status = "censored" if censored else ("quantified" if val_ug is not None
                                         else "unresolved")
    if censored and loq_ug is None:
        return "censored_no_loq"
    if not censored and val_ug is None:
        return "censored_no_loq"
    out = censo_outcome(status, None if censored else val_ug, loq_ug, mac,
                        precondition=precondition)
    if out == "compliant":
        return "compliant_censored" if censored else "compliant_quantified"
    if out in ("indeterminate_unresolved", "indeterminate_other"):
        return "censored_no_loq"
    return out          # exceedance | method_insufficient | precondition_unmet
                        # | possible_exceedance


VERDICTS = ("exceedance", "possible_exceedance", "compliant_quantified",
            "compliant_censored", "precondition_unmet", "method_insufficient",
            "censored_no_loq")


def index_aggregated(path, mac_cas):
    """Station-year -> (mean in ug/L, CAS) for substances carrying a MAC.

    Only those substances, so the index stays small: the comparison it feeds
    is undefined for a substance with no maximum-allowable standard.
    """
    idx, dup = {}, set()
    rows = stream_rows(path)
    hdr = next(rows)
    hdr[0] = hdr[0].lstrip("﻿")
    h = {c.strip().lower(): i for i, c in enumerate(hdr)}
    need = ("countrycode", "monitoringsiteidentifier",
            "observedpropertydeterminandcode", "procedureanalysedmatrix",
            "phenomenontimereferenceyear", "resultuom", "resultmeanvalue",
            "parameterwaterbodycategory")
    if any(k not in h for k in need):
        return {}, set()
    for row in rows:
        if not row or row[h["parameterwaterbodycategory"]].strip() not in ("RW", ""):
            continue
        code = row[h["observedpropertydeterminandcode"]].strip()
        cas = code[4:] if code.upper().startswith("CAS_") else ""
        if cas not in mac_cas:
            continue
        f = TO_UG_L.get(row[h["resultuom"]].strip().lower().replace(" ", ""))
        m = num(row[h["resultmeanvalue"]])
        if f is None or m is None:
            continue
        key = "|".join((row[h["countrycode"]].strip(),
                        row[h["monitoringsiteidentifier"]].strip(), code,
                        row[h["procedureanalysedmatrix"]].strip(),
                        row[h["phenomenontimereferenceyear"]].strip()[:4]))
        if key in idx:
            # Two aggregated rows for one station-year: a sampling-period split.
            # Dropped rather than guessed, and counted so the exclusion is
            # visible.
            dup.add(key)
            continue
        idx[key] = (m * f, cas)
    for k in dup:
        idx.pop(k, None)
    return idx, dup


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path,
                    help="the disaggregated release; found in Data/waterbase "
                         "when omitted")
    ap.add_argument("--aggregated", type=Path,
                    help="the aggregated release, for the station-year "
                         "comparison")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if self_test():
        return 1

    EVAL.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)

    src = args.file or find("disaggregated")
    if src is None or not src.exists():
        print("  no disaggregated release in "
              f"{DATA.relative_to(ROOT)}/; skipping.")
        print("  This stage is the only one that needs it. The annual-average "
              "audit -- every headline number in the paper -- runs on the "
              "aggregated release alone.")
        print("  A maximum-allowable standard is defined against a single "
              "measurement, so it cannot be evaluated on annual means at all; "
              "that is why it is a separate stage and not a column.")
        return 0

    aa_eqs, mac_eqs, cond = load_thresholds()
    if not mac_eqs:
        print("  no maximum-allowable thresholds in derived/processed/"
              "eu_eqs.csv; run scripts/10_parse_eu_eqs.py first")
        return 0
    print(f"  {len(set(mac_eqs.values()))} maximum-allowable values over "
          f"{len(mac_eqs)} CAS numbers; group standards excluded")

    agg = args.aggregated or find("aggregated")
    idx, dup = ({}, set())
    if agg and agg.exists():
        print(f"  indexing {agg.name} for the station-year comparison …",
              flush=True)
        idx, dup = index_aggregated(agg, set(mac_eqs))
        print(f"    {len(idx):,} station-years of a substance carrying both "
              f"standards ({len(dup):,} ambiguous keys dropped)")

    print(f"  streaming {src.name} ({src.stat().st_size/1e9:.2f} GB on disk) …",
          flush=True)
    rows = stream_rows(src)
    hdr = next(rows)
    hdr[0] = hdr[0].lstrip("﻿")
    h = {c.strip().lower(): i for i, c in enumerate(hdr)}
    for k in ("observedpropertydeterminandcode", "resultobservedvalue",
              "resultqualityobservedvaluebelowloq", "procedureloqvalue",
              "resultuom"):
        if k not in h:
            sys.exit(f"column {k} not found; header was {hdr[:12]}")
    i_cat = h.get("parameterwaterbodycategory")
    i_cty = h.get("countrycode")
    i_site = h.get("monitoringsiteidentifier")
    i_mat = h.get("procedureanalysedmatrix")
    i_date = h.get("phenomenontimesamplingdate")
    i_lbl = h.get("observedpropertydeterminandlabel")

    tot = defaultdict(int)
    by_sub = defaultdict(lambda: defaultdict(int))
    by_country = defaultdict(lambda: defaultdict(int))
    by_era = defaultdict(lambda: defaultdict(int))
    uom_unknown = defaultdict(int)
    # station-year -> [max quantified value in ug/L, any sample exceeds]
    per_sy = {}

    n = kept = 0
    for row in rows:
        if not row:
            continue
        n += 1
        if args.limit and n > args.limit:
            break
        if n % 10_000_000 == 0:
            print(f"    {n:,} rows read, {kept:,} assessable …", flush=True)
        if i_cat is not None and row[i_cat].strip() not in ("RW", ""):
            continue
        code = row[h["observedpropertydeterminandcode"]].strip()
        cas = code[4:] if code.upper().startswith("CAS_") else ""
        mac = mac_eqs.get(cas)
        if mac is None:
            continue
        f = TO_UG_L.get(row[h["resultuom"]].strip().lower().replace(" ", ""))
        if f is None:
            uom_unknown[row[h["resultuom"]].strip() or "(blank)"] += 1
            continue
        kept += 1

        censored = row[h["resultqualityobservedvaluebelowloq"]].strip() == "1"
        v = num(row[h["resultobservedvalue"]])
        lq = num(row[h["procedureloqvalue"]])
        v_ug = v * f if v is not None else None
        lq_ug = lq * f if lq is not None else None
        out = verdict(censored, v_ug, lq_ug, mac,
                      precondition=cond.get(cas))

        d = row[i_date].strip() if i_date is not None else ""
        yr = int(d[:4]) if len(d) >= 4 and d[:4].isdigit() else None
        era = era_of(yr)
        sub = (row[i_lbl].strip() if i_lbl is not None else "") or code
        cty = (row[i_cty].strip() if i_cty is not None else "") or "??"

        for t in (tot, by_sub[sub], by_country[cty], by_era[era]):
            t["n"] += 1
            t[out] += 1
            if not censored and v_ug is not None:
                t["quantified"] += 1
            if censored:
                t["censored"] += 1

        if idx and i_site is not None and i_mat is not None and yr:
            key = "|".join((cty, row[i_site].strip(), code,
                            row[i_mat].strip(), str(yr)))
            if key in idx:
                st = per_sy.get(key)
                if st is None:
                    st = per_sy[key] = [None, False]
                if not censored and v_ug is not None:
                    if st[0] is None or v_ug > st[0]:
                        st[0] = v_ug
                    if v_ug > mac:
                        st[1] = True

    print(f"  {n:,} rows read; {kept:,} assessable against a "
          f"maximum-allowable standard")

    # ---- the two standards on the same station-year ----------------------
    cross = defaultdict(int)
    for key, (mean_ug, cas) in idx.items():
        st = per_sy.get(key)
        if st is None:
            cross["no_samples_found"] += 1
            continue
        aa = aa_eqs.get(cas)
        mac = mac_eqs.get(cas)
        if aa is None or mac is None or st[0] is None:
            cross["not_assessable_both"] += 1
            continue
        cross["both_assessable"] += 1
        aa_exc, mac_exc = mean_ug > aa, st[1]
        cross[("exceeding" if aa_exc else "compliant") + "_aa__"
              + ("exceeding" if mac_exc else "compliant") + "_mac"] += 1

    COLS = ["n", "quantified", "censored"] + list(VERDICTS)
    with (PROC / "mac_exceedance.csv").open("w", newline="",
                                            encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scope", "key"] + COLS)
        for scope, d in (("total", {"": tot}), ("substance", by_sub),
                         ("country", by_country), ("era", by_era)):
            for k, v in sorted(d.items(), key=lambda kv: -kv[1]["n"]):
                w.writerow([scope, k] + [v[c] for c in COLS])
        for k, v in sorted(cross.items()):
            w.writerow(["station_year_cross", k] + [v] + [""] * (len(COLS) - 1))

    def pct(a, b):
        return f"{100*a/b:.1f}%" if b else "—"

    L = []
    A = L.append
    A("# The maximum-allowable standard, at the unit it is defined on\n")
    A("Generated by `scripts/27_mac_exceedance.py`.\n")
    A(f"- source: `{src.name}` (EEA Waterbase, disaggregated release)")
    A(f"- rows read: **{n:,}**; assessable against a maximum-allowable "
      f"standard: **{kept:,}**")
    A(f"- thresholds: {len(set(mac_eqs.values()))} maximum-allowable values "
      f"over {len(mac_eqs)} CAS numbers, group standards excluded\n")
    A("Annex I of Directive 2008/105/EC states two standards for most priority "
      "substances: an annual average, defined against an annual mean, and a "
      "maximum allowable concentration, defined against an individual "
      "measurement. Every other stage in this pipeline evaluates the first, on "
      "the aggregated release, because one aggregated row *is* an annual mean. "
      "The second cannot be evaluated there at any level of effort — the "
      "quantity it applies to was averaged away before publication. It is not a "
      "stricter test of the same thing; it is a test with a different unit of "
      "observation, which is why the vocabulary holds "
      "`censo:AnnualAverageThreshold` and `censo:MaximumAllowableThreshold` "
      "disjoint and why `scripts/test_axioms.py` T8 makes conflating them an "
      "inconsistency.\n")

    A("## Verdicts on individual samples\n")
    A("| verdict | n | share |")
    A("|---|---|---|")
    LABEL = {
        "exceedance": "**Exceedance** — a measured value above the standard",
        "possible_exceedance": "**PossibleExceedance** — a measured value whose "
                               "widest lawful uncertainty interval (Art. 4(1), "
                               "k=2) straddles the standard",
        "precondition_unmet": "**PreconditionUnmet** — the standard is defined "
                              "on a quantity the record does not report "
                              "(Annex I footnotes 9 and 12: hardness class, "
                              "bioavailable concentration)",
        "compliant_quantified": "Compliant — a measured value at or below it",
        "compliant_censored": "Compliant — not detected, and the "
                              "quantification limit clears the standard",
        "method_insufficient": "**MethodInsufficient** — not detected, but the "
                               "quantification limit is *above* the standard, "
                               "so no result this method could return would "
                               "decide it (Art. 3(3b))",
        "censored_no_loq": "Unresolved — censoring declared with no limit "
                           "recorded, or no value at all",
    }
    for k in VERDICTS:
        A(f"| {LABEL[k]} | {tot[k]:,} | {pct(tot[k], kept)} |")
    A("")
    if tot["method_insufficient"]:
        A(f"> **{tot['method_insufficient']:,} samples "
          f"({pct(tot['method_insufficient'], kept)}) are undecidable against "
          f"a standard that applies to them individually**, because the "
          f"laboratory could not quantify below it. A two-valued pipeline "
          f"records every one of them as compliant, and the aggregated release "
          f"cannot see them at all: averaged into an annual mean, they become "
          f"one number compared against a different standard.\n")

    if uom_unknown:
        drop = sum(uom_unknown.values())
        A(f"> Excluded: {drop:,} row(s) report a unit this pipeline does not "
          f"convert to \\si{{\\micro\\gram\\per\\litre}} and are not compared "
          f"against any threshold. Units seen: "
          + ", ".join(f"`{u}` ({c:,})" for u, c in
                      sorted(uom_unknown.items(), key=lambda kv: -kv[1])[:6])
          + ".\n")

    if cross.get("both_assessable"):
        b = cross["both_assessable"]
        A("## The same station-year under both standards\n")
        A(f"The annual-average verdict is taken from the published mean; the "
          f"maximum-allowable verdict from the samples behind that mean. "
          f"**{b:,}** station-years can be assessed under both.\n")
        A("| annual average | maximum allowable | n | share |")
        A("|---|---|---|---|")
        for aa_s in ("compliant", "exceeding"):
            for mac_s in ("compliant", "exceeding"):
                k = f"{aa_s}_aa__{mac_s}_mac"
                A(f"| {aa_s} | {mac_s} | {cross[k]:,} | {pct(cross[k], b)} |")
        A("")
        # The off-diagonal TOTAL, stated rather than left to be added up. The
        # manuscript quotes it, and a quantity a reader has to compute from two
        # cells is one the audit cannot trace into shipped data.
        other = cross["exceeding_aa__compliant_mac"]
        hidden = cross["compliant_aa__exceeding_mac"]
        A(f"> **{hidden + other:,} of these station-years "
          f"({pct(hidden + other, b)}) receive different verdicts under the "
          f"two standards, and they disagree in both directions.** Neither "
          f"standard is a stricter version of the other: they are written "
          f"about different units of observation.\n")
        if hidden:
            A(f"> **{hidden:,} station-years ({pct(hidden, b)}) are compliant "
              f"on the annual mean while a sample behind that mean breaches "
              f"the maximum allowable concentration.** Neither verdict is "
              f"wrong and neither supersedes the other: they are answers to "
              f"different questions, asked of different units of observation, "
              f"and Annex I asks both. A schema that stores one threshold per "
              f"substance can hold only one of them, and cannot record which "
              f"one it holds.\n")
        A(f"Coverage: of the {len(idx):,} indexed station-years for these "
          f"substances, {cross['no_samples_found']:,} have no samples in the "
          f"disaggregated release and {cross['not_assessable_both']:,} lack "
          f"one of the two standards or a quantified sample. The shares above "
          f"describe the {b:,} that can be read both ways.\n")

    worst = sorted(((k, v) for k, v in by_sub.items() if v["n"] >= 1000),
                   key=lambda kv: -kv[1]["method_insufficient"] / max(kv[1]["n"], 1))
    worst = [kv for kv in worst if kv[1]["method_insufficient"]][:15]
    if worst:
        A("## Substances least often decidable against their "
          "maximum-allowable standard\n")
        A("| substance | assessable samples | undecidable | exceedances |")
        A("|---|---|---|---|")
        for k, v in worst:
            A(f"| {k} | {v['n']:,} | {pct(v['method_insufficient'], v['n'])} | "
              f"{v['exceedance']:,} |")
        A("")

    if by_era:
        A(f"## Before and after {RECENT_FROM}\n")
        A("| period | assessable samples | exceedances | undecidable |")
        A("|---|---|---|---|")
        for e, lbl in (("pre2015", f"before {RECENT_FROM}"),
                       ("2015plus", f"{RECENT_FROM} onwards"),
                       ("undated", "no date")):
            v = by_era.get(e)
            if not v or not v["n"]:
                continue
            A(f"| {lbl} | {v['n']:,} | {pct(v['exceedance'], v['n'])} | "
              f"{pct(v['method_insufficient'], v['n'])} |")
        A("")

    A("## Limits\n")
    A("- The disaggregated release does not hold the samples behind every "
      "aggregated station-year. The coverage is reported above; the shares "
      "describe the stratum that can be read at both units, not the whole "
      "record.")
    A("- A censored sample is decided by its quantification limit, never by "
      "the number the reporter wrote in its place. That number is a "
      "substitution, and using it here would import the artefact the "
      "annual-average analysis exists to expose.")
    A("- Group standards are excluded, as everywhere else: a sum limit is not "
      "a limit on any of its members.")
    A("- Nothing here revises an annual-average result. The two standards are "
      "reported side by side because Annex I states both, not because one "
      "corrects the other.\n")

    text = "\n".join(L)
    (EVAL / "mac_exceedance.md").write_text(text, encoding="utf-8")
    print("\n" + text[:1800])
    print(f"\nwrote: {EVAL/'mac_exceedance.md'}, {PROC/'mac_exceedance.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
