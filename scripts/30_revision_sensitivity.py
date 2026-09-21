#!/usr/bin/env python3
"""
Three objections a referee raised against the Waterbase headline, measured.

WHY THIS FILE EXISTS
--------------------
The headline is that 43.8 % of the 696,168 assessable river station-years cannot
be decided from the record as reported. A referee reading only the PDF made
three objections that the data can answer and the manuscript cannot:

  (A) PRECONDITION. 18.8 % of the assessments are PreconditionUnmet because
      cadmium's standard depends on water hardness and lead's and nickel's on
      bioavailability, and WISE-6 "reports none of them on the row". On the row
      is true. In the release it is not: hardness, calcium, magnesium, pH and
      dissolved organic carbon are reported as determinands of their own, at
      the same station, in the same year. So the question is how many of those
      verdicts a join recovers, and it is answered here rather than argued.

      Cadmium. With a hardness for the station-year the class standard is
      known and the ordinary decision applies. Without one the verdict can
      still be reached when it is the same under EVERY class -- a result that
      clears the strictest class standard clears all five, and one that
      exceeds the most permissive exceeds all five. That is not a convention:
      it is the interval over the condition, the same move the vocabulary
      makes over the measurement.

      Lead and nickel. A bioavailable concentration never exceeds the dissolved
      one, and a dissolved concentration never exceeds the total. So a result
      that clears the bioavailable standard on whatever fraction was measured
      is compliant whatever the local chemistry is -- the first tier of the
      Water Framework Directive guidance on bioavailability, applied without a
      biotic ligand model. An apparent exceedance cannot be affirmed without
      one, and stays indeterminate; how many of those carry pH and DOC, so that
      a model could be run, is counted and not pretended.

      Matrix. The metal standards refer to the dissolved concentration. An
      exceedance on a whole-water result is therefore not affirmable for these
      three metals, and is kept indeterminate even where the class is known.

  (B) COMPOSITION. Spain supplies a large part of the assessed rows, and the
      reporters change across the record. The headline share is recomputed
      without Spain, with every country weighted equally, and leaving each
      country out in turn; and the 2012 -> 2013 fall in rows declaring neither
      a flag nor a limit, which the manuscript calls "a step", is decomposed
      into the reporters present on both sides of it and those who were not.

  (C) PLAUSIBILITY. A chlorpyrifos quantification limit of 50 ug/L against a
      standard of 0.00046 ug/L is 108,696 times the standard, and looks like a
      unit slip. Every limit is screened against the other limits reported for
      the same substance; the rows that fail are counted, named, and the
      headline is recomputed without them and with them divided by 1000.

The decision procedure is IMPORTED from 22_waterbase_external, not restated, so
that every number here differs from the headline only by the change it names.

Inputs  : Data/waterbase/WISE6_AggregatedData-csv.zip (or --file)
          derived/processed/eu_eqs.csv
Outputs : derived/processed/revision_sensitivity.json
          eval/revision_sensitivity.md

Usage:  python scripts/30_revision_sensitivity.py [--file <zip>] [--limit N]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
DATA = ROOT / "Data" / "waterbase"
EVAL = ROOT / "eval"

sys.path.insert(0, str(Path(__file__).resolve().parent))
_m = __import__("22_waterbase_external")
open_rows, pick, num, norm = _m.open_rows, _m.pick, _m.num, _m.norm
TO_UG_L, verify_digest = _m.TO_UG_L, _m.verify_digest
detection_status, censo_outcome = _m.detection_status, _m.censo_outcome
two_valued, SUBSTITUTIONS = _m.two_valued, _m.SUBSTITUTIONS
conditional_thresholds = _m.conditional_thresholds

CD, PB, NI = "7440-43-9", "7439-92-1", "7440-02-0"

# Annex I, footnote 9, and the inland annual-average column for No 6, read from
# refs/legal/EU-2008-105_consolidated-2026-05-10.pdf. Class 1 is printed as
# "<= 0,08": a Member State may set it lower, so a compliant verdict reached at
# 0.08 is compliant against the Annex value and not necessarily against a
# stricter national one. That caveat is carried into the report.
CD_CLASSES = ((40.0, 0.08), (50.0, 0.08), (100.0, 0.09), (200.0, 0.15),
              (math.inf, 0.25))
CD_T_MIN, CD_T_MAX = 0.08, 0.25

# Co-parameters, by WISE-6 determinand code.
HARDNESS, CALCIUM, MAGNESIUM = "EEA_31-01-6", "CAS_7440-70-2", "CAS_7439-95-4"
PH, DOC = "EEA_3152-01-0", "EEA_3133-05-9"
# Hardness as CaCO3 from calcium and magnesium in mg/L (molar-mass ratios
# 100.09/40.08 and 100.09/24.31).
CA_TO_CACO3, MG_TO_CACO3 = 2.497, 4.118
HARDNESS_TO_MG_CACO3 = {"mg{caco3}/l": 1.0, "mg/l": 1.0, "mmol/l": 100.09}

UNDECIDABLE = ("possible_exceedance", "precondition_unmet",
               "method_insufficient", "indeterminate_unresolved",
               "indeterminate_other")
AFFIRMED = "exceedance"

# (C) A limit is implausible for its substance when it sits at least this many
# decades above the median limit reported for that substance. Three decades is
# the signature of a mg/ug or ug/ng slip; two is reported as the looser screen.
SLIP_DECADES = 3.0
LOOSE_DECADES = 2.0
MIN_LIMITS_PER_SUBSTANCE = 50

# (B) A country's share is only reported when it rests on this many rows.
MIN_COUNTRY_ROWS = 2000


def cd_class_standard(h):
    for upper, t in CD_CLASSES:
        if h < upper:
            return t
    return CD_T_MAX


def is_dissolved(matrix):
    return "DIS" in matrix.upper()


def share(counts, keys=UNDECIDABLE):
    n = sum(counts.values())
    return 100.0 * sum(counts.get(k, 0) for k in keys) / n if n else float("nan")


def resolve_metal(r, eqs, cop):
    """The outcome for a Cd/Pb/Ni row once the co-parameters are joined.

    Returns (outcome, route). The outcome keys are 22's, so the tallies add up
    against the headline; route says which rule decided it.
    """
    cas, status, v, l, matrix = r["cas"], r["status"], r["v"], r["l"], r["matrix"]
    status, v = art52(status, v, l)
    c = cop.get((r["site"], r["year"]), {})
    # the bound test and Article 5(2) first, exactly as assess() asks them, so
    # this function and the cumulative scenarios cannot diverge -- the assertion
    # in main() compares them on every run and stopped this script when they did
    probe = bare(status, v, l, eqs[cas])
    if probe in ("indeterminate_unresolved", "indeterminate_other"):
        return probe, "no bound established"
    if cas == CD:
        h = c.get("hardness")
        route = "hardness"
        if h is None and c.get("ca") is not None and c.get("mg") is not None:
            h = CA_TO_CACO3 * c["ca"] + MG_TO_CACO3 * c["mg"]
            route = "ca+mg"
        if h is not None:
            o = bare(status, v, l, cd_class_standard(h))
        else:
            lo = bare(status, v, l, CD_T_MIN)
            hi = bare(status, v, l, CD_T_MAX)
            if lo == hi and lo in ("compliant", "exceedance"):
                o, route = lo, "invariant-over-classes"
            else:
                return "precondition_unmet", "no-hardness"
        if o in ("exceedance", "possible_exceedance") and not is_dissolved(matrix):
            return "precondition_unmet", "total-not-dissolved"
        return o, route
    # lead, nickel: bioavailable <= dissolved <= total
    o = bare(status, v, l, eqs[cas])
    if o == "compliant":
        return "compliant", "tier1-clears-bioavailable"
    if o == "method_insufficient":
        return "method_insufficient", "tier1-limit-above-standard"
    blm = c.get("ph") is not None and c.get("doc") is not None
    return "precondition_unmet", ("needs-BLM:pH+DOC-present" if blm
                                  else "needs-BLM:pH/DOC-missing")


# THE JOIN AND THE RULES ARE DIFFERENT CHANGES, and the headline has to say how
# much of its movement each one owns. Joining a covariate the release reports
# is DATA: the existing question "is the precondition satisfied?" is answered
# more often, and the decision procedure is unchanged. Deciding without the
# covariate -- a verdict that is the same under every hardness class, or a
# bioavailable concentration that cannot exceed the measured one -- is LOGIC,
# and it changes the procedure. So the four steps are counted cumulatively.
SCENARIOS = ("data join only", "+ verdict invariant over the classes",
             "+ bioavailability tier 1", "+ dissolved-fraction rule")
GUIDANCE = "guidance-bounded (headline)"


def bare(status, v, l, thr):
    """The comparison with no applicability step, through assess().

    Imported rather than restated, so that every scenario here carries the
    bound test and Article 5(2) exactly as the headline does and differs from
    it only by the rule the row is named for. Calling censo_outcome() directly
    -- which this did until the headline gained both -- made the first column
    of the table a different procedure from the last.
    """
    return _m.assess(status, v, l, thr, cas="", condition=None,
                     fraction_rule=False)[0]


def art52(status, v, l):
    """Article 5(2) of Directive 2009/90/EC, as assess() applies it.

    A mean below its own limit is a '<LOQ' result. assess() converts it before
    anything else, and the metal branches here have to convert it too: without
    this, five rows whose value sits a floating-point step under their own limit
    (0.3 against 0.30000001) were Compliant in the headline and
    PreconditionUnmet in this table, which is exactly the kind of drift the two
    columns exist to rule out.
    """
    if status == "quantified" and v is not None and l is not None and v < l:
        return "censored", None
    return status, v


def scenario_outcomes(r, eqs, cop):
    """{scenario: outcome} for one Cd/Pb/Ni row, cumulative in SCENARIOS order."""
    cas, status, v, l = r["cas"], r["status"], r["v"], r["l"]
    status, v = art52(status, v, l)
    c = cop.get((r["site"], r["year"]), {})
    out = {}
    if cas == CD:
        h = c.get("hardness")
        if h is None and c.get("ca") is not None and c.get("mg") is not None:
            h = CA_TO_CACO3 * c["ca"] + MG_TO_CACO3 * c["mg"]
        if h is not None:
            o1 = o2 = bare(status, v, l, cd_class_standard(h))
        else:
            o1 = bare(status, v, l, CD_T_MIN)
            o1 = o1 if o1 in ("indeterminate_unresolved",
                              "indeterminate_other") else "precondition_unmet"
            lo = bare(status, v, l, CD_T_MIN)
            hi = bare(status, v, l, CD_T_MAX)
            o2 = lo if (lo == hi and lo in ("compliant", "exceedance",
                                            "indeterminate_unresolved",
                                            "indeterminate_other")) \
                else "precondition_unmet"
        o3 = o2
    else:
        t = bare(status, v, l, eqs[cas])
        o1 = o2 = (t if t in ("indeterminate_unresolved", "indeterminate_other")
                   else "precondition_unmet")
        o3 = t if t in ("compliant", "method_insufficient",
                        "indeterminate_unresolved",
                        "indeterminate_other") else "precondition_unmet"
    o4 = o3
    if o4 in ("exceedance", "possible_exceedance") and not is_dissolved(r["matrix"]):
        o4 = "precondition_unmet"
    out = dict(zip(SCENARIOS, (o1, o2, o3, o4)))
    # THE HEADLINE READING: only what a cited source sanctions. Cadmium's class
    # standard where hardness is known (CIS Guidance No. 38, Tier 2); lead and
    # nickel compared with the bioavailable standard on a DISSOLVED result only
    # (Guidance No. 38, section 2.2.1, Tier 1); and the metal standards read as
    # dissolved concentrations (Directive 2008/105/EC, Annex I Part B point 3),
    # so no verdict other than a pass rests on a whole-water result. The
    # invariant-over-classes verdict and a pass on total metal are our own
    # reasoning and stay in the cumulative rows above as sensitivities.
    dissolved = is_dissolved(r["matrix"])
    if o4 in ("indeterminate_unresolved", "indeterminate_other"):
        out[GUIDANCE] = o4
        return out
    if cas == CD:
        # dissolved only, as for lead and nickel: a pass on a whole-water result
        # (total >= dissolved) is our reasoning, not the Directive's, and the
        # first version of this row allowed it for cadmium and not for the other
        # two -- two different rules for one provision
        g = o1 if dissolved else "precondition_unmet"
    else:
        t = bare(status, v, l, eqs[cas])
        g = (t if dissolved and t in ("compliant", "method_insufficient")
             else "precondition_unmet")
    if g in ("exceedance", "possible_exceedance") and not dissolved:
        g = "precondition_unmet"
    out[GUIDANCE] = g
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report-only", action="store_true",
                    help="re-render eval/revision_sensitivity.md from the JSON")
    args = ap.parse_args()
    if args.report_only:
        with (PROC / "eu_eqs.csv").open(encoding="utf-8") as fh:
            write_report(json.loads((PROC / "revision_sensitivity.json")
                                    .read_text(encoding="utf-8")),
                         list(csv.DictReader(fh)))
        return 0

    path = Path(args.file) if args.file else DATA / "WISE6_AggregatedData-csv.zip"
    print(f"reading {path.name}")
    if not args.limit:
        verify_digest(path)

    eqs = {}
    with (PROC / "eu_eqs.csv").open(encoding="utf-8") as fh:
        eqs_rows = list(csv.DictReader(fh))
    for r in eqs_rows:
        if r.get("is_group") == "True":
            continue
        v = num(r.get("aa_inland"))
        if not v:
            continue
        for c in (r.get("all_cas") or "").replace(" ", "").split(";"):
            if c:
                eqs.setdefault(c, v)
    cond = {c: k for c, k in conditional_thresholds(eqs_rows).items() if c in eqs}
    assert {CD, PB, NI} <= set(cond), f"conditional set changed: {cond}"

    rows = open_rows(path)
    header = next(rows)
    col = pick(header)
    idx = {norm(h): i for i, h in enumerate(header)}
    i_matrix = idx.get("procedureanalysedmatrix")

    def get(row, role):
        i = col.get(role)
        return row[i].strip() if i is not None and i < len(row) else ""

    assessed = []                       # one dict per assessed row
    cop_raw = defaultdict(lambda: defaultdict(list))
    silent_cy = defaultdict(lambda: [0, 0])     # (country, year) -> [silent, n]
    n = kept = 0
    for row in rows:
        if not row:
            continue
        n += 1
        if args.limit and n > args.limit:
            break
        if n % 2_000_000 == 0:
            print(f"    {n:,} rows read")
        if "category" in col and get(row, "category") not in ("RW", ""):
            continue
        kept += 1
        code = get(row, "code")
        site = get(row, "site")
        year = get(row, "year")[:4]
        cty = get(row, "country") or "??"
        val = num(get(row, "value"))
        loq = num(get(row, "loq"))
        uom = get(row, "uom").lower().replace(" ", "")

        if year.isdigit():
            s = silent_cy[(cty, int(year))]
            s[1] += 1
            if get(row, "below_loq") == "" and loq is None:
                s[0] += 1

        if code in (HARDNESS, CALCIUM, MAGNESIUM, PH, DOC) and val is not None:
            if code == HARDNESS:
                f = HARDNESS_TO_MG_CACO3.get(uom)
                if f and val > 0:
                    cop_raw[(site, year)]["hardness"].append(val * f)
            elif code in (CALCIUM, MAGNESIUM):
                f = {"mg/l": 1.0, "ug/l": 1e-3}.get(uom)
                if f and val > 0:
                    cop_raw[(site, year)]["ca" if code == CALCIUM else "mg"] \
                        .append(val * f)
            elif code == PH and 0 < val < 14:
                cop_raw[(site, year)]["ph"].append(val)
            elif code == DOC and val > 0:
                cop_raw[(site, year)]["doc"].append(val)
            continue

        cas = code[4:] if code.upper().startswith("CAS_") else ""
        factor = TO_UG_L.get(uom)
        if cas not in eqs or factor is None:
            continue
        thr = eqs[cas]
        v_ug = val * factor if val is not None else None
        l_ug = loq * factor if loq is not None else None
        status = detection_status(get(row, "below_loq"), v_ug, l_ug)
        outcome = censo_outcome(status, v_ug, l_ug, thr,
                                precondition=cond.get(cas))
        half = two_valued(v_ug, l_ug, status == "censored", thr, 0.5)
        assessed.append({
            "cas": cas, "site": site, "year": year, "cty": cty,
            "status": status, "v": v_ug, "l": l_ug, "thr": thr,
            "matrix": (row[i_matrix].strip() if i_matrix is not None
                       and i_matrix < len(row) else ""),
            "outcome": outcome, "half": half,
            "flag": get(row, "below_loq"),
        })
    print(f"  {n:,} rows read, {kept:,} river rows, {len(assessed):,} assessed")

    cop = {k: {p: statistics.fmean(vs) for p, vs in d.items()}
           for k, d in cop_raw.items()}

    base = defaultdict(int)
    for r in assessed:
        base[r["outcome"]] += 1
    N = len(assessed)
    out = {"assessed": N, "baseline": dict(base),
           "baseline_undecidable_pct": share(base)}

    # ------------------------------------------------ the half-LOQ funnel ----
    funnel = defaultdict(int)
    for r in assessed:
        if r["half"] == "exceeding":
            funnel[r["outcome"]] += 1
    out["half_loq_exceedances_by_outcome"] = dict(funnel)

    # ------------------------------------------------ (A) the join ----------
    joined = defaultdict(int)
    routes = defaultdict(lambda: defaultdict(int))
    moved = defaultdict(int)
    matrices = defaultdict(lambda: defaultdict(int))
    scen = {s: defaultdict(int) for s in SCENARIOS + (GUIDANCE,)}
    for r in assessed:
        if r["cas"] in (CD, PB, NI):
            for s, o_s in scenario_outcomes(r, eqs, cop).items():
                scen[s][o_s] += 1
        else:
            # A substance with no applicability condition is the same verdict in
            # every scenario -- but it is assess()'s verdict, not the row-level
            # one. Carrying r["outcome"] here left the unflagged means Article
            # 5(2) reclassifies in their row-level class, so the guidance row
            # disagreed with the headline by 41 assessments in a table whose
            # whole point is that it differs from the headline only by the rule
            # each row names.
            o_ = bare(r["status"], r["v"], r["l"], r["thr"])
            for s in scen:
                scen[s][o_] += 1
    for r in assessed:
        # the same reason as in the scenario loop: outside the conditional
        # metals the join changes nothing, but the verdict is still assess()'s
        o = bare(r["status"], r["v"], r["l"], r["thr"])
        if r["cas"] in (CD, PB, NI):
            matrices[r["cas"]][r["matrix"] or "(blank)"] += 1
            o2, route = resolve_metal(r, eqs, cop)
            routes[r["cas"]][f"{route} -> {o2}"] += 1
            moved[(o, o2)] += 1
            o = o2
        r["joined"] = o
        joined[o] += 1
    out["join"] = {
        "outcomes": dict(joined),
        "undecidable_pct": share(joined),
        "routes": {k: dict(v) for k, v in routes.items()},
        "transitions": {f"{a} -> {b}": c for (a, b), c in moved.items()},
        "matrix": {k: dict(v) for k, v in matrices.items()},
        "scenarios": {s: {"outcomes": dict(d), "undecidable_pct": share(d)}
                      for s, d in scen.items()},
    }
    assert scen[SCENARIOS[-1]] == joined, \
        "the cumulative scenarios and resolve_metal() disagree"

    # ------------------------------------------------ (B) composition -------
    by_c = defaultdict(lambda: defaultdict(int))
    for r in assessed:
        by_c[r["cty"]][r["outcome"]] += 1
    big = {c: d for c, d in by_c.items() if sum(d.values()) >= MIN_COUNTRY_ROWS}
    per_country = {c: {"n": sum(d.values()), "undecidable_pct": share(d),
                       "affirmed": d.get(AFFIRMED, 0)}
                   for c, d in sorted(by_c.items(),
                                      key=lambda kv: -sum(kv[1].values()))}

    def pooled(exclude=()):
        agg = defaultdict(int)
        for c, d in by_c.items():
            if c in exclude:
                continue
            for k, v in d.items():
                agg[k] += v
        return agg

    loo = {c: share(pooled({c})) for c in big}
    no_es = pooled({"ES"})
    shares_big = [share(d) for d in big.values()]
    out["composition"] = {
        "countries_assessed": len(by_c),
        "countries_over_floor": len(big),
        "floor": MIN_COUNTRY_ROWS,
        "per_country": per_country,
        "without_ES": {"n": sum(no_es.values()), "undecidable_pct": share(no_es),
                       "affirmed": no_es.get(AFFIRMED, 0)},
        "equal_weight_mean_pct": statistics.fmean(shares_big),
        "equal_weight_median_pct": statistics.median(shares_big),
        "leave_one_out_min": min(loo.items(), key=lambda kv: kv[1]),
        "leave_one_out_max": max(loo.items(), key=lambda kv: kv[1]),
    }
    # the same, after the join, because that is the number that will be quoted
    by_cj = defaultdict(lambda: defaultdict(int))
    for r in assessed:
        by_cj[r["cty"]][r["joined"]] += 1
    agg = defaultdict(int)
    for c, d in by_cj.items():
        if c != "ES":
            for k, v in d.items():
                agg[k] += v
    out["composition"]["joined_without_ES_pct"] = share(agg)
    out["composition"]["joined_equal_weight_mean_pct"] = statistics.fmean(
        [share(d) for c, d in by_cj.items() if c in big])

    # the "step": 2012 -> 2013, silent rows, split by who was present
    def yr(y):
        return {c: v for (c, yy), v in silent_cy.items() if yy == y}
    y12, y13 = yr(2012), yr(2013)
    both = set(y12) & set(y13)
    step = {}
    for label, cs12, cs13 in (("all reporters", set(y12), set(y13)),
                              ("present in both years", both, both)):
        s12 = sum(y12[c][0] for c in cs12); n12 = sum(y12[c][1] for c in cs12)
        s13 = sum(y13[c][0] for c in cs13); n13 = sum(y13[c][1] for c in cs13)
        step[label] = {"2012": [s12, n12, 100 * s12 / n12 if n12 else None],
                       "2013": [s13, n13, 100 * s13 / n13 if n13 else None],
                       "countries_2012": len(cs12), "countries_2013": len(cs13)}
    step["only_2012"] = {c: y12[c] for c in sorted(set(y12) - both)}
    step["only_2013"] = {c: y13[c] for c in sorted(set(y13) - both)}
    step["both_detail"] = {c: {"2012": y12[c], "2013": y13[c]}
                           for c in sorted(both)}
    out["step_2012_2013"] = step

    # undecidable share by year, all vs without ES, over the plotted window
    by_y = defaultdict(lambda: defaultdict(int))
    by_y_noes = defaultdict(lambda: defaultdict(int))
    ctys_y = defaultdict(set)
    for r in assessed:
        if not r["year"].isdigit():
            continue
        y = int(r["year"])
        by_y[y][r["outcome"]] += 1
        ctys_y[y].add(r["cty"])
        if r["cty"] != "ES":
            by_y_noes[y][r["outcome"]] += 1
    out["by_year"] = {
        y: {"n": sum(by_y[y].values()), "undecidable_pct": share(by_y[y]),
            "n_without_ES": sum(by_y_noes[y].values()),
            "undecidable_without_ES_pct": share(by_y_noes[y]),
            "countries": len(ctys_y[y]),
            "ES_share_pct": 100 * (1 - sum(by_y_noes[y].values())
                                   / sum(by_y[y].values()))}
        for y in sorted(by_y) if 2000 <= y}

    # ------------------------------------------------ (C) plausibility ------
    limits = defaultdict(list)
    for r in assessed:
        if r["l"] is not None and r["l"] > 0:
            limits[r["cas"]].append(math.log10(r["l"]))
    med = {c: statistics.median(v) for c, v in limits.items()
           if len(v) >= MIN_LIMITS_PER_SUBSTANCE}
    flagged = {"slip": [], "loose": []}
    for i, r in enumerate(assessed):
        if r["l"] is None or r["l"] <= 0 or r["cas"] not in med:
            continue
        d = math.log10(r["l"]) - med[r["cas"]]
        if d >= SLIP_DECADES:
            flagged["slip"].append(i)
        if d >= LOOSE_DECADES:
            flagged["loose"].append(i)
    plaus = {}
    for name, ids in flagged.items():
        ids_set = set(ids)
        kept_c = defaultdict(int)
        fixed_c = defaultdict(int)
        subs = defaultdict(int)
        ctys = defaultdict(int)
        moved_o = defaultdict(int)
        for i, r in enumerate(assessed):
            if i in ids_set:
                subs[r["cas"]] += 1
                ctys[r["cty"]] += 1
                moved_o[r["outcome"]] += 1
                l2 = r["l"] / 1000.0
                v2 = r["v"] / 1000.0 if (r["v"] is not None and
                                         r["flag"] == "1") else r["v"]
                o2 = censo_outcome(detection_status(r["flag"], v2, l2), v2, l2,
                                   r["thr"], precondition=cond.get(r["cas"]))
                fixed_c[o2] += 1
            else:
                kept_c[r["outcome"]] += 1
                fixed_c[r["outcome"]] += 1
        plaus[name] = {
            "decades_above_substance_median": (SLIP_DECADES if name == "slip"
                                               else LOOSE_DECADES),
            "rows": len(ids),
            "pct_of_assessed": 100 * len(ids) / N,
            "their_outcomes": dict(moved_o),
            "excluded_undecidable_pct": share(kept_c),
            "excluded_method_insufficient": kept_c.get("method_insufficient", 0),
            "divided_by_1000_undecidable_pct": share(fixed_c),
            "top_substances": sorted(subs.items(), key=lambda kv: -kv[1])[:10],
            "top_countries": sorted(ctys.items(), key=lambda kv: -kv[1])[:8],
        }
    cpf = [r["l"] for r in assessed if r["cas"] == "2921-88-2" and r["l"]]
    plaus["chlorpyrifos"] = {
        "limits": len(cpf),
        "median_ug_L": statistics.median(cpf) if cpf else None,
        "at_or_above_1_ug_L": sum(1 for x in cpf if x >= 1),
        "values_at_or_above_1": sorted({x for x in cpf if x >= 1}),
    }
    out["plausibility"] = plaus

    if args.limit:
        print(json.dumps({k: out[k] for k in ("assessed", "baseline",
                                              "baseline_undecidable_pct")},
                         indent=1, default=str))
        print(json.dumps(out["join"]["routes"], indent=1))
        return 0

    PROC.mkdir(parents=True, exist_ok=True)
    (PROC / "revision_sensitivity.json").write_text(
        json.dumps(out, indent=1, default=str), encoding="utf-8")
    write_report(out, eqs_rows)
    print("wrote derived/processed/revision_sensitivity.json, "
          "eval/revision_sensitivity.md")
    return 0


def write_report(o, eqs_rows):
    name = {}
    for r in eqs_rows:
        # a group standard lists its members' CAS numbers, and naming a member
        # after the group put "Sum of active substances" at the top of a table
        if r.get("is_group") == "True":
            continue
        for c in (r.get("all_cas") or "").replace(" ", "").split(";"):
            if c:
                name.setdefault(c, (r.get("name") or "").split("(")[0].strip())
    b = o["baseline"]; j = o["join"]; cp = o["composition"]; pl = o["plausibility"]
    L = []
    w = L.append
    w("# Three referee objections, measured\n")
    w("Generated by `scripts/30_revision_sensitivity.py`. The decision procedure "
      "is imported from `22_waterbase_external`, so every figure below differs "
      "from the headline only by the change its row names.\n")
    w(f"- assessed station-year rows: **{o['assessed']:,}**")
    w(f"- undecidable, as published: **{o['baseline_undecidable_pct']:.1f} %**\n")

    w("## The half-limit funnel, by outcome\n")
    w("| CENSO outcome of the rows a half-LOQ pipeline calls exceeding | n |")
    w("|---|---|")
    for k, v in sorted(o["half_loq_exceedances_by_outcome"].items(),
                       key=lambda kv: -kv[1]):
        w(f"| `{k}` | {v:,} |")
    w(f"| **total** | **{sum(o['half_loq_exceedances_by_outcome'].values()):,}** |\n")

    w("## (A) Joining the co-parameters the release reports on other rows\n")
    w("| | as published | after the join |")
    w("|---|---|---|")
    for k in ("compliant", "exceedance", "possible_exceedance",
              "precondition_unmet", "method_insufficient",
              "indeterminate_unresolved", "indeterminate_other"):
        w(f"| `{k}` | {b.get(k, 0):,} | {j['outcomes'].get(k, 0):,} |")
    w(f"| **undecidable** | **{o['baseline_undecidable_pct']:.1f} %** | "
      f"**{j['undecidable_pct']:.1f} %** |\n")
    if "scenarios" in j:
        w("### What the data owns and what the rules own\n")
        w("The first four rows are cumulative: the first changes no step of the "
          "decision procedure and each later row adds one. The last row is the "
          "headline reading, which keeps only the steps a cited source "
          "sanctions -- Cd class standards where hardness is known and Pb/Ni "
          "tier 1 on dissolved results (CIS Guidance No. 38), metal standards "
          "read as dissolved (Annex I Part B point 3).\n")
        w("| step | kind | PreconditionUnmet | Compliant | Exceedance | "
          "undecidable |")
        w("|---|---|---|---|---|---|")
        w(f"| row level, as the record reports it | — | "
          f"{b.get('precondition_unmet', 0):,} | "
          f"{b.get('compliant', 0):,} | {b.get('exceedance', 0):,} | "
          f"{o['baseline_undecidable_pct']:.1f} % |")
        for i, (s, d) in enumerate(j["scenarios"].items()):
            oc = d["outcomes"]
            w(f"| {s} | {'data' if i == 0 else 'rule'} | "
              f"{oc.get('precondition_unmet', 0):,} | {oc.get('compliant', 0):,} | "
              f"{oc.get('exceedance', 0):,} | {d['undecidable_pct']:.1f} % |")
        w("")
    for cas, rt in j["routes"].items():
        w(f"**{name.get(cas, cas)}**\n")
        w("| route -> outcome | n |")
        w("|---|---|")
        for k, v in sorted(rt.items(), key=lambda kv: -kv[1]):
            w(f"| {k} | {v:,} |")
        w("")
        w("matrix: " + ", ".join(f"`{m}` {c:,}" for m, c in
                                 sorted(j["matrix"][cas].items(),
                                        key=lambda kv: -kv[1])) + "\n")

    w("## (B) Who the headline describes\n")
    w("| reading | undecidable |")
    w("|---|---|")
    w(f"| pooled, as published | {o['baseline_undecidable_pct']:.1f} % |")
    w(f"| without Spain ({cp['without_ES']['n']:,} rows) | "
      f"{cp['without_ES']['undecidable_pct']:.1f} % |")
    w(f"| every country weighted equally ({cp['countries_over_floor']} with "
      f">= {cp['floor']:,} rows), mean | {cp['equal_weight_mean_pct']:.1f} % |")
    w(f"| same, median | {cp['equal_weight_median_pct']:.1f} % |")
    lo, hi = cp["leave_one_out_min"], cp["leave_one_out_max"]
    w(f"| leaving one country out, range | {lo[1]:.1f} % (without {lo[0]}) – "
      f"{hi[1]:.1f} % (without {hi[0]}) |")
    w(f"| after the join, without Spain | {cp['joined_without_ES_pct']:.1f} % |")
    w(f"| after the join, equal weights | "
      f"{cp['joined_equal_weight_mean_pct']:.1f} % |\n")
    w("| country | assessed rows | undecidable | affirmed exceedances |")
    w("|---|---|---|---|")
    for c, d in cp["per_country"].items():
        w(f"| {c} | {d['n']:,} | {d['undecidable_pct']:.1f} % | {d['affirmed']:,} |")
    w("")
    st = o["step_2012_2013"]
    w("### The 2012 -> 2013 fall in rows declaring neither a flag nor a limit\n")
    w("| reporters | 2012 silent / rows | 2013 silent / rows |")
    w("|---|---|---|")
    for lab in ("all reporters", "present in both years"):
        a, z = st[lab]["2012"], st[lab]["2013"]
        w(f"| {lab} ({st[lab]['countries_2012']} / {st[lab]['countries_2013']}"
          f" countries) | {a[0]:,} / {a[1]:,} ({a[2] or 0:.1f} %) | "
          f"{z[0]:,} / {z[1]:,} ({z[2] or 0:.1f} %) |")
    w("")
    w("Reporting in 2012 only: " + (", ".join(
        f"{c} ({v[0]:,}/{v[1]:,} silent)" for c, v in st["only_2012"].items())
        or "none"))
    w("\nReporting in both years: " + ", ".join(
        f"{c} ({d['2012'][0]:,}/{d['2012'][1]:,} -> {d['2013'][0]:,}/"
        f"{d['2013'][1]:,})" for c, d in st["both_detail"].items()))
    w("\nReporting in 2013 only: " + (", ".join(
        f"{c} ({v[0]:,}/{v[1]:,} silent)" for c, v in st["only_2013"].items())
        or "none") + "\n")
    w("### Undecidable share by year\n")
    w("| year | rows | countries | Spain's share of rows | undecidable | without Spain |")
    w("|---|---|---|---|---|---|")
    for y, d in o["by_year"].items():
        if d["n"] < 2000:
            continue
        w(f"| {y} | {d['n']:,} | {d['countries']} | {d['ES_share_pct']:.0f} % | "
          f"{d['undecidable_pct']:.1f} % | "
          + (f"{d['undecidable_without_ES_pct']:.1f} %" if d["n_without_ES"] >= 2000
             else "—") + " |")
    w("")

    w("## (C) Implausible quantification limits\n")
    w("A limit is screened against the median limit reported for the same "
      "substance across the release. The divided-by-1000 column is the unit-slip "
      "hypothesis, not a correction: it shows how far the headline would move "
      "if every flagged limit were a mg/ug slip.\n")
    w("| screen | rows | of assessed | undecidable if excluded | if divided by 1000 |")
    w("|---|---|---|---|---|")
    for k in ("slip", "loose"):
        d = pl[k]
        w(f"| >= {d['decades_above_substance_median']:.0f} decades above the "
          f"substance median | {d['rows']:,} | {d['pct_of_assessed']:.2f} % | "
          f"{d['excluded_undecidable_pct']:.1f} % | "
          f"{d['divided_by_1000_undecidable_pct']:.1f} % |")
    w("")
    for k in ("slip", "loose"):
        d = pl[k]
        w(f"**{k}**: outcomes of the flagged rows " + ", ".join(
            f"`{a}` {c:,}" for a, c in sorted(d["their_outcomes"].items(),
                                              key=lambda kv: -kv[1])))
        w("; substances " + ", ".join(f"{name.get(c, c)} {n:,}"
                                      for c, n in d["top_substances"]))
        w("; countries " + ", ".join(f"{c} {n:,}" for c, n in d["top_countries"])
          + "\n")
    c = pl["chlorpyrifos"]
    w(f"Chlorpyrifos: {c['limits']:,} limits, median {c['median_ug_L']} ug/L; "
      f"{c['at_or_above_1_ug_L']:,} at or above 1 ug/L, with values "
      f"{', '.join(str(x) for x in c['values_at_or_above_1'])}.\n")
    (EVAL / "revision_sensitivity.md").write_text("\n".join(L) + "\n",
                                                  encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
