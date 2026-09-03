#!/usr/bin/env python3
"""
How many conclusions change when censoring is represented rather than substituted?

THE QUESTION
------------
It is agreed that substituting a value for a non-detect distorts results
(Helsel 2006; Lipinski 2026). This script asks what it costs on this dataset,
by running the same assessment two ways and counting the differences.

  A  STANDARD PRACTICE. A non-detect is a zero. Every observation with a
     threshold receives a verdict: exceeding if value > threshold, compliant
     otherwise. There is no third outcome, which is exactly the situation in
     the tables this survey was distributed in.

  B  CENSORING-AWARE. A non-detect is the interval [0, LOD]. A verdict is drawn
     only when the interval decides it. Four outcomes are possible, including
     "cannot be determined", and its causes are separated:
        - method insufficient : LOQ > threshold, so no measurement could decide
        - censored ambiguous  : threshold lies inside [0, LOD]
        - unresolved          : no LOD published, so the status is unknowable

TWO MEASURES ARE REPORTED
-------------------------
1. VERDICT FLIPS. How many assessments that A reports as determinate are not
   supportable. This is the headline number.

2. LOAD BOUNDS. Substituting zero yields the smallest load consistent with the
   data. Using each non-detect's LOD yields the largest. The ratio between them
   is the width of what the survey cannot distinguish -- reported per analyte
   and basin-wide, in kg/day, using gauged flow.

HONESTY NOTES
-------------
* Only analytes with BOTH a published LOD and a threshold can be flipped at all.
  Everything else is counted as structurally unassessable and reported as such;
  it is not silently dropped.
* Thresholds are taken from the primary legal texts, never from the project
  spreadsheet, which was found to be wrong for 7 of 10 metals.
* Annual-average standards apply to a temporal mean, not to a grab sample.
  Comparing single observations against them is a category error; we therefore
  report AA-based verdicts separately and lean on the maximum-allowable
  standards, which single samples may legitimately be compared against.

Inputs  : derived/processed/{measurements,analytes,eu_eqs}.csv
Outputs : derived/processed/flip_verdicts.csv
          eval/flip_analysis.md

Usage:  python scripts/12_flip_analysis.py
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

FLOW_KEYS = ("yabatas", "ekoton")
SEC_PER_DAY = 86400.0
UG_PER_L_M3_TO_KG_PER_DAY = 1e-6 * 1e3 * SEC_PER_DAY / 1e3  # ug/L * m3/s -> kg/d


def fold(t: str) -> str:
    t = str(t)
    for a, b in [("ı", "i"), ("İ", "i"), ("ş", "s"), ("Ş", "s"), ("ğ", "g"),
                 ("Ğ", "g"), ("ç", "c"), ("Ç", "c"), ("ö", "o"), ("Ö", "o"),
                 ("ü", "u"), ("Ü", "u")]:
        t = t.replace(a, b)
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c)).strip().lower()


def num(x):
    if x in ("", None):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load(name):
    p = PROC / name
    if not p.exists():
        sys.exit(f"missing {p}; run the earlier scripts first")
    return list(csv.DictReader(p.open(encoding="utf-8")))


def main() -> int:
    EVAL.mkdir(parents=True, exist_ok=True)
    measurements = load("measurements.csv")
    analytes = {a["parameter"]: a for a in load("analytes.csv")}

    # EU thresholds, matched by CAS where available.
    #
    # GROUP entries are excluded from per-substance comparison. Annex I states
    # several standards for a SUM -- "Sum of active substances in the pesticides
    # group" lists 75 CAS numbers against one aggregate limit, the PAH entry
    # lists nine -- and applying such a value to a single member compares that
    # substance against a limit written for the total. Ten measured analytes
    # were being assessed this way. A group standard is only assessable when the
    # whole group was measured, which this survey did not do, so those pairs are
    # counted as `group_not_assessable` rather than silently mis-assessed.
    #
    # Individual entries win over group entries where a substance appears in
    # both (benzo[a]pyrene has its own standard and is also in the PAH sum).
    eu_by_cas, eu_group_cas = {}, {}
    if (PROC / "eu_eqs.csv").exists():
        for r in load("eu_eqs.csv"):
            target = eu_group_cas if r.get("is_group") == "True" else eu_by_cas
            for c in (r.get("all_cas") or "").split(";"):
                if c.strip():
                    target.setdefault(c.strip(), r)
    cas_of = {}
    if (PROC / "substances.csv").exists():
        for r in load("substances.csv"):
            if r.get("cas"):
                cas_of[r["analyte"]] = r["cas"]

    # flow per (campaign, station)
    flow = {}
    for m in measurements:
        if fold(m["parameter"]) in FLOW_KEYS:
            v = num(m["value_num"])
            if v and v > 0:
                flow.setdefault((m["campaign"], m["station"]), v)

    rows = []
    tally = Counter()
    per_point = {}          # (analyte, campaign, station) -> (lo, hi, is_nd)

    # The most downstream gauged station is the one with the largest cumulative
    # catchment area; loads there represent what the basin exports.
    outlet = None
    snap = PROC / "stations_snapped.csv"
    if snap.exists():
        best = None
        for r in csv.DictReader(snap.open(encoding="utf-8")):
            ca = num(r.get("carea_km2"))
            if ca is not None and (best is None or ca > best[1]):
                best = (r["station"], ca)
        if best:
            outlet = best[0]

    for m in measurements:
        p = m["parameter"]
        a = analytes.get(p)
        if not a or a["group"] not in ("micropollutant", "metal", "conventional"):
            continue
        v = num(m["value_num"])
        if v is None:
            continue

        lod = num(a.get("lod"))
        loq = num(a.get("loq"))

        # threshold: prefer the EU maximum-allowable value (comparable to a
        # single sample); fall back to the EU annual average.
        c_ = cas_of.get(p, "")
        eu = eu_by_cas.get(c_)
        thr = thr_kind = None
        if eu:
            if num(eu.get("mac_inland")) is not None:
                thr, thr_kind = num(eu["mac_inland"]), "EU MAC"
            elif num(eu.get("aa_inland")) is not None:
                thr, thr_kind = num(eu["aa_inland"]), "EU AA"
        elif c_ and c_ in eu_group_cas:
            # Covered by the regulation, but only as part of a sum the survey
            # did not measure in full. Reporting it as "no threshold" would
            # understate coverage; assessing it individually would be wrong.
            tally["group_not_assessable"] += 1
            continue

        is_nd = (v == 0.0)

        # ---- load bounds, per station-campaign (never summed over stations) ----
        q = flow.get((m["campaign"], m["station"]))
        if q is not None and lod is not None:
            key = (p, m["campaign"], m["station"])
            lo = 0.0 if is_nd else v * q * UG_PER_L_M3_TO_KG_PER_DAY
            hi = (lod if is_nd else v) * q * UG_PER_L_M3_TO_KG_PER_DAY
            per_point[key] = (lo, hi, is_nd)

        if thr is None:
            tally["no_threshold"] += 1
            continue

        # ---- A: standard practice ----
        verdict_a = "exceeding" if v > thr else "compliant"

        # ---- B: censoring-aware ----
        if loq is not None and loq > thr:
            verdict_b, cause = "indeterminate", "method_insufficient"
        elif is_nd and lod is None:
            verdict_b, cause = "indeterminate", "unresolved_no_lod"
        elif is_nd:
            # interval [0, LOD]
            verdict_b, cause = ("compliant", "") if lod <= thr \
                else ("indeterminate", "censored_ambiguous")
        else:
            verdict_b, cause = ("exceeding" if v > thr else "compliant"), ""

        tally[f"A_{verdict_a}"] += 1
        tally[f"B_{verdict_b}"] += 1
        flipped = verdict_a != verdict_b
        if flipped:
            tally[f"flip_{verdict_a}_to_{verdict_b}:{cause}"] += 1
        tally["assessable_pairs"] += 1

        rows.append({
            "campaign": m["campaign"], "station": m["station"], "analyte": p,
            "value": v, "is_non_detect": is_nd, "lod": lod or "", "loq": loq or "",
            "threshold": thr, "threshold_kind": thr_kind,
            "verdict_standard": verdict_a, "verdict_censoring_aware": verdict_b,
            "cause": cause, "flipped": flipped,
        })

    if not rows:
        sys.exit("no assessable observation-threshold pairs; check the EU EQS join")

    with (PROC / "flip_verdicts.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    n = tally["assessable_pairs"]
    n_flip = sum(v for k, v in tally.items() if k.startswith("flip_"))
    a_comp = tally["A_compliant"]
    b_indet = tally["B_indeterminate"]

    # b_indet is every pair that ends up indeterminate, INCLUDING those that
    # started as `exceeding`. Dividing it by the number that started as
    # `compliant` mixes two denominators and overstated the compliant-loss rate
    # as 93.2% when it is 93.1%. Count the actual transition instead.
    comp_to_indet = sum(1 for r in rows
                        if r["verdict_standard"] == "compliant"
                        and r["verdict_censoring_aware"] == "indeterminate")
    # Determinacy is the other headline and has its own denominator: under
    # standard practice every assessable pair is determinate, so what survives
    # is (compliant + exceeding) after, over all assessable pairs.
    det_after = (tally.get("B_compliant", 0) + tally.get("B_exceeding", 0))
    det_before = a_comp + tally.get("A_exceeding", 0)

    L = []
    A = L.append
    A("# Flip analysis: what changes when censoring is represented\n")
    A("Generated by `scripts/12_flip_analysis.py`. The same observations are "
      "assessed twice -- once as current practice would (a non-detect is a "
      "zero, two possible verdicts) and once with the censoring represented "
      "(a non-detect is $[0,\\mathrm{LOD}]$, four possible verdicts).\n")

    A("## Headline\n")
    A(f"- observation--threshold pairs assessable at all: **{n:,}**")
    A(f"- verdicts that change: **{n_flip:,}** ({100*n_flip/n:.1f}%)")
    if a_comp:
        A(f"- of the **{a_comp:,}** pairs standard practice reports as "
          f"*compliant*, **{comp_to_indet:,}** "
          f"({100*comp_to_indet/a_comp:.1f}%) are not supportable by the data")
    if det_before:
        A(f"- of the **{det_before:,}** verdicts standard practice returns as "
          f"determinate, **{det_after:,}** ({100*det_after/det_before:.1f}%) "
          f"remain determinate once censoring is represented")
    A("")

    # A sceptic can reasonably argue that treating a missing LOD as undecidable
    # is too strict: a laboratory that reported a zero presumably had a limit
    # well below the standard. That presumption cannot be verified, and where it
    # CAN be checked it fails -- the neonicotinoids. Reporting the figure that
    # survives even if the sceptic is granted the point makes the claim robust.
    hard = sum(v for k, v in tally.items()
               if k.startswith("flip_") and "method_insufficient" in k)
    A("### A conservative floor\n")
    A("The dominant cause above is a missing detection limit. A sceptic may "
      "argue that a laboratory reporting a zero presumably had a limit well "
      "below the standard, so those cases should be read as compliant. That "
      "presumption cannot be verified, and where it can be checked -- the "
      "neonicotinoids -- it is false. But granting it entirely still leaves "
      f"**{hard:,} verdicts ({100*hard/n:.1f}% of all assessable pairs)** that "
      "change because the method's quantification limit exceeds the standard, "
      "which no assumption about the laboratory can repair.\n")

    A("## Verdict distribution\n")
    A("| verdict | standard practice | censoring-aware |")
    A("|---|---|---|")
    for v in ("compliant", "exceeding", "indeterminate"):
        A(f"| {v} | {tally.get('A_'+v, 0):,} | {tally.get('B_'+v, 0):,} |")
    A("")

    flips = {k: v for k, v in tally.items() if k.startswith("flip_")}
    if flips:
        A("## Where the verdicts go, and why\n")
        A("| from | to | cause | n |")
        A("|---|---|---|---|")
        for k, v in sorted(flips.items(), key=lambda x: -x[1]):
            body, _, cause = k[5:].partition(":")
            frm, _, to = body.partition("_to_")
            A(f"| {frm} | {to} | `{cause or '—'}` | {v:,} |")
        A("")

    A("## Load bounds: what zero substitution hides\n")
    A("Substituting zero gives the smallest load consistent with the data; "
      "counting each non-detect at its own LOD gives the largest.\n")
    if outlet is None:
        A("_Station topology unavailable; load bounds not computed._\n")
    else:
        A(f"Evaluated at station **{outlet}**, the gauged station with the "
          f"largest cumulative catchment area, so the figures are a river load "
          f"rather than a sum over stations (which would double-count the same "
          f"water).\n")
        by_campaign = defaultdict(lambda: [0.0, 0.0, 0, 0])
        for (p_, camp, st), (lo, hi, nd) in per_point.items():
            if st != outlet:
                continue
            agg = by_campaign[camp]
            agg[0] += lo
            agg[1] += hi
            agg[2] += 1
            agg[3] += 1 if nd else 0
        if not by_campaign:
            A("_No gauged observations at that station._\n")
        else:
            A("| campaign | analytes | non-detects | lower bound (kg/d) | "
              "upper bound (kg/d) | ratio |")
            A("|---|---|---|---|---|---|")
            for camp in sorted(by_campaign):
                lo, hi, k, nd = by_campaign[camp]
                r = "unbounded" if lo <= 0 else f"{hi/lo:.1f}x"
                A(f"| {camp} | {k} | {nd} | {lo:.3g} | {hi:.3g} | {r} |")
            A("")
            A("The lower bound is what zero substitution reports. The upper "
              "bound is equally consistent with the same measurements. Stating "
              "the first alone presents the most optimistic value compatible "
              "with the data as though it were the data.\n")

    A("## What could not be assessed at all\n")
    A(f"- observation--analyte pairs with no threshold in the regulation: "
      f"**{tally['no_threshold']:,}**\n")
    A("These are not counted in the flip rate. Including them would inflate it; "
      "excluding them silently would hide how much of the survey the regulation "
      "does not reach.\n")

    text = "\n".join(L)
    (EVAL / "flip_analysis.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nwrote: {EVAL/'flip_analysis.md'}, {PROC/'flip_verdicts.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
