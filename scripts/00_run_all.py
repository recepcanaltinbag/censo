#!/usr/bin/env python3
"""
Rebuild everything, in dependency order, from one command.

WHY THIS EXISTS
---------------
The pipeline was a set of scripts that had to be run in the right order by
someone who knew the order. That is not reproducibility; it is a folklore
requirement. Twice it produced a real defect in the manuscript: the
dual-regulation analysis was quoted while older than the regulation packages it
read, and the figures were quoted while older than the table behind them. In
both cases every individual script was correct.

So the order is written down here, executable, and the audit is the last stage.
A reader who has the Waterbase download and this file can reproduce every
number, every figure and every supplementary table without being told anything
else.

WHAT DEPENDS ON WHAT
--------------------
    EUR-Lex Annex I  --10-->  eu_eqs.csv  --19-->  regulation packages
                                   |                       |
                                   v                       v
    Waterbase zip  --22-->  waterbase_summary.csv    23-->  ABox
                                   |                  |      |
                        24, 25 ----+                  |   17, 18 (queries, SHACL)
                                   |                  |
                                   +--------> 90 (figures) --> 98 (supplementary)
                                                                     |
                                                        96 (flatten) + 95 + 99

Stages are skipped, not failed, when an optional input is absent, so the parts
that need no download still run on a fresh clone.

Usage:
    python scripts/00_run_all.py --waterbase <WISE6_AggregatedData-csv.zip>
    python scripts/00_run_all.py --from 90        # resume at a stage
    python scripts/00_run_all.py --list
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

# (script, human label, needs the Waterbase download?)
STAGES = [
    ("10_parse_eu_eqs.py", "parse EU Annex I from the consolidated text", False),
    ("08_verify_thresholds.py", "verify thresholds against the primary text", False),
    ("19_build_regulation_packages.py", "build the two regulation packages", False),
    ("22_waterbase_external.py", "audit Waterbase (counters, no ontology)", True),
    ("23_waterbase_abox.py", "express a Waterbase subset in CENSO", True),
    ("24_dual_regulation.py", "assess the same rows under both jurisdictions", True),
    ("25_country_confounders.py", "test the between-country spread", True),
    ("26_source_conformance.py", "validate the record as reported", True),
    # The only stage that reads the DISAGGREGATED release, and the only one
    # that can: a maximum-allowable standard is defined against an individual
    # measurement, which the aggregated file no longer contains. It finds both
    # releases itself rather than being handed --waterbase, and skips cleanly
    # when the disaggregated one is absent, so the documented reproduction path
    # -- the 165 MB aggregated download -- still runs the whole paper except
    # this section.
    ("27_mac_exceedance.py", "assess the maximum-allowable standard", False),
    # After 19: it reads the released packages. Before 24, which is the
    # analysis the alignment has to agree with.
    ("20_align_external.py", "align to ChEBI and CHMO", False),
    ("07_verify_gap_table.py", "parse the comparison ontologies", False),
    ("11_assess_competitor_papers.py", "assess paper-only ontologies", False),
    ("09_verify_bibliography.py", "check the bibliography against Crossref", False),
    ("validate_ontology.py", "validate the ontology modules", False),
    ("test_axioms.py", "run the axiom test suite", False),
    ("14_reasoning_benchmark.py", "measure reasoning cost", False),
    # These two read derived/abox/censo-waterbase.ttl, which only stage 23
    # produces. They are NOT marked as needing the download: needs_wb also
    # decides whether --file is passed, and neither accepts it. They skip
    # themselves when the ABox is absent, which is the same promise reached the
    # other way -- "skipped, not failed, when an optional input is absent".
    ("17_run_competency_questions.py", "run the competency questions", False),
    ("18_shacl_validate.py", "SHACL validation and materialisation", False),
    ("90_figures.py", "draw every figure and ship its data", False),
    # After BOTH 07, which writes the gap matrix it reads, and 90, which ships
    # the witness row it argues over. It turns the gap table from a term list
    # into an entailment claim, and exits 1 if a comparison vocabulary turns
    # out to separate the readings after all -- which is how this result
    # would fail. It skips cleanly when the figure data is absent, so a run
    # without the Waterbase download still completes.
    ("13_separation.py", "show what the vocabularies cannot separate", False),
    ("98_supplementary.py", "generate the supplementary tables", False),
    # 16 before 97. It writes ontology/dist/, which 97 copies to publish/site/.
    # It was not in this list at all, so dist/ was regenerated only by hand:
    # an edit to censo-core.ttl reached neither the distribution nor the
    # published copy, and 97 --check compared publish/site against dist/ --
    # both stale, both agreeing, the audit green. That is how the ontology the
    # permanent IRI serves came to carry a disjointness axiom the source had
    # dropped.
    ("16_export_for_scanners.py", "export the standalone distribution", False),
    ("97_assemble_publish.py", "assemble the published ontology copy", False),
    # After 97, because it assesses the PUBLISHED IRI and not the working copy
    # -- content negotiation and version-IRI resolution cannot be tested on a
    # file. The only stage that touches the network; it caches the service
    # response in eval/ and falls back to it, so an offline run still writes
    # the report and 99_audit.py still finds the numbers it checks.
    ("15_foops.py", "assess FAIR publication with FOOPS!", False),
    ("96_flatten_paper.py", "inline the manuscript into one file", False),
    ("95_numbers_manifest.py", "trace every number to its script", False),
    ("99_audit.py", "recompute every claim and fail on a mismatch", False),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--waterbase", type=Path,
                    help="WISE6_AggregatedData-csv.zip; stages needing it are "
                         "skipped when absent")
    ap.add_argument("--from", dest="start", default=None,
                    help="resume at the stage whose script starts with this")
    ap.add_argument("--list", action="store_true", help="list the stages")
    ap.add_argument("--keep-going", action="store_true",
                    help="continue after a failing stage")
    args = ap.parse_args()

    if args.list:
        for i, (s, label, wb) in enumerate(STAGES, 1):
            print(f"  {i:2}. {s:34} {label}{'  [needs --waterbase]' if wb else ''}")
        return 0

    stages = STAGES
    if args.start:
        idx = [i for i, (s, _, _) in enumerate(stages)
               if s.startswith(args.start)]
        if not idx:
            sys.exit(f"no stage matches {args.start!r}; try --list")
        stages = stages[idx[0]:]

    wb = args.waterbase
    if wb and not wb.exists():
        sys.exit(f"not found: {wb}")

    t0 = time.time()
    ran = skipped = 0
    failed = []
    for i, (script, label, needs_wb) in enumerate(stages, 1):
        path = ROOT / "scripts" / script
        if not path.exists():
            print(f"  [{i:2}/{len(stages)}] SKIP  {label} ({script} absent)")
            skipped += 1
            continue
        if needs_wb and not wb:
            print(f"  [{i:2}/{len(stages)}] SKIP  {label} (no --waterbase)")
            skipped += 1
            continue
        cmd = [PY, str(path)] + (["--file", str(wb)] if needs_wb else [])
        print(f"  [{i:2}/{len(stages)}] {label} …", flush=True)
        t = time.time()
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"        FAILED after {time.time()-t:.1f}s")
            tail = (r.stderr or r.stdout).strip().splitlines()[-6:]
            for line in tail:
                print(f"        {line}")
            failed.append(script)
            if not args.keep_going:
                print(f"\n  stopped at {script}. Fix it, then resume with:")
                print(f"    python scripts/00_run_all.py --from {script[:2]}"
                      + (f" --waterbase {wb}" if wb else ""))
                return 1
        else:
            print(f"        ok ({time.time()-t:.1f}s)")
            ran += 1

    print(f"\n  {ran} stage(s) run, {skipped} skipped, {len(failed)} failed "
          f"in {time.time()-t0:.0f}s")
    if not wb:
        print("  Waterbase stages were skipped. Download the aggregated release "
              "and pass --waterbase to reproduce the empirical results:")
        print("  https://www.eea.europa.eu/en/datahub/datahubitem-view/"
              "fbf3717c-cd7b-4785-933a-d0cf510542e1")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
