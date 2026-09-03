#!/usr/bin/env python3
"""
Can this machine run the pipeline? Answer before spending an hour finding out.

WHY
---
The project is moving between machines and on to a larger release. Everything
here resolves paths from the repository root and nothing is hard-coded to a
home directory, so portability is mostly a question of what is installed and
how big the input is. This check answers both, and says what to do about each
failure rather than only that it failed.

It is deliberately the cheapest stage: no data is read, nothing is written.

Usage:  python scripts/01_check_environment.py [--waterbase PATH]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (import name, why it is needed, whether the pipeline is useless without it)
PACKAGES = [
    ("rdflib", "parse and query the ontology and the knowledge graph", True),
    ("pyshacl", "closed-world validation and materialisation", True),
    ("owlrl", "OWL 2 RL entailment", True),
    ("matplotlib", "figures", True),
    ("numpy", "figures and the spatial helpers", True),
    ("pypdf", "parse the legal texts", False),
    ("openpyxl", "read spreadsheet inputs, if any are added", False),
    ("shapefile", "shapefiles (pyshp), only for map figures", False),
    ("pyproj", "equal-area projection for the map", False),
]

# Rough working-set sizes, so a machine can be judged before the run.
FOOTPRINT = {
    "aggregated release (162 MB zip)": "streams; peak RSS well under 1 GB",
    "knowledge graph in rdflib": "~2.5 GB RSS at 450k triples",
    "pyshacl validation": "~4 GB RSS at 450k triples, superlinear",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--waterbase", type=Path,
                    help="the release to be processed, if not in Data/waterbase")
    args = ap.parse_args()

    problems, warnings = [], []

    print("  Python")
    v = sys.version_info
    print(f"    {sys.version.split()[0]}  ({sys.executable})")
    if v < (3, 8):
        problems.append(f"Python {v.major}.{v.minor} is too old; 3.8 or later")
    elif v >= (3, 13):
        warnings.append(
            f"Python {v.major}.{v.minor} is newer than the pinned environment "
            "(3.8). requirements.txt pins exact versions that may have no "
            "wheel here; install without the pins if pip refuses, then record "
            "what actually resolved.")

    print("\n  Packages")
    for mod, why, required in PACKAGES:
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "?")
            print(f"    ok       {mod:12} {ver:10} {why}")
        except ImportError:
            print(f"    MISSING  {mod:12} {'':10} {why}")
            (problems if required else warnings).append(
                f"{mod} is not installed ({why})")

    print("\n  Input data")
    cands = []
    if args.waterbase:
        cands = [args.waterbase]
    else:
        d = ROOT / "Data" / "waterbase"
        if d.exists():
            cands = [p for p in sorted(d.iterdir())
                     if p.suffix.lower() in (".zip", ".csv", ".gz")]
    if not cands:
        warnings.append(
            "no Waterbase release found. Stages 22-26 will be skipped. "
            "Download from https://www.eea.europa.eu/en/datahub/"
            "datahubitem-view/fbf3717c-cd7b-4785-933a-d0cf510542e1 and put it "
            "in Data/waterbase/, or pass --waterbase")
        print("    none found (the ontology stages still run)")
    for p in cands:
        if not p.exists():
            problems.append(f"{p} does not exist")
            continue
        gb = p.stat().st_size / 1e9
        print(f"    {p.name}  {gb:.2f} GB")
        if gb > 1.0:
            warnings.append(
                f"{p.name} is {gb:.1f} GB. The counting stages stream and will "
                "cope, but the graph stages are bounded by --max-rows, not by "
                "the input: keep 23 and 26 at a sample size the machine can "
                "hold rather than raising it to match the file.")

    # The disaggregated release is a Deflate64 archive. Python's zipfile cannot
    # open it, so stage 9 shells out to 7z or bsdtar. Discovering that 35
    # minutes into a run is exactly what this script exists to prevent.
    print("\n  External tools")
    have_disagg = any("Disaggregated" in p.name for p in cands
                      if getattr(p, "name", None))
    # pdftotext is a HARD requirement of stage 1: Annex I is read by column
    # position from `pdftotext -layout`, and the stage exits rather than fall
    # back to flattened text, which cannot tell an empty cell from a missing one.
    # A fresh clone died at stage 1 of 24 because this was never checked here.
    pdftotext = shutil.which("pdftotext")
    print(f"    {'ok  ' if pdftotext else 'MISSING'}     "
          f"{'pdftotext':8} {pdftotext or 'not on PATH -- REQUIRED by stage 1'}")
    if not pdftotext:
        problems.append(
            "pdftotext (poppler-utils) is missing. Stage 1 reads Annex I by "
            "column position and will not guess: `apt install poppler-utils`")
    extractors = [(n, shutil.which(n)) for n in ("7z", "7za", "bsdtar")]
    found = [n for n, w in extractors if w]
    for n, w in extractors:
        print(f"    {'ok  ' if w else '--  '}     {n:8} "
              f"{w or 'not on PATH'}")
    if not found:
        msg = ("no 7z or bsdtar on PATH. The disaggregated release is a "
               "Deflate64 archive that Python's zipfile cannot read")
        if have_disagg:
            warnings.append(msg + ", so stage 9 (the maximum-allowable "
                            "standard) will skip itself even though the file "
                            "is present. apt install p7zip-full")
        else:
            print("    (only needed for the disaggregated release, "
                  "which is absent)")

    print("\n  Disk")
    free = shutil.disk_usage(ROOT).free / 1e9
    print(f"    {free:.1f} GB free at {ROOT}")
    if free < 5:
        problems.append(f"only {free:.1f} GB free; the graphs and caches need ~5 GB")

    print("\n  Expected memory")
    for what, size in FOOTPRINT.items():
        print(f"    {what:34} {size}")

    print()
    for w in warnings:
        print(f"  WARN  {w}")
    for p_ in problems:
        print(f"  FAIL  {p_}")
    if problems:
        print(f"\n  {len(problems)} blocking problem(s).")
        if any("not installed" in p_ for p_ in problems):
            print("    pip install -r requirements.txt")
        if any("free" in p_ for p_ in problems):
            print("    free disk space, or move the repository to a larger "
                  "volume. derived/abox/ and derived/interim/ are both "
                  "regenerable and are the usual place to reclaim from:")
            print("      rm -rf derived/abox derived/interim")
        return 1
    print(f"  ready ({len(warnings)} warning(s))")
    print("  next:  python scripts/00_run_all.py --waterbase <release>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
