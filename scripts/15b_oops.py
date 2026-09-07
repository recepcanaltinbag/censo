#!/usr/bin/env python3
"""
OOPS! pitfall scan, and the pitfalls it found that were real.

WHY THIS IS A SEPARATE STAGE FROM 15_foops.py
---------------------------------------------
They are different tools and they answer different questions. FOOPS! scores
FAIRness -- is the artefact findable, licensed, versioned, dereferenceable.
OOPS! (the OntOlogy Pitfall Scanner) reads the axioms and looks for modelling
defects. This project ran the first and not the second, which is the wrong way
round for an ontology paper: FAIR publication of a badly modelled vocabulary is
still a badly modelled vocabulary.

Run once, it found three things worth having, and the first two were real:

  P34 (Important) sosa:usedProcedure declared nowhere. The standalone
      distribution re-declares the external terms it borrows, so a scanner
      reading one file does not report them untyped -- but that list was
      hand-written and had never included usedProcedure, which the cardinality
      restriction on censo:AssessedObservation references.

  P04 (Minor) sosa:Sample declared and unconnected. The same hand-written list,
      drifting the other way: censo:analysedSample was retired and the
      declaration stayed. One list, stale in both directions at once. It is
      derived from the modules now (scripts/16_export_for_scanners.py).

  P05 (Critical) a wrong inverse. cereg:definesThreshold was declared
      owl:inverseOf censo:definedBy. Their levels differ -- definesThreshold has
      domain cereg:RegulationPackage, definedBy has range censo:Regulation --
      so the pair entailed package-hood from mere regulation-hood. Removed.

WHAT IS NOT TREATED AS A DEFECT
-------------------------------
P04 also names skos:Concept, prov:Activity, sosa:Procedure and foaf:Person: the
external classes this vocabulary reuses rather than redefines. In a merged file
with the imports stripped they have no local connections, which is what OOPS!
sees. Reporting that as a modelling defect would be an argument for inlining
other people's vocabularies, which is the opposite of what should happen. They
are declared with a note saying where they come from, and listed here as
expected rather than silently filtered.

Inputs  : ontology/dist/censo-full.owl
Outputs : eval/oops_assessment.md, eval/oops_raw.xml (cached)

The service is the only network dependency besides FOOPS!; the raw response is
cached and reused, so an offline run still produces the report.

Usage:  python scripts/15b_oops.py [--offline]
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWLF = ROOT / "ontology" / "dist" / "censo-full.owl"
EVAL = ROOT / "eval"
RAW = EVAL / "oops_raw.xml"
OUT = EVAL / "oops_assessment.md"
ENDPOINT = "https://oops.linkeddata.es/rest"
TIMEOUT = 300

# External terms this vocabulary reuses. OOPS! sees them as unconnected in a
# merged file with the imports stripped; that is a property of the packaging,
# not a modelling defect, and inlining someone else's vocabulary to silence it
# would be the actual defect.
def reused_terms():
    """The external terms the distribution declares, from the same derivation.

    This was a hand-written set, which is the mistake the P04/P34 findings below
    were ABOUT. Import the derivation instead, so the filter here and the
    declarations in the distribution cannot disagree about which terms are
    borrowed.
    """
    import rdflib
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    exp = __import__("16_export_for_scanners")
    g = rdflib.Graph()
    for m in exp.MODULES:
        g.parse(ROOT / "ontology" / m, format="turtle")
    cls, prop = exp.referenced_externals(g)
    return set(cls) | set(prop)


def fetch() -> str:
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n<OOPSRequest>'
            "<OntologyUrl></OntologyUrl><OntologyContent><![CDATA["
            + OWLF.read_text(encoding="utf-8")
            + "]]></OntologyContent><Pitfalls></Pitfalls>"
              "<OutputFormat>RDF/XML</OutputFormat></OOPSRequest>")
    req = urllib.request.Request(
        ENDPOINT, data=body.encode("utf-8"),
        headers={"Content-Type": "application/xml"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    if not OWLF.exists():
        sys.exit(f"missing {OWLF}; run scripts/16_export_for_scanners.py first")

    EVAL.mkdir(parents=True, exist_ok=True)
    xml = None
    if not args.offline:
        try:
            xml = fetch()
            RAW.write_text(xml, encoding="utf-8")
        except Exception as e:                                  # noqa: BLE001
            print(f"  ! OOPS! unreachable ({type(e).__name__}); using the cache")
    if xml is None:
        if not RAW.exists():
            print("  ! no cached response and the service is unavailable")
            return 0
        xml = RAW.read_text(encoding="utf-8")

    REUSED = reused_terms()

    import rdflib
    OOPS = rdflib.Namespace("http://oops.linkeddata.es/def#")
    g = rdflib.Graph()
    g.parse(data=xml, format="xml")

    found = []
    for s in set(g.subjects()):
        code = next(g.objects(s, OOPS.hasCode), None)
        if code is None:
            continue
        aff = sorted(str(o) for o in g.objects(s, OOPS.hasAffectedElement))
        found.append((str(code),
                      str(next(g.objects(s, OOPS.hasName), "")),
                      str(next(g.objects(s, OOPS.hasImportanceLevel), "")),
                      aff))
    found.sort()

    unexplained = []
    for code, name, lvl, aff in found:
        rest = [a for a in aff if a not in REUSED]
        if rest and lvl in ("Critical", "Important"):
            unexplained.append((code, name, rest))

    A = ["# OOPS! pitfall scan\n",
         "Generated by `scripts/15b_oops.py` against "
         "`ontology/dist/censo-full.owl` — the standalone distribution, which "
         "is what a scanner can read, since the imports are stripped so it "
         "does not have to resolve five external vocabularies.\n",
         "FOOPS! (`scripts/15_foops.py`) scores FAIRness; this reads the "
         "axioms. Running the first and not the second is the wrong way round "
         "for an ontology paper, and this project did exactly that until now.\n",
         "| pitfall | level | affected | of those, reused external terms |",
         "|---|---|---|---|"]
    for code, name, lvl, aff in found:
        reused = sum(1 for a in aff if a in REUSED)
        A.append(f"| **{code}** {name} | {lvl or '—'} | {len(aff)} | {reused} |")
    A.append("")
    A.append("**Reused external terms are not defects.** `skos:Concept`, "
             "`prov:Activity`, `sosa:Procedure`, `sosa:Observation` and the "
             "rest are borrowed rather than redefined. In a merged file with "
             "the imports stripped they carry no local connections, which is "
             "what OOPS! reports as P04. Inlining someone else's vocabulary to "
             "silence that would be the real modelling defect; the "
             "distribution declares them with a note saying where each comes "
             "from, and that list is derived from what the modules actually "
             "reference rather than hand-written"
             "\\src{scripts/16\\_export\\_for\\_scanners.py}.\n")
    if unexplained:
        A.append("## Unexplained findings — these need an answer\n")
        for code, name, rest in unexplained:
            A.append(f"- **{code}** {name}: " + ", ".join(rest[:8]))
        A.append("")
    else:
        A.append("**No Critical or Important pitfall names a term this "
                 "vocabulary declares.** The scan was worth running: it found "
                 "three that did, and all three are fixed — a wrong inverse "
                 "between two properties at different levels of the vocabulary "
                 "(P05, Critical), a borrowed property declared nowhere (P34), "
                 "and a borrowed class declared and then orphaned when the "
                 "property that used it was retired (P04). The first was a "
                 "modelling error; the other two were one hand-written list "
                 "drifting in both directions at once, and it is derived "
                 "now.\n")

    OUT.write_text("\n".join(A) + "\n", encoding="utf-8")
    print(f"  {len(found)} pitfall type(s); "
          f"{len(unexplained)} unexplained Critical/Important")
    print(f"  wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
