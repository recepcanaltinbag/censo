#!/usr/bin/env python3
"""
Assemble the files that get served at https://w3id.org/censo/.

WHY THIS IS A SCRIPT AND NOT A COPY COMMAND
-------------------------------------------
publish/site/ is what the permanent IRI resolves to. If it drifts from
ontology/, the vocabulary the world downloads is not the vocabulary the paper
describes -- and nothing in the repository would say so. That already happened
once: the regulation packages were copied before threshold labels were added,
so the published copies carried unlabelled thresholds while the source did not.

So the directory is generated, never edited, and --check fails when it is out
of date. The JSON-LD serialisation is produced here too, because the .htaccess
offers it and no other script emits it.

Inputs  : ontology/dist/censo-full.{ttl,owl}
          ontology/censo-{shapes,regulation}.ttl
          ontology/reg/*.ttl
Outputs : publish/site/**

Usage:  python scripts/97_assemble_publish.py [--check]
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONTO = ROOT / "ontology"
SITE = ROOT / "publish" / "site"

# (source, destination relative to publish/site/)
FILES = [
    (ONTO / "dist" / "censo-full.ttl", "censo-full.ttl"),
    (ONTO / "dist" / "censo-full.owl", "censo-full.owl"),
    (ONTO / "censo-shapes.ttl", "censo-shapes.ttl"),
    (ONTO / "censo-regulation.ttl", "censo-regulation.ttl"),
    # Published as its own file and deliberately NOT merged into censo-full:
    # the alignment commits to claims about ChEBI and CHMO that a consumer of
    # the vocabulary alone should not have to take. Same reason the regulation
    # packages are separate. It has to be resolvable, though — an alignment
    # nobody can dereference reconciles nothing.
    (ONTO / "censo-alignment.ttl", "censo-alignment.ttl"),
]


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the published copy is out of date")
    args = ap.parse_args()

    pairs = list(FILES)
    for pkg in sorted((ONTO / "reg").glob("*.ttl")):
        pairs.append((pkg, f"reg/{pkg.name}"))

    # The ontology declares owl:versionIRI https://w3id.org/censo/<version>.
    # That IRI is inside the published file, so it has to resolve to something:
    # an artefact whose own version identifier 404s is worse than one that
    # carries none. The version is read from the file rather than hard-coded,
    # so a release bump cannot silently leave the redirect pointing at nothing.
    core = ONTO / "dist" / "censo-full.ttl"

    # The guard comes FIRST. It used to sit seven lines below the read above,
    # so a tree without ontology/dist/ died on an uncaught FileNotFoundError
    # instead of the deliberate message -- and the message is the useful part,
    # because the fix is to run scripts/16_export_for_scanners.py.
    missing = [str(s.relative_to(ROOT)) for s, _ in pairs if not s.exists()]
    if not core.exists():
        missing.append(str(core.relative_to(ROOT))
                       + " (run scripts/16_export_for_scanners.py)")
    if missing:
        sys.exit("missing sources: " + ", ".join(missing))

    # The ontology declares owl:versionIRI https://w3id.org/censo/<version>.
    m = re.search(r'owl:versionInfo\s+"([^"]+)"', core.read_text(encoding="utf-8"))
    version = m.group(1) if m else None
    if version:
        # A RELEASE DIRECTORY IS IMMUTABLE, and this did not enforce it.
        #
        # The version is read from the file, so as long as owl:versionInfo said
        # "1.0.0" every run rewrote releases/1.0.0/ with whatever the vocabulary
        # currently was. Twenty-one terms were retired and releases/1.0.0/
        # quietly became a 50-class file where it had been 58 -- so anyone who
        # dereferenced https://w3id.org/censo/1.0.0 before and after got
        # different axioms under one version IRI, which is the single promise a
        # version IRI makes.
        #
        # Refuse instead. If the vocabulary changed, the version has to change;
        # that is what the version is for.
        frozen = SITE / "releases" / version / "censo-full.ttl"
        if frozen.exists() and digest(frozen) != digest(core):
            sys.exit(
                f"releases/{version}/censo-full.ttl already exists and differs "
                f"from the current build.\n"
                f"A published release is immutable: bump owl:versionInfo in "
                f"ontology/censo-core.ttl (removing a term is a MAJOR change) "
                f"and re-run scripts/16_export_for_scanners.py, or restore the "
                f"archived file if the change was unintended.")
        pairs.append((core, f"releases/{version}/censo-full.ttl"))
        pairs.append((ONTO / "dist" / "censo-full.owl",
                      f"releases/{version}/censo-full.owl"))
        missing = [str(s.relative_to(ROOT)) for s, _ in pairs if not s.exists()]
        if missing:
            sys.exit("missing sources: " + ", ".join(missing))

    if args.check:
        stale = []
        for src, dst in pairs:
            d = SITE / dst
            if not d.exists() or digest(d) != digest(src):
                stale.append(dst)
        if stale:
            print("  publish/site is OUT OF DATE: " + ", ".join(stale))
            print("  re-run: python scripts/97_assemble_publish.py")
            return 1
        print(f"  publish/site is current ({len(pairs)} files)")
        return 0

    SITE.mkdir(parents=True, exist_ok=True)
    for src, dst in pairs:
        d = SITE / dst
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, d)

    # JSON-LD: offered by the .htaccess, emitted nowhere else.
    try:
        import rdflib
        g = rdflib.Graph()
        g.parse(ONTO / "dist" / "censo-full.ttl", format="turtle")
        g.serialize(destination=str(SITE / "censo-full.jsonld"),
                    format="json-ld", indent=2)
    except ImportError:
        print("  (rdflib absent; JSON-LD not regenerated)")

    total = 0
    for f in sorted(SITE.rglob("*")):
        # the directory is a git working tree once pushed; do not report its
        # internals as published content
        if ".git" in f.parts:
            continue
        if f.is_file():
            total += f.stat().st_size
            print(f"  {f.relative_to(SITE)!s:34s} {f.stat().st_size/1024:8.0f} KB")
    print(f"\n  {total/1024:.0f} KB in {SITE.relative_to(ROOT)}")
    print("  push this directory to the repository GitHub Pages serves")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
