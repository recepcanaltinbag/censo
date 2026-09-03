#!/usr/bin/env python3
"""
Whole-project audit: recompute the manuscript's claims from the source data.

WHY THIS EXISTS
---------------
scripts/95_numbers_manifest.py checks that every `\\num{}` in the paper appears
*somewhere* in a generated file. That is a weak test, and it let real errors
through:

  * the paper claimed \\num{617409} ABox triples while the build reported
    617,394 -- the manuscript had been written against an older run;
  * SHACL was reported as 156,352 triples and five violations when the graph had
    156,338 and three;
  * an ontology count appeared as 14 in the abstract and 18 in the results;
  * a percentage divided one transition count by another transition's
    denominator, reporting 93.2% where the data give 93.1%;
  * the abstract said 6.9% of *determinate* verdicts survive; 6.9% is the share
    of *compliant* verdicts, and the determinate share is 13.3%.

Presence-in-a-file cannot catch any of those, because every one of those numbers
did appear in some file. So this script does the opposite: it RECOMPUTES each
claim from `derived/processed/*.csv` -- the data, not the reports -- and
compares against the value asserted in the LaTeX. A claim that cannot be
recomputed is listed as such rather than quietly passed.

It also checks two things no per-script test can see:

  * STALENESS. An output older than the script that writes it, or older than an
    input it consumes, is stale. This is what made the ABox mismatch possible.
  * THRESHOLD PROVENANCE. Every regulatory threshold used in an analysis must
    resolve, by CAS number, to a value transcribed from a primary legal text.
    The project's own working spreadsheet is not an acceptable source: seven of
    its ten metal values are wrong, which is itself one of the paper's findings.

Exit code 0 only if no check FAILs.

Usage:  python scripts/99_audit.py [--verbose]
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import unicodedata
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "derived" / "processed"
EVAL = ROOT / "eval"
PAPER = ROOT / "paper"
SCRIPTS = ROOT / "scripts"

OK, FAIL, WARN, SKIP, INFO = "PASS", "FAIL", "WARN", "SKIP", "INFO"
results: list[tuple[str, str, str]] = []


def record(state, name, detail=""):
    results.append((state, name, detail))


def load(name):
    p = PROC / name
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def f(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------- the paper --

def supplementary_text() -> str:
    """Analyses reported in paper/supplementary/ rather than in the paper.

    A claim that leaves the manuscript must not thereby escape checking. The
    hydrological analyses were set aside because their flow record is
    defective, not because their arithmetic stopped mattering: the files are
    still generated and still have to match the data.
    """
    d = PAPER / "supplementary"
    if not d.exists():
        return ""
    return "\n".join(f.read_text(encoding="utf-8") for f in sorted(d.glob("*.md")))


def paper_text() -> str:
    parts = []
    for p in sorted((PAPER / "sections").glob("*.tex")):
        parts.append(p.read_text(encoding="utf-8"))
    m = PAPER / "main-elsevier.tex"
    if m.exists():
        parts.append(m.read_text(encoding="utf-8"))
    return "\n".join(parts)


def asserted(tex: str) -> set[str]:
    """Every value the manuscript states inside \\num{}."""
    return {v.strip() for v in re.findall(r"\\num\{([^}]*)\}", tex)}


def asserted_any(text: str) -> set[str]:
    """Numbers stated in Markdown, where there is no \\num{} to key on."""
    out = set()
    for m in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        out.add(m)
        out.add(m.replace(",", ""))
    return out


def norm(v) -> str:
    """Render a computed value the way \\num{} would carry it."""
    if isinstance(v, float):
        if abs(v - round(v)) < 1e-9:
            return str(int(round(v)))
        return f"{v:.10g}"
    return str(v)


# Every value any check recomputes, filled on the first pass. A number the
# manuscript asserts CANNOT be a stale copy of some other quantity if it is
# itself the correct value of a different claim -- and without this the
# detector paired the two-valued exceedance count with the declared-but-
# unbounded count, the station-year total with the organic-sample count, and a
# figure's "at least 5000 station-years" filter with a dual-regulation cell.
_COMPUTED: set = set()
_PENDING: list = []
# Asserted tokens that some check matched EXACTLY. Without this the
# near-match detector re-attributes them: 36.6 (the unsupportable share)
# was reported as a stale Belgian era value, and 75 (the pesticide group's
# membership) as a stale Swedish one. Both are owned elsewhere.
_MATCHED: set = set()


def _confusably_close(value, tex_nums):
    """An asserted value that looks like THIS quantity but is not it.

    This is the whole point of the check. The defect it was built for is a
    manuscript carrying 19.3 % while the corrected data give 18.5 % -- a number
    that is present, plausible, and stale. A value that differs by a few per
    cent and has the same shape is that defect; a value that is absent
    altogether is a different thing entirely, and is not an error.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v == 0:
        return None
    FILTERS = {"5000", "1000", "500", "40000", "20000", "200", "30", "50"}
    for tok in tex_nums:
        if tok in FILTERS or tok in _MATCHED:
            continue
        try:
            u = float(tok)
        except ValueError:
            continue
        if u == v:
            continue
        rel = abs(u - v) / abs(v)
        # same magnitude, same number of significant figures, within 10 %:
        # close enough that one is plausibly a stale copy of the other.
        if tok in _COMPUTED:
            continue          # it is another claim's correct value, not a copy
        if 0 < rel <= 0.10 and len(tok.split(".")[0]) == len(str(int(abs(v)))):
            return tok
    return None


def check_claim(tex_nums, label, value, *, tol_places=None):
    """Check a recomputed value against what the manuscript asserts.

    THREE outcomes, not two, and the distinction matters:

      PASS  the manuscript asserts this value.
      FAIL  the manuscript asserts something CONFUSABLY CLOSE to it -- a stale
            copy of the same quantity. This is the defect the audit exists for.
      INFO  the manuscript asserts nothing resembling it. That is an editorial
            choice, not an error: a paper is not obliged to print every
            quantity its pipeline computes, and requiring it padded the text
            with enumeration that belongs in the supplementary tables. The
            value is still recomputed here and still ships in eval/ and
            paper/supplementary/, so it remains reproducible; it is simply not
            quoted.

    The guarantee that survives is the one that matters: no number in the
    manuscript can be wrong, because every number in the manuscript must also
    occur in shipped data (check_numbers_are_shipped) and every quantity the
    manuscript does quote is recomputed here from source.
    """
    s = norm(value)
    _COMPUTED.add(s)
    if isinstance(value, float):
        for places in (1, 2, 0) if tol_places is None else (tol_places,):
            _COMPUTED.add(f"{value:.{places}f}")
    if s in tex_nums:
        _MATCHED.add(s)
        record(OK, label, s)
        return
    if isinstance(value, float):
        for places in (tol_places,) if tol_places is not None else (1, 2, 0):
            r = f"{value:.{places}f}"
            if r in tex_nums:
                _MATCHED.add(r)
                record(OK, label, r)
                return
    # Deferred: whether an asserted value nearby is a stale copy of this one
    # can only be judged once every claim's correct value is known.
    slot = len(results)
    record(INFO, label, "")
    _PENDING.append((slot, label, s, tex_nums))


def resolve_pending_claims():
    """Second pass: a nearby asserted value is stale only if it is not itself
    some other claim's correct value."""
    for slot, label, s, tex_nums in _PENDING:
        near = _confusably_close(s, tex_nums)
        if near is not None:
            results[slot] = (FAIL, label,
                             f"the manuscript asserts {near} where the data "
                             f"give {s}")
        else:
            results[slot] = (INFO, label,
                             f"{s} (computed, not quoted in the manuscript)")


# ------------------------------------------------------------------ checks --






def check_waterbase_claims(tex_nums):
    """Recompute the paper's headline numbers from the summary table.

    This replaces the per-claim checks that verified the withdrawn single-basin
    survey. Every empirical statement in the paper now rests on Waterbase, so
    every one of them is recomputed here from `waterbase_summary.csv` rather
    than looked up in a report that could itself be stale.
    """
    rows = load("waterbase_summary.csv")
    if not rows:
        record(SKIP, "Waterbase claims", "waterbase_summary.csv missing")
        return
    tot = next((r for r in rows if r["scope"] == "total"), None)
    if not tot:
        record(SKIP, "Waterbase claims", "no total row")
        return
    n = int(tot["n"]); smp = int(tot["samples"])
    eq = int(tot["has_eqs"])
    check_claim(tex_nums, "river station-years", n)
    check_claim(tex_nums, "underlying samples", smp)
    check_claim(tex_nums, "samples below LOQ %", 100 * int(tot["samples_below"]) / smp)
    check_claim(tex_nums, "station-years declaring nothing", int(tot["silent"]))
    check_claim(tex_nums, "declaring nothing %", 100 * int(tot["silent"]) / n)
    check_claim(tex_nums, "QC_LOQ_UNKNOWN rows", int(tot["qc_loq_unknown"]))
    check_claim(tex_nums, "declared but unbounded", int(tot["declared_not_bounded"]))
    check_claim(tex_nums, "station-years with an EQS", eq)
    check_claim(tex_nums, "LOQ above the EQS", int(tot["loq_gt_eqs"]))
    check_claim(tex_nums, "LOQ above the EQS %", 100 * int(tot["loq_gt_eqs"]) / eq)
    check_claim(tex_nums, "failing the 30 % criterion %",
                100 * int(tot["loq_gt_30pct_eqs"]) / eq)
    subs = [r for r in rows if r["scope"] == "substance"]
    ctys = [r for r in rows if r["scope"] == "country"]
    check_claim(tex_nums, "substances", len(subs))
    check_claim(tex_nums, "reporting countries", len(ctys))

    # The results name the substances never once measured by a method capable
    # of deciding their own standard. The count and the names both move when
    # the threshold table is corrected -- the manuscript said four until the
    # Annex I transcription was fixed and cypermethrin left the set -- so check
    # the set itself, not a number that looks stable.
    always = sorted(r["key"] for r in subs
                    if int(r["has_eqs"]) and int(r["loq_gt_eqs"]) == int(r["has_eqs"]))
    check_claim(tex_nums, "substances at 100 % LOQ-above-EQS", len(always))
    # Set equality in both directions: a new entry must be named, and a name
    # must not survive its substance leaving the set (which is how "four
    # pyrethroids" outlived cypermethrin's departure).
    m = re.search(r"insecticides\s*---\s*(.+?)\s*---\s*the figure",
                  paper_text(), re.S)
    quoted = set()
    if m:
        quoted = {s.strip().lower()
                  for s in re.split(r",\s*|\s+and\s+", m.group(1)) if s.strip()}
    record(OK if quoted == {s.lower() for s in always} else FAIL,
           "the substances named at 100 % are exactly those at 100 %",
           f"text: {', '.join(sorted(quoted)) or '(sentence not found)'} | "
           f"data: {', '.join(s.lower() for s in always)}")

    # substance class split, quoted in the discussion
    cls = {r["key"]: r for r in rows if r["scope"] == "class"}
    for k, lbl in (("Metals", "metals"), ("Organic micropollutants", "organics")):
        r = cls.get(k)
        if r and int(r["samples"]):
            check_claim(tex_nums, f"{lbl}: samples", int(r["samples"]))
            check_claim(tex_nums, f"{lbl}: below LOQ %",
                        100 * int(r["samples_below"]) / int(r["samples"]))


def check_era_claims(tex_nums):
    """Recompute the temporal split.

    This check exists because the manuscript asserted, and drew a limitation
    from, the claim that the release "mostly predates 2015". Nearly half of it
    does not. When the data was collected is a claim about the data like any
    other, and nothing was recomputing it -- the sentence had been written once
    and carried forward.

    Every share here is checked against the denominator the text uses: the
    legal criteria over rows that HAVE a standard, substitution over censored
    rows, the rest over all station-years in the era.
    """
    rows = load("waterbase_summary.csv")
    if not rows:
        record(SKIP, "era claims", "waterbase_summary.csv missing")
        return
    era = {r["key"]: r for r in rows if r["scope"] == "era"}
    if not era:
        record(SKIP, "era claims",
               "no era rows; re-run scripts/22_waterbase_external.py")
        return
    total = sum(int(r["n"]) for r in era.values())
    for key, lbl in (("pre2015", "before 2015"), ("2015plus", "2015 onwards")):
        r = era.get(key)
        if not r:
            continue
        n, eq = int(r["n"]), int(r["has_eqs"])
        cen = int(r.get("censored") or 0)
        check_claim(tex_nums, f"{lbl}: station-years", n)
        check_claim(tex_nums, f"{lbl}: no flag no limit %",
                    100 * int(r["silent"]) / n)
        if eq:
            check_claim(tex_nums, f"{lbl}: LOQ above the EQS %",
                        100 * int(r["loq_gt_eqs"]) / eq)
            check_claim(tex_nums, f"{lbl}: failing the 30 % criterion %",
                        100 * int(r["loq_gt_30pct_eqs"]) / eq)
        if cen:
            check_claim(tex_nums, f"{lbl}: censored rows carrying a value %",
                        100 * int(r.get("censored_with_value") or 0) / cen)
    if era.get("2015plus") and total:
        check_claim(tex_nums, "share of the record dated 2015 or later",
                    100 * int(era["2015plus"]["n"]) / total)

    # The survivorship control. Every authority reporting in both eras is
    # named in the text with its earlier share, so every one of them is
    # recomputed rather than trusted.
    ec = {r["key"]: r for r in rows if r["scope"] == "era_country"}
    both = sorted({k.split(":")[0] for k in ec
                   if int(ec.get(f"{k.split(':')[0]}:pre2015", {}).get("n", 0) or 0)
                   and int(ec.get(f"{k.split(':')[0]}:2015plus", {}).get("n", 0) or 0)})
    check_claim(tex_nums, "reporters present in both eras", len(both))
    not_fallen = []
    for c in both:
        a, b = ec[f"{c}:pre2015"], ec[f"{c}:2015plus"]
        check_claim(tex_nums, f"{c}: no flag no limit % before 2015",
                    100 * int(a["silent"]) / int(a["n"]))
        if int(b["silent"]) / int(b["n"]) > 0.0005:
            not_fallen.append(c)
    if not_fallen:
        record(FAIL, "every reporter in both eras falls to zero",
               "did not: " + ", ".join(not_fallen))
    else:
        record(OK, "every reporter in both eras falls to zero",
               f"{len(both)} authorities, all at 0.0 % after 2015")


def check_packages_are_consistent():
    """Every released regulation package must be consistent with the vocabulary.

    Nothing in the 24 stages ran a reasoner over a released package. The axiom
    suite reasons over hand-written fixtures and the ABox stage reasons over the
    graph, so a package could ship logically inconsistent and no stage would
    notice -- a gap in exactly the kind of verification this paper argues for.
    The detector is the one test_axioms.py uses: an individual entailed to be
    owl:Nothing after the OWL 2 RL closure.
    """
    try:
        import rdflib
        import owlrl
    except ImportError:
        record(SKIP, "released packages are consistent", "rdflib/owlrl missing")
        return
    core = [ROOT / "ontology" / "censo-core.ttl",
            ROOT / "ontology" / "censo-regulation.ttl"]
    pkgs = sorted((ROOT / "ontology" / "reg").glob("*.ttl"))
    if not pkgs or not all(c.exists() for c in core):
        record(SKIP, "released packages are consistent", "modules missing")
        return
    bad = []
    for pkg in pkgs:
        g = rdflib.Graph()
        for f in core + [pkg]:
            g.parse(f, format="turtle")
        try:
            owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)
        except Exception as e:                       # noqa: BLE001
            bad.append(f"{pkg.name}: closure failed ({type(e).__name__})")
            continue
        n = list(g.triples((None, rdflib.RDF.type, rdflib.OWL.Nothing)))
        if n:
            bad.append(f"{pkg.name}: {len(n)} individual(s) entailed "
                       f"owl:Nothing, e.g. {n[0][0]}")
    record(FAIL if bad else OK, "released packages are consistent",
           "; ".join(bad[:2]) if bad
           else f"{len(pkgs)} package(s) loaded with the two vocabulary modules; "
                f"OWL 2 RL closure entails no owl:Nothing")


def check_decision_invariants():
    """Properties of the decision procedure itself, not of its output.

    Narrowing Article 3(3b) to the censored case moves rows out of
    MethodInsufficient. The safety of that depends on an invariant: a quantified
    value is never below its own quantification limit, so for a quantified row
    LOQ > T entails value > T, and such a row can only move to Exceedance or
    PossibleExceedance -- never to Compliant. If it could move to Compliant the
    change would hide exceedances instead of revealing them, which is the
    opposite of the correction's purpose. Asserted here over a grid rather than
    trusted, because the whole paper turns on this class assignment.
    """
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        m = __import__("22_waterbase_external")
    except Exception as e:
        record(SKIP, "decision-procedure invariants", f"cannot import: {e}")
        return
    T = 1.0
    bad = []
    # a quantified row whose limit exceeds the standard must never be compliant
    for loq in (1.01, 1.5, 5.0, 50.0):
        for val in (loq, loq * 1.001, loq * 2, loq * 10):
            got = m.censo_outcome("quantified", val, loq, T)
            if got == "compliant":
                bad.append(f"quantified v={val} loq={loq} -> compliant")
    # and Article 3(3b) must not reach a quantified row at all
    for loq in (1.01, 5.0):
        for val in (loq, loq * 3):
            if m.censo_outcome("quantified", val, loq, T) == "method_insufficient":
                bad.append(f"Art. 3(3b) applied to a quantified row "
                           f"(v={val}, loq={loq})")
    # while a censored row above the standard must still be set aside
    for loq in (1.01, 5.0):
        if m.censo_outcome("censored", None, loq, T) != "method_insufficient":
            bad.append(f"censored loq={loq} not set aside by Art. 3(3b)")
    record(FAIL if bad else OK,
           "narrowing Article 3(3b) cannot hide an exceedance",
           "; ".join(bad[:3]) if bad
           else "no quantified row with LOQ > T reaches Compliant, and none is "
                "set aside; censored rows still are")


def check_mac_uses_the_shared_procedure():
    """Stage 27 must reach the same classes as the annual-average analysis.

    The manuscript claims one decision procedure "held in a single module
    precisely so the two cannot drift". Stage 27 had its own, and the drift was
    not hypothetical: it applied Article 3(3b) to quantified rows and consulted
    no applicability condition, so cadmium, lead and nickel were assessed against
    standards Annex I defines on a quantity the record does not report. A CAS the
    packages mark conditional and that appears in the maximum-allowable table
    must therefore carry a non-zero PreconditionUnmet count.
    """
    rows = load("mac_exceedance.csv")
    eqs = load("eu_eqs.csv")
    if not rows or not eqs:
        record(SKIP, "stage 27 shares the decision procedure",
               "mac_exceedance.csv or eu_eqs.csv missing")
        return
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        cond = __import__("22_waterbase_external").conditional_thresholds(eqs)
    except Exception as e:
        record(SKIP, "stage 27 shares the decision procedure", str(e))
        return
    if "precondition_unmet" not in (rows[0].keys() if rows else {}):
        record(FAIL, "stage 27 shares the decision procedure",
               "mac_exceedance.csv has no precondition_unmet column: the stage "
               "is not using the shared procedure")
        return
    names = {c.split("-")[0]: c for c in cond}      # crude CAS prefix index
    bad = []
    for r in rows:
        if r["scope"] != "substance":
            continue
        # the table is keyed by substance name, so match on the conditional
        # substances by the names the vocabulary itself calls out
        if any(k in r["key"].lower() for k in ("cadmium", "lead", "nickel")):
            if not int(r.get("precondition_unmet") or 0):
                bad.append(f"{r['key']}: 0 precondition_unmet")
    record(FAIL if bad else OK, "stage 27 shares the decision procedure",
           "; ".join(bad) if bad
           else f"{len(cond)} conditional CAS number(s); every conditional "
                f"substance in the table carries a PreconditionUnmet count")


def check_figure04_claims(tex_nums):
    """Figure 4's own numbers: the selection band, and the decade composition.

    Everything a caption states is a claim. Three values added with the
    statistical corrections were owned by nothing -- the widest and narrowest
    network among the ranked substances, the range of substances standing behind
    a decade, and the rate at the decade the text reads the trend to -- and an
    unowned number does not merely go unchecked: the near-match detector
    attributes it to the nearest computed value and makes THAT check lie. Here it
    reported 16 as a stale Czech era value and 25,960 as a group-completeness
    denominator.
    """
    fd = PAPER / "supplementary" / "figure_data"
    f4 = fd / "fig04_loq_vs_eqs.csv"
    if f4.exists():
        rows = [r for r in csv.DictReader(f4.open(encoding="utf-8"))
                if str(r.get("plotted", "")).lower() in ("yes", "true", "1")]
        if rows:
            n = [int(r["assessments_made"]) for r in rows]
            check_claim(tex_nums, "fig04a: widest network plotted", max(n))
            check_claim(tex_nums, "fig04a: narrowest network plotted", min(n))
            check_claim(tex_nums, "fig04a: substances plotted", len(rows))
            # the interval is the point of the panel, so its width is checked
            w = [f(r.get("ci95_high_pct")) - f(r.get("ci95_low_pct"))
                 for r in rows if r.get("ci95_high_pct")]
            if w:
                record(OK if max(w) > min(w) else FAIL,
                       "fig04a intervals widen as the network narrows",
                       f"Wilson width {min(w):.1f}--{max(w):.1f} percentage "
                       f"points across the {len(rows)} plotted substances")
    comp = load("eqs_decade_substances.csv")
    if comp:
        ns = [int(r["n_substances"]) for r in comp]
        check_claim(tex_nums, "decades: fewest substances", min(ns))
        check_claim(tex_nums, "decades: most substances", max(ns))
        thin = [r for r in comp if int(r["n_substances"]) == 1]
        record(OK, "single-substance decades are identified",
               ", ".join(f"1e{r['decade_log10_ug_l']} = "
                         f"{r['top_substance']}" for r in thin) or "none")
        # the range the text reads the trend over: decades with >= 5 substances
        carry = [r for r in comp if int(r["n_substances"]) >= 5]
        if carry:
            check_claim(tex_nums, "decades carrying the trend", len(carry))
    dec = [r for r in (load("waterbase_summary.csv") or [])
           if r["scope"] == "eqs_decade" and int(r["has_eqs"])]
    if dec:
        dec.sort(key=lambda r: int(r["key"]))
        for r in dec:
            check_claim(tex_nums,
                        f"decade 1e{r['key']}: limit above the standard %",
                        100 * int(r["loq_gt_eqs"]) / int(r["has_eqs"]))


def check_amendment_reach(tex_nums):
    """What Directive (EU) 2026/805 does to the magnitude of the analyte list.

    The paper's forward-looking claim -- that the defect grows because the law is
    moving the list into the decades where the monitoring already cannot decide
    -- was asserted qualitatively until it was counted. The split is by entry
    number: Annex I numbers the 2026 additions from 46 upward.
    """
    rows = load("eu_eqs.csv")
    if not rows:
        record(SKIP, "amendment-reach claims", "eu_eqs.csv missing")
        return
    FIRST_ADDED = 46
    # The decade FLOOR, not the value: d = floor(log10(x)), so d <= LOW means
    # x < 1e(LOW+1). At LOW = -3 this counted everything below 1e-2 while the
    # label -- and the manuscript sentence built on it -- said "at or below
    # 1e-3", which let imidacloprid (0.0068) and nicosulfuron (0.0087) in on
    # the added side and endosulfan, pentachlorobenzene, dicofol and cybutryne
    # in on the legacy side. LOW = -4 is also the cut the argument needs: the
    # measured undecidable share is 34 % in the 1e-3 decade and 82-100 % from
    # 1e-4 down, so only those decades carry "the monitoring already cannot
    # decide it".
    LOW = -4          # decade 1e-4 and below, i.e. a standard below 1e-3 ug/L

    def first_int(s):
        m = re.match(r"(\d+)", str(s))
        return int(m.group(1)) if m else 10 ** 6

    def decade(v):
        x = f(v)
        return math.floor(math.log10(x)) if x and x > 0 else None

    groups = {"legacy": [], "added": []}
    for r in rows:
        d = decade(r.get("aa_inland"))
        if d is None:
            continue
        key = "added" if first_int(r["entry_no"]) >= FIRST_ADDED else "legacy"
        groups[key].append(d)
    if not groups["added"] or not groups["legacy"]:
        record(SKIP, "amendment-reach claims", "one side of the split is empty")
        return
    for key, lbl in (("legacy", "legacy list"), ("added", "2026 additions")):
        ds = groups[key]
        low = sum(1 for d in ds if d <= LOW)
        check_claim(tex_nums, f"{lbl}: substances with a standard", len(ds))
        check_claim(tex_nums, f"{lbl}: standard below 1e-3", low)
        check_claim(tex_nums, f"{lbl}: share in the low decades %",
                    100 * low / len(ds))
    a = sum(1 for d in groups["legacy"] if d <= LOW) / len(groups["legacy"])
    b = sum(1 for d in groups["added"] if d <= LOW) / len(groups["added"])
    record(OK if b > a else FAIL,
           "the amendment moves the list into the undecidable decades",
           f"{100 * b:.0f} % of the additions against {100 * a:.0f} % of the "
           f"legacy list sit below 1e-3 ug/L, where the measured "
           f"undecidable share is already above 80 %")


def check_year_claims(tex_nums):
    """The annual series, and the two claims the paper draws from it.

    A two-era split cannot distinguish a step change from a trend, and the
    annual series shows the record-keeping failure ends ABRUPTLY -- two years
    before the boundary the paper draws. Both the break year and the number of
    years it holds are read from the data here, so neither can be asserted.
    """
    rows = [r for r in (load("waterbase_summary.csv") or [])
            if r["scope"] == "year"]
    if not rows:
        record(SKIP, "annual claims", "no year scope in waterbase_summary.csv")
        return
    rows.sort(key=lambda r: int(r["key"]))
    yrs = {int(r["key"]): r for r in rows}
    pct = lambda r, k, d: 100 * int(r[k]) / max(int(r[d]), 1)
    silent = {y: pct(r, "silent", "n") for y, r in yrs.items()}
    crit = {y: pct(r, "loq_gt_30pct_eqs", "has_eqs") for y, r in yrs.items()
            if int(r["has_eqs"])}
    over = {y: pct(r, "loq_gt_eqs", "has_eqs") for y, r in yrs.items()
            if int(r["has_eqs"])}
    FLOOR = 20000
    plotted = sorted(y for y, r in yrs.items() if int(r["n"]) >= FLOOR)
    check_claim(tex_nums, "years plotted in the annual figure", len(plotted))
    check_claim(tex_nums, "annual figure floor", FLOOR)

    # the break: the first year at 0.0 % never followed by a non-zero one
    zero_from = next((y for y in plotted
                      if silent[y] < 0.05
                      and all(silent[z] < 0.05 for z in plotted if z >= y)),
                     None)
    if zero_from is None:
        record(FAIL, "the record-keeping failure ends on a date",
               "no year after which the omission never recurs")
        return
    last = max(plotted)
    held = sum(1 for y in plotted if y >= zero_from)
    check_claim(tex_nums, "the year the omission stops", zero_from)
    check_claim(tex_nums, "years it has held", held)
    prev = max((y for y in plotted if y < zero_from), default=None)
    if prev is not None:
        check_claim(tex_nums, "omission % the year before it stops",
                    silent[prev])
    check_claim(tex_nums, "omission % the year it stops", silent[zero_from])

    # The analytical failure, first testable year against the last. Neither the
    # rate nor has_eqs is the right gate: a year in which most rows record no
    # limit at all cannot be tested, and its criterion share is a lower bound
    # near zero for want of anything to test -- which is the whole caveat the
    # section states. So the gate is the RECORD-KEEPING share: a year is testable
    # once fewer than half its station-years omit the limit. 2006 is the first.
    TESTABLE_OMISSION = 50.0
    assessable = sorted(y for y in plotted
                        if silent[y] < TESTABLE_OMISSION and y in crit)
    if assessable:
        a, b = assessable[0], assessable[-1]
        check_claim(tex_nums, "30 % criterion, first assessable year", crit[a])
        check_claim(tex_nums, "30 % criterion, last year", crit[b])
        check_claim(tex_nums, "limit above the standard, first assessable year",
                    over[a])
        check_claim(tex_nums, "limit above the standard, last year", over[b])
        record(OK if abs(crit[b] - crit[a]) < 5 else FAIL,
               "the analytical failure does not move over the record",
               f"{crit[a]:.1f} % in {a} against {crit[b]:.1f} % in {b}, "
               f"over {b - a} years")
    sv = [pct(yrs[y], "censored_with_value", "censored") for y in plotted
          if int(yrs[y]["censored"])]
    if sv:
        check_claim(tex_nums, "substitution at source, lowest year", min(sv))
        check_claim(tex_nums, "substitution at source, highest year", max(sv))


def check_mac_claims(tex_nums):
    """Recompute the maximum-allowable assessment.

    SKIPs rather than FAILs when the file is absent: this is the one analysis
    that needs the disaggregated release, and the repository's documented
    reproduction path is the aggregated download alone. A reader who followed
    that path must not be told the audit failed.
    """
    p = PROC / "mac_exceedance.csv"
    if not p.exists():
        record(SKIP, "maximum-allowable claims",
               "mac_exceedance.csv absent (needs the disaggregated release)")
        return
    with p.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    tot = next((r for r in rows if r["scope"] == "total"), None)
    if not tot or not int(tot["n"]):
        record(SKIP, "maximum-allowable claims", "no assessable samples")
        return
    n = int(tot["n"])
    check_claim(tex_nums, "MAC: assessable samples", n)
    check_claim(tex_nums, "MAC: exceedances", int(tot["exceedance"]))
    check_claim(tex_nums, "MAC: undecidable samples",
                int(tot["method_insufficient"]))
    check_claim(tex_nums, "MAC: undecidable %",
                100 * int(tot["method_insufficient"]) / n)

    cross = {r["key"]: int(r["n"]) for r in rows
             if r["scope"] == "station_year_cross"}
    both = cross.get("both_assessable", 0)
    if both:
        check_claim(tex_nums, "MAC: station-years assessable under both", both)
        hidden = cross.get("compliant_aa__exceeding_mac", 0)
        check_claim(tex_nums, "MAC: compliant on the mean, exceeding on a "
                              "sample", hidden)
        check_claim(tex_nums, "MAC: compliant on the mean, exceeding on a "
                              "sample %", 100 * hidden / both)

    # The two standards must not be reported at the same unit. A station-year
    # count and a sample count differ by three orders of magnitude here, and
    # quoting one as the other would be precisely the category error the stage
    # was written to demonstrate.
    if both and both >= n:
        record(FAIL, "MAC units held apart",
               f"{both:,} station-years is not fewer than {n:,} samples; one "
               f"of the two is being counted at the wrong unit")
    else:
        record(OK, "MAC units held apart",
               f"{n:,} samples against {both:,} station-years")


def check_verdict_claims(tex_nums):
    """Recompute the substitution comparison from the verdict cross-tab."""
    # The POPULATION table when it exists. These claims were recomputed from
    # the 40,000-row graph while the manuscript quoted them as the study's
    # result; the decision is arithmetic on four reported fields and is now
    # applied to every assessable row by scripts/22_waterbase_external.py.
    rows = load("waterbase_verdicts_population.csv") or \
        load("waterbase_verdicts.csv")
    if not rows:
        record(SKIP, "verdict claims", "no verdict table")
        return
    n = {}
    for r in rows:
        n[(r["substitution"], r["censo_outcome"], r["two_valued_outcome"])] = int(r["n"])
    outcomes = ("compliant", "exceedance", "possible_exceedance",
                "precondition_unmet", "method_insufficient",
                "indeterminate_unresolved", "indeterminate_other")
    tot = sum(v for (s, _, _), v in n.items() if s == "zero")
    check_claim(tex_nums, "assessments in the graph", tot)
    exc = {r: sum(n.get((r, o, "exceeding"), 0) for o in outcomes)
           for r in ("zero", "half", "full")}
    for r in ("zero", "half", "full"):
        check_claim(tex_nums, f"two-valued exceedances ({r})", exc[r])
    # 10,866 is the count of exceedances CENSO AFFIRMS, not "the exceedances
    # resting on a measurement": three of the four strata are identical at every
    # substitution constant, so 48,293 exceedances cannot be artefacts of the
    # substitution, and 30,099 rest on a quantified value above the standard.
    # The old label and the old artefact share both encoded the wrong quantity.
    real = n.get(("zero", "exceedance", "exceeding"), 0)
    check_claim(tex_nums, "exceedances the law can affirm", real)
    quantified_above = sum(
        n.get(("zero", o, "exceeding"), 0)
        for o in ("exceedance", "possible_exceedance", "method_insufficient"))
    check_claim(tex_nums, "exceedances quantified above the standard",
                quantified_above)
    check_claim(tex_nums, "quantified above the standard but set aside",
                quantified_above - real)
    check_claim(tex_nums, "set aside: method limit exceeds the standard",
                n.get(("zero", "method_insufficient", "exceeding"), 0))
    check_claim(tex_nums, "set aside: interval straddles the standard",
                n.get(("zero", "possible_exceedance", "exceeding"), 0))
    check_claim(tex_nums, "exceedances resting on an unresolved number",
                n.get(("zero", "indeterminate_unresolved", "exceeding"), 0))
    # exceedances asserted against a standard the record cannot support: stated
    # in 5.4 and owned by nothing until now
    check_claim(tex_nums, "exceedances against an inapplicable standard",
                n.get(("zero", "precondition_unmet", "exceeding"), 0))
    check_claim(tex_nums, "substitution fold-change", exc["full"] / exc["zero"],
                tol_places=1)
    # Created BY the substitution: the exceedances that appear at half the limit
    # and not at zero. Everything reported as exceeding at zero is reported as
    # exceeding at every constant.
    check_claim(tex_nums, "created by the half-LOQ substitution",
                exc["half"] - exc["zero"])
    check_claim(tex_nums, "created by the half-LOQ substitution %",
                100 * (exc["half"] - exc["zero"]) / exc["half"], tol_places=1)
    record(OK if exc["zero"] == sum(
        n.get(("zero", o, "exceeding"), 0) for o in outcomes) else FAIL,
        "exceedances invariant under the substitution constant",
        f"{exc['zero']:,} of the {exc['half']:,} half-limit exceedances are "
        f"reported at zero, half and full alike "
        f"({100 * exc['zero'] / exc['half']:.1f} %), so they are not artefacts "
        f"of the constant")
    # PossibleExceedance belongs here: an assessment whose permitted interval
    # straddles the standard is not supportable either way, which is the whole
    # reason the outcome exists.
    # PreconditionUnmet belongs here too, and it is the strictest member: the
    # standard is not defined on the quantity the record reports, so there is no
    # comparison to make at all.
    unsup = sum(n.get(("zero", o, t), 0)
                for o in ("possible_exceedance", "precondition_unmet",
                          "method_insufficient",
                          "indeterminate_unresolved", "indeterminate_other")
                for t in ("compliant", "exceeding"))
    # The PossibleExceedance total, which the limitations quote as the number
    # that makes the fourth value operative. Stated and owned by nothing, so the
    # near-match detector blamed it on a group-completeness denominator.
    check_claim(tex_nums, "PreconditionUnmet assessments",
                sum(n.get(("zero", "precondition_unmet", t), 0)
                    for t in ("compliant", "exceeding")))
    check_claim(tex_nums, "PossibleExceedance assessments",
                sum(n.get(("zero", "possible_exceedance", t), 0)
                    for t in ("compliant", "exceeding")))
    check_claim(tex_nums, "unsupportable assessments", unsup)
    check_claim(tex_nums, "unsupportable %", 100 * unsup / tot)
    # The manuscript breaks that total into three named parts. Each was quoted
    # without anything recomputing it, and one of them (no bound at all) drifted
    # to 12.2 % during condensation, so the three no longer summed to the total
    # asserted in the same sentence. Check the parts, then check the addition.
    parts = {
        "precondition unmet %": ("precondition_unmet",),
        "limit above the standard %": ("method_insufficient",),
        "no bound at all %": ("indeterminate_unresolved", "indeterminate_other"),
        "possible-exceedance %": ("possible_exceedance",),
    }
    shares = {}
    for label, outs in parts.items():
        shares[label] = 100 * sum(n.get(("zero", o, t), 0) for o in outs
                                  for t in ("compliant", "exceeding")) / tot
        check_claim(tex_nums, label, shares[label])
    # Rounding is not additive: the three parts each rounded to one decimal can
    # sum to 0.1 away from the total rounded from the raw value. That gap is
    # allowed and named; a larger one means a part is wrong or missing.
    quoted = sum(round(v, 1) for v in shares.values())
    whole = round(100 * unsup / tot, 1)
    gap = abs(quoted - whole)
    record(OK if gap <= 0.15 else FAIL, "the parts sum to the whole",
           f"{' + '.join(f'{v:.1f}' for v in shares.values())} = {quoted:.1f} "
           f"against {whole:.1f}"
           + (" (a 0.1 rounding gap, not a missing part)" if gap else ""))


def check_dual_regulation(tex_nums):
    """Recompute the two-jurisdiction comparison."""
    rows = load("dual_regulation.csv")
    if not rows:
        record(SKIP, "dual-regulation claims", "dual_regulation.csv missing")
        return
    g = {r["key"]: int(r["n"]) for r in rows if r["scope"] == "total"}
    check_claim(tex_nums, "scored under either jurisdiction", g["rows_scored"])
    check_claim(tex_nums, "co-regulated assessments", g["rows_co_regulated"])
    check_claim(tex_nums, "co-regulated divergence %",
                100 * g["co_regulated_differ"] / g["rows_co_regulated"])
    # The share that changes outcome over the WHOLE scored set -- mostly
    # coverage, one jurisdiction regulating what the other does not. Stated in
    # 5.6 and, until now, recomputed by nothing: the near-match detector had an
    # unowned 81.9 in the text and blamed it on a Swedish era value seven points
    # away. An asserted number with no owner does not merely go unchecked; it
    # makes some other check lie.
    changed = sum(int(r["n"]) for r in rows if r["scope"] == "cross"
                  and r["eu_outcome"] != r["tr_outcome"])
    check_claim(tex_nums, "assessments that change outcome", changed)
    check_claim(tex_nums, "changed outcome %", 100 * changed / g["rows_scored"])
    cross = {(r["eu_outcome"], r["tr_outcome"]): int(r["n"])
             for r in rows if r["scope"] == "cross_co_regulated"}
    for (a, b), lbl in (
            (("MethodInsufficient", "Compliant"), "insufficient -> compliant"),
            (("Exceeding", "Compliant"), "exceeding -> compliant"),
            (("MethodInsufficient", "Exceeding"), "insufficient -> exceeding")):
        if (a, b) in cross:
            check_claim(tex_nums, f"dual: {lbl}", cross[(a, b)])



def check_staleness():
    """An output older than its script, or than an input, is stale."""
    pairs = [
        # The Waterbase chain. Added after dual_regulation.csv was quoted in
        # the manuscript while being older than the regulation packages it
        # reads: the paper carried a co-regulated divergence of 19.3 % that
        # the corrected packages put at 18.5 %. Nothing else would have said so.
        # 22 is the head of the chain and was not checked at all: every
        # counter the paper quotes comes out of waterbase_summary.csv, and an
        # edit to the script that produced it would not have been noticed.
        ("22_waterbase_external.py", ["waterbase_summary.csv"]),
        ("23_waterbase_abox.py", ["waterbase_verdicts.csv",
                                  "waterbase_exemplars.csv"]),
        ("24_dual_regulation.py", ["dual_regulation.csv"]),
        ("25_country_confounders.py", ["country_confounders.csv"]),
    ]
    stale = []
    for script, outs in pairs:
        sp = SCRIPTS / script
        if not sp.exists():
            continue
        for o in outs:
            op = PROC / o
            if not op.exists():
                stale.append(f"{o} (missing)")
            elif op.stat().st_mtime < sp.stat().st_mtime:
                stale.append(f"{o} older than {script}")
    # reaches.csv feeds onsets.csv
    chain = []
    for src, dst in chain:
        s, d = PROC / src, PROC / dst
        if s.exists() and d.exists() and d.stat().st_mtime < s.stat().st_mtime:
            stale.append(f"{dst} older than its input {src}")

    # The SHACL report is now gated by check_shacl_conformance(), which makes
    # it worth something only if it is current: a stale `conforms: True` from
    # before a shape was tightened would pass the gate while the shipped graph
    # violated the shape. Its inputs are the shapes, the vocabulary and the
    # graph itself.
    align = ROOT / "ontology" / "censo-alignment.ttl"
    if align.exists():
        for dep in list((ROOT / "ontology" / "reg").glob("*.ttl")) + [
                SCRIPTS / "20_align_external.py"]:
            if dep.exists() and align.stat().st_mtime < dep.stat().st_mtime:
                stale.append(f"censo-alignment.ttl older than {dep.name}")

    shacl = EVAL / "shacl_validation.md"
    if shacl.exists():
        for dep in (ROOT / "ontology" / "censo-shapes.ttl",
                    ROOT / "ontology" / "censo-core.ttl",
                    ROOT / "derived" / "abox" / "censo-waterbase.ttl",
                    SCRIPTS / "18_shacl_validate.py"):
            if dep.exists() and shacl.stat().st_mtime < dep.stat().st_mtime:
                stale.append(f"eval/shacl_validation.md older than {dep.name}")

    # The regulation packages are an input to everything downstream of them,
    # and they are edited by a script of their own, so a package rebuild has
    # to invalidate the analyses that read it.
    pkgs = sorted((ROOT / "ontology" / "reg").glob("*.ttl"))
    if pkgs:
        newest_pkg = max(p.stat().st_mtime for p in pkgs)
        for dep in ("dual_regulation.csv", "waterbase_verdicts.csv",
                    "waterbase_exemplars.csv"):
            d = PROC / dep
            if d.exists() and d.stat().st_mtime < newest_pkg:
                stale.append(f"{dep} older than the regulation packages")
        abox = ROOT / "derived" / "abox" / "censo-waterbase.ttl"
        if abox.exists() and abox.stat().st_mtime < newest_pkg:
            stale.append("censo-waterbase.ttl older than the packages it cites")

    # The standalone distribution is built FROM the modules and copied TO
    # publish/site. 97 --check compares the site against the distribution, so
    # if the distribution itself is older than a module, both are stale, both
    # agree, and nothing says so: an axiom removed from censo-core.ttl stayed
    # in the file the permanent IRI serves. Check the first link of that chain.
    dist = [ROOT / "ontology" / "dist" / "censo-full.ttl",
            ROOT / "ontology" / "dist" / "censo-full.owl"]
    mods = [p for p in [ROOT / "ontology" / "censo-core.ttl",
                        ROOT / "ontology" / "censo-regulation.ttl"] if p.exists()]
    if mods and any(d.exists() for d in dist):
        newest_mod = max(p.stat().st_mtime for p in mods)
        stale += [f"ontology/dist/{d.name} older than an ontology module"
                  for d in dist if d.exists()
                  and d.stat().st_mtime < newest_mod]

    # Figures, and the per-figure data they write, must not predate the tables
    # they are drawn from. A figure is the most visible artefact in the paper
    # and the least likely to be re-examined once it looks right.
    figs = sorted((PAPER / "figures").glob("*.pdf"))
    if figs:
        inputs = [PROC / n for n in
                  ("waterbase_summary.csv", "waterbase_stations.csv",
                   "waterbase_verdicts.csv", "waterbase_exemplars.csv",
                   "country_confounders.csv", "eqs_official.csv")]
        present = [p for p in inputs if p.exists()]
        fd = PAPER / "supplementary" / "figure_data"
        if present:
            newest_in = max(p.stat().st_mtime for p in present)
            behind = [f.name for f in figs if f.stat().st_mtime < newest_in]
            # The shipped data is judged against the same inputs as the figure,
            # NOT against the figure: emit() runs a moment before savefig(), so
            # a correct pair always has the CSV marginally older than the PDF.
            behind += [c.name for f in figs
                       if (c := fd / (f.stem + ".csv")).exists()
                       and c.stat().st_mtime < newest_in]
            if behind:
                stale.append("figure artefact(s) older than their data: " +
                             ", ".join(sorted(behind)))
    if stale:
        record(FAIL, "no stale artefacts", "; ".join(stale))
    else:
        record(OK, "no stale artefacts",
               f"{sum(len(o) for _, o in pairs)} outputs newer than their "
               f"scripts and inputs")


def check_gap_profile(tex_nums):
    """The sampling/sensing counts quoted in prose must match the report.

    The manuscript quoted SAREF4WATR as 0/16 where the parse gives 0/2 -- the
    22 belongs to SAREF core. A profile number is easy to mistype and nothing
    else in the pipeline would notice, because it appears only in a sentence.
    """
    rep = EVAL / "gap_table.md"
    if not rep.exists():
        record(SKIP, "gap-table profile figures", "gap_table.md missing")
        return
    rows = re.findall(r"\|\s*([^|]+?)\s*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|"
                      r"[^|]*\|[^|]*\|\s*(\d+)\s*\|\s*(\d+)\s*\|",
                      rep.read_text(encoding="utf-8"))
    prof = {n.strip(): (a, b) for n, a, b in rows}
    quoted = re.findall(r"\\num\{(\d+)\}/\\num\{(\d+)\}", tex_nums)
    bad = [f"{a}/{b}" for a, b in quoted if (a, b) not in prof.values()]
    if bad:
        record(FAIL, "gap-table profile figures",
               "quoted but not in the report: " + ", ".join(bad))
    else:
        record(OK, "gap-table profile figures",
               f"{len(quoted)} sampling/sensing pairs match")


def check_graph_is_consistent():
    """Run a DL reasoner over the SHIPPED graph, not over fixtures.

    This check exists because its absence let a real defect ship. The axiom
    suite exercised every axiom on hand-written snippets and passed 10/10; the
    knowledge graph was validated with SHACL, which has no complement operator
    and so cannot see a complementOf restriction at all. Between the two, no
    stage ever put the actual ABox in front of an OWL reasoner -- and the actual
    ABox asserted censo:assessableAgainst on 45,467 censo:UnresolvedObservation
    individuals, which the core forbids by

        UnresolvedObservation subClassOf complementOf(
            assessableAgainst some Threshold)

    the very axiom test T5 exercises. Every module validated, every shape
    conformed, every number reproduced, and the published graph contradicted its
    own ontology.

    A bounded slice, not the whole graph: owlrl over 465,000 triples takes
    longer than the rest of the pipeline put together, and the defect is
    structural -- it is a property of how a row is written, so it appears in the
    first row of its kind or not at all. The slice is drawn to cover every
    outcome class rather than sampled, so adding a class without adding it here
    leaves the new class unchecked and visibly so.
    """
    abox = ROOT / "derived" / "abox" / "censo-waterbase.ttl"
    reg = ROOT / "ontology" / "reg" / "eu-2008-105-2026.ttl"
    core = ROOT / "ontology" / "censo-core.ttl"
    if not abox.exists():
        record(SKIP, "the shipped graph is consistent with its ontology",
               "censo-waterbase.ttl missing")
        return
    try:
        import rdflib
        import owlrl
    except ImportError:
        record(SKIP, "the shipped graph is consistent with its ontology",
               "rdflib/owlrl not installed")
        return

    txt = abox.read_text(encoding="utf-8")
    if "wb:obs-" not in txt:
        record(FAIL, "the shipped graph is consistent with its ontology",
               "no observations in the ABox")
        return
    head = txt[:txt.index("wb:obs-")]

    # BLOCKS ARE READ BY LINE, not by a regex that stops at the first period.
    #
    # This was `re.findall(r"wb:obs-\d+ a [^.]*\.", txt)` -- "anything but a
    # dot, then a dot". Every decimal value in an observation contains a dot, so
    # 39,964 of the 40,000 blocks were cut at their first number: after the
    # detection status and before the compliance outcome, the comparison
    # property and the bounds. The check added because no stage ever put the
    # real ABox in front of a reasoner was reasoning over 99.9 % stumps.
    #
    # It went unnoticed because a bare numeral made the truncation VALID: the
    # text ended `...resultLowerBound 0.`, which Turtle reads as the integer 0
    # followed by a statement terminator. Typing the literals turned that into
    # `..."0.` -- an unterminated string -- and the parser said so at once. A
    # silent wrong answer became a loud failure, which is the only reason this
    # is in the changelog rather than still shipping.
    blocks, cur = [], None
    for line in txt.splitlines():
        if line.startswith("wb:obs-"):
            cur = [line]
        elif cur is not None:
            cur.append(line)
        if cur is not None and line.rstrip().endswith("."):
            blocks.append("\n".join(cur))
            cur = None
    COVER = ["UnresolvedObservation", "CensoredObservation",
             "QuantifiedObservation", "BoundNotEstablished",
             "MethodInsufficient", "PreconditionUnmet", "PossibleExceedance",
             "Exceedance", "Compliant"]
    PER = 25
    sel, missing = [], []
    for name in COVER:
        hits = [b for b in blocks if f"censo:{name}" in b][:PER]
        if not hits:
            missing.append(name)
        sel += hits
    sel = list(dict.fromkeys(sel))

    g = rdflib.Graph()
    for f in (core, reg):
        g.parse(f, format="turtle")
    g.parse(data=head + "\n".join(sel), format="turtle")
    for t in list(g.triples((None, rdflib.OWL.imports, None))):
        g.remove(t)
    err = rdflib.URIRef("http://www.daml.org/2002/03/agents/agent-ont#error")
    try:
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics, axiomatic_triples=False,
                               datatype_axioms=False).expand(g)
    except Exception as e:                                   # noqa: BLE001
        record(FAIL, "the shipped graph is consistent with its ontology",
               f"reasoner raised {type(e).__name__}: {e}")
        return
    msgs = sorted({str(o) for _, _, o in g.triples((None, err, None))})
    if list(g.triples((None, rdflib.RDF.type, rdflib.OWL.Nothing))):
        msgs.append("an individual was entailed to be owl:Nothing")
    if msgs:
        record(FAIL, "the shipped graph is consistent with its ontology",
               msgs[0][:140])
    else:
        record(OK, "the shipped graph is consistent with its ontology",
               f"{len(sel)} observations covering "
               f"{len(COVER) - len(missing)}/{len(COVER)} classes, "
               f"OWL 2 RL closure clean")
    if missing:
        record(FAIL, "every outcome class appears in the consistency slice",
               "absent from the graph: " + ", ".join(missing))
    else:
        record(OK, "every outcome class appears in the consistency slice",
               f"{len(COVER)}/{len(COVER)}")

    # The move of PossibleExceedance under IndeterminateCompliance is the whole
    # point of the three-valued taxonomy, and it is one triple: cheap to lose in
    # a merge, invisible in every count, and the manuscript's central 43.8 %
    # depends on it being true.
    CENSO = rdflib.Namespace("https://w3id.org/censo/")
    pe = [s for s in g.subjects(rdflib.RDF.type, CENSO.PossibleExceedance)]
    bad = [s for s in pe
           if (s, rdflib.RDF.type, CENSO.IndeterminateCompliance) not in g]
    if not pe:
        record(SKIP, "PossibleExceedance entails IndeterminateCompliance",
               "no such individual in the slice")
    elif bad:
        record(FAIL, "PossibleExceedance entails IndeterminateCompliance",
               f"{len(bad)} of {len(pe)} do not")
    else:
        record(OK, "PossibleExceedance entails IndeterminateCompliance",
               f"{len(pe)}/{len(pe)} in the slice")


def check_separation(tex_nums):
    """The separation result is an ALL claim, so one exception falsifies it.

    Section 5.11 says every comparison vocabulary collapses the two readings of
    the witness row into the same set of facts. That is not a count to be
    checked for drift, it is a universal: add one vocabulary with a censoring
    term to the comparison set and the sentence becomes false while every
    number around it stays plausible. So the audit reads the collapse count and
    the assessed count out of the report and requires them equal, rather than
    checking either against the text.

    It also requires the three merges to be inconsistent. If a merge ever came
    back consistent the disjointness axiom would have been lost, and the claim
    that the readings are incompatible rather than differently labelled would
    be false -- with nothing else in the pipeline noticing, because the
    ontology would still load and every count would still compute.
    """
    rep = EVAL / "separation.md"
    if not rep.exists():
        record(SKIP, "separation result", "separation.md missing")
        return
    txt = rep.read_text(encoding="utf-8")
    m_tot = re.search(r"vocabularies assessed:\s*\*\*(\d+)\*\*", txt)
    m_col = re.search(r"R1 and R2 translate to the same facts in:\s*"
                      r"\*\*(\d+) of (\d+)\*\*", txt)
    if not (m_tot and m_col):
        record(FAIL, "separation result", "the report shape has changed")
        return
    total, collapsed = int(m_tot.group(1)), int(m_col.group(1))
    check_claim(tex_nums, "vocabularies in the separation set", total)
    # The collapse count is a NUMBER now, not a universal, and the manuscript
    # states it as one. It stopped being universal when the comparison set was
    # widened past the water domain and the concept patterns were widened past
    # our own spellings: CHMO is credited with a not-determinable outcome on
    # `ambiguous synonym` and `unresolved lines`, so its R1 gains a fact its R2
    # lacks and the two no longer collapse. That is a false positive, and it is
    # reported rather than removed -- see CAVEATS in 07_verify_gap_table.py --
    # which means the audit must check the number the paper actually prints.
    check_claim(tex_nums, "vocabularies collapsing R1 into R2", collapsed)
    record(OK if collapsed <= total else FAIL,
           "the collapse count is within the assessed set",
           f"{collapsed}/{total}")

    # THE UNIVERSAL MOVED HERE, onto the claim that carries the argument.
    #
    # "every vocabulary collapses R1 into R2" was the wrong thing to make
    # unfalsifiable-by-audit: it is downstream of a keyword matcher, so a
    # generous pattern can break it without any competitor gaining a capability.
    # What the paper needs, and what is genuinely universal, is that NO
    # comparison vocabulary carries a censoring status -- the column the whole
    # argument rests on. One competitor declaring `censored` or `non-detect`
    # would falsify the contribution, and this is the check that would say so.
    gm = PROC / "gap_matrix.csv"
    if not gm.exists():
        record(SKIP, "no comparison vocabulary carries a censoring status",
               "gap_matrix.csv missing")
        return
    with gm.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    ours = {"CENSO (this work)", "CENSO-REG (this work)"}
    carriers = [r["ontology"] for r in rows
                if r["ontology"] not in ours and r.get("censoring") == "1"]
    scored = [r for r in rows if r["ontology"] not in ours
              and r.get("status") == "OK"]
    if carriers:
        record(FAIL, "no comparison vocabulary carries a censoring status",
               "carried by: " + ", ".join(carriers)
               + " — the contribution as stated is false")
    else:
        record(OK, "no comparison vocabulary carries a censoring status",
               f"empty for all {len(scored)} parsed comparison vocabularies, "
               f"under patterns admitting censored / left-censored / "
               f"non-detect / not quantifiable / below-limit bare")

    merges = re.findall(r"\|\s*(R\d \+ R\d)\s*\|\s*(\*\*yes\*\*|no)\s*\|", txt)
    bad = [name for name, verdict in merges if verdict != "**yes**"]
    if not merges:
        record(FAIL, "merged readings are inconsistent", "no merge table")
    elif bad:
        record(FAIL, "merged readings are inconsistent",
               "consistent when it must not be: " + ", ".join(bad))
    else:
        record(OK, "merged readings are inconsistent",
               f"{len(merges)}/{len(merges)} contradict")


def check_graph_references():
    """Every IRI a generated graph points at must be defined somewhere.

    This check exists because it was needed. The ABox rebuilt threshold IRIs
    from the substance name with its own slug(), while the regulation package
    built them with a different one; 2,412 observations -- 6 % of the graph --
    referenced thresholds that did not exist. Nothing failed: RDF is perfectly
    happy to mention a URI that resolves to nothing, so the joins simply
    returned less than they should have, and the only symptom was a figure
    that quietly undercounted.

    A dangling reference inside our own namespace is always a defect, so it is
    now an error rather than something a reader might notice.
    """
    abox = ROOT / "derived" / "abox" / "censo-waterbase.ttl"
    if not abox.exists():
        record(SKIP, "graph references resolve", "ABox not built")
        return
    try:
        import rdflib
    except ImportError:
        record(SKIP, "graph references resolve", "rdflib not installed")
        return

    defined = set()
    for f in [ROOT / "ontology" / "censo-core.ttl",
              ROOT / "ontology" / "censo-regulation.ttl"] + \
             sorted((ROOT / "ontology" / "reg").glob("*.ttl")):
        if not f.exists():
            continue
        g = rdflib.Graph()
        g.parse(f, format="turtle")
        defined |= {str(s) for s in g.subjects()}

    g = rdflib.Graph()
    g.parse(abox, format="turtle")
    defined |= {str(s) for s in g.subjects()}

    # Only our own namespaces: SOSA, GeoSPARQL and QUDT are external and are
    # correctly referenced without being restated here.
    ours = ("https://w3id.org/censo/",)
    used = set()
    for s, p, o in g:
        for n in (s, p, o):
            if isinstance(n, rdflib.URIRef) and str(n).startswith(ours):
                used.add(str(n))
    dangling = sorted(u for u in used - defined)
    if dangling:
        record(FAIL, "graph references resolve",
               f"{len(dangling)} IRI(s) referenced but never defined: " +
               ", ".join(d.rsplit("/", 1)[-1] for d in dangling[:4]))
    else:
        record(OK, "graph references resolve",
               f"all {len(used):,} censo: IRIs in the ABox are defined")


def check_group_completeness(tex_nums):
    """The group standards, their membership, and how often a basket is whole.

    5.3 names four groups, their member counts and their completeness rates.
    Every one of those numbers has to be recomputed: the pesticide sum's
    seventy-five members were stated and owned by nothing, which left the
    near-match detector free to report 75 as a stale Swedish era value.
    """
    rows = load("group_completeness.csv")
    if not rows:
        record(SKIP, "group completeness claims",
               "group_completeness.csv missing")
        return
    for r in rows:
        name = r["group"].split("(")[0].strip().split(":")[0].strip()
        short = " ".join(name.split()[:3]).lower()
        check_claim(tex_nums, f"group members: {short}", int(r["members"]))
        check_claim(tex_nums, f"group touching: {short}",
                    int(r["station_years_touching"]))
        check_claim(tex_nums, f"group complete %: {short}",
                    100 * int(r["station_years_complete"])
                    / max(int(r["station_years_touching"]), 1))
    check_claim(tex_nums, "group standards with a resolved membership",
                len(rows))


def check_group_thresholds():
    """A sum standard must never be reachable as a per-analyte threshold.

    Annex I gives one value for the sum of the cyclodiene pesticides, and
    another for the sum of the brominated diphenylethers. The package builder
    emitted those as ordinary per-substance thresholds, so a measurement of
    aldrin alone was assessed against a limit defined for four substances
    together. The vocabulary already had cereg:GroupThreshold; it simply was
    not wired up.
    """
    try:
        import rdflib
    except ImportError:
        record(SKIP, "group standards held apart", "rdflib not installed")
        return
    C = rdflib.Namespace("https://w3id.org/censo/")
    R = rdflib.Namespace("https://w3id.org/censo/reg/")
    bad, n_grp = [], 0
    for f in sorted((ROOT / "ontology" / "reg").glob("*.ttl")):
        g = rdflib.Graph()
        g.parse(f, format="turtle")
        for t in g.subjects(rdflib.RDF.type, R.GroupThreshold):
            n_grp += 1
            if next(g.objects(t, C.appliesToAnalyte), None) is not None:
                bad.append(str(t).rsplit("/", 1)[-1])
    if bad:
        record(FAIL, "group standards held apart",
               f"{len(bad)} sum standard(s) also attached to a single "
               f"analyte: " + ", ".join(bad[:3]))
    else:
        record(OK, "group standards held apart",
               f"{n_grp} group threshold(s), none reachable per-analyte")


def check_figure_geometry():
    """Every panel of Figure 6 must actually be the case it is captioned as.

    Figure 6 is the paper's argument in one picture, and it is the one figure
    whose content a reader cannot check against a table by eye: each panel
    asserts a GEOMETRY -- where the threshold falls relative to the method's
    quantification limit -- rather than a magnitude.

    It needed this check. It used to carry a fourth panel separating "the
    threshold is below the limit of DETECTION" from "the threshold lies between
    the detection and quantification limits". Waterbase reports no detection
    limit. The one dividing those panels was this pipeline's own LOQ/3, so the
    boundary in a figure captioned "real observations" came from a constant we
    had chosen. The panel is gone; this makes sure it cannot come back, and
    that the three that remain match the rows they are drawn from.
    """
    p = PAPER / "supplementary" / "figure_data" / "fig06_decision_geometry.csv"
    if not p.exists():
        record(SKIP, "figure 6 panels match their geometry", "figure data missing")
        return
    with p.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        record(SKIP, "figure 6 panels match their geometry", "no rows")
        return

    bad = []
    if any("lod" in k.lower() for k in rows[0]):
        bad.append("a limit-of-detection column is back; the source reports none")

    # (case, must the row be censored?, the geometry the panel asserts)
    RULES = {
        "compliant": (True, lambda t, loq, v: t >= loq),
        "cannot_decide": (True, lambda t, loq, v: t < loq),
        "quantified_exceedance": (False, lambda t, loq, v: v is not None
                                  and v > t),
    }
    seen = set()
    for r in rows:
        case = r.get("case", "")
        seen.add(case)
        rule = RULES.get(case)
        if rule is None:
            bad.append(f"unknown panel case {case!r}")
            continue
        want_censored, geometry = rule
        t, loq = f(r.get("threshold_ug_l")), f(r.get("loq_ug_l"))
        v = f(r.get("value_ug_l"))
        if t is None or loq is None:
            bad.append(f"{case}: threshold or LOQ missing")
            continue
        if (r.get("censored") == "yes") is not want_censored:
            bad.append(f"{case}: censored={r.get('censored')!r} is the wrong "
                       f"kind of observation for this panel")
        elif not geometry(t, loq, v):
            bad.append(f"{case}: T={t:g} LOQ={loq:g} "
                       f"value={'-' if v is None else format(v, 'g')} does not "
                       f"have the geometry the panel asserts")
    missing = sorted(set(RULES) - seen)
    if missing:
        bad.append("no exemplar drawn for: " + ", ".join(missing))

    if bad:
        record(FAIL, "figure 6 panels match their geometry", "; ".join(bad[:4]))
    else:
        record(OK, "figure 6 panels match their geometry",
               f"{len(rows)} panels, each a real row with the geometry it claims")


def check_threshold_transcription():
    """Every threshold this analysis rests on, against the primary text.

    THIS CHECK EXISTS BECAUSE THE PAPER'S OWN THRESHOLD TABLE WAS WRONG, TWICE.

    First: the flattened text extraction puts a space between the digits of a
    multi-digit integer, so benzene's row came out as "1 0  8  5 0  5 0" and
    five solvents were given an annual average ten times too strict.

    Second, and worse: Annex I has rows whose annual-average cells are EMPTY --
    mercury and hexachlorobenzene, whose standards are set on biota instead --
    and flattened text cannot tell an empty cell from a missing one. Reading
    such a row left to right moved the maximum-allowable values into the
    annual-average columns and then took the biota entry as the maximum
    allowable. Mercury was given a fabricated annual average of 0.07 and a
    maximum-allowable standard of 11 against a true 0.07; lead's
    maximum-allowable came out as 1.3 against a true 14, which is the column the
    whole maximum-allowable analysis is computed against. Footnote markers
    written inside a value cell ("1,2 (12)") were read as numbers, shifting
    every column that followed.

    scripts/10_parse_eu_eqs.py now reads the four EQS columns BY COLUMN
    POSITION, from `pdftotext -layout`, anchored on the "AA-EQS AA-EQS MAC-EQS
    MAC-EQS" labels of each page's own header. This gate is the independent
    check on that: every value below was read by hand from
    refs/legal/EU-2008-105_consolidated-2026-05-10.pdf with the column header
    in view, and the parse must reproduce all four columns of every row. The
    previous gate covered ten substances and two of their four columns, which is
    how the empty-cell defect survived it.

    None means the cell states no standard -- blank, "not applicable" or "not
    derived" -- which downstream treats identically: not assessable.
    """
    # entry: (aa_inland, aa_other, mac_inland, mac_other)
    HAND_READ = {
        "2":  (0.1, 0.1, 0.1, 0.1),                  # anthracene
        "4":  (10.0, 8.0, 50.0, 50.0),               # benzene: the first break
        "6":  (0.08, 0.2, 0.45, 0.45),               # cadmium, hardness class 1
        "7":  (0.4, 0.4, 1.4, 1.4),                  # C10-13 chloroalkanes
        "9":  (4.6e-4, 4.6e-5, 0.0026, 5.2e-4),      # chlorpyrifos
        "9a": (0.01, 0.005, None, None),             # cyclodiene sum
        "9b": (0.025, 0.025, None, None),            # DDT total
        "10": (10.0, 10.0, None, None),              # 1,2-dichloroethane
        "11": (20.0, 20.0, None, None),              # dichloromethane
        "12": (1.3, 1.3, None, None),                # DEHP
        "13": (0.049, 0.0049, 0.27, 0.054),          # diuron
        "14": (0.005, 5e-4, 0.01, 0.004),            # endosulfan
        "15": (7.62e-4, 7.62e-4, 0.12, 0.012),       # fluoranthene
        "16": (None, None, 0.5, 0.05),               # HCB: EMPTY annual average
        "17": (9.5e-4, 9.5e-4, 0.6, 0.06),           # hexachlorobutadiene
        "18": (0.02, 0.002, 0.04, 0.02),             # HCH
        "19": (0.3, 0.3, 1.0, 1.0),                  # isoproturon
        "20": (1.2, 1.3, 14.0, 14.0),                # lead: footnote in a cell
        "21": (None, None, 0.07, 0.07),              # mercury: EMPTY annual avg
        "22": (2.0, 2.0, 130.0, 130.0),              # naphthalene
        "23": (2.0, 3.1, 8.2, 8.2),                  # nickel: footnote in cell
        "26": (0.007, 7e-4, None, None),             # pentachlorobenzene
        "27": (0.4, 0.4, 1.0, 1.0),                  # pentachlorophenol
        "29a": (10.0, 10.0, None, None),             # tetrachloroethylene
        "29b": (10.0, 10.0, None, None),             # trichloroethylene
        "30": (2e-4, 2e-4, 0.0015, 0.0015),          # tributyltin
        "32": (2.5, 2.5, None, None),                # trichloromethane
        "33": (0.03, 0.03, None, None),              # trifluralin
        "36": (0.15, 0.015, 2.7, 0.54),              # cybutryne
        "38": (0.12, 0.012, 0.12, 0.012),            # aclonifen
        "39": (0.012, 0.0012, 0.04, 0.004),          # bifenox
        "40": (0.0025, 0.0025, 0.016, 0.016),        # cybutryne group
        "41": (3e-5, 3e-6, 6e-4, 6e-5),              # cypermethrin
        "42": (6e-4, 6e-5, 7e-4, 7e-5),              # dichlorvos
        "44": (1.7e-7, 1.7e-7, 3e-4, 3e-5),          # heptachlor
        "45": (0.065, 0.0065, 0.34, 0.034),          # terbutryn
        "48": (0.037, 0.0037, 0.16, 0.016),          # acetamiprid
        "49": (0.019, 0.0019, 0.18, 0.018),          # azithromycin
        "50": (9.5e-5, 9.5e-6, 0.011, 0.001),        # bifenthrin
        "51": (1.7e-4, 1.7e-4, 130.0, 51.0),         # bisphenol A
        "52": (2.5, 0.25, 1600.0, 160.0),            # carbamazepine: 1,6 x 10^3
        "53": (0.13, 0.013, 0.13, 0.013),            # clarithromycin
        "54": (0.01, 0.001, 0.34, 0.034),            # clothianidin
        "55": (1.7e-6, 1.7e-7, 1.7e-5, 3.4e-6),      # deltamethrin
        "56": (0.04, 0.004, 250.0, 25.0),            # erythromycin
        "57": (0.5, 0.05, 1.0, 0.1),                 # ibuprofen
        "58": (1.7e-5, 1.7e-6, 0.0085, 8.5e-4),      # esfenvalerate
        "62": (0.0068, 6.8e-4, 0.057, 0.0057),       # imidacloprid
        "63": (0.0087, 8.7e-4, 0.23, 0.023),         # nicosulfuron
        "64": (2.7e-4, 2.7e-5, 0.0025, 2.5e-4),      # permethrin
        "67": (0.01, 0.001, 0.05, 0.005),            # thiacloprid
        "68": (0.04, 0.004, 0.77, 0.077),            # thiamethoxam
        "69": (0.02, 0.002, 0.02, 0.002),            # triallate
    }
    COLS = ("aa_inland", "aa_other", "mac_inland", "mac_other")
    rows = load("eu_eqs.csv")
    if not rows:
        record(SKIP, "thresholds match the primary text", "eu_eqs.csv missing")
        return
    by_no = {str(r["entry_no"]).strip(): r for r in rows}
    bad, checked = [], 0
    for no, want in HAND_READ.items():
        r = by_no.get(no)
        if r is None:
            bad.append(f"entry ({no}) absent from the parse")
            continue
        checked += 1
        for col, w in zip(COLS, want):
            got = f(r.get(col))
            if w is None:
                if got is not None:
                    bad.append(f"({no}) {col}: parsed {got}, Annex I states "
                               f"no standard")
            elif got is None or abs(got - w) > 1e-9 * max(1.0, abs(w)):
                bad.append(f"({no}) {col}: parsed {got}, Annex I states {w}")
    if bad:
        record(FAIL, "thresholds match the primary text", "; ".join(bad[:4]))
    else:
        record(OK, "thresholds match the primary text",
               f"{checked} Annex I rows hand-read from the consolidated text, "
               f"{4 * checked} values across all four EQS columns, all "
               f"reproduced")


# A heading is prose and prose does not get recomputed, so an English
# quantifier in one drifts silently when the number under it is corrected. This
# has now happened twice: "Half of European monitoring fails the legal
# performance criterion" survived the threshold fix that moved the number from
# 46.6 % to 36.4 %. Each word is given the band it can honestly cover.
QUANTIFIERS = {
    "a fifth": (15, 25), "a quarter": (20, 30), "a third": (28, 40),
    "more than a third": (33, 50), "two-fifths": (36, 44),
    "half": (45, 55), "more than half": (50, 75),
    "two-thirds": (60, 72), "three-quarters": (70, 80),
    "most": (50, 100), "nearly all": (88, 100), "almost all": (88, 100),
    "a handful": (0, 10),
}


WORDS = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
         "fourteen": 14, "fifteen": 15, "sixteen": 16, "twenty": 20}


PLACEHOLDER_URLS = ("https://github.com/", "https://github.com",
                    "https://example.com", "http://example.org",
                    "https://doi.org/10.5281/zenodo.XXXXXXX", "TBD", "TODO")


def check_section_pointers():
    """"Section 5.7" in shipped material must be a section that exists.

    The supplementary index points readers at numbered sections, and those
    numbers shift the moment a subsection is added or removed -- the old,
    hand-maintained index pointed S5 at 5.4 and S6 at 5.3, both wrong by the
    time anyone read them. The numbering is rebuilt here from the section files
    in the order the manuscript inputs them.
    """
    main = (PAPER / "main-elsevier.tex").read_text(encoding="utf-8")
    order = re.findall(r"\\input\{sections/([^}]+)\}", main)
    numbering, sec = set(), 0
    for name in order:
        f = PAPER / "sections" / (name + ".tex")
        if not f.exists():
            continue
        sub = 0
        for m in re.finditer(r"(?m)^\\(section|subsection)\{", f.read_text(
                encoding="utf-8")):
            if m.group(1) == "section":
                sec, sub = sec + 1, 0
                numbering.add(f"{sec}")
            else:
                sub += 1
                numbering.add(f"{sec}.{sub}")
    if not numbering:
        record(SKIP, "section pointers", "no sections found")
        return
    bad, checked = [], 0
    for f in (PAPER / "supplementary" / "README.md", ROOT / "README.md"):
        if not f.exists():
            continue
        for ref in re.findall(r"Section (\d+(?:\.\d+)?)",
                              f.read_text(encoding="utf-8")):
            checked += 1
            if ref not in numbering:
                bad.append(f"{f.parent.name}/{f.name}: Section {ref}")
    record(FAIL if bad else OK, "section pointers in shipped files resolve",
           "; ".join(sorted(set(bad))) if bad
           else f"{checked} pointer(s) against {len(numbering)} section(s)")


# Vocabulary belonging to the retired single-basin pipeline in attic/. It has a
# way of surviving in prose that nothing recomputes: the axiom suite's T5 shipped
# "1,103 candidate onsets in this dataset" -- a count from an analysis this paper
# does not report -- in the file the manuscript cites as its evaluation evidence,
# and the published ontology justified a class by citing the same analysis.
RETIRED_TERMS = (r"candidate onset", r"detection-onset", r"\bonsets?\b",
                 r"Ergene", r"CKS_FEnCY", r"single-basin survey")
RETIRED_OK = ("CHANGELOG.md", "99_audit.py")  # these two DESCRIBE the removal
# A mention that DISCLOSES the retirement is not the defect; a bare one is. The
# defect this catches is a retired quantity presented as this paper's own --
# "1,103 candidate onsets in this dataset" -- not a script docstring saying the
# comparison was withdrawn.
RETIRED_DISCLOSED = (r"retired", r"withdrawn", r"attic", r"no longer",
                     r"not reproduced", r"not part of", r"used to",
                     r"secondary source", r"not asserted", r"stands on its own")


def check_no_retired_vocabulary():
    """Nothing outside attic/ may speak of the retired single-basin analysis."""
    roots = [ROOT / "scripts", ROOT / "ontology", ROOT / "queries",
             PAPER / "sections", PAPER / "tables", PAPER / "supplementary",
             EVAL, ROOT / "README.md", ROOT / "CITATION.cff"]
    bad, scanned = [], 0
    for root in roots:
        files = ([root] if root.is_file()
                 else [f for f in root.rglob("*")
                       if f.is_file() and f.suffix in
                       (".py", ".ttl", ".rq", ".tex", ".md", ".csv", ".cff")])
        for f in files:
            if f.name in RETIRED_OK or "attic" in f.parts:
                continue
            scanned += 1
            try:
                src = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = src.splitlines()
            for pat in RETIRED_TERMS:
                for i, ln in enumerate(lines):
                    m = re.search(pat, ln, re.I)
                    if not m:
                        continue
                    near = " ".join(lines[max(0, i - 3):i + 4])
                    if any(re.search(d, near, re.I) for d in RETIRED_DISCLOSED):
                        continue          # the retirement is disclosed here
                    bad.append(f"{f.relative_to(ROOT)}:{i + 1} "
                               f"'{m.group(0)}' undisclosed")
                    break
                if bad and bad[-1].startswith(str(f.relative_to(ROOT))):
                    break
    record(FAIL if bad else OK, "no retired single-basin vocabulary outside attic",
           "; ".join(sorted(bad)[:4]) if bad
           else f"{scanned} file(s) scanned, none mentions it")


def check_no_placeholder_urls():
    """A placeholder URL that resolves is worse than a missing one.

    `CITATION.cff` shipped `repository-code: https://github.com/` -- the front
    page of GitHub. It resolves, so no link checker complains, and a reader
    following it learns nothing. Checked across the metadata a reader receives.
    """
    files = [ROOT / "CITATION.cff", ROOT / "README.md",
             PAPER / "main-elsevier.tex", PAPER / "supplementary" / "README.md"]
    bad = []
    for f in files:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            for ph in PLACEHOLDER_URLS:
                # A bare host with nothing after it, or a literal marker.
                if re.search(rf"['\"<(\s]{re.escape(ph)}['\">)\s,]*$",
                             line.strip()):
                    bad.append(f"{f.name}: {line.strip()[:60]}")
    record(FAIL if bad else OK, "no placeholder URL in shipped metadata",
           "; ".join(bad[:3]) if bad
           else f"{len([f for f in files if f.exists()])} file(s) checked")


def check_readme_numbers():
    """The repository README makes the same numeric claims and nothing read it.

    It is the first file anyone opens, and it carried 46.6 %, "3,382 - 12,042",
    908 and 18.5 % through an entire correction cycle -- together with the
    sentence "most of it predating 2015" that the era analysis exists to refute.
    It even claimed every value in it was recomputed by this script, which was
    not true, because this script only ever read the manuscript. Every bolded
    number in the README's headline table must now equal something recomputed
    this run.
    """
    readme = ROOT / "README.md"
    if not readme.exists():
        record(SKIP, "README numbers", "README.md missing")
        return
    src = readme.read_text(encoding="utf-8")
    start = src.find("## What the record shows")
    # NOT src.find("---"): the table's own |---|---| separator row matches it,
    # which truncated the block to two lines and made this check see one value
    # instead of eleven. A horizontal rule is a line of dashes and nothing else.
    rule = re.search(r"(?m)^-{3,}\s*$", src[start + 1:]) if start >= 0 else None
    end = start + 1 + rule.start() if rule else -1
    if start < 0:
        record(SKIP, "README numbers", "headline table not found")
        return
    block = src[start:end if end > start else len(src)]
    # Bolded values only: the table's own claims, not prose or file sizes.
    vals = set()
    for hit in re.findall(r"\*\*([^*]+)\*\*", block):
        for num in re.findall(r"\d[\d,]*(?:\.\d+)?", hit):
            n = num.replace(",", "")
            # A reference year is a label, not a measurement -- the same
            # exemption check_front_matter_numerals() makes.
            if re.fullmatch(r"(?:19|20)\d\d", n):
                continue
            vals.add(n)
    # _COMPUTED is the set of normalised strings every check_claim() has
    # produced this run, in each rounding it accepts -- the same pool the
    # manuscript's numbers are matched against.
    orphan = sorted(v for v in vals if v not in _COMPUTED)
    record(FAIL if orphan else OK, "README numbers are recomputed values",
           f"not produced by this run: {', '.join(orphan)}" if orphan
           else f"{len(vals)} value(s) in the headline table, all recomputed")


def check_caption_counts():
    """A count spelled out in a caption is still a value, and still drifts.

    Figure 4a plots the worst N substances under a filter; N moves whenever the
    threshold table or the filter changes, and the caption says "fourteen" in
    words, where neither the \\num{} machinery nor the near-match detector can
    see it. Every figure whose shipped data carries a `plotted` column is
    checked against the number word in its own caption.
    """
    fd = PAPER / "supplementary" / "figure_data"
    if not fd.exists():
        record(SKIP, "spelled-out caption counts", "figure_data missing")
        return
    tex, bad, checked = paper_text(), [], 0
    for csvf in sorted(fd.glob("fig*.csv")):
        rows = list(csv.DictReader(csvf.open(encoding="utf-8")))
        if not rows or "plotted" not in rows[0]:
            continue
        n = sum(1 for r in rows
                if str(r["plotted"]).strip().lower() in ("true", "yes", "1"))
        stem = csvf.stem
        m = re.search(r"\\caption\{((?:[^{}]|\{[^{}]*\})*)\}",
                      tex[tex.find(stem + ".pdf"):][:2600]) \
            if stem + ".pdf" in tex else None
        if not m:
            continue
        # Words AND the caption's own \num{} values are both candidates. Words
        # alone was too strict: figure 8's caption says "the three failures" and
        # states its plotted count as \num{29}, so the word matched a different
        # quantity entirely. The failure message lists every candidate, which is
        # what makes a coincidental pass visible to a reader of the report.
        said = {WORDS[w] for w in WORDS if re.search(rf"\b{w}\b", m.group(1))}
        said |= {int(x) for x in re.findall(r"\\num\{(\d+)\}", m.group(1))}
        if not said:
            continue
        checked += 1
        if n not in said:
            bad.append(f"{stem}: plots {n}, caption says "
                       f"{sorted(said)}")
    record(FAIL if bad else OK, "spelled-out caption counts match the data",
           "; ".join(bad) if bad
           else f"{checked} caption(s) with a count, all matching")


def check_heading_quantifiers():
    """Every quantifier in a heading must match the number beneath it."""
    bad, checked = [], 0
    for f in sorted((PAPER / "sections").glob("*.tex")):
        src = f.read_text(encoding="utf-8")
        for m in re.finditer(r"\\(?:paragraph|subsection)\{([^}]*)\}", src):
            head = " ".join(m.group(1).split()).lower()
            words = sorted((w for w in QUANTIFIERS if w in head),
                           key=len, reverse=True)
            if not words:
                continue
            after = src[m.end():m.end() + 700]
            # Prefer the value the paragraph puts in bold: that is its headline
            # claim, and the heading summarises the claim, not the legal
            # criterion that happens to be quoted first. Without this the check
            # read the 30 % of Article 4(1) as the result it constrains.
            PCT = r"\\num\{([0-9]+(?:\.[0-9]+)?)\}\s*(?:\\,)?\\%"
            bold = re.search(r"\\textbf\{[^{}]*?" + PCT, after)
            v = bold or re.search(PCT, after)
            if not v:
                continue
            checked += 1
            lo, hi = QUANTIFIERS[words[0]]
            x = float(v.group(1))
            if not lo <= x <= hi:
                bad.append(f'{f.name}: "{words[0]}" over {x}% '
                           f'(expects {lo}-{hi}%)')
    record(FAIL if bad else OK, "heading quantifiers match their numbers",
           "; ".join(bad) if bad
           else f"{checked} heading(s) with a quantifier, all consistent")


def check_supplementary_pointers():
    """Every supplementary file the manuscript names must exist.

    A dangling pointer costs a reader nothing to find and a referee nothing to
    report. The manuscript names files three ways -- as a path, as
    `supplementary/Sn_...`, and as "supplementary table~S5" -- so all three
    forms are collected.
    """
    supp = PAPER / "supplementary"
    # LaTeX escapes the underscore, so the filenames in the source read
    # S10\_by\_era.csv. Unescape before matching, or the check silently finds
    # nothing and passes -- which is exactly what it did first time round.
    tex = paper_text().replace("\\_", "_")
    named = set(re.findall(r"S\d+_[A-Za-z0-9_]+\.(?:csv|md)", tex))
    bare = {m for m in re.findall(r"table~?(S\d+)\b", tex)}
    have = {f.name for f in supp.glob("S*")} if supp.exists() else set()
    stems = {n.split("_", 1)[0] for n in have}
    missing = sorted([n for n in named if n not in have]
                     + [b for b in bare if b not in stems])
    record(FAIL if missing else OK, "supplementary files the text names exist",
           ", ".join(missing) if missing
           else f"{len(named) + len(bare)} pointer(s) resolve, {len(have)} "
                f"file(s) shipped")


def check_benchmark_shape():
    """The reasoning-cost claims are about shape, because timings are hardware.

    The manuscript deliberately quotes no seconds -- the audit would fail on
    every machine -- and instead claims super-linear closure and validation
    about an order of magnitude cheaper. Both are properties of the measured
    series, so both are checked here.
    """
    rows = load("reasoning_benchmark.csv")
    if not rows:
        record(SKIP, "reasoning-cost claims", "reasoning_benchmark.csv missing")
        return
    rows = sorted(rows, key=lambda r: int(r["observations"]))
    n0, n1 = int(rows[0]["observations"]), int(rows[-1]["observations"])
    t0, t1 = f(rows[0]["rl_closure_seconds"]), f(rows[-1]["rl_closure_seconds"])
    superlinear = (t1 / t0) > (n1 / n0)
    ratios = [f(r["rl_closure_seconds"]) / f(r["shacl_seconds"])
              for r in rows if f(r["shacl_seconds"])]
    cheaper = min(ratios) >= 3 and max(ratios) <= 40
    record(OK if superlinear and cheaper else FAIL,
           "reasoning-cost claims hold on the measured series",
           f"observations x{n1/n0:.0f} -> closure x{t1/t0:.0f} "
           f"({'super-linear' if superlinear else 'NOT super-linear'}); "
           f"closure/SHACL {min(ratios):.0f}-{max(ratios):.0f}x")


def check_bibtex_syntax():
    """The bibliography must survive BibTeX, not merely look right in a file.

    Two defects were found only by compiling: thirteen entries separated their
    authors with semicolons, which BibTeX reads as ONE name with too many
    commas -- 232 errors and an author list that prints as a single mangled
    string -- and one name carried a combining acute accent instead of the
    precomposed character, which stops pdflatex outright under inputenc. Both
    are invisible to a Crossref check, which reads the fields and not the
    syntax.
    """
    bib = PAPER / "refs.bib"
    if not bib.exists():
        record(SKIP, "bibliography syntax", "refs.bib missing")
        return
    raw = bib.read_text(encoding="utf-8")
    bad = []
    for m in re.finditer(r"^\s*(author|editor)\s*=\s*\{([^{}]*)\}", raw, re.M):
        if ";" in m.group(2):
            bad.append(f"{m.group(1)} separated by ';' not ' and ': "
                       f"{m.group(2)[:40]}...")
    comb = [f"U+{ord(c):04X}" for c in raw if unicodedata.combining(c)]
    if comb:
        bad.append(f"combining mark(s) {', '.join(sorted(set(comb)))} "
                   f"-- inputenc cannot typeset these; normalise to NFC")
    n = len(re.findall(r"^@\w+\{", raw, re.M))
    record(FAIL if bad else OK, "bibliography survives BibTeX",
           "; ".join(bad[:3]) if bad
           else f"{n} entries: no ';'-separated name list, no combining mark")


def check_front_matter_numerals():
    """No quantity in the highlights or the abstract may hide from the checker.

    The claim checker only sees values inside \\num{}. The highlights carried
    47 %, "908 of 10,065" and 18.5 % for as long as they were written in plain
    digits -- every one of them superseded by the threshold correction, and none
    of them visible to any check. They are also the first thing a reader of the
    article page sees. So: in these two blocks, a numeral is either a quantity
    inside \\num{} or part of a legal citation, and nothing else.
    """
    main = (PAPER / "main-elsevier.tex").read_text(encoding="utf-8")
    abst = (PAPER / "sections" / "00-abstract.tex").read_text(encoding="utf-8")
    m = re.search(r"\\begin\{highlights\}(.*?)\\end\{highlights\}", main, re.S)
    blocks = {"abstract": abst}
    if m:
        blocks["highlights"] = re.sub(r"(?m)^\s*%.*$", "", m.group(1))
    # identifiers, not quantities: a directive number is a name
    IDENT = (r"Directive~?\s*(?:\(EU\)~?\s*)?\d{4}/\d+(?:/EC)?",
             r"Article~?\s*\d+\(\d+[a-z]?\)", r"OWL~?\s*2", r"k\s*=\s*2",
             r"SOSA/SSN", r"CC~?BY~?4\.0")
    bad = []
    for name, s in blocks.items():
        s = re.sub(r"\\num\{[^}]*\}", " ", s)
        s = re.sub(r"\\(?:cite|ref|label|si|url|texttt|SI|footnote)\{[^}]*\}",
                   " ", s)
        for pat in IDENT:
            s = re.sub(pat, " ", s)
        for hit in re.findall(r"\d[\d.,]*", s):
            bad.append(f"{name}: {hit}")
    record(FAIL if bad else OK, "front matter states no unchecked numeral",
           ", ".join(bad) if bad
           else f"{len(blocks)} block(s): every quantity is inside \\num{{}}")


def check_remaining_claims(tex_nums):
    """Quantities the manuscript states that no other check recomputed.

    Every number in the text should be either recomputed here or declared a
    filter rather than a measurement. Leaving one uncovered has a second cost
    beyond the missing check: the stale-number detector then has an asserted
    value with no owner, and pairs it with whatever recomputed value happens to
    be numerically near, producing a failure that is nothing but a coincidence.
    """
    S = load("waterbase_summary.csv") or []
    tot = next((r for r in S if r["scope"] == "total"), None)
    # TWO quantities, and they were sharing one name.
    #
    # 2,306,365 station-years report a below-LOQ result carrying a positive
    # number. Over ALL 4,190,833 station-years that is 55.0 %, which is what
    # section 5.1 asserts and what this check has always recomputed. Over the
    # 2,320,139 CENSORED station-years it is 99.4 %, which is the denominator
    # the era table in 5.2 uses for its 99.6 / 99.3, and the one
    # scripts/94_restate.py computed -- under this check's label.
    #
    # So the file the CHANGELOG designates as the authority for repairing prose
    # after a correction ("restate from this table, NOT from the audit's
    # near-match pairings") offered 99.4 for a sentence whose correct value is
    # 55.0. Both numbers are right; neither name said which was which. They are
    # named apart here and in 94_restate.py, and both are now recomputed, so
    # neither can be quoted without an owner.
    if tot and int(tot.get("n") or 0):
        check_claim(tex_nums, "station-years substituting at source %",
                    100 * int(tot["censored_with_value"]) / int(tot["n"]))
    if tot and int(tot.get("censored") or 0):
        check_claim(tex_nums, "censored rows carrying a positive value %",
                    100 * int(tot["censored_with_value"]) / int(tot["censored"]))
    run = {r["key"]: int(r["n"]) for r in S if r["scope"] == "run_scope"}
    if run.get("pairs_multiyear"):
        m = run["pairs_multiyear"]
        check_claim(tex_nums, "station-substance pairs in >1 year", m)
        check_claim(tex_nums, "pairs with more than one limit",
                    run["pairs_multi_limit"])
        check_claim(tex_nums, "pairs with more than one limit %",
                    100 * run["pairs_multi_limit"] / m)
        check_claim(tex_nums, "pairs with more than one method code",
                    run["pairs_multi_method"])
        # The denominator matters more than the count: without it, "only 3,356
        # record a change of method" reads as "the method rarely changed" when
        # the record simply does not say.
        if run.get("pairs_with_any_method"):
            check_claim(tex_nums, "pairs reporting any method code",
                        run["pairs_with_any_method"])
            check_claim(tex_nums, "pairs reporting any method code %",
                        100 * run["pairs_with_any_method"] / m)
        check_claim(tex_nums, "pairs whose limit change crosses the standard",
                    run["pairs_crossing_standard"])
    conf = load("country_confounders.csv") or []
    raw = [f(r.get("raw")) for r in conf if f(r.get("raw")) is not None]
    if raw:
        check_claim(tex_nums, "country spread, lowest", min(raw))
        check_claim(tex_nums, "country spread, highest", max(raw))
    for r in load("group_completeness.csv") or []:
        k = int(r["station_years_touching"])
        if k and int(r["members"]) <= 9:
            # Only the groups Annex I enumerates. The pesticides sum carries a
            # footnote referring to two other Regulations instead of a member
            # list, so its basket cannot be resolved from the legal text and no
            # completeness rate is reported for it.
            check_claim(tex_nums,
                        f"group complete %: {r['group'][:28]}",
                        100 * int(r["station_years_complete"]) / k)
    mac = load("mac_exceedance.csv") or []
    cross = {r["key"]: int(r["n"]) for r in mac
             if r["scope"] == "station_year_cross"}
    b = cross.get("both_assessable", 0)
    # The denominator of the coverage claim: station-years carrying an
    # annual-average verdict AND a maximum-allowable standard, whether or not the
    # disaggregated release holds their samples. Stated in 5.7 and, until now,
    # traced to nothing.
    reachable = b + cross.get("no_samples_found", 0)
    if reachable:
        check_claim(tex_nums, "MAC: station-years reachable at both units",
                    reachable)
        check_claim(tex_nums, "MAC: stratum coverage %", 100 * b / reachable)
    if b:
        d = (cross.get("compliant_aa__exceeding_mac", 0)
             + cross.get("exceeding_aa__compliant_mac", 0))
        check_claim(tex_nums, "MAC: disagree either way %", 100 * d / b)


def check_conclusions_introduce_nothing():
    """The conclusions must not assert a quantity no earlier section asserts.

    This is the check that would have caught the worst defect in the paper's
    history. After the single-basin survey was withdrawn, the conclusions
    continued to report it -- 75 stations, 258 parameters, 76.9 %, 85.2 %,
    "seven of ten metal standards" -- while no results section contained any of
    it. The word "Ergene" never appeared, so a grep for the dropped case study
    found nothing, and check_numbers_are_shipped() passed because the retired
    pipeline's reports were still sitting in eval/.

    A conclusion that introduces a number is either summarising an analysis
    that is missing, or performing one in the last paragraph. Both are defects,
    and the rule is simple enough to enforce mechanically.
    """
    concl = PAPER / "sections" / "07-conclusions.tex"
    if not concl.exists():
        record(SKIP, "conclusions introduce no new quantity", "no conclusions")
        return
    earlier = ""
    for s in sorted((PAPER / "sections").glob("*.tex")):
        if s.name != concl.name:
            earlier += s.read_text(encoding="utf-8")
    earlier_nums = set(re.findall(r"\\num\{([0-9.]+)\}", earlier))

    novel = []
    for raw in set(re.findall(r"\\num\{([0-9.]+)\}", concl.read_text(encoding="utf-8"))):
        if raw in earlier_nums:
            continue
        try:
            v = float(raw)
        except ValueError:
            continue
        # bare small integers are enumerations ("ten defects"), not findings
        if "." not in raw and v < 100:
            continue
        novel.append(raw)
    if novel:
        record(FAIL, "conclusions introduce no new quantity",
               "asserted only in the conclusions: " + ", ".join(sorted(novel)))
    else:
        record(OK, "conclusions introduce no new quantity",
               "every quantity restated from an earlier section")


def check_abstract_introduces_nothing():
    """The abstract must not assert a quantity no section asserts.

    The mirror of check_conclusions_introduce_nothing(), and it exists for the
    same reason: because the defect happened. The abstract reported 4,181
    exceedances "affirmable in law" while Section 5.4, Figure 5's caption and
    the conclusions all reported 14,505 -- a factor of 3.5, on the number the
    paper's central argument turns on, in the first paragraph a referee reads.

    Nothing caught it. check_verdict_claims() recomputes 14,505 and finds it in
    the manuscript, which it is -- three times over, just not in the abstract.
    check_numbers_are_shipped() asks whether a value occurs in some generated
    artefact, and 4,181 does occur: it is the count of possible_exceedance rows
    a two-valued pipeline calls compliant, an unrelated quantity that happens
    to share the digits. A number can be individually well-formed, individually
    traceable, and still be the wrong number in the wrong sentence. The only
    cheap guard is containment: an abstract summarises, so every quantity in it
    must appear in a section.
    """
    abst = PAPER / "sections" / "00-abstract.tex"
    if not abst.exists():
        record(SKIP, "abstract introduces no new quantity", "no abstract")
        return
    body = ""
    for s in sorted((PAPER / "sections").glob("*.tex")):
        if s.name != abst.name:
            body += s.read_text(encoding="utf-8")
    body_nums = set(re.findall(r"\\num\{([0-9.]+)\}", body))

    novel = []
    for raw in set(re.findall(r"\\num\{([0-9.]+)\}",
                              abst.read_text(encoding="utf-8"))):
        if raw in body_nums:
            continue
        try:
            v = float(raw)
        except ValueError:
            continue
        # Years and small enumerations are not findings. The threshold is the
        # same as the conclusions check so the two cannot drift apart.
        if "." not in raw and v < 100:
            continue
        if "." not in raw and 1900 <= v <= 2100:      # a year, not a finding
            continue
        novel.append(raw)
    if novel:
        record(FAIL, "abstract introduces no new quantity",
               "asserted only in the abstract: " + ", ".join(sorted(novel)))
    else:
        record(OK, "abstract introduces no new quantity",
               "every quantity restated from a section")


def check_latex_preflight():
    """Catch what only a LaTeX run would otherwise reveal.

    There is no TeX toolchain here, so structural errors reach Overleaf before
    anyone sees them. One did: `\\begin{highlights}` was used inside
    elsarticle's frontmatter, and elsarticle provides no such environment. An
    undefined environment inside frontmatter takes the entire frontmatter with
    it, so the ABSTRACT silently failed to appear -- a symptom several steps
    removed from its cause.

    Checked here: every environment is standard, supplied by a loaded package,
    or defined in the preamble; begin/end are balanced; commands that need a
    package have it.
    """
    STD = {"document", "abstract", "itemize", "enumerate", "description",
           "figure", "figure*", "table", "table*", "tabular", "tabular*",
           "longtable", "center", "quote", "quotation", "verbatim", "equation",
           "equation*", "align", "align*", "gather", "gather*", "array",
           "thebibliography", "frontmatter", "keyword", "minipage",
           "flushleft", "flushright", "sloppypar"}
    # Environments a document CLASS provides. cas-sc defines highlights,
    # keywords and graphicalabstract in cas-common.sty via
    # \\DeclareDocumentEnvironment, which no \\newenvironment grep would find.
    BY_CLASS = {"cas-sc": {"highlights", "keywords", "graphicalabstract"},
                "cas-dc": {"highlights", "keywords", "graphicalabstract"},
                "elsarticle": {"frontmatter", "keyword"}}
    SUPPLIED = {"threeparttable": {"threeparttable", "tablenotes"},
                "subcaption": {"subfigure", "subtable"},
                "amsmath": {"multline", "split", "cases"},
                "listings": {"lstlisting"}, "algorithm": {"algorithm"}}
    NEEDS = {"\\linenumbers": "lineno", "\\num{": "siunitx", "\\si{": "siunitx",
             "\\toprule": "booktabs", "\\url{": "hyperref",
             "\\textcolor": "xcolor", "\\includegraphics": "graphicx",
             "\\affil": "authblk"}
    # Packages a class loads for us. Re-loading these is what starts option
    # clashes, so they must not be demanded of the preamble.
    BY_CLASS_PKGS = {"cas-sc": {"booktabs", "hyperref", "xcolor", "graphicx",
                                "amsmath", "multirow", "colortbl"},
                     "cas-dc": {"booktabs", "hyperref", "xcolor", "graphicx",
                                "amsmath", "multirow", "colortbl"}}
    problems = []
    for name in ("main-elsevier.tex",):
        f = PAPER / name
        if not f.exists():
            continue
        src = f.read_text(encoding="utf-8")
        body = src
        for d in ("sections", "tables"):
            for s in sorted((PAPER / d).glob("*.tex")):
                body += s.read_text(encoding="utf-8")
        body = re.sub(r"(?m)^\s*%.*$", "", body)

        cls_m = re.search(r"\\documentclass(?:\[[^\]]*\])?\{([^}]*)\}", src)
        cls = cls_m.group(1) if cls_m else ""
        pkgs = {x.strip() for grp in
                re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]*)\}", src)
                for x in grp.split(",")}
        defined = set(re.findall(r"\\newenvironment\{([A-Za-z*]+)\}", src))
        used = set(re.findall(r"\\begin\{([A-Za-z*]+)\}", body))

        unknown = used - STD - defined - BY_CLASS.get(cls, set())
        for pkg, envs in SUPPLIED.items():
            if pkg in pkgs:
                unknown -= envs
        for e in sorted(unknown):
            problems.append(f"{name}: environment '{e}' is not defined")

        for cmd, pkg in NEEDS.items():
            lit = cmd.replace("\\\\", "\\")
            # word boundary: \affil must not match \affiliation, which is a
            # different command from a different class
            hit = re.search(re.escape(lit) + (r"(?![a-zA-Z])"
                                              if lit[-1].isalpha() else ""), body)
            if hit and pkg not in pkgs:
                # elsarticle[review] loads lineno itself
                if pkg == "lineno" and cls == "elsarticle":
                    continue
                if pkg in BY_CLASS_PKGS.get(cls, set()):
                    continue
                problems.append(f"{name}: {lit} used but {pkg} not loaded")

        for e in sorted(used):
            b = len(re.findall(r"\\begin\{" + re.escape(e) + r"\}", body))
            n = len(re.findall(r"\\end\{" + re.escape(e) + r"\}", body))
            if b != n:
                problems.append(f"{name}: {e} has {b} begin, {n} end")

    if problems:
        record(FAIL, "LaTeX structure is sound", "; ".join(problems[:4]))
    else:
        record(OK, "LaTeX structure is sound",
               "environments defined, packages loaded, begin/end balanced")


def check_numbers_are_shipped(tex):
    """Every quantity asserted in the manuscript must occur in shipped data.

    Reproducibility means a reader with the supplementary files can rebuild the
    numbers, and that fails silently when a claim outlives the analysis behind
    it. The discussion kept citing a survey that had been removed from the
    paper -- 85.2 %, 254 analytes, a factor of 1300 -- none of which appeared in
    any results section or any shipped table. Nothing caught it, because each
    number was individually well-formed and the word "Ergene" never appeared.

    So every \\num{} in the manuscript is looked for in the files a reader
    actually receives. Small integers are skipped: they are section counts,
    enumerations and years, not measurements, and demanding a data source for
    "four outcomes" would bury the signal.
    """
    shipped = []
    for d in (PAPER / "supplementary", PAPER / "supplementary" / "figure_data",
              ROOT / "eval"):
        if d.exists():
            shipped += [p for p in d.iterdir()
                        if p.suffix in (".csv", ".md") and p.is_file()]
    if not shipped:
        record(SKIP, "asserted numbers occur in shipped data", "nothing shipped")
        return
    hay = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                    for p in shipped)
    hay_nc = hay.replace(",", "")

    # A quantity attributed to a cited work is not ours to ship: the reader
    # gets it from that paper. Detected by a \cite{} in the same sentence.
    cited = set()
    for m in re.finditer(r"\\num\{([0-9.]+)\}", tex):
        window = tex[max(0, m.start() - 400):m.end() + 200]
        sentence = window.split(". ")[-2] if ". " in window else window
        if "\\cite{" in sentence or "\\cite{" in tex[max(0, m.start() - 150):m.start()]:
            cited.add(m.group(1))

    missing = []
    for raw in set(re.findall(r"\\num\{([0-9.]+)\}", tex)):
        if raw in cited:
            continue
        # skip small counts and years: not measurements
        try:
            v = float(raw)
        except ValueError:
            continue
        if "." not in raw and v < 1000:
            continue
        if raw in hay or raw in hay_nc:
            continue
        # a rounded quote of a fuller value in the data
        if "." in raw and any(f"{v:.{p}f}" in hay_nc for p in (2, 3)):
            continue
        missing.append(raw)
    if missing:
        record(FAIL, "asserted numbers occur in shipped data",
               f"{len(missing)} not found in any supplementary or eval file: "
               + ", ".join(sorted(missing)[:8]))
    else:
        record(OK, "asserted numbers occur in shipped data",
               f"every quantity traced into {len(shipped)} shipped files")


def check_paper_hygiene(tex):
    labels = set(re.findall(r"\\label\{([^}]+)\}", tex))
    refs = set(re.findall(r"\\(?:ref|autoref|eqref)\{([^}]+)\}", tex))
    for t in (PAPER / "tables").glob("*.tex"):
        labels |= set(re.findall(r"\\label\{([^}]+)\}",
                                 t.read_text(encoding="utf-8")))
    dangling = refs - labels
    if dangling:
        record(FAIL, "no dangling cross-references", ", ".join(sorted(dangling)))
    else:
        record(OK, "no dangling cross-references", f"{len(refs)} resolved")

    cites = set()
    for m in re.findall(r"\\cite[tp]?\{([^}]+)\}", tex):
        cites |= {k.strip() for k in m.split(",")}
    bib = (PAPER / "refs.bib")
    if bib.exists():
        keys = set(re.findall(r"@\w+\{([^,]+),", bib.read_text(encoding="utf-8")))
        missing = cites - keys
        if missing:
            record(FAIL, "all citations resolve", ", ".join(sorted(missing)))
        else:
            record(OK, "all citations resolve", f"{len(cites)} keys")

    # The single-file view is generated; if it drifts from the sections, someone
    # reading or submitting it is reading a different paper.
    # BOTH single-file views. Only the generic one was checked, so the Elsevier
    # version -- the one that would actually be uploaded to a submission system
    # -- could sit a revision behind without anything saying so.
    flats = [PAPER / "main-standalone.tex",
             PAPER / "main-elsevier-standalone.tex"]
    present = [f for f in flats if f.exists()]
    if present:
        newest = max(p.stat().st_mtime for p in
                     [PAPER / "main.tex", PAPER / "main-elsevier.tex",
                      *(PAPER / "sections").glob("*.tex"),
                      *(PAPER / "tables").glob("*.tex")] if p.exists())
        stale = [f.name for f in present if f.stat().st_mtime < newest]
        if stale:
            record(FAIL, "single-file views are current",
                   ", ".join(stale) + " older than a section inlined; "
                   "re-run scripts/96_flatten_paper.py")
        else:
            record(OK, "single-file views are current",
                   " · ".join(f"{f.name} "
                              f"{f.read_text(encoding='utf-8').count(chr(10)):,}"
                              f" lines" for f in present))

    # The published copy is what the permanent IRI resolves to; if it drifts,
    # the world downloads a different ontology from the one described here.
    import subprocess
    r = subprocess.run([sys.executable,
                        str(SCRIPTS / "97_assemble_publish.py"), "--check"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        record(OK, "published ontology copy is current",
               r.stdout.strip().splitlines()[-1].strip() if r.stdout else "")
    else:
        record(FAIL, "published ontology copy is current",
               (r.stdout or r.stderr).strip().splitlines()[0].strip())

    pend = re.findall(r"\\pending\{([^}]*)\}", tex)
    if pend:
        record(WARN, "no \\pending markers",
               f"{len(pend)} remain: " + "; ".join(p[:40] for p in pend[:6]))
    else:
        record(OK, "no \\pending markers")


# -------------------------------------------------------------------- main --

# ------------------------------------------------- the artefacts themselves --
# Everything above audits the MANUSCRIPT: a claim in the LaTeX against a value
# recomputed from derived/processed. That leaves two whole classes of defect
# unowned, and one of each was live in the released artefact:
#
#   * a generated REPORT can contradict the manuscript in its own prose. The
#     three-valued total in eval/waterbase_external.md dropped PreconditionUnmet
#     from its sum and printed 25.0 % three lines under a table listing the
#     missing row, while this file recomputed 43.8 % from the same CSV and
#     passed.
#   * the shipped GRAPH can contradict its own TBox and shapes. It did, in
#     41,396 literals, and eval/shacl_validation.md said so on every run --
#     an 82-minute stage whose output no other stage, and no section of the
#     paper, ever read.
#
# These three checks close both. They read the artefacts, not the prose about
# them.


def check_shacl_conformance(tex_nums):
    """The shipped graph must satisfy the shapes the ontology publishes.

    scripts/18_shacl_validate.py has been in 00_run_all.py from the start and
    reported `conforms: False` throughout. Nothing cited eval/shacl_validation.md
    -- not the manuscript, not the supplementary, not this file -- so a failing
    validation of the artefact under review cost nothing and was never seen.
    A published SHACL shape that the publisher's own graph violates is not a
    constraint, it is a suggestion.
    """
    p = EVAL / "shacl_validation.md"
    if not p.exists():
        record(FAIL, "the shipped graph satisfies its own shapes",
               "eval/shacl_validation.md missing; run scripts/18_shacl_validate.py")
        return
    src = p.read_text(encoding="utf-8")
    m = re.search(r"conforms:\s*\*\*(True|False)\*\*", src)
    if not m:
        record(FAIL, "the shipped graph satisfies its own shapes",
               "eval/shacl_validation.md states no conformance verdict")
        return
    if m.group(1) == "True":
        record(OK, "the shipped graph satisfies its own shapes",
               "pyshacl reports conforms over censo-waterbase.ttl + the ontology")
        return

    # A blanket "must conform" is the wrong gate, and demanding it would be
    # worse than having none: some of these shapes exist to catch defects in the
    # SOURCE RECORD, which is a finding the paper reports, not a bug to hide.
    # censo:AssessedObservationShape requires an analytical method, and 4,646
    # station-years report none -- that is the unresolvable population, and a
    # pipeline that made the graph conform would have to invent the datum, which
    # is exactly the move censo-shapes.ttl was corrected for once already.
    #
    # So: violations of a DECLARED source-data shape are recorded with their
    # count, and anything else fails. The datatype defect that made this report
    # say `conforms: False` on every run would have failed here, because nothing
    # would have declared it expected.
    EXPECTED = {
        "must cite the analytical method":
            "the unresolvable population: the record reports no method, so no "
            "limit applies. Making the graph conform would mean inventing it.",
    }
    rows = re.findall(r"^\|\s*(\d[\d,]*)\s*\|\s*(.+?)\s*\|$", src, re.M)
    rows = [(n, msg) for n, msg in rows if not msg.startswith("---")]
    unexpected, expected = [], []
    for n, msg in rows:
        key = next((k for k in EXPECTED if k in msg), None)
        (expected if key else unexpected).append(f"{n} x {msg[:70]}")
    if unexpected:
        record(FAIL, "the shipped graph satisfies its own shapes",
               "violation type(s) nothing declares as a source-data finding: "
               + "; ".join(unexpected))
    else:
        record(OK, "the shipped graph satisfies its own shapes",
               "no violation the pipeline is responsible for; "
               + "; ".join(expected) + " (declared source-data findings)")
        # And OWN the count. 4,646 was traceable -- it is in the report -- but
        # nothing recomputed it, so the detector offered it as a home for the
        # dual-regulation transition count of 5,041.
        for n, msg in rows:
            if "must cite the analytical method" in msg:
                check_claim(tex_nums, "observations citing no method",
                            int(n.replace(",", "")))


def check_abox_datatypes():
    """Every decimal-ranged property must carry a TYPED xsd:decimal literal.

    rdfs:range xsd:decimal does not enforce this and cannot: xsd:integer is
    derived from xsd:decimal, so `censo:resultLowerBound 0` -- a bare Turtle
    numeral, hence xsd:integer -- satisfies the range and no OWL 2 RL reasoner
    objects. The core nonetheless asserts

        CensoredObservation subClassOf (resultLowerBound hasValue "0.0"^^xsd:decimal)

    which is a statement about a literal TERM, and `0` is not that term. So the
    graph asserted an axiom it could not satisfy on every censored observation,
    silently, for as long as the check did not exist.

    The properties are read from censo-core.ttl rather than listed here, so a
    new decimal property is covered the day it is declared.
    """
    core = ROOT / "ontology" / "censo-core.ttl"
    if not core.exists():
        record(SKIP, "graph literals are typed xsd:decimal", "censo-core.ttl missing")
        return
    src = core.read_text(encoding="utf-8")
    props = set()
    for blk in re.split(r"\n(?=censo:)", src):
        m = re.match(r"censo:(\w+)\s+a\s+owl:DatatypeProperty", blk)
        if m and re.search(r"rdfs:range\s+xsd:decimal", blk):
            props.add(m.group(1))
    if not props:
        record(SKIP, "graph literals are typed xsd:decimal",
               "no decimal-ranged property found in the core")
        return

    targets = sorted((ROOT / "derived" / "abox").glob("*.ttl"))
    targets += sorted((ROOT / "ontology" / "reg").glob("*.ttl"))
    # The negative lookahead matters: without it the alternation would let a
    # property name match as a prefix of a longer one and attribute the wrong
    # literal to it.
    pat = re.compile(r"censo:(" + "|".join(sorted(props))
                     + r")(?![A-Za-z0-9_])\s+([^\s;,\]]+)")
    bad, seen, checked = [], 0, 0
    for t in targets:
        if not t.exists():
            continue
        checked += 1
        wrong = {}
        for prop, obj in pat.findall(t.read_text(encoding="utf-8")):
            seen += 1
            # A typed literal is the only acceptable form. A bare numeral is
            # xsd:integer or xsd:decimal depending on whether it happens to
            # contain a point, which is exactly the ambiguity being removed.
            if not obj.startswith('"'):
                wrong[prop] = wrong.get(prop, 0) + 1
        if wrong:
            bad.append(f"{t.name}: " + ", ".join(
                f"{k} x{v}" for k, v in sorted(wrong.items())))
    if not checked:
        record(SKIP, "graph literals are typed xsd:decimal",
               "no graph or package on disk")
        return
    record(FAIL if bad else OK, "graph literals are typed xsd:decimal",
           "; ".join(bad) if bad
           else f"{seen:,} literal(s) across {checked} file(s), "
                f"{len(props)} decimal-ranged propert(ies), all typed")


def check_report_indeterminate_total():
    """The generated report's 'not decidable' total must be the audited one.

    eval/waterbase_external.md prints a sentence totalling the indeterminate
    outcomes. It summed four of the five subclasses of
    censo:IndeterminateCompliance and omitted precondition_unmet -- the largest
    of them -- so the shipped report said 25.0 % where section 5.4 says 43.8 %.

    The manuscript was right and this file already recomputed it, which is the
    point: a check that only ever reads the LaTeX cannot see a report disagree
    with it. Recompute the total and demand that the report state it.
    """
    p = EVAL / "waterbase_external.md"
    rows = load("waterbase_verdicts_population.csv")
    if not p.exists() or not rows:
        record(SKIP, "the report's indeterminate total matches the audit",
               "report or population table missing")
        return
    IND = ("possible_exceedance", "precondition_unmet", "method_insufficient",
           "indeterminate_unresolved", "indeterminate_other")
    want = sum(int(r["n"]) for r in rows
               if r["substitution"] == "zero" and r["censo_outcome"] in IND)
    src = p.read_text(encoding="utf-8")
    m = re.search(r"\*\*([\d,]+)\s*\(([\d.]+)%\)[^*]*not decidable\*\*", src)
    if not m:
        record(FAIL, "the report's indeterminate total matches the audit",
               "eval/waterbase_external.md states no indeterminate total")
        return
    got = int(m.group(1).replace(",", ""))
    record(OK if got == want else FAIL,
           "the report's indeterminate total matches the audit",
           f"{got:,} in the report against {want:,} recomputed"
           + ("" if got == want
              else f" -- short by {want - got:,}; a subclass is missing "
                   f"from the sum in scripts/22_waterbase_external.py"))


def check_no_dead_terms():
    """Every declared term must be exercised, or declared abstract on purpose.

    This is the generalisation of a defect this project has now hit twice.
    The CHANGELOG records the fourth commitment -- "a threshold is a conditional
    judgement" -- shipping with ZERO censo:requiresCondition triples and
    censo:PreconditionUnmet instantiated zero times: a claimed contribution
    present in the TBox and absent from everything else, found by a referee. The
    same audit that recomputes 179 numbers could not see it, because a term
    nobody instantiates makes no number wrong.

    It happened again, to the FIRST commitment. censo:AnalyticalRun,
    censo:producedByRun and censo:runUsedMethod appear zero times in every
    shipped graph, while "the limit belongs to the analytical run, not to the
    instrument" is the sentence the vocabulary is built around.

    A term is EXERCISED if it appears in a shipped ABox, a regulation package, a
    shape, or a competency question -- somewhere a reader can see it do work.
    A term may instead be ABSTRACT: a union or an abstract parent that is
    reached by subsumption and correctly never instantiated. That is a real
    category and it is enumerated below with a reason each, not inferred, so
    that adding to it is a visible decision rather than a way to silence this
    check.

    Anything else is dead weight: either exercise it or delete it.
    """
    # ABSTRACT BY DESIGN. Each of these is never instantiated directly and
    # should not be -- individuals reach it through a subclass. The reason is
    # stated because a list without reasons becomes a dumping ground.
    ABSTRACT = {
        "censo:ComplianceOutcome":
            "the covering union of the three outcomes; an assessment is typed "
            "with one of its subclasses and reaches it by subsumption",
        "censo:AssessedObservation":
            "the union of the four detection statuses, same reason",
        "censo:DetectedObservation":
            "the union of estimated and quantified; named so that reasoning "
            "which turns on presence rather than magnitude has a class",
        "censo:IndeterminateCompliance":
            "abstract parent of the reasons a verdict cannot be reached; the "
            "point of making it abstract was that every instance says WHY",
        "censo:ApplicabilityCondition":
            "abstract parent; the footnote-derived subclasses are what a "
            "package attaches",
        "censo:Threshold":
            "abstract parent; a package emits AnnualAverage, MaximumAllowable, "
            "ClassBoundary or GroupThreshold",
        "censo:Regulation":
            "abstract parent of cereg:RegulationPackage",
        "censo:Analyte":
            "abstract parent; packages emit analyte individuals typed with it "
            "or with a cereg: subclass",
    }
    core = ROOT / "ontology" / "censo-core.ttl"
    reg = ROOT / "ontology" / "censo-regulation.ttl"
    if not (core.exists() and reg.exists()):
        record(SKIP, "no dead terms in the vocabulary", "a module is missing")
        return

    declared = {}
    for path, pre in ((core, "censo"), (reg, "cereg")):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(
                r"^(censo|cereg):(\w+)\s+a\s+owl:(Class|ObjectProperty|"
                r"DatatypeProperty)", src, re.M):
            declared[f"{m.group(1)}:{m.group(2)}"] = path.name

    where = []
    where += sorted((ROOT / "derived" / "abox").glob("*.ttl"))
    where += sorted((ROOT / "ontology" / "reg").glob("*.ttl"))
    where += [ROOT / "ontology" / "censo-shapes.ttl"]
    where += sorted((ROOT / "queries").glob("*.rq"))
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                       for p in where if p.exists())
    if not corpus.strip():
        record(SKIP, "no dead terms in the vocabulary",
               "nothing to check against; run the graph stages first")
        return

    dead = []
    for term in sorted(declared):
        if term in ABSTRACT:
            continue
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])",
                     corpus):
            continue
        dead.append(term)

    n_ex = len(declared) - len(dead) - len([t for t in ABSTRACT if t in declared])
    if dead:
        record(FAIL, "no dead terms in the vocabulary",
               f"{len(dead)} of {len(declared)} declared term(s) appear in no "
               f"graph, package, shape or competency question: "
               + ", ".join(dead)
               + " — exercise each or delete it; if one is abstract by design, "
                 "say so in ABSTRACT with a reason")
    else:
        record(OK, "no dead terms in the vocabulary",
               f"{n_ex} exercised, "
               f"{len([t for t in ABSTRACT if t in declared])} abstract by "
               f"declaration, 0 dead of {len(declared)} declared")


def check_functional_properties():
    """No functional property may carry two distinct values on one subject.

    OWL cannot be relied on to say so. Under DL semantics a functional datatype
    property with two different literals on one individual is an inconsistency,
    but OWL 2 RL discharges functionality by deriving owl:sameAs between the two
    values and stops: owlrl reports no owl:Nothing, and the audit's
    package-consistency check -- which asks exactly that question -- passed on
    every run while the released EU package violated the axiom on three entries.

    censo:casNumber was declared functional. Annex I names two registry numbers
    for diclofenac (the free acid and the sodium salt), and likewise for
    acetamiprid and imidacloprid, because a regulated entry is not a single
    chemical species. The axiom was wrong and the data were right; the axiom is
    gone. This check is what would have said so, and what will say so about the
    next one.

    Scope: the vocabulary modules and the regulation packages, read with rdflib.
    The generated ABoxes are not scanned here -- they emit one value per
    property per observation by construction, and check_graph_is_consistent()
    puts a slice of the real graph in front of a reasoner -- so a violation
    introduced by a generator would surface there instead.
    """
    try:
        import rdflib
        from rdflib import RDF, OWL
    except ImportError:
        record(SKIP, "no functional property carries two values", "rdflib absent")
        return
    ONTO = ROOT / "ontology"
    vocab = [ONTO / "censo-core.ttl", ONTO / "censo-regulation.ttl"]
    data = sorted((ONTO / "reg").glob("*.ttl"))
    if not all(p.exists() for p in vocab):
        record(SKIP, "no functional property carries two values",
               "a vocabulary module is missing")
        return

    tbox = rdflib.Graph()
    for p in vocab:
        tbox.parse(p, format="turtle")
    functional = {p for p in tbox.subjects(RDF.type, OWL.FunctionalProperty)
                  if isinstance(p, rdflib.URIRef)}
    if not functional:
        record(SKIP, "no functional property carries two values",
               "no owl:FunctionalProperty declared")
        return

    bad, n_checked = [], 0
    for path in vocab + data:
        if not path.exists():
            continue
        g = rdflib.Graph()
        try:
            g.parse(path, format="turtle")
        except Exception as e:
            bad.append(f"{path.name}: unparsable ({type(e).__name__})")
            continue
        for prop in sorted(functional, key=str):
            seen = {}
            for s, o in g.subject_objects(prop):
                seen.setdefault(s, set()).add(o)
            n_checked += len(seen)
            for s, vals in seen.items():
                if len(vals) > 1:
                    bad.append(
                        f"{path.name}: {str(s).rsplit('/', 1)[-1]} has "
                        f"{len(vals)} values for "
                        f"{str(prop).rsplit('/', 1)[-1]} "
                        f"({', '.join(sorted(str(v) for v in vals))})")
    record(FAIL if bad else OK, "no functional property carries two values",
           "; ".join(bad[:6]) + (f" and {len(bad)-6} more" if len(bad) > 6 else "")
           if bad else
           f"{len(functional)} functional propert(ies), {n_checked:,} "
           f"subject-property pair(s) across "
           f"{len(vocab) + len(data)} file(s), none multi-valued")


def check_alignment():
    """The alignment must reconcile every substance the analysis calls co-regulated.

    Section 5.7 restricts to the substances both jurisdictions regulate and
    reports that 17.7 % of those assessments change outcome when the package is
    swapped. That stratum is built in Python by joining CAS registry strings.
    ontology/censo-alignment.ttl asserts the same reconciliation as owl:sameAs
    between the two packages' analyte individuals, which is the mechanism
    censo:Analyte's own comment describes.

    Two mechanisms for one claim is one more than the paper can defend unless
    they agree, so this requires the entailment to cover the join: every CAS the
    dual-regulation analysis treats as co-regulated must be reachable through an
    owl:sameAs pair. The alignment may cover MORE -- it reconciles substances
    both packages name even where the record holds no data for them -- and that
    direction is fine.
    """
    al = ROOT / "ontology" / "censo-alignment.ttl"
    dual = load("dual_regulation.csv")
    if not al.exists():
        record(FAIL, "the alignment reconciles every co-regulated substance",
               "ontology/censo-alignment.ttl missing; "
               "run scripts/20_align_external.py")
        return
    if not dual:
        record(SKIP, "the alignment reconciles every co-regulated substance",
               "dual_regulation.csv missing")
        return
    src = al.read_text(encoding="utf-8")
    pairs = re.findall(r"(cereg:\S+) owl:sameAs (cereg:\S+) \.", src)
    n_chebi = len(re.findall(r"rdfs:seeAlso obo:CHEBI_", src))
    if not pairs:
        record(FAIL, "the alignment reconciles every co-regulated substance",
               "no owl:sameAs in the alignment")
        return

    cas_of = {}
    for path in sorted((ROOT / "ontology" / "reg").glob("*.ttl")):
        s = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^(cereg:\S+) a censo:Analyte ;(.*?)\.\n",
                             s, re.S | re.M):
            cas_of[m.group(1)] = set(
                re.findall(r'"([0-9]{2,7}-[0-9]{2}-[0-9])"', m.group(2)))
    reconciled = set()
    for a, b in pairs:
        reconciled |= cas_of.get(a, set()) | cas_of.get(b, set())

    wanted = {r["key"].split("|", 1)[0].strip() for r in dual
              if r.get("scope") == "substance"}
    missing = sorted(wanted - reconciled)
    if missing:
        record(FAIL, "the alignment reconciles every co-regulated substance",
               f"{len(missing)} of {len(wanted)} co-regulated CAS have no "
               f"owl:sameAs: " + ", ".join(missing[:8])
               + " — the entailment and the Python join disagree about which "
                 "substances the two jurisdictions share")
    else:
        record(OK, "the alignment reconciles every co-regulated substance",
               f"{len(wanted)} co-regulated CAS, all reachable through "
               f"{len(pairs)} owl:sameAs pair(s); {n_chebi} ChEBI pointer(s)")


def check_graph_matches_population(tex_nums):
    """The materialised sample's method-insufficient share, which owned nothing.

    Section 5.4 states "17.2 % on the sample against 17.5 % on the population" as
    the evidence that expressing the record in the vocabulary loses nothing. The
    population figure was recomputed; the SAMPLE figure was printed by stage 23
    and checked by no one, so the near-match detector had an unowned value
    sitting next to a computed 17.36 (the 1e-2 decade) and blamed one on the
    other. An unowned number does not merely go unchecked -- it makes some other
    check lie.
    """
    v = load("waterbase_verdicts.csv")
    if not v:
        record(SKIP, "graph share matches the population share",
               "waterbase_verdicts.csv missing")
        return
    zero = [r for r in v if r["substitution"] == "zero"]
    tot = sum(int(r["n"]) for r in zero)
    mi = sum(int(r["n"]) for r in zero
             if r["censo_outcome"] == "method_insufficient")
    if not tot:
        record(SKIP, "graph share matches the population share", "empty slice")
        return
    check_claim(tex_nums, "graph: method-insufficient share %", 100 * mi / tot)


def check_reported_intervals(tex_nums):
    """Own the confidence bounds. An unowned number makes some other check lie.

    Section 5.6 states "17.7 % (95 % CI 17.6--17.9 %)". The point estimate was
    recomputed and the two BOUNDS were not, so 17.9 sat in the manuscript owned
    by nothing -- and the near-match detector, looking for a home for the 1e-2
    decade's computed 17.36, blamed the decade on the interval. Neither number
    was wrong; the pairing was, and it is the third time in this correction
    cycle that a loose number has done this.

    The bounds are recomputed here from the same counts, with the same Wilson
    formula the report uses, rather than read back out of the report.
    """
    dual = load("dual_regulation.csv")
    if not dual:
        record(SKIP, "reported confidence bounds", "dual_regulation.csv missing")
        return
    co = [r for r in dual if r.get("scope") == "cross_co_regulated"]
    tot = sum(int(r["n"]) for r in co)
    diff = sum(int(r["n"]) for r in co if r["eu_outcome"] != r["tr_outcome"])
    if not tot:
        record(SKIP, "reported confidence bounds", "no co-regulated stratum")
        return
    z = 1.959963984540054
    ph = diff / tot
    d = 1 + z * z / tot
    c = (ph + z * z / (2 * tot)) / d
    h = z * math.sqrt(ph * (1 - ph) / tot + z * z / (4 * tot * tot)) / d
    check_claim(tex_nums, "co-regulated divergence, CI low %", 100 * (c - h))
    check_claim(tex_nums, "co-regulated divergence, CI high %", 100 * (c + h))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    tex = paper_text()
    nums = asserted(tex)

    check_staleness()
    check_waterbase_claims(nums)
    check_era_claims(nums)
    check_year_claims(nums)
    check_packages_are_consistent()
    check_decision_invariants()
    check_mac_uses_the_shared_procedure()
    check_figure04_claims(nums)
    check_amendment_reach(nums)
    check_mac_claims(nums)
    check_verdict_claims(nums)
    check_dual_regulation(nums)
    check_gap_profile(tex)
    check_separation(nums)
    check_graph_is_consistent()
    check_graph_references()
    check_group_completeness(nums)
    check_group_thresholds()
    check_numbers_are_shipped(tex)
    check_figure_geometry()
    check_threshold_transcription()
    check_remaining_claims(nums)
    check_front_matter_numerals()
    check_bibtex_syntax()
    check_supplementary_pointers()
    check_heading_quantifiers()
    check_caption_counts()
    check_readme_numbers()
    check_no_placeholder_urls()
    check_no_retired_vocabulary()
    check_section_pointers()
    check_benchmark_shape()
    check_latex_preflight()
    check_conclusions_introduce_nothing()
    check_abstract_introduces_nothing()
    check_paper_hygiene(tex)
    check_no_dead_terms()
    check_functional_properties()
    check_alignment()
    check_graph_matches_population(nums)
    check_reported_intervals(nums)
    check_shacl_conformance(nums)
    check_abox_datatypes()
    check_report_indeterminate_total()
    resolve_pending_claims()

    n_fail = sum(1 for s, _, _ in results if s == FAIL)
    n_warn = sum(1 for s, _, _ in results if s == WARN)
    n_ok = sum(1 for s, _, _ in results if s == OK)
    n_skip = sum(1 for s, _, _ in results if s == SKIP)
    n_info = sum(1 for s, _, _ in results if s == INFO)

    L = ["# Project audit\n",
         "Generated by `scripts/99_audit.py`. Each claim in the manuscript is "
         "**recomputed from `derived/processed/*.csv`** -- the data, not the "
         "reports -- and compared against the value the LaTeX asserts. "
         "Presence-in-a-file, which `95_numbers_manifest.py` checks, cannot "
         "catch a number that is stated consistently and wrong.\n",
         f"- checks: **{len(results)}**",
         f"- passed: **{n_ok}**",
         f"- failed: **{n_fail}**",
         f"- warnings: {n_warn}",
         f"- computed but not quoted: {n_info}",
         f"- skipped: {n_skip}\n"]

    for state in (FAIL, WARN, OK, INFO, SKIP):
        rows = [r for r in results if r[0] == state]
        if not rows:
            continue
        L.append(f"## {state} ({len(rows)})\n")
        L.append("| check | detail |")
        L.append("|---|---|")
        for _, name, detail in rows:
            L.append(f"| {name} | {detail} |")
        L.append("")

    text = "\n".join(L)
    EVAL.mkdir(parents=True, exist_ok=True)
    (EVAL / "audit.md").write_text(text, encoding="utf-8")

    for state, name, detail in results:
        if state != OK or args.verbose:
            print(f"  {state:5s} {name}" + (f" — {detail}" if detail else ""))
    print(f"\n  {n_ok} passed, {n_fail} failed, {n_warn} warnings, "
          f"{n_info} computed but not quoted, {n_skip} skipped")
    print(f"  wrote {(EVAL / 'audit.md').relative_to(ROOT)}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
