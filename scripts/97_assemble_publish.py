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


# The documentation page is GENERATED, and this is why.
#
# index.html was hand-maintained, so it drifted -- exactly the failure the rest
# of this script exists to prevent for the RDF. By the time anyone looked, it
# announced version 1.0.0 after the vocabulary had moved to 2.0.0, counted 40
# classes where there are 32, gave the EU package 117 thresholds where it has
# 103, listed no censo-alignment.ttl, and still described the argument in
# retired terms: "the detection limit belongs to the analytical run" (that class
# is gone) and "compliance becomes four-valued" (it is three-valued, with the
# third subtyped by the reason). A human-facing page that contradicts the file
# beside it is worse than no page: it is the vocabulary's own front door.
#
# Every count below is read from the artefacts. The CSS is carried verbatim,
# because it is design and not data.

CSS = """:root{--ink:#1f1f1f;--muted:#5c6470;--line:#e3e6ea;--acc:#123f66;--bg:#fff}
@media(prefers-color-scheme:dark){:root{--ink:#e8eaed;--muted:#9aa3ae;--line:#2a2f36;--acc:#8ab0d6;--bg:#15181c}}
*{box-sizing:border-box}
body{margin:0;padding:2.5rem 1.25rem 4rem;background:var(--bg);color:var(--ink);
font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
main{max-width:46rem;margin:0 auto}
h1{font-size:1.7rem;line-height:1.25;margin:0 0 .4rem;letter-spacing:-.01em}
h2{font-size:1.05rem;margin:2.4rem 0 .7rem;letter-spacing:-.005em}
.iri{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.9rem;
color:var(--acc);word-break:break-all}
p{margin:.7rem 0} .lede{color:var(--muted);margin-bottom:1.6rem}
table{border-collapse:collapse;width:100%;font-size:.86rem;margin:.6rem 0;
display:block;overflow-x:auto}
th,td{text-align:left;padding:.5rem .7rem;border-bottom:1px solid var(--line);
vertical-align:top}
th{color:var(--muted);font-weight:600}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.85em}
a{color:var(--acc)} .k{display:flex;gap:1.5rem;flex-wrap:wrap;margin:1.2rem 0}
.k div{min-width:5rem} .k b{display:block;font-size:1.35rem;line-height:1.2}
.k span{font-size:.76rem;color:var(--muted)}
blockquote{margin:1rem 0;padding:.1rem 0 .1rem 1rem;border-left:3px solid var(--line);
color:var(--muted);font-size:.92rem}
footer{margin-top:3rem;padding-top:1.2rem;border-top:1px solid var(--line);
font-size:.83rem;color:var(--muted)}"""


def render_index(version, prev_versions):
    """Build index.html from the artefacts, so it cannot say something else."""
    import rdflib
    from rdflib import RDF, RDFS, OWL, URIRef
    from rdflib.namespace import DCTERMS
    CENSO = rdflib.Namespace("https://w3id.org/censo/")

    voc = rdflib.Graph()
    for f in ("censo-core.ttl", "censo-regulation.ttl"):
        voc.parse(ONTO / f, format="turtle")
    n_cls = len({s for s in voc.subjects(RDF.type, OWL.Class)
                 if isinstance(s, URIRef)})
    n_prop = len({s for t in (OWL.ObjectProperty, OWL.DatatypeProperty)
                  for s in voc.subjects(RDF.type, t) if isinstance(s, URIRef)})

    pkgs = []
    for f in sorted((ONTO / "reg").glob("*.ttl")):
        g = rdflib.Graph()
        g.parse(f, format="turtle")
        title = next((str(o) for o in g.objects(None, DCTERMS.title)), f.stem)
        pkgs.append((f.stem, title,
                     len(list(g.subject_objects(CENSO.thresholdValue)))))
    n_thr = sum(n for _, _, n in pkgs)

    align = ONTO / "censo-alignment.ttl"
    n_align = 0
    if align.exists():
        ag = rdflib.Graph()
        ag.parse(align, format="turtle")
        n_align = (len(list(ag.triples((None, OWL.sameAs, None))))
                   + len([1 for _, _, o in ag.triples((None, RDFS.seeAlso, None))
                          if "CHEBI" in str(o)]))

    rows = [("https://w3id.org/censo/",
             "the vocabulary &mdash; Turtle, RDF/XML or JSON-LD by content "
             "negotiation"),
            ("https://w3id.org/censo/" + version, "this release specifically")]
    for v in prev_versions:
        rows.append(("https://w3id.org/censo/" + v,
                     "the " + v + " release, unchanged since it was published"))
    rows.append(("https://w3id.org/censo/reg/",
                 "the regulation-package vocabulary"))
    for stem, title, n in pkgs:
        rows.append(("https://w3id.org/censo/reg/" + stem,
                     title + " &mdash; " + str(n) + " thresholds"))
    rows.append(("https://w3id.org/censo/shapes",
                 "SHACL shapes for validation and materialisation"))
    if n_align:
        rows.append(("https://w3id.org/censo/alignment",
                     "pointers to ChEBI and CHMO &mdash; imported by nothing, "
                     "so take it only if you want it"))

    files = [("censo-full.ttl", "Turtle"), ("censo-full.owl", "RDF/XML"),
             ("censo-full.jsonld", "JSON-LD"),
             ("censo-regulation.ttl", "regulation vocabulary"),
             ("censo-shapes.ttl", "SHACL")]
    if n_align:
        files.append(("censo-alignment.ttl", "external alignment"))
    files += [("reg/" + stem + ".ttl", title) for stem, title, _ in pkgs]

    H = []
    A = H.append
    A('<!doctype html>')
    A('<html lang="en"><head><meta charset="utf-8">')
    A('<meta name="viewport" content="width=device-width,initial-scale=1">')
    A('<title>CENSO &mdash; an ontology for censored environmental '
      'observations</title>')
    A("<style>")
    A(CSS)
    A("</style></head><body><main>")
    A("")
    A("<h1>CENSO</h1>")
    A('<p class="lede">An ontology for censored environmental observations '
      '&middot; version ' + version + "</p>")
    A('<p class="iri">https://w3id.org/censo/</p>')
    A("")
    A('<div class="k">')
    for val, lab in ((n_cls, "classes"), (n_prop, "properties"),
                     (n_thr, "thresholds"), (len(pkgs), "jurisdictions")):
        A("<div><b>" + str(val) + "</b><span>" + lab + "</span></div>")
    A("</div>")
    A("")
    A("<h2>What it is</h2>")
    A("<p>CENSO extends SOSA/SSN for measurements produced by a method that "
      "has a limit of detection. Its modelling commitment is that the limit is "
      "<em>carried onto the result</em>. SSN-System binds a detection limit to "
      "a <em>sensor</em>; CHMO, the closest prior art, binds it to the "
      "<em>method</em>, as a figure of merit of an assay. Neither can say that "
      "a particular measurement fell below it &mdash; and "
      "&ldquo;censored&rdquo; is a property of a result, not of the procedure "
      "that produced it.</p>")
    A("<p>Because the limit reaches the result, a non-detection is typed as "
      "the interval [0,&nbsp;LOQ] it actually establishes rather than stored "
      "as a zero, and compliance is <strong>three-valued</strong>: compliant, "
      "exceeding, or not determinable &mdash; with the third subtyped by the "
      "<em>reason</em> it could not be decided.</p>")
    A("<p>The third outcome is not a convenience:</p>")
    A("<blockquote>Where a result is referred to as &ldquo;less than limit of "
      "quantification&rdquo;, and the limit of quantification of that "
      "technique is above the EQS, the result for the substance being measured "
      "shall not be considered for the purposes of assessing the overall "
      "chemical status of that water body.<br>&mdash; Directive 2008/105/EC, "
      "Article 3(3b)</blockquote>")
    A("<p>That outcome is neither compliant nor exceeding. A two-valued data "
      "model cannot express it, so compliance with the provision cannot be "
      "audited.</p>")
    A("")
    A("<h2>Resolvable IRIs</h2>")
    A("<table><tr><th>IRI</th><th>Resolves to</th></tr>")
    for iri, what in rows:
        A('<tr><td class="iri">' + iri + "</td><td>" + what + "</td></tr>")
    A("</table>")
    A("<p>Regulation packages contribute individuals only &mdash; no class, "
      "no property &mdash; which is what makes one safe to load in place of, "
      "or alongside, another.</p>")
    A("")
    A("<h2>Files</h2>")
    A("<table><tr><th>File</th><th>Format</th></tr>")
    for f, kind in files:
        A("<tr><td><code>" + f + "</code></td><td>" + kind + "</td></tr>")
    A("</table>")
    A("")
    A("<h2>Reuse</h2>")
    A("<p>CC&nbsp;BY&nbsp;4.0. Built on SOSA/SSN, PROV-O, SKOS and QUDT, and "
      "aligned outward rather than renamed: " + str(n_align) + " pointers into "
      "ChEBI and CHMO ship in <code>censo-alignment.ttl</code>, which nothing "
      "imports, so a consumer who does not want those commitments need not "
      "take them.</p>")
    A("")
    A("<footer>Generated by <code>scripts/97_assemble_publish.py</code> from "
      "the published artefacts &mdash; every count on this page is read from "
      "the files it describes, because a front door that contradicts the "
      "vocabulary behind it is worse than no front door.</footer>")
    A("</main></body></html>")
    return "\n".join(H) + "\n"


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
    prev = sorted(d.name for d in (SITE / "releases").glob("*")
                  if d.is_dir() and d.name != version)
    (SITE / "index.html").write_text(render_index(version, prev),
                                     encoding="utf-8")
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
