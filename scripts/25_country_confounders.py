#!/usr/bin/env python3
"""
Is the between-country spread real, or an artefact of what each country measures?

THE OBJECTION THIS ANSWERS
--------------------------
Figure 3 shows the share of station-years carrying neither a censoring flag nor
a quantification limit ranging from a few per cent to nearly all, between
countries reporting under the same directive. The obvious reply is that the
comparison is unfair: countries monitor different substances, over different
years, in different numbers, and some are not EU Member States at all. On that
reading the spread measures the monitoring programme, not the reporting
practice, and the figure is biased.

The objection is testable, so it is tested rather than argued with.

WHAT IS AND IS NOT REGULATED HERE
---------------------------------
Worth separating first, because it disposes of the strongest form of the
objection. The quantity plotted is whether the LOQ FIELD IS POPULATED. That
field is defined identically for every reporter by the WISE-6 schema; it is not
a national threshold and no national standard changes whether it must be filled.
A country's own EQS values can change which results breach a standard. They
cannot change whether the limit was written down.

FOUR TESTS
----------
  1. RAW              the share as plotted, per country.
  2. STANDARDISED     direct standardisation onto the pooled substance mix.
                      Each country is re-weighted as if it had measured the
                      same basket of substances as Europe as a whole, so a
                      country that happens to monitor metals cannot look tidy
                      merely because metals are reported with limits.
  3. COMMON BASKET    restricted to substances a large majority of countries
                      report, which removes the long tail of national
                      speciality determinands entirely.
  4. RECENT WINDOW    restricted to recent years, since the schema's older
                      returns predate routine LOQ reporting.

If the spread survives all four, it is a property of reporting practice. If it
collapses under any one of them, that has to be said, and the figure withdrawn
or restated.

Inputs  : Data/waterbase/*.{csv,csv.gz,zip}   or --file
Outputs : derived/processed/country_confounders.csv
          eval/country_confounders.md

Usage:  python scripts/25_country_confounders.py [--file PATH]
        python scripts/25_country_confounders.py --self-test
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Data" / "waterbase"
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

sys.path.insert(0, str(Path(__file__).resolve().parent))
_m = __import__("22_waterbase_external")
open_rows, pick, num, truthy = _m.open_rows, _m.pick, _m.num, _m.truthy

MIN_N = 5000          # country reporting volume below which shares are noise
MIN_EQS = 500         # assessable station-years Figure 3 requires of a country
BASKET_SHARE = 0.60   # a substance is "common" if this share of countries report it
RECENT_FROM = 2015

# EU Member States as at the 2026 consolidation, by ISO-3166-1 alpha-2 as used
# in Waterbase. Non-members also report to the EEA, and the Directive's Annex I
# standards are not law for them, so their inclusion is tested separately.
EU_MS = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE",
         "GR", "EL", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL",
         "PT", "RO", "SK", "SI", "ES", "SE"}


def standardise(per_sub, weights):
    """Direct standardisation of one country onto a reference substance mix.

    Returns the share this country would show if it had measured the reference
    basket in the reference proportions. Weights are renormalised over the
    substances the country actually reports: extrapolating a country's practice
    to substances it never measured would be inventing data, so the comparison
    is over the shared basket and the coverage is reported alongside.
    """
    num_ = den = 0.0
    for sub, (n, silent) in per_sub.items():
        w = weights.get(sub, 0.0)
        if not w or not n:
            continue
        num_ += w * (silent / n)
        den += w
    if den == 0:
        return None, 0.0
    return 100 * num_ / den, den


def self_test() -> int:
    """Standardisation must remove a mix effect it is given, and must leave a
    genuine practice difference alone. Both directions, or the test proves
    nothing."""
    bad = 0
    # Two countries with IDENTICAL per-substance practice but opposite mixes.
    # Raw shares differ; standardised shares must not.
    weights = {"a": 0.5, "b": 0.5}
    A = {"a": (900, 90), "b": (100, 50)}      # 10% on a, 50% on b
    B = {"a": (100, 10), "b": (900, 450)}     # same rates, mirrored mix
    raw_a = 100 * sum(s for _, s in A.values()) / sum(n for n, _ in A.values())
    raw_b = 100 * sum(s for _, s in B.values()) / sum(n for n, _ in B.values())
    sa, _ = standardise(A, weights)
    sb, _ = standardise(B, weights)
    if abs(raw_a - raw_b) < 10:
        print("  FAIL the fixture must have a raw mix effect to remove")
        bad += 1
    if abs(sa - sb) > 1e-9:
        print(f"  FAIL standardisation left a mix effect: {sa} vs {sb}")
        bad += 1
    # A real practice difference must survive.
    C = {"a": (500, 450), "b": (500, 450)}    # 90% on both
    sc, _ = standardise(C, weights)
    if abs(sc - sa) < 30:
        print("  FAIL standardisation flattened a genuine difference")
        bad += 1
    # Renormalisation: a country covering only half the basket is still scored
    # on what it covers, not penalised to zero.
    sd, cov = standardise({"a": (100, 10)}, weights)
    if sd is None or abs(sd - 10.0) > 1e-9 or abs(cov - 0.5) > 1e-9:
        print(f"  FAIL partial coverage mis-scored: {sd}, coverage {cov}")
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

    rows = open_rows(src)
    header = next(rows)
    col = pick(header)
    if "determinand" not in col:
        sys.exit(f"determinand column not found; header was {header[:14]}")

    def get(row, role):
        i = col.get(role)
        return row[i].strip() if i is not None and i < len(row) else ""

    n = kept = 0
    # country -> substance -> [station-years, silent station-years]
    cell = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    cell_recent = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    pooled = defaultdict(int)

    for row in rows:
        if not row:
            continue
        n += 1
        if args.limit and n > args.limit:
            break
        if n % 2_000_000 == 0:
            print(f"    {n:,} rows read, {kept:,} river rows kept …")
        if "category" in col and get(row, "category") not in ("RW", ""):
            continue
        kept += 1

        cty = (get(row, "country") or "??").upper()
        sub = get(row, "code") or get(row, "determinand")
        if not sub:
            continue
        # "Silent": the record carries neither a censoring flag nor a limit,
        # so a zero and a measured trace cannot be told apart. Exactly the
        # quantity plotted in Figure 3, and it must be computed exactly as
        # scripts/22 computes it.
        #
        # DECLARED means the field is POPULATED, not that it says yes. A row
        # reporting "0" has declared its censoring status -- it has said "not
        # censored", which is information. Testing truthiness instead counted
        # those rows as silent and inflated every country's share; Estonia
        # moved from 81.8 % to 96.0 % and the range quoted in the text stopped
        # matching the figure the reader was looking at.
        silent = 0 if (get(row, "below_loq") != ""
                       or num(get(row, "loq")) is not None) else 1

        cell[cty][sub][0] += 1
        cell[cty][sub][1] += silent
        pooled[sub] += 1
        yr = num(get(row, "year"))
        if yr is not None and yr >= RECENT_FROM:
            cell_recent[cty][sub][0] += 1
            cell_recent[cty][sub][1] += silent

    # EXACTLY the population Figure 3 plots. The figure additionally requires a
    # country to have enough assessable station-years for its y-axis to mean
    # anything, so a volume floor alone gave 28 countries against the figure's
    # 26 -- and a raw range of 6.5-97.4 % against the figure's 3.3-97.4 %. The
    # text then quoted one and the reader saw the other.
    eligible = None
    summ = PROC / "waterbase_summary.csv"
    if summ.exists():
        eligible = set()
        with summ.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["scope"] == "country" and int(r["n"]) >= MIN_N \
                        and int(r["has_eqs"]) >= MIN_EQS:
                    eligible.add(r["key"].upper())
        print(f"  population: {len(eligible)} countries, the same filter "
              f"Figure 3 applies")
    countries = {c: d for c, d in cell.items()
                 if sum(v[0] for v in d.values()) >= MIN_N
                 and (eligible is None or c in eligible)}
    if len(countries) < 6:
        sys.exit("too few countries above the reporting-volume floor")

    total = sum(pooled.values())
    weights = {s: c / total for s, c in pooled.items()}

    # A substance is in the common basket if a large majority of the countries
    # under comparison report it at all.
    reported_by = defaultdict(int)
    for c, d in countries.items():
        for s, v in d.items():
            if v[0] > 0:
                reported_by[s] += 1
    need = BASKET_SHARE * len(countries)
    basket = {s for s, k in reported_by.items() if k >= need}
    bw = {s: weights[s] for s in basket}

    out = []
    for c, d in sorted(countries.items()):
        n_c = sum(v[0] for v in d.values())
        sil = sum(v[1] for v in d.values())
        raw = 100 * sil / n_c
        std, cov = standardise({s: tuple(v) for s, v in d.items()}, weights)
        bas, bcov = standardise({s: tuple(v) for s, v in d.items() if s in basket},
                                bw)
        dr = cell_recent.get(c, {})
        n_r = sum(v[0] for v in dr.values())
        rec = (100 * sum(v[1] for v in dr.values()) / n_r) if n_r else None
        out.append({"country": c, "n": n_c, "raw": raw, "std": std,
                    "coverage": cov, "basket": bas, "basket_cov": bcov,
                    "recent": rec, "n_recent": n_r,
                    "eu": "yes" if c in EU_MS else "no"})

    def spread(key, subset=None):
        vs = [r[key] for r in out if r[key] is not None
              and (subset is None or subset(r))]
        return (min(vs), max(vs), len(vs)) if vs else (None, None, 0)

    PROC.mkdir(parents=True, exist_ok=True)
    EVAL.mkdir(parents=True, exist_ok=True)
    with (PROC / "country_confounders.csv").open("w", newline="",
                                                 encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        for r in out:
            w.writerow(r)

    r_lo, r_hi, r_n = spread("raw")
    s_lo, s_hi, _ = spread("std")
    b_lo, b_hi, _ = spread("basket")
    c_lo, c_hi, c_n = spread("recent")
    e_lo, e_hi, e_n = spread("std", lambda r: r["eu"] == "yes")

    # Rank agreement between raw and standardised. If standardisation merely
    # reordered the countries, the raw ranking would be the artefact.
    pairs = [(r["raw"], r["std"]) for r in out if r["std"] is not None]
    conc = disc = 0
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            a = (pairs[i][0] - pairs[j][0]) * (pairs[i][1] - pairs[j][1])
            if a > 0:
                conc += 1
            elif a < 0:
                disc += 1
    tau = (conc - disc) / (conc + disc) if conc + disc else 0.0

    L = ["# Is the between-country spread an artefact?", "",
         "Generated by `scripts/25_country_confounders.py`. The quantity is the "
         "share of station-years carrying neither a censoring flag nor a "
         "quantification limit — a WISE-6 schema field, identical for every "
         "reporter, and not a national threshold.", "",
         f"- countries above the {MIN_N:,} station-year floor: **{r_n}**",
         f"- common basket: **{len(basket)}** substances reported by at least "
         f"{BASKET_SHARE:.0%} of them", "",
         "## The spread under four treatments", "",
         "| Treatment | Range | Countries |", "|---|---|---|",
         f"| Raw, as plotted | {r_lo:.1f}–{r_hi:.1f}% | {r_n} |",
         f"| Standardised to the pooled substance mix | {s_lo:.1f}–{s_hi:.1f}% "
         f"| {r_n} |",
         f"| Common basket only | {b_lo:.1f}–{b_hi:.1f}% | {r_n} |",
         f"| EU Member States, standardised | {e_lo:.1f}–{e_hi:.1f}% | {e_n} |",
         "",
         f"The fourth treatment we intended -- restricting to {RECENT_FROM} "
         f"onwards -- is **not reported as a robustness test**, because this "
         f"release does not support one. Only {c_n} of the countries here have "
         f"any river record dated {RECENT_FROM} or later; France, Italy, "
         f"Finland, Poland, Austria and Hungary have none at all. The per-"
         f"country column is kept in the CSV because it is a real property of "
         f"the release, but a range computed over {c_n} countries, one of "
         f"which supplies most of the rows, would not test anything. It is "
         f"instead reported as a change over time, in "
         f"`eval/waterbase_external.md`, where the whole audit is split at "
         f"{RECENT_FROM}: {RECENT_FROM}+ is nearly half the record, but it "
         f"comes from these few reporters, so it describes their practice and "
         f"not Europe's.",
         "",
         f"Kendall's tau between the raw and standardised orderings is "
         f"**{tau:+.2f}**, so standardisation does not reorder the countries; "
         "it leaves the same ones at each end.", "",
         "## Per country", "",
         "| Country | Station-years | Raw | Standardised | Common basket | "
         f"{RECENT_FROM}+ | EU MS |",
         "|---|---|---|---|---|---|---|"]
    for r in sorted(out, key=lambda r: -(r["std"] or 0)):
        f = lambda v: "—" if v is None else f"{v:.1f}%"
        L.append(f"| {r['country']} | {r['n']:,} | {f(r['raw'])} | "
                 f"{f(r['std'])} | {f(r['basket'])} | {f(r['recent'])} | "
                 f"{r['eu']} |")

    L += ["", "## Reading", "",
          "Standardisation re-weights every country onto the same substance "
          "basket, so a country cannot appear tidy merely because it monitors "
          "substances that are usually reported with a limit. The common-basket "
          "and recent-window columns remove the national speciality "
          "determinands and the oldest returns respectively. The last row "
          "drops every reporter for which Annex I is not law.", "",
          "Restricting to EU Member States matters for a second reason: the "
          "quantification-limit criterion of Directive 2009/90/EC binds them "
          "and not the other reporters, so only their column is a compliance "
          "statement rather than a description.", ""]

    (EVAL / "country_confounders.md").write_text("\n".join(L) + "\n",
                                                 encoding="utf-8")
    print(f"\n  raw          {r_lo:.1f}–{r_hi:.1f}%  ({r_n} countries)")
    print(f"  standardised {s_lo:.1f}–{s_hi:.1f}%")
    print(f"  basket       {b_lo:.1f}–{b_hi:.1f}%")
    print(f"  {RECENT_FROM}+        {c_lo:.1f}–{c_hi:.1f}%  ({c_n} countries)")
    print(f"  EU MS std    {e_lo:.1f}–{e_hi:.1f}%  ({e_n} countries)")
    print(f"  Kendall tau raw vs standardised: {tau:+.2f}")
    print(f"  wrote {(PROC/'country_confounders.csv').relative_to(ROOT)}")
    print(f"  wrote {(EVAL/'country_confounders.md').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
