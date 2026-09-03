#!/usr/bin/env python3
"""
Does a published scientific conclusion move when censoring is represented?

BACKGROUND
----------
Emadian et al. (2021, STOTEN 758:143656) analysed this survey and classified its
micropollutants using the KURTOSIS of their concentration and load
distributions, reporting 41 "core micropollutants". Their stated rule places a
substance among the source-specific, persistent group when

    K_concentration > 9   and   K_load < 9

Kurtosis is dominated by point masses and tail behaviour. In a distribution
where 85% of observations are the single value 0, that point mass is most of
what the statistic sees. The classification therefore rests on a data-preparation
convention, and this script asks whether it survives changing it.

WHAT IS COMPARED
----------------
Two admissible readings of the same measurements, following the bounds a
non-detection actually establishes:

  ZERO : every non-detect is 0            -- the published convention, and the
                                             lower bound of the interval
  LOD  : every non-detect is its own LOD  -- the upper bound

Neither is "the truth"; they bracket it. A substance whose classification is the
same under both is robust to the convention. One that moves is not, and the
published category for it cannot be attributed to the data alone.

WHAT THIS IS NOT
----------------
This is not a reproduction of Emadian et al. and not a claim that their result
is wrong. Their 41-substance list and the details of their implementation are
not available to us, so we apply the stated rule ourselves to both readings and
report only the DIFFERENCE between them. For an occurrence study their
convention is entirely standard. The point is that the conclusion is sensitive
to it, which is knowable only if the censoring is represented.

Inputs  : derived/processed/{measurements,analytes,stations_snapped}.csv
Outputs : derived/processed/kurtosis_flip.csv
          eval/kurtosis_flip.md

Usage:  python scripts/13_kurtosis_flip.py [--k-threshold 9]
"""

from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"

FLOW_KEYS = ("yabatas", "ekoton")
MIN_OBS = 30            # below this, kurtosis is not meaningful


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


def kurtosis(xs):
    """Pearson kurtosis (not excess), the convention used with a K>9 threshold."""
    n = len(xs)
    if n < 4:
        return None
    mean = sum(xs) / n
    m2 = sum((x - mean) ** 2 for x in xs) / n
    if m2 <= 0:
        return None                      # constant series: undefined
    m4 = sum((x - mean) ** 4 for x in xs) / n
    return m4 / (m2 ** 2)


def load(name):
    p = PROC / name
    if not p.exists():
        sys.exit(f"missing {p}; run the earlier scripts first")
    return list(csv.DictReader(p.open(encoding="utf-8")))


def classify(k_conc, k_load, thr):
    """The published 2x2: persistence from K_load, source type from K_conc."""
    if k_conc is None or k_load is None:
        return None
    persistent = k_load < thr
    specific = k_conc > thr
    return ("non/slowly biodegradable" if persistent else "biodegradable") + \
           (", specific source" if specific else ", dispersed source")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k-threshold", type=float, default=9.0)
    args = ap.parse_args()
    EVAL.mkdir(parents=True, exist_ok=True)
    thr = args.k_threshold

    measurements = load("measurements.csv")
    analytes = {a["parameter"]: a for a in load("analytes.csv")}

    flow = {}
    for m in measurements:
        if fold(m["parameter"]) in FLOW_KEYS:
            v = num(m["value_num"])
            if v and v > 0:
                flow.setdefault((m["campaign"], m["station"]), v)

    # per analyte: the two readings of concentration, and the matching loads
    conc = defaultdict(lambda: {"zero": [], "lod": []})
    load_ = defaultdict(lambda: {"zero": [], "lod": []})
    nd_count = Counter()
    obs_count = Counter()

    for m in measurements:
        p = m["parameter"]
        a = analytes.get(p)
        if not a or a["group"] != "micropollutant":
            continue
        v = num(m["value_num"])
        if v is None:
            continue
        lod = num(a.get("lod"))
        if lod is None:
            continue                     # cannot form the upper reading
        obs_count[p] += 1
        is_nd = (v == 0.0)
        if is_nd:
            nd_count[p] += 1
        c_zero = 0.0 if is_nd else v
        c_lod = lod if is_nd else v
        conc[p]["zero"].append(c_zero)
        conc[p]["lod"].append(c_lod)
        q = flow.get((m["campaign"], m["station"]))
        if q is not None:
            load_[p]["zero"].append(c_zero * q)
            load_[p]["lod"].append(c_lod * q)

    rows, moved, stable, undefined = [], [], [], []
    for p in sorted(conc):
        if obs_count[p] < MIN_OBS:
            continue
        kc_z = kurtosis(conc[p]["zero"])
        kc_l = kurtosis(conc[p]["lod"])
        kl_z = kurtosis(load_[p]["zero"]) if load_[p]["zero"] else None
        kl_l = kurtosis(load_[p]["lod"]) if load_[p]["lod"] else None
        cls_z = classify(kc_z, kl_z, thr)
        cls_l = classify(kc_l, kl_l, thr)

        rec = {
            "analyte": p, "n_obs": obs_count[p], "n_nondetect": nd_count[p],
            "pct_nondetect": round(100 * nd_count[p] / obs_count[p], 1),
            "K_conc_zero": kc_z, "K_conc_lod": kc_l,
            "K_load_zero": kl_z, "K_load_lod": kl_l,
            "class_zero": cls_z, "class_lod": cls_l,
            "changed": (cls_z is not None and cls_l is not None
                        and cls_z != cls_l),
        }
        rows.append(rec)
        if cls_z is None or cls_l is None:
            undefined.append(rec)
        elif rec["changed"]:
            moved.append(rec)
        else:
            stable.append(rec)

    if not rows:
        sys.exit("no analyte had both an LOD and enough observations")

    with (PROC / "kurtosis_flip.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    n_cls = len(moved) + len(stable)
    L = []
    A = L.append
    A("# Does the published classification survive the censoring convention?\n")
    A("Generated by `scripts/13_kurtosis_flip.py`.\n")
    A("Emadian et al. (2021) classified this survey's micropollutants using the "
      "kurtosis of their concentration and load distributions, with a threshold "
      f"of K = {thr:g}. Kurtosis is dominated by point masses, and in these data "
      "the single value 0 accounts for most observations. This script applies "
      "the same stated rule to the two admissible readings of the same "
      "measurements -- every non-detect at 0 (the published convention and the "
      "lower bound), and every non-detect at its own LOD (the upper bound) -- "
      "and reports only the difference.\n")
    A("> This is **not** a reproduction of that study and not a claim that it is "
      "wrong. Their substance list and implementation details are not available "
      "to us. For an occurrence study the convention is standard. The question "
      "is whether the conclusion depends on it.\n")

    A("## Result\n")
    A(f"- micropollutants with a published LOD and at least {MIN_OBS} "
      f"observations: **{len(rows)}**")
    A(f"- classifiable under both readings: **{n_cls}**")
    A(f"- **classification changes: {len(moved)}** "
      f"({100*len(moved)/n_cls:.0f}% of those classifiable)" if n_cls else "")
    A(f"- unchanged: {len(stable)}")
    A(f"- undefined under at least one reading (constant series): {len(undefined)}\n")

    if moved:
        A("## Substances whose category depends on the convention\n")
        A("| analyte | non-detects | $K_{conc}$ zero $\\to$ LOD | "
          "$K_{load}$ zero $\\to$ LOD | class under zero | class under LOD |")
        A("|---|---|---|---|---|---|")
        for r in sorted(moved, key=lambda x: -x["pct_nondetect"]):
            def f(x):
                return "—" if x is None else f"{x:.1f}"
            A(f"| {r['analyte'][:34]} | {r['pct_nondetect']}% | "
              f"{f(r['K_conc_zero'])} → {f(r['K_conc_lod'])} | "
              f"{f(r['K_load_zero'])} → {f(r['K_load_lod'])} | "
              f"{r['class_zero']} | {r['class_lod']} |")
        A("")

    A("## Reading this\n")
    if moved:
        A(f"For **{len(moved)}** substances the category assigned by the "
          "published rule is not determined by the measurements alone: it "
          "depends on how non-detections are written down. Those assignments "
          "should carry that caveat, and representing the censoring is what "
          "makes the caveat visible at all.\n")
    else:
        A("No substance changes category. The published classification is "
          "robust to the censoring convention, which is a useful negative "
          "result and is reported as such: the convention matters for "
          "compliance verdicts and load estimates, but not for this "
          "classification.\n")
    A("Kurtosis under the two readings is reported per substance in "
      "`derived/processed/kurtosis_flip.csv` so any individual case can be "
      "checked.\n")

    text = "\n".join(L)
    (EVAL / "kurtosis_flip.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nwrote: {EVAL/'kurtosis_flip.md'}, {PROC/'kurtosis_flip.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
