#!/usr/bin/env python3
"""
Measure what the pipeline costs, stage by stage, on the graph it publishes.

WHY THIS EXISTS
---------------
The manuscript describes an implementation -- stages, runtime, memory, "runs
from a single pip install" -- and none of those numbers were produced by any
script. A performance claim measured once by hand in a terminal is not a
claim this repository can defend: it cannot be re-checked, it is not in
eval/, and scripts/95_numbers_manifest.py cannot trace it. Everything the
implementation subsection asserts is measured here and nowhere else.

WHAT IS MEASURED, AND WHAT IS NOT
---------------------------------
The production path over the published graph is: parse -> rdfs:subClassOf
type closure to a fixed point -> SHACL validation with advanced mode (which
is where the indeterminate outcomes are added, because they are SPARQL
CONSTRUCT rules). That is the path timed below.

Full OWL 2 RL closure over the published graph is NOT on that path, and the
manuscript must not say it is. scripts/17_run_competency_questions.py states
the reason: owlrl in pure Python over ~650k triples is impractical. owlrl is
used on bounded inputs -- the axiom tests, the separation demonstration, the
reasoning benchmark, and the covering slice in scripts/99_audit.py -- and
--owlrl measures it here on the same published graph under a wall-clock
budget, so that "impractical" is a measurement rather than a recollection.

The row-level assessment of the full record does not build a graph at all: it
is a streaming pass in scripts/22_waterbase_external.py. Timing it needs the
Waterbase archive, so it is behind --full-record.

Outputs: eval/pipeline_performance.md
         derived/processed/pipeline_performance.csv

Usage:  python scripts/14b_pipeline_performance.py
        python scripts/14b_pipeline_performance.py --owlrl --owlrl-budget 1800
        python scripts/14b_pipeline_performance.py --full-record Data/waterbase/WISE6_AggregatedData-csv.zip
"""
from __future__ import annotations

import argparse
import csv
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
PROCD = ROOT / "derived" / "processed"

try:
    import rdflib
except ImportError:
    sys.exit("requires rdflib")


def peak_mb() -> float:
    """Peak resident set size of this process, in MB.

    ru_maxrss is a high-water mark and never decreases, so a per-stage value
    is "peak up to and including this stage" -- which is the figure a reader
    needs (how much memory must the machine have) rather than a per-stage
    delta (which would be unmeasurable without a separate process anyway).
    """
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def hardware() -> list[tuple[str, str]]:
    cpu, cores, mem = platform.processor() or "unknown", "?", "?"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
        cores = str(sum(1 for l in Path("/proc/cpuinfo").read_text().splitlines()
                        if l.startswith("processor")))
    except OSError:
        pass
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                mem = f"{int(line.split()[1]) / 1048576:.0f} GB"
                break
    except OSError:
        pass
    ver = {}
    for mod in ("rdflib", "pyshacl", "owlrl"):
        try:
            import importlib.metadata as md
            ver[mod] = md.version(mod)
        except Exception:                                    # noqa: BLE001
            ver[mod] = "not installed"
    return [("CPU", cpu), ("logical cores", cores), ("system memory", mem),
            ("OS", f"{platform.system()} {platform.release()}"),
            ("Python", platform.python_version()),
            ("rdflib", ver["rdflib"]), ("pyshacl", ver["pyshacl"]),
            ("owlrl", ver["owlrl"])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--abox", default=None)
    ap.add_argument("--owlrl", action="store_true",
                    help="also attempt full OWL 2 RL closure on this graph")
    ap.add_argument("--owlrl-budget", type=float, default=1800.0)
    ap.add_argument("--full-record", default=None,
                    help="Waterbase archive; times the streaming assessment")
    args = ap.parse_args()
    EVAL.mkdir(parents=True, exist_ok=True)
    PROCD.mkdir(parents=True, exist_ok=True)

    abox = (Path(args.abox) if args.abox
            else ROOT / "derived" / "abox" / "censo-waterbase.ttl")
    if not abox.exists():
        print(f"  no ABox at {abox.name}; skipping.")
        return 0

    rows: list[tuple[str, str, str, str]] = []      # stage, unit, value, note
    def rec(stage, unit, value, note=""):
        rows.append((stage, unit, value, note))
        print(f"  {stage:38} {value:>12} {unit}")

    # ---- stage 1: parse ---------------------------------------------------
    t0 = time.perf_counter()
    g = rdflib.Graph()
    g.parse(abox, format="turtle")
    n_abox = len(g)
    g.parse(ROOT / "ontology" / "censo-core.ttl", format="turtle")
    g.parse(ROOT / "ontology" / "censo-regulation.ttl", format="turtle")
    pkgs = sorted((ROOT / "ontology" / "reg").glob("*.ttl"))
    for p in pkgs:
        g.parse(p, format="turtle")
    for t in list(g.triples((None, rdflib.OWL.imports, None))):
        g.remove(t)
    t_parse = time.perf_counter() - t0
    n_parsed = len(g)

    # COUNTED AFTER THE CLOSURE, NOT BEFORE.
    # The ABox types an observation by its detection status --
    # censo:CensoredObservation and friends -- and nothing in the file says
    # those are sosa:Observation. Counting sosa:Observation on the parsed
    # graph therefore returns 0, which is what the first run of this script
    # reported: a measurement of the wrong graph state, not of the data.
    rec("triples in the ABox file", "", f"{n_abox:,}")
    rec("triples after loading ontology + packages", "", f"{n_parsed:,}",
        f"{len(pkgs)} regulation package(s)")
    rec("parse", "s", f"{t_parse:.1f}")
    rec("peak memory after parse", "MB", f"{peak_mb():.0f}")

    # ---- stage 2: subclass type closure ----------------------------------
    t0 = time.perf_counter()
    n_sub, sweep = 0, True
    while sweep:
        sweep = False
        for sub, _, sup in list(g.triples((None, rdflib.RDFS.subClassOf, None))):
            if isinstance(sup, rdflib.term.BNode):
                continue
            for s_ in set(g.subjects(rdflib.RDF.type, sub)):
                if (s_, rdflib.RDF.type, sup) not in g:
                    g.add((s_, rdflib.RDF.type, sup))
                    n_sub += 1
                    sweep = True
    t_sub = time.perf_counter() - t0
    rec("rdfs:subClassOf type closure", "s", f"{t_sub:.1f}",
        f"{n_sub:,} triples added")
    rec("triples after closure", "", f"{len(g):,}")
    n_obs = len(set(g.subjects(
        rdflib.RDF.type,
        rdflib.URIRef("http://www.w3.org/ns/sosa/Observation"))))
    rec("observations in the published graph", "", f"{n_obs:,}")
    rec("peak memory after closure", "MB", f"{peak_mb():.0f}")

    # ---- stage 3: SHACL ---------------------------------------------------
    try:
        import pyshacl
    except ImportError:
        rec("SHACL validation", "s", "skipped", "pyshacl not installed")
    else:
        s = rdflib.Graph()
        s.parse(ROOT / "ontology" / "censo-shapes.ttl", format="turtle")
        t0 = time.perf_counter()
        conforms, _, txt = pyshacl.validate(g, shacl_graph=s, advanced=True,
                                            inplace=False)
        t_shacl = time.perf_counter() - t0
        n_viol = sum(1 for l in txt.splitlines() if "Message:" in l)
        rec("SHACL validation (advanced mode)", "s", f"{t_shacl:.1f}",
            f"conforms={conforms}, {n_viol:,} violation(s)")
        rec("SHACL validation", "min", f"{t_shacl / 60:.1f}")
        rec("peak memory after SHACL", "MB", f"{peak_mb():.0f}")
        rec("end-to-end on the published graph", "min",
            f"{(t_parse + t_sub + t_shacl) / 60:.1f}",
            "parse + closure + validation")

    # ---- optional: full OWL 2 RL closure on the same graph ---------------
    if args.owlrl:
        try:
            import owlrl
        except ImportError:
            rec("OWL 2 RL closure on the published graph", "s", "skipped",
                "owlrl not installed")
        else:
            # Measured on a copy so the timing above is not disturbed, and
            # under a budget: the point is whether it is practical, and an
            # unbounded run would simply never return.
            import threading
            h = rdflib.Graph()
            for t in g:
                h.add(t)
            out: dict[str, object] = {}
            def run():
                t = time.perf_counter()
                try:
                    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics,
                                           axiomatic_triples=False,
                                           datatype_axioms=False).expand(h)
                    out["s"] = time.perf_counter() - t
                except Exception as e:                       # noqa: BLE001
                    out["err"] = f"{type(e).__name__}: {e}"
            th = threading.Thread(target=run, daemon=True)
            th.start()
            th.join(args.owlrl_budget)
            if "s" in out:
                rec("OWL 2 RL closure on the published graph", "s",
                    f"{out['s']:.1f}", f"{len(h):,} triples after closure")
            elif "err" in out:
                rec("OWL 2 RL closure on the published graph", "s", "error",
                    str(out["err"])[:120])
            else:
                rec("OWL 2 RL closure on the published graph", "s",
                    f">{args.owlrl_budget:.0f}",
                    "did not finish within the budget; not on the "
                    "production path")
            rec("peak memory after OWL 2 RL attempt", "MB", f"{peak_mb():.0f}")

    # ---- optional: the streaming full-record assessment -------------------
    if args.full_record:
        z = Path(args.full_record)
        if not z.exists():
            rec("full-record streaming assessment", "min", "skipped",
                f"{z} not found")
        else:
            t0 = time.perf_counter()
            r = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "22_waterbase_external.py"),
                 "--file", str(z)],
                cwd=ROOT, capture_output=True, text=True)
            t_full = time.perf_counter() - t0
            rec("full-record streaming assessment", "min", f"{t_full / 60:.1f}",
                f"exit {r.returncode}; no graph is built on this path")

    # ---- report -----------------------------------------------------------
    L = ["# Pipeline cost, measured\n",
         "Generated by `scripts/14b_pipeline_performance.py`. Every runtime "
         "and memory figure in the implementation subsection of the "
         "manuscript comes from this table and from nowhere else.\n",
         "## Machine and library versions\n",
         "| item | value |", "|---|---|"]
    for k, v in hardware():
        L.append(f"| {k} | {v} |")
    L += ["", "## Measurements\n", "| stage | value | unit | note |",
          "|---|---|---|---|"]
    for stage, unit, value, note in rows:
        L.append(f"| {stage} | **{value}** | {unit} | {note} |")
    L += ["",
          "## What is on the production path and what is not\n",
          "The published graph is processed as parse, `rdfs:subClassOf` type "
          "closure to a fixed point, then SHACL validation in advanced mode "
          "-- advanced mode is where the indeterminate outcomes are added, "
          "because the rules that add them are SPARQL `CONSTRUCT` rules. "
          "Full OWL 2 RL closure over this graph is **not** on that path: "
          "`owlrl` runs in pure Python and is used on bounded inputs "
          "(`scripts/test_axioms.py`, `scripts/13_separation.py`, "
          "`scripts/14_reasoning_benchmark.py`, and the covering slice in "
          "`scripts/99_audit.py`). A description of the implementation that "
          "puts an OWL 2 RL materialisation step on the production path would "
          "misdescribe it.",
          "",
          "The assessment of the full record is a third path again: "
          "`scripts/22_waterbase_external.py` streams the archive row by row "
          "and builds no graph, which is why it completes in minutes while "
          "validating a 40,000-observation graph takes hours. The three "
          "figures are not comparable and the manuscript should not present "
          "them as one number.", ""]
    (EVAL / "pipeline_performance.md").write_text("\n".join(L) + "\n",
                                                  encoding="utf-8")
    with (PROCD / "pipeline_performance.csv").open("w", newline="",
                                                   encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["stage", "value", "unit", "note"])
        for stage, unit, value, note in rows:
            w.writerow([stage, value, unit, note])
    print(f"\nwrote: {EVAL / 'pipeline_performance.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
