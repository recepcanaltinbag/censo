#!/usr/bin/env python3
"""
Flatten the manuscript into one self-contained .tex file.

WHY
---
`paper/main-elsevier.tex` is deliberately thin: it holds the preamble and `\\input`s the
seven section files, which is what keeps diffs readable and lets each section be
edited without merge conflicts. The cost is that opening main-elsevier.tex shows about a
hundred lines and none of the actual paper.

This script produces the other view -- `paper/main-standalone.tex`, every
section and generated table inlined, ready to open in one window or paste into
Overleaf as a single document. It is GENERATED, so it can never drift from the
split sources: edit the sections, re-run this, never edit the standalone file.

Inlining is recursive (a section may itself \\input a generated table) and each
insertion is marked with the file it came from, so a number can still be traced
back to the section that owns it.

Inputs  : paper/main-elsevier.tex and everything it \\input s
Outputs : paper/main-standalone.tex

Usage:  python scripts/96_flatten_paper.py [--check]
        --check exits 1 if the standalone file is out of date, for CI.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPER = ROOT / "paper"
# One front-end. The generic article-class variant was retired to
# paper/attic/ once the target narrowed to Elsevier; keeping two meant
# every edit had to stay consistent across both for no gain.
MAIN = PAPER / "main-elsevier.tex"
OUT = PAPER / "main-elsevier-standalone.tex"

INPUT = re.compile(r"^([ \t]*)\\input\{([^}]+)\}[ \t]*$", re.M)

HEADER = """\
% ============================================================================
%  GENERATED FILE — do not edit.
%
%  Produced by scripts/96_flatten_paper.py from main-elsevier.tex and sections/*.tex.
%  This is main-elsevier.tex with every \\input inlined, so the whole manuscript can be
%  read or compiled as a single document (e.g. pasted into Overleaf).
%
%  To change the text, edit the section file named in the marker comment above
%  the passage, then re-run:
%
%      python scripts/96_flatten_paper.py
%
%  Editing this file directly will be overwritten.
% ============================================================================

"""


def resolve(name: str) -> Path | None:
    """LaTeX \\input takes a path relative to the main file, .tex optional."""
    for cand in (PAPER / name, PAPER / f"{name}.tex"):
        if cand.is_file():
            return cand
    return None


def inline(path: Path, seen: tuple[str, ...] = ()) -> str:
    rel = path.relative_to(PAPER).as_posix()
    if rel in seen:
        # A cycle would otherwise recurse until the stack blows.
        return f"% [flatten] cycle detected at {rel}; not expanded again\n"
    text = path.read_text(encoding="utf-8")

    def repl(m: re.Match) -> str:
        indent, target = m.group(1), m.group(2)
        p = resolve(target)
        if p is None:
            # Leave it alone rather than silently drop content.
            return (f"{indent}% [flatten] MISSING: \\input{{{target}}} could "
                    f"not be resolved\n{m.group(0)}")
        sub = inline(p, seen + (rel,))
        tag = p.relative_to(PAPER).as_posix()
        return (f"{indent}% >>> begin {tag}\n"
                f"{sub.rstrip()}\n"
                f"{indent}% <<< end {tag}")

    return INPUT.sub(repl, text)


def build() -> str:
    if not MAIN.exists():
        sys.exit(f"missing {MAIN}")
    body = inline(MAIN)
    # The bibliography stays as \bibliography{refs}: inlining a .bbl would
    # freeze the reference list, and refs.bib is the source of truth.
    return HEADER + body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the standalone file is out of date")
    args = ap.parse_args()

    text = build()
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("  main-elsevier-standalone.tex is OUT OF DATE — re-run without --check")
            return 1
        print("  main-standalone.tex is up to date")
        return 0

    OUT.write_text(text, encoding="utf-8")
    n_lines = text.count("\n") + 1
    n_inlined = text.count("% >>> begin ")
    n_fig = len(re.findall(r"\\includegraphics", text))
    n_tab = len(re.findall(r"\\begin\{table\*?\}", text))
    n_pend = len(re.findall(r"\\pending\{", text))
    print(f"  inlined files : {n_inlined}")
    print(f"  lines         : {n_lines:,}")
    print(f"  figures       : {n_fig}")
    print(f"  tables        : {n_tab}")
    print(f"  \\pending      : {n_pend}")
    print(f"\n  wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
