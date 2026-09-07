#!/usr/bin/env python3
"""
What would change if the uncertainty band were applied to non-detections too.

THE ASYMMETRY, STATED PLAINLY
-----------------------------
censo_outcome applies Article 4(1)'s expanded measurement uncertainty -- 50 % at
the level of the standard -- to QUANTIFIED results: a value whose interval
straddles the threshold is censo:PossibleExceedance, because a method meeting
only the legal minimum cannot decide it either way.

It does not apply that band to CENSORED results. A non-detection whose
quantification limit clears the standard is censo:Compliant, full stop. Read
symmetrically, the interval for such a row would run to LOQ + 0.5*T rather than
to LOQ, and every row with LOQ > 0.5*T would straddle the threshold and become
undecidable.

So a non-detection is currently treated as MORE decisive than a detection at the
same position, which is the opposite of what this paper argues about
non-detections everywhere else. A referee will notice, so the choice is argued
here and its cost is measured rather than asserted.

WHY THE ASYMMETRY IS KEPT
-------------------------
1. The law is asymmetric, and CENSO represents it. Article 3(3b) gives censored
   results their own rule -- where the limit exceeds the standard, the result
   "shall not be considered" -- and that rule is a POINT comparison of LOQ
   against the EQS. It does not say LOQ + U. Article 4(1)'s uncertainty figure
   is specified "at the level of the standard", which characterises measurements
   made near the EQS: quantified ones.

2. It would double-count. A quantification limit is DEFINED by uncertainty --
   conventionally the concentration at which relative uncertainty falls to an
   acceptable value. "Below the LOQ" already means "the signal was too small to
   quantify with acceptable uncertainty". Adding a further band to a bound that
   is itself an uncertainty statement counts the same thing twice. A quantified
   point value needs the band because a point carries no interval of its own; a
   censored result is already an interval.

3. The burden of proof runs against us. Applying the band would RAISE this
   paper's own headline -- the undecidable share -- by the amount reported
   below. A methodological change that inflates one's own result has to be right
   on the merits, not merely symmetrical.

The alternative is reported rather than hidden, because "we chose A over B" is
worth more when B is quantified.

Inputs  : Data/waterbase/... or --file, derived/processed/eu_eqs.csv
Outputs : eval/uncertainty_sensitivity.md

Usage:  python scripts/28_uncertainty_sensitivity.py --file <release.zip>
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
DATA = ROOT / "Data" / "waterbase"
EVAL = ROOT / "eval"

sys.path.insert(0, str(Path(__file__).resolve().parent))
_m = __import__("22_waterbase_external")
open_rows, pick, num, truthy = _m.open_rows, _m.pick, _m.num, _m.truthy
TO_UG_L, U = _m.TO_UG_L, _m.LEGAL_UNCERTAINTY_AT_EQS
conditional_thresholds = _m.conditional_thresholds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path)
    args = ap.parse_args()
    src = args.file
    if src is None:
        cand = sorted(DATA.glob("*Aggregated*.zip"))
        src = cand[0] if cand else None
    if src is None or not src.exists():
        print("  ! aggregated release not found; skipping")
        return 0

    p_eqs = PROC / "eu_eqs.csv"
    if not p_eqs.exists():
        print("  ! derived/processed/eu_eqs.csv missing; run stage 10 first")
        return 0
    eqs, rows_eqs = {}, []
    with p_eqs.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows_eqs.append(r)
            if r.get("is_group") == "True":
                continue
            v = num(r.get("aa_inland"))
            if not v:
                continue
            for c in (r.get("all_cas") or "").replace(" ", "").split(";"):
                if c:
                    eqs.setdefault(c, v)
    cond = conditional_thresholds(rows_eqs)

    it = open_rows(src)
    headers = next(it)
    col = pick(headers)
    get = lambda row, k: (row[col[k]].strip()
                          if k in col and col[k] < len(row) else "")

    n_assessable = n_censored_compliant = n_would_flip = 0
    for row in it:
        if "category" in col and get(row, "category") not in ("RW", ""):
            continue
        cas = get(row, "code")
        cas = cas[4:] if cas.upper().startswith("CAS_") else ""
        if cas not in eqs:
            continue
        T = eqs[cas]
        n_assessable += 1
        # a precondition is prior to everything, exactly as in censo_outcome
        if cond.get(cas) is not None:
            continue
        factor = TO_UG_L.get(get(row, "uom").lower().replace(" ", ""))
        loq = num(get(row, "loq"))
        n_bel = num(get(row, "n_below"))
        censored = truthy(get(row, "below_loq")) or (n_bel or 0) > 0
        if not (censored and loq is not None and factor):
            continue
        loq_ug = loq * factor
        if loq_ug > T:
            continue                      # already MethodInsufficient, Art. 3(3b)
        n_censored_compliant += 1
        if loq_ug + U * T > T:            # the symmetric reading straddles
            n_would_flip += 1

    pct = (lambda a, b: f"{100 * a / b:.1f}" if b else "0.0")

    # What the headline would become. Recomputed from the same verdict table
    # section 5.4 is built from, so the two cannot drift apart.
    IND = ("possible_exceedance", "precondition_unmet", "method_insufficient",
           "indeterminate_unresolved", "indeterminate_other")
    now = after = None
    vp = PROC / "waterbase_verdicts_population.csv"
    if vp.exists():
        with vp.open(encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r["substitution"] == "zero"]
        tot = sum(int(r["n"]) for r in rows)
        unsup = sum(int(r["n"]) for r in rows if r["censo_outcome"] in IND)
        if tot:
            now = 100 * unsup / tot
            after = 100 * (unsup + n_would_flip) / tot
    A = ["# Sensitivity: the uncertainty band, applied to non-detections\n",
         "Generated by `scripts/28_uncertainty_sensitivity.py`.\n",
         "Article 4(1) permits an expanded measurement uncertainty of "
         f"{U:.0%} at the level of the standard. CENSO applies that band to "
         "**quantified** results, where a straddling interval yields "
         "`censo:PossibleExceedance`, and not to **censored** ones, where a "
         "quantification limit clearing the standard yields `censo:Compliant`. "
         "Read symmetrically, a censored result would carry the interval "
         "[0, LOQ + 0.5·T] and every row with LOQ above half the standard "
         "would become undecidable.\n",
         "That is an asymmetry in which a non-detection is treated as *more* "
         "decisive than a detection at the same position, so it is argued "
         "rather than left implicit, and its cost is measured here.\n",
         "| | n | share |", "|---|---|---|",
         f"| station-years a European annual-average standard reaches "
         f"| {n_assessable:,} | |",
         f"| of those, censored and currently `Compliant` "
         f"| {n_censored_compliant:,} | {pct(n_censored_compliant, n_assessable)} % |",
         f"| **would become `PossibleExceedance` under the symmetric reading** "
         f"| **{n_would_flip:,}** | **{pct(n_would_flip, n_assessable)} %** |",
         ""]
    if now is not None:
        A += [f"**The undecidable share would go from {now:.1f}\u2009% to "
              f"{after:.1f}\u2009%** \u2014 a rise of "
              f"{after - now:.1f} percentage points, recomputed from the same "
              f"verdict table Section 5.4 is built from.\n"]
    A += [
         "## Why the band is not applied\n",
         "**The law is asymmetric here, and the vocabulary represents it.** "
         "Article 3(3b) gives a below-quantification result its own rule --- "
         "where the limit exceeds the standard the result shall not be "
         "considered --- and that rule is a point comparison of the limit "
         "against the standard. It does not say limit plus uncertainty. "
         "Article 4(1)'s figure is specified *at the level of the standard*, "
         "which characterises measurements made near it.\n",
         "**It would double-count.** A quantification limit is defined by "
         "uncertainty: it is the concentration at which relative uncertainty "
         "falls to an acceptable value. “Below the LOQ” already says "
         "“the signal was too small to quantify with acceptable "
         "uncertainty”. A quantified point value needs a band because a "
         "point carries no interval of its own; a censored result is already "
         "an interval, and adding a band to it counts the same uncertainty "
         "twice.\n",
         "**The burden of proof runs against us.** Applying the band would "
         f"move {n_would_flip:,} station-years out of `Compliant` and into "
         "the undecidable stratum, raising this paper's own headline. A "
         "methodological change that inflates one's own result has to be right "
         "on the merits and not merely symmetrical, and the two reasons above "
         "are why we judge it is not.\n",
         "What the symmetric reading would be right about is narrower and is "
         "worth stating: a laboratory whose method only just meets the legal "
         "minimum, reporting a non-detection at a limit just under the "
         "standard, has not established much. The vocabulary can already say "
         "so --- that row fails the Article 4(1) criterion whenever the limit "
         "exceeds 30 % of the standard, which is a stricter test than the one "
         "considered here and which the paper reports separately.\n"]
    EVAL.mkdir(parents=True, exist_ok=True)
    (EVAL / "uncertainty_sensitivity.md").write_text("\n".join(A) + "\n",
                                                     encoding="utf-8")
    print(f"  {n_would_flip:,} of {n_assessable:,} station-years "
          f"({pct(n_would_flip, n_assessable)} %) would change under the "
          f"symmetric reading")
    print("  wrote eval/uncertainty_sensitivity.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
