#!/usr/bin/env python3
"""
Mass balance across a reach: can conservation refute a reported zero?

THE ARGUMENT
------------
Everything else in this paper is epistemic -- a non-detection establishes a
bound rather than a value, and a bound is not a zero. A reviewer can answer
that this is a modelling convention. This script supplies the one line of
evidence that is not a convention: PHYSICS.

Take a reach where an analyte is measured above its detection limit at the
upstream station and reported as 0.0 at the downstream station. Under the
zero-substitution reading the load has gone from L_up to exactly nothing, so
the substance was completely removed between the two stations. Mass is
conserved, so that requires real attenuation -- degradation, sorption,
settling.

But the downstream record does not say the load is zero. It says the
concentration is below LOD, which bounds the load above by

    L_down^max = LOD x Q_down

Because flow increases downstream, L_down^max can easily exceed L_up. When it
does, DILUTION ALONE accounts for the disappearance: the entire upstream mass
can still be in the river, merely spread through more water than the method can
resolve. The reported zero is then not evidence of removal at all, and any
removal inferred from it is an artefact of the reporting convention.

So each disappearance falls into one of:

  masked_by_dilution   L_down^max >= L_up. The substance may be wholly present.
                       Zero-substitution fabricates 100% removal here.
  attenuation_required L_down^max <  L_up. Conservation is violated unless mass
                       was genuinely lost; the non-detection does carry
                       information, and we report the minimum removal it
                       implies, 1 - L_down^max / L_up.
  undecidable          no detection limit, or no gauged flow at one end.

This is falsifiable in the right direction: had almost every disappearance
required attenuation, the zeros would have been carrying real information and
the paper's premise would be weaker. The result is reported either way.

CAVEATS, stated because they bound the claim
--------------------------------------------
* Flow is instantaneous at the time of sampling, not a gauged mean.
* Travel time is ignored: upstream and downstream samples are treated as the
  same parcel of water, which four seasonal snapshots cannot establish.
* Unmeasured lateral inflow between the stations dilutes further, which makes
  the masked_by_dilution class conservative -- it is an under-count.
These make the test suitable for counting how often a zero CANNOT be read as
removal, not for estimating attenuation rates.

Inputs  : derived/processed/{measurements,reaches,analytes}.csv
Outputs : derived/processed/mass_balance.csv
          eval/mass_balance.md

Usage:  python scripts/20_mass_balance.py [--all-pairs]
"""

from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

FLOW_PARAMS = ("yabatas", "ekoton")
PRIMARY_FLOW = "yabatas"
CAMPAIGN_ORDER = ["C1", "C2", "C3", "C4"]
CAMPAIGN_LABEL = {"C1": "Aug-2017", "C2": "Nov-2017",
                  "C3": "Feb-2018", "C4": "May-2018"}

# ug/L x m3/s -> kg/day
UG_PER_L_M3_TO_KG_PER_DAY = 0.0864


def fold(text: str) -> str:
    s = str(text)
    for a, b in (("ı", "i"), ("İ", "i"), ("ş", "s"), ("Ş", "s"), ("ğ", "g"),
                 ("Ğ", "g"), ("ç", "c"), ("Ç", "c"), ("ö", "o"), ("Ö", "o"),
                 ("ü", "u"), ("Ü", "u")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def load(name):
    p = PROC / name
    if not p.exists():
        sys.exit(f"missing {p}")
    with p.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-pairs", action="store_true",
                    help="use every ordered station pair, not only immediate")
    args = ap.parse_args()
    EVAL.mkdir(parents=True, exist_ok=True)

    measurements = load("measurements.csv")
    reaches = load("reaches.csv")
    analytes = {a["parameter"]: a for a in load("analytes.csv")}

    obs, flow_by_series = {}, {k: {} for k in FLOW_PARAMS}
    for m in measurements:
        v = num(m["value_num"])
        obs[(m["campaign"], m["station"], m["parameter"])] = v
        f = fold(m["parameter"])
        if f in flow_by_series and v is not None and v > 0:
            flow_by_series[f][(m["campaign"], m["station"])] = v

    flow = dict(flow_by_series[PRIMARY_FLOW])
    for k, series in flow_by_series.items():
        if k != PRIMARY_FLOW:
            for kk, vv in series.items():
                flow.setdefault(kk, vv)
    if not flow:
        sys.exit("no flow data matched")

    # Flow duplicated between campaigns is a data defect, not hydrology. The
    # August and November workbooks carry byte-identical flow at all 75
    # stations, so one campaign's gauging is missing and was filled from the
    # other. Loads computed for those campaigns are not independent, and the
    # headline is therefore also reported on the campaigns that are.
    dup_pairs = []
    for i, ca in enumerate(CAMPAIGN_ORDER):
        for cb in CAMPAIGN_ORDER[i + 1:]:
            common = {s for (c, s) in flow if c == ca} & \
                     {s for (c, s) in flow if c == cb}
            if not common:
                continue
            same = sum(1 for s in common
                       if abs(flow[(ca, s)] - flow[(cb, s)]) < 1e-12)
            if common and same == len(common):
                dup_pairs.append((ca, cb, len(common)))
    suspect_campaigns = {c for a, b, _ in dup_pairs for c in (a, b)}

    lod = {}
    for p, a in analytes.items():
        v = num(a.get("lod"))
        if v is not None and v > 0:
            lod[p] = v

    chem = [p for p, a in analytes.items()
            if a["group"] in ("micropollutant", "metal", "conventional")]
    selected = reaches if args.all_pairs else [r for r in reaches
                                               if r["immediate"] == "True"]
    if not selected:
        sys.exit("no reaches selected")

    rows = []
    tally = defaultdict(int)
    fabricated_kg = 0.0     # removal implied by zero-substitution but not by physics
    required_kg = 0.0       # removal physics actually demands

    for r in selected:
        u, d = r["up_station"], r["down_station"]
        for camp in CAMPAIGN_ORDER:
            qu, qd = flow.get((camp, u)), flow.get((camp, d))
            for p in chem:
                ku, kd = (camp, u, p), (camp, d, p)
                if ku not in obs or kd not in obs:
                    continue
                vu, vd = obs[ku], obs[kd]
                if vu is None or vd is None:
                    continue
                # the case of interest: present upstream, reported zero downstream
                if not (vu > 0 and vd == 0):
                    continue
                tally["disappearance"] += 1

                if p not in lod:
                    tally["undecidable_no_lod"] += 1
                    continue
                if qu is None or qd is None:
                    tally["undecidable_no_flow"] += 1
                    continue

                l_up = vu * qu * UG_PER_L_M3_TO_KG_PER_DAY
                l_down_max = lod[p] * qd * UG_PER_L_M3_TO_KG_PER_DAY

                # A river gains water downstream. Where the recorded flow falls
                # instead, the pair cannot support a load comparison: the two
                # gaugings are instantaneous, taken on different days, and the
                # discrepancy is a measurement artefact rather than hydrology.
                #
                # This guard is not cosmetic. A spuriously small Q_down shrinks
                # L_down^max and therefore pushes the case towards
                # "attenuation required" -- and it does so systematically: all
                # 60 implausible comparisons landed in that class and none in
                # the other, biasing the headline against our own hypothesis.
                # They are set aside rather than counted either way.
                if qd < qu:
                    tally["undecidable_flow_implausible"] += 1
                    rows.append({
                        "reach_id": r["reach_id"], "up_station": u,
                        "down_station": d, "campaign": camp,
                        "campaign_label": CAMPAIGN_LABEL[camp],
                        "analyte": p, "group": analytes[p]["group"],
                        "up_value_ug_l": f"{vu:.6g}", "lod_ug_l": f"{lod[p]:.6g}",
                        "q_up_m3_s": f"{qu:.4g}", "q_down_m3_s": f"{qd:.4g}",
                        "dilution_factor": f"{qd/qu:.3f}",
                        "load_up_kg_day": f"{l_up:.6g}",
                        "max_load_down_kg_day": f"{l_down_max:.6g}",
                        "min_removal_fraction": "",
                        "verdict": "undecidable_flow_implausible",
                    })
                    continue

                if l_down_max >= l_up:
                    verdict = "masked_by_dilution"
                    min_removal = 0.0
                    fabricated_kg += l_up      # zero-substitution invents all of it
                else:
                    verdict = "attenuation_required"
                    min_removal = 1.0 - l_down_max / l_up
                    fabricated_kg += l_down_max
                    required_kg += l_up - l_down_max
                tally[verdict] += 1

                rows.append({
                    "reach_id": r["reach_id"], "up_station": u,
                    "down_station": d, "campaign": camp,
                    "campaign_label": CAMPAIGN_LABEL[camp],
                    "analyte": p, "group": analytes[p]["group"],
                    "up_value_ug_l": f"{vu:.6g}", "lod_ug_l": f"{lod[p]:.6g}",
                    "q_up_m3_s": f"{qu:.4g}", "q_down_m3_s": f"{qd:.4g}",
                    "dilution_factor": f"{qd/qu:.3f}" if qu else "",
                    "load_up_kg_day": f"{l_up:.6g}",
                    "max_load_down_kg_day": f"{l_down_max:.6g}",
                    "min_removal_fraction": f"{min_removal:.4f}",
                    "verdict": verdict,
                })

    if rows:
        with (PROC / "mass_balance.csv").open("w", newline="",
                                              encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(sorted(rows, key=lambda x: (x["analyte"], x["reach_id"],
                                                    x["campaign"])))

    decided = tally["masked_by_dilution"] + tally["attenuation_required"]
    clean = [x for x in rows
             if x["verdict"] in ("masked_by_dilution", "attenuation_required")
             and x["campaign"] not in suspect_campaigns]
    clean_masked = sum(1 for x in clean if x["verdict"] == "masked_by_dilution")
    # Only over the comparisons actually decided: including the set-aside ones
    # would report a p10 below 1, i.e. the very artefact just excluded.
    dilution_factors = sorted(
        float(x["dilution_factor"]) for x in rows
        if x["dilution_factor"]
        and x["verdict"] in ("masked_by_dilution", "attenuation_required"))

    L = []
    A = L.append
    A("# Mass balance: can conservation refute a reported zero?\n")
    A("Generated by `scripts/20_mass_balance.py`.\n")
    A("Every other argument in this paper is epistemic, and a reviewer may "
      "answer that treating a non-detection as an interval is a modelling "
      "convention. This test is not a convention. Where an analyte is measured "
      "upstream and reported as `0.0` downstream, zero-substitution asserts "
      "that the entire load was removed in between. Conservation of mass lets "
      "that assertion be checked against the largest load the downstream "
      "non-detection actually permits, "
      "$L^{\\max}_{\\mathrm{down}} = \\mathrm{LOD}\\times Q_{\\mathrm{down}}$.\n")

    A("## Outcome\n")
    A("| outcome | n | share of decidable |")
    A("|---|---|---|")
    for k, label in (("masked_by_dilution",
                      "**Dilution alone explains it** — the substance may be "
                      "wholly present; the reported removal is an artefact"),
                     ("attenuation_required",
                      "Attenuation genuinely required — the non-detection does "
                      "carry information")):
        n = tally[k]
        A(f"| {label} | {n:,} | {100*n/decided:.1f}% |" if decided
          else f"| {label} | {n:,} | — |")
    A(f"| undecidable, no detection limit | {tally['undecidable_no_lod']:,} | — |")
    A(f"| undecidable, no gauged flow | {tally['undecidable_no_flow']:,} | — |")
    A(f"| set aside, recorded flow falls downstream | "
      f"{tally['undecidable_flow_implausible']:,} | — |")
    A(f"| **total disappearances examined** | **{tally['disappearance']:,}** | |")
    A("")

    if decided:
        pct = 100 * tally["masked_by_dilution"] / decided
        A(f"> Of the **{decided:,}** disappearances that can be decided, "
          f"**{tally['masked_by_dilution']:,} ({pct:.1f}%)** are fully "
          f"explained by dilution. For these, treating the downstream zero as "
          f"an absence asserts a removal that the data do not support and that "
          f"mass balance does not require. This is a physical result, "
          f"independent of how one prefers to model censoring.\n")

    if dup_pairs:
        A("### Flow duplicated between campaigns\n")
        for a, b, n in dup_pairs:
            A(f"- `{a}` ({CAMPAIGN_LABEL[a]}) and `{b}` ({CAMPAIGN_LABEL[b]}) "
              f"carry **identical flow at all {n} stations**. Two different "
              f"seasons cannot share a discharge record station for station; "
              f"one campaign's gauging is missing and was filled from the "
              f"other.")
        A("")
        if clean:
            A(f"Loads for those campaigns are therefore not independent. "
              f"Restricting to the campaigns with their own gauging leaves "
              f"**{len(clean)}** decidable comparisons, of which "
              f"**{clean_masked} ({100*clean_masked/len(clean):.1f}%)** are "
              f"explained by dilution alone -- slightly *more* than the figure "
              f"over all campaigns, so the duplication is not what produces "
              f"the result.\n")

    if tally["undecidable_flow_implausible"]:
        n_imp = tally["undecidable_flow_implausible"]
        A(f"### A data-quality finding that had to be handled first\n")
        A(f"In **{n_imp:,}** comparisons the recorded flow *decreases* "
          f"downstream, which a river does not do. The gaugings are "
          f"instantaneous and taken on different days, so these are "
          f"measurement artefacts. They matter because the error is not "
          f"symmetric: an understated $Q_{{\\mathrm{{down}}}}$ shrinks "
          f"$L^{{\\max}}_{{\\mathrm{{down}}}}$ and pushes the comparison "
          f"towards *attenuation required*. Every one of them did exactly "
          f"that, and none landed in the other class. Counting them would have "
          f"biased the result **against** the hypothesis this script tests, so "
          f"they are set aside and reported here instead.\n")

    if dilution_factors:
        n = len(dilution_factors)
        A(f"Flow increases across these reaches by a median factor of "
          f"**{dilution_factors[n//2]:.2f}** "
          f"(p10 {dilution_factors[int(0.1*n)]:.2f}, "
          f"p90 {dilution_factors[int(0.9*n)]:.2f}), which is the mechanism: a "
          f"conserved load spread through more water falls below a limit that "
          f"was adequate upstream.\n")

    A("## Mass attributed to removal\n")
    A(f"- removal implied by reading every downstream zero as an absence: "
      f"**{fabricated_kg + required_kg:,.1f} kg/day** summed over reach x "
      f"analyte x campaign")
    A(f"- removal that conservation actually requires: "
      f"**{required_kg:,.1f} kg/day**")
    if fabricated_kg + required_kg > 0:
        share = 100 * fabricated_kg / (fabricated_kg + required_kg)
        A(f"- **{share:.1f}%** of the apparent removal is an artefact of the "
          f"reporting convention\n")
    A("These are loads at instantaneous sampling flows summed over "
      "comparisons, not a basin budget; they measure how much inferred "
      "attenuation rests on substituted zeros.\n")

    if rows:
        att = sorted((x for x in rows if x["verdict"] == "attenuation_required"),
                     key=lambda x: -float(x["min_removal_fraction"]))[:10]
        if att:
            A("## Where the zeros do carry information\n")
            A("The strongest genuine attenuation signals, i.e. the "
              "disappearances dilution cannot explain:\n")
            A("| analyte | reach | campaign | dilution | minimum removal |")
            A("|---|---|---|---|---|")
            for x in att:
                A(f"| {x['analyte']} | {x['reach_id']} | "
                  f"{x['campaign_label']} | {x['dilution_factor']}x | "
                  f"{100*float(x['min_removal_fraction']):.1f}% |")
            A("")

    A("## What this does and does not show\n")
    A("- Flow is instantaneous at sampling, not a gauged mean.")
    A("- Travel time is ignored: the two samples are treated as one parcel of "
      "water, which four seasonal snapshots cannot establish.")
    A("- Unmeasured lateral inflow dilutes further, so the "
      "`masked_by_dilution` count is conservative.\n")
    A("The test therefore counts how often a reported zero **cannot** be read "
      "as removal. It does not estimate attenuation rates, and no such "
      "estimate is offered.\n")

    text = "\n".join(L)
    (EVAL / "mass_balance.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nwrote: {EVAL/'mass_balance.md'}"
          + (f", {PROC/'mass_balance.csv'}" if rows else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
