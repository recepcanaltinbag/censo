#!/usr/bin/env python3
"""Render the manuscript to .docx for reading and comment.

WHY THIS EXISTS

Elsevier takes LaTeX, so the .docx is not the submission -- it is for co-authors
and reviewers who want to comment in Word. It is generated rather than exported
by hand so that it cannot drift from the manuscript, which is the same rule the
figures and the supplementary tables follow.

TWO THINGS PANDOC CANNOT DO HERE, both handled rather than ignored:

  * pandoc 2.5 has no built-in citeproc and pandoc-citeproc is not installed, so
    \\cite{key} would render as literal LaTeX. Keys are resolved against
    paper/refs.bib into author-year form first. A key with no author (a directive,
    a standard) resolves to its title's leading words, which is how the
    author-year style renders it too.
  * siunitx is not understood, so \\num{} and \\si{} are unwrapped, and the
    thin-space and unit markup is replaced by plain text.

Usage:  python scripts/93_make_docx.py [-o OUT]
Input :  paper/main-elsevier-standalone.tex  (written by 96_flatten_paper.py)
Output:  paper/censo-manuscript.docx
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPER = ROOT / "paper"
SRC = PAPER / "main-elsevier-standalone.tex"


def bib_index(path: Path) -> dict:
    """key -> author-year label, as an author-year style would print it."""
    out = {}
    if not path.exists():
        return out
    text = path.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r"@\w+\{([^,]+),(.*?)\n\}", text, re.S):
        key, body = m.group(1).strip(), m.group(2)

        def field(name):
            f = re.search(rf"^\s*{name}\s*=\s*\{{(.*?)\}}\s*,?\s*$",
                          body, re.M | re.S)
            return " ".join(f.group(1).split()) if f else ""

        year = re.sub(r"\D", "", field("year"))[:4]
        author = field("author") or field("editor")
        if author:
            first = author.split(" and ")[0]
            # "Surname, Given" or "Given Surname"; corporate names keep braces
            surname = (first.split(",")[0] if "," in first
                       else first.split()[-1] if first.split() else first)
            label = surname.strip("{} ")
        else:
            title = field("title") or key
            label = " ".join(re.sub(r"[{}\\]", "", title).split()[:3])
        out[key] = f"{label}, {year}" if year else label
    return out


def resolve_citations(tex: str, bib: dict) -> tuple:
    missing = []

    def one(m):
        keys = [k.strip() for k in m.group(2).split(",") if k.strip()]
        parts = []
        for k in keys:
            if k in bib:
                parts.append(bib[k])
            else:
                missing.append(k)
                parts.append(k)
        return "(" + "; ".join(parts) + ")"

    return re.sub(r"\\cite([tp]?)\{([^}]*)\}", one, tex), missing


def plain_units(tex: str) -> str:
    """Unwrap the siunitx markup pandoc would print verbatim."""
    tex = re.sub(r"\\num\{([^{}]*)\}", r"\1", tex)
    tex = re.sub(r"\\SI\{([^{}]*)\}\{([^{}]*)\}", r"\1 \2", tex)
    UNITS = {r"\\micro\\gram\\per\\litre": "ug/L",
             r"\\milli\\gram\\per\\litre": "mg/L",
             r"\\nano\\gram\\per\\litre": "ng/L"}
    for pat, rep in UNITS.items():
        tex = re.sub(r"\\si\{" + pat + r"\}", rep, tex)
    tex = re.sub(r"\\si\{([^{}]*)\}", r"\1", tex)
    tex = tex.replace("\\,", " ").replace("\\;", " ").replace("\\ ", " ")
    # NOT \% -> %. A bare per-cent sign starts a LaTeX comment, so replacing it
    # swallowed the rest of the line and broke brace matching: pandoc failed on
    # "\textbf{44.9%" with the closing brace now inside a comment. pandoc
    # understands \% perfectly well; leave it alone.
    tex = tex.replace("\u2009", " ")
    # \src{...} is a footnote naming the producing script: keep it, as a note
    tex = re.sub(r"\\src\{([^{}]*)\}", r"\\footnote{Produced by \1.}", tex)
    tex = re.sub(r"\\pending\{([^{}]*)\}", r"[TO COMPUTE: \1]", tex)
    return tex


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=str(PAPER / "censo-manuscript.docx"))
    args = ap.parse_args()

    if not shutil.which("pandoc"):
        sys.exit("pandoc is required:  apt install pandoc")
    if not SRC.exists():
        sys.exit(f"missing {SRC}; run scripts/96_flatten_paper.py first")

    bib = bib_index(PAPER / "refs.bib")
    tex, missing = resolve_citations(SRC.read_text(encoding="utf-8"), bib)
    tex = plain_units(tex)
    print(f"  {len(bib)} bibliography entries indexed")
    if missing:
        print(f"  WARNING: {len(set(missing))} citation key(s) not in refs.bib: "
              + ", ".join(sorted(set(missing))[:5]))

    tmp = PAPER / ".docx-source.tex"
    tmp.write_text(tex, encoding="utf-8")
    out = Path(args.out)
    cmd = ["pandoc", "-f", "latex", "-t", "docx",
           "--resource-path", f"{PAPER / 'figures'}:{PAPER}",
           "-o", str(out), str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r.returncode:
        print(r.stderr[:800])
        sys.exit("pandoc failed")
    kb = out.stat().st_size / 1024
    print(f"  wrote {out.relative_to(ROOT)}  ({kb:,.0f} kB)")
    print("  NOTE: the .docx is for reading and comment. Elsevier takes the "
          "LaTeX; paper/main-elsevier.tex is the submission.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
