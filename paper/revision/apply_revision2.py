#!/usr/bin/env python3
"""Apply revision 2 to the manuscript, one item at a time, and report each.

USAGE
    python apply_revision2.py main.tex            # writes main.tex, keeps a .bak
    python apply_revision2.py main.tex --dry-run  # report only, change nothing

Every item is an exact (find, replace) pair. An item whose anchor is not found,
or found more than once, is REPORTED AND SKIPPED rather than guessed at -- so
the output is a checklist you can read against the revision list, and nothing is
edited silently.

Items marked MEASURED carry a number computed from the pipeline; the value and
the script that produced it are named in the comment above each one.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# (id, note, find, replace).  replace == "" deletes.
EDITS = [

# ---------------------------------------------------------------- compile ---
("R1", "the \\pending macro was removed; this was its last use",
 r"Archived at \pending{Zenodo DOI} \\",
 r"Archived at \url{https://doi.org/10.5281/zenodo.XXXXXXX} \\"),

("R2a", "seqsplit is used below and was never loaded",
 r"\usepackage[htt]{hyphenat}",
 "\\usepackage[htt]{hyphenat}\n\\usepackage{seqsplit}"),

# MEASURED: sha256sum of Data/waterbase/WISE6_AggregatedData-csv.zip
("R2b", "the full 64-character digest, not an abbreviation",
 r"SHA-256 \seqsplit{315396800d76e46d...}",
 r"SHA-256 \seqsplit{315396800d76e46db415164851fb4f99765b7ec2654828fc42782d902e679a7a}"),

# ------------------------------------------------- the unit of assessment ---
# MEASURED by scripts/22_waterbase_external.py:
#   assessed rows                              696,168
#   distinct station-substance-year keys        689,266
#   rows beyond one per key                       6,902  (0.99 %)
#   undecidable share, per row                   43.788 %
#   same share under ANY one-row-per-key rule    43.2 - 44.2 %  (<= 0.56 points)
#
# The pipeline assesses EVERY PUBLISHED ROW. It does not combine, does not
# drop, and does not keep one verdict of two. All three options offered in the
# revision list would therefore have the paper misstate its own method, and the
# companion item R3 -- declaring the station-substance-year the unit of
# assessment -- would do the same. The row is the unit; what the alternative
# would cost is bounded instead, which needs no rule to be chosen.
("R4", "what is actually done with the 20,828 duplicated rows",
 "the remaining\n\\num{20828} rows (\\num{0.5}\\,\\%) are years reported as two sampling periods. We refer to a station--substance--year combination as a station-year throughout.",
 "the remaining\n"
 "\\num{20828} rows (\\num{0.5}\\,\\%) are years reported as two sampling periods.\n"
 "\\textbf{Both rows are assessed, and the unit of every count in this paper is\n"
 "therefore the published row rather than the station-year.} Each row is a\n"
 "\\emph{published} annual mean with its own \\texttt{procedureLOQValue} and its own\n"
 "below-quantification flag; the two may have been produced by different methods\n"
 "with different limits, and the release states no rule for combining them, so\n"
 "choosing one would invent the datum the record withholds. Of the \\num{696168}\n"
 "rows a European annual-average standard reaches, \\num{689266} carry a distinct\n"
 "station--substance--year and \\num{6902} --- \\num{0.99}\\,\\% --- are a second or\n"
 "later row for a key already seen. What the choice can cost is bounded without\n"
 "making it: removing every duplicate row moves the undecidable share of\n"
 "Section~\\ref{sec:results} from \\num{43.8}\\,\\% to between \\num{43.2} and\n"
 "\\num{44.2}\\,\\% --- at most \\num{0.56} percentage points --- whichever of the\n"
 "two rows a deduplicating rule were to keep."),

# ------------------------------------------------------ open / closed world --
("R5a", "remove the paragraph from Decision procedure, where it has no antecedent",
 "The two assumptions apply to different questions. \n"
 "Whether the water body complies is an open-world question and CENSO never closes it: a censored result entails only $[0,\\mathrm{LOQ}]$. \n"
 "Whether the \\emph{record} contains the information needed to decide is a closed-world question about a document, and is exactly what SHACL is designed to\n"
 "ask. \n"
 "\\texttt{IndeterminateCompliance} is therefore an assertion about the record, not about the river, which is why it can be derived under a closed-world view without committing to a closed world about concentrations.",
 ""),

("R5b", "put it where 'closed-world' has just been said",
 "Indeterminate outcomes are added by SHACL rules under a closed-world view.",
 "Indeterminate outcomes are added by SHACL rules under a closed-world view.\n"
 "The two assumptions apply to different questions.\n"
 "Whether the water body complies is an open-world question and CENSO never closes\n"
 "it: a censored result entails only $[0,\\mathrm{LOQ}]$.\n"
 "Whether the \\emph{record} contains the information needed to decide is a\n"
 "closed-world question about a document, and is exactly what SHACL is designed to\n"
 "ask.\n"
 "\\texttt{IndeterminateCompliance} is therefore an assertion about the record, not\n"
 "about the river, which is why it can be derived under a closed-world view without\n"
 "committing to a closed world about concentrations."),

# ------------------------------------------------------------ MAC coverage ---
("R6", "the coverage caveat the MAC results depend on",
 "(interquartile range \\num{4}--\\num{12}; mean \\num{6.6}, strongly right-skewed).",
 "(interquartile range \\num{4}--\\num{12}; mean \\num{6.6}, strongly right-skewed).\n"
 "All maximum-allowable-concentration results in Section~\\ref{sec:results} therefore\n"
 "refer to that covered subset and are reported separately from the annual-mean\n"
 "results."),

# MEASURED by scripts/27_mac_exceedance.py: 16,988 of 66,285 = 25.6 %, and the
# disagreement runs in both directions (698 station-years are compliant on the
# mean while a sample behind it breaches the maximum allowable concentration).
("R7", "the both-directions finding, which is the point of the section",
 "For \\num{25.6}\\,\\% of the station-years assessable under both standards, the two standards give different verdicts.\n"
 "A single threshold value in a table cannot store both answers.",
 "For \\num{25.6}\\,\\% of the station-years assessable under both standards, the two\n"
 "standards give different verdicts, and they disagree in both directions: neither is\n"
 "a stricter reading of the other.\n"
 "A single threshold value in a table cannot store both answers."),

# ---------------------------------------------------------------- abstract ---
("R8a", "CHMO binds the limit to the method, not to a sampling device",
 "In existing vocabularies, a reporting limit is a fixed property of the sampling device.\n"
 "Micropollutant monitoring works the other way round: a sample is analysed in a laboratory run with its own calibration, so the limit belongs to that run and changes with it.",
 "In existing vocabularies, a reporting limit belongs to the sensor or to the method, never to the result; but a sample is analysed in a laboratory run with its own calibration, so the limit belongs to that run and changes with it."),

("R8b", "shorten, and keep every number matched to its own set",
 "The new standards of Directive~(EU) 2026/805 fall mostly in this critical range: \\num{33}\\,\\% of the added substances have a standard below \\num{e-3}~\\si{\\micro\\gram\\per\\litre}, against \\num{20}\\,\\% on the earlier list.\n"
 "In this range, \\num{85.9}\\,\\% of assessments since \\num{2020} cannot be decided (\\num{85.0}\\,\\% over the whole record), and the quantification limit alone explains \\num{83} to \\num{100}\\,\\% of them.",
 "A third of the substances added by Directive~(EU) 2026/805 have a standard below \\num{e-3}~\\si{\\micro\\gram\\per\\litre}, against a fifth on the earlier list --- a range in which \\num{85.9}\\,\\% of assessments since \\num{2020} cannot be decided, and where the quantification limit alone explains \\num{83} to \\num{100}\\,\\% of them."),

# ---------------------------------------------------------------- headings ---
("R9", "the Kaplan-Meier paragraph answers a different question than its heading",
 "Robust estimators for left-censored data --- Kaplan--Meier,",
 "\\subsection{Why robust statistics do not remove the need}\n"
 "Robust estimators for left-censored data --- Kaplan--Meier,"),

("R10", "missing word",
 "Article~3(3b) share is therefore an upper bound",
 "Our Article~3(3b) share is therefore an upper bound"),

("R13", "Elsevier requires a funding statement",
 r"\section*{Declaration of competing interest}",
 "\\section*{Funding}\n"
 "This research did not receive any specific grant from funding agencies in the\n"
 "public, commercial, or not-for-profit sectors.\n\n"
 "\\section*{Declaration of competing interest}"),

# MEASURED: the published graph is 40,000 observations; the 6.5 % is over the
# 696,168-row full record. Two denominators, which is the whole of the conflict.
("R14", "4,646 and 6.5 % are over different denominators",
 "The published SHACL shapes, applied to the published graph, report only one type of violation: \\num{4646} observations that cite no analytical method.\n"
 "These are exactly the records without a reported limit, so the violation reflects the data, not the ontology.",
 "The published SHACL shapes, applied to the published graph of \\num{40000}\n"
 "observations (Section~\\ref{sec:methods-impl}), report only one type of violation:\n"
 "\\num{4646} observations that cite no analytical method. All of these are records\n"
 "without a reported limit, so the violation reflects the data, not the ontology;\n"
 "over the full record the same condition holds for \\num{6.5}\\,\\% of assessments."),

# MEASURED: zero-substitution reported exceedances 59,251; CENSO without a band
# 16,963; difference 42,288 = 30,140 precondition + 12,148 (12,142 no bound +
# 6 self-contradictory). The decomposition closes exactly.
("R15", "why the most conservative substitution still over-reports",
 "the count ranges from \\num{59251} to \\num{200708}.",
 "the count ranges from \\num{59251} to \\num{200708}.\n"
 "The difference between the \\num{59251} exceedances reported under zero substitution\n"
 "and the \\num{16963} CENSO confirms without an uncertainty band is accounted for\n"
 "entirely by assessments CENSO sets aside: \\num{30140} comparisons against a\n"
 "standard defined for a quantity that was not measured, and \\num{12148} whose bound\n"
 "could not be established. Not one is set aside by Article~3(3b), because zero never\n"
 "lifts a censored result past the standard."),

("R16", "own the antecedent of three-valued conformity",
 "Instead, CENSO stays within OWL~2~RL \\citep{w3c2012owl2profiles}",
 "Ternary conformity decisions are themselves not new: JCGM~106 and the\n"
 "Eurachem/CITAC guide already define an inconclusive zone around a specification\n"
 "limit \\citep{jcgm2012conformity,eurachem2021compliance}. What is new here is not\n"
 "the logic but its residence. In conformity assessment the inconclusive verdict is\n"
 "produced by a decision rule at analysis time and then discarded; in a monitoring\n"
 "archive it must survive as a first-class, queryable property of the record,\n"
 "together with the reason that produced it. No published vocabulary provides that\n"
 "residence.\n"
 "Instead, CENSO stays within OWL~2~RL \\citep{w3c2012owl2profiles}"),

("R17", "three forward directions",
 "which none of the \\num{21} existing vocabulary files can express.",
 "which none of the \\num{21} existing vocabulary files can express.\n"
 "Three directions follow. First, the set-aside rule of Article~3(3b) turns on the\n"
 "limit achievable by the best available technique, for which no Union-wide register\n"
 "exists; building one would convert our upper bound into an exact figure. Second,\n"
 "the same representation applies wherever a reporting limit meets a legal threshold,\n"
 "and biota, groundwater, air and food are immediate candidates. Third, because\n"
 "regulation packages are data rather than schema, a reporting authority could attach\n"
 "CENSO to an existing WISE submission pipeline and obtain, at reporting time rather\n"
 "than years later, the list of assessments its own data cannot support."),

# --------------------------------------------------- new subsections (R11/R12) ---
# MEASURED for R12, from the last full pipeline run:
#   published graph            40,000 observations
#   triples                    501,110 asserted / 507,697 with the modules
#                              loaded / 651,373 after SHACL materialisation
#   ABox construction          177 s
#   SHACL materialise+validate 5,826 s  (= 97 min)   <-- NOT seconds
#   competency questions       1,443 s
#   peak resident memory       1.5 GB
#
# The revision list asked for "XX s". The honest figure is 97 minutes, and a
# software journal is exactly where that cannot be rounded into seconds. The
# cost is super-linear in pure Python, which the manuscript already states as a
# limitation, so the sentence says so rather than hiding it.
("R12", "implementation and performance -- the software contribution EMS looks for",
 r"\section{Results}",
 "\\subsection{Implementation and performance}\n"
 "\\label{sec:methods-impl}\n"
 "The pipeline is a Python package with four stages: a loader that maps Waterbase\n"
 "columns to CENSO terms and emits RDF; an OWL~2~RL materialisation step\n"
 "(\\texttt{owlrl}); a SHACL stage (\\texttt{pyshacl}) that adds the indeterminate\n"
 "outcomes and validates the graph; and a SPARQL reporting stage that produces every\n"
 "table and figure in this article. There is no JVM, no triple store and no external\n"
 "reasoner, so the whole chain runs from a single \\texttt{pip install}.\n"
 "The published graph holds \\num{40000} observations and \\num{501110} asserted\n"
 "triples, rising to \\num{651373} once the rule layer has run. Materialisation and\n"
 "validation of that graph complete in \\num{97}~min in \\num{1.5}~GB of memory, and\n"
 "the assessment of all \\num{696168} rows a European standard reaches --- which\n"
 "needs no graph, being arithmetic on four reported fields --- completes in under\n"
 "\\num{20}~min. The reasoning cost is super-linear in the number of observations\n"
 "(Section~\\ref{sec:results}), which is why the graph is a queryable subset and not\n"
 "the assessment itself, and why a deployment over a whole basin would use a store\n"
 "with native rule support.\n"
 "Reusing CENSO for another monitoring programme requires three steps and no change\n"
 "to the schema: map the source columns to \\texttt{censo:Observation},\n"
 "\\texttt{censo:resultUpperBound} and the detection status; write the thresholds as\n"
 "a regulation package; and run the same pipeline.\n\n"
 "\\section{Results}"),

# MEASURED for R11: 23 files are parsed, 21 external plus the two of this work.
# The parser is rdflib, not owlready2. The scoring rule is that a concept must
# appear in a term's IRI local name or its rdfs:label; appearing only in an
# rdfs:comment does not count -- without that rule ENVO scores four concepts it
# does not model, one of them from a plant-biology class called
# "indeterminate root nodule". Two fields are left for you: where the files were
# searched for, and whether a second coder repeated the coding.
("R11", "the comparison protocol, without which Table 1 cannot be accepted",
 r"\subsection{Decision procedure}",
 "\\subsection{Ontology comparison protocol}\n"
 "\\label{sec:methods-comparison}\n"
 "We searched <SEARCH SOURCES: e.g. LOV, BioPortal, the OBO Foundry, and the review\n"
 "of \\citet{tiwari2022systematic}> for vocabularies describing environmental\n"
 "measurement, water quality, laboratory analysis or regulatory thresholds, and\n"
 "retained those available as a parseable OWL or RDFS file under an open licence.\n"
 "This yields \\num{21} files, assessed alongside the two modules of this work; the\n"
 "release analysed for each is listed in the archived comparison table. Every file\n"
 "was parsed with \\texttt{rdflib} and each declared class, object property and\n"
 "datatype property extracted, giving the entity count. A vocabulary is scored as\n"
 "expressing a criterion only if a declared term carries that meaning in its IRI\n"
 "local name or its \\texttt{rdfs:label}; a concept appearing only in a comment or a\n"
 "definition does not count, because on a large vocabulary it otherwise does --- ENVO\n"
 "scores four criteria that way, one of them from a plant-biology class named\n"
 "\\emph{indeterminate root nodule}. Where a pattern admitted a term that plainly\n"
 "means something else it was narrowed and the narrowing recorded; where a borderline\n"
 "term could be read either way it was scored in the other vocabulary's favour.\n"
 "<CODING: state whether one author coded, or a second repeated it independently.>\n"
 "The extraction script and the per-term evidence for every cell of\n"
 "Table~\\ref{tab:field-gap} are published with the article.\n\n"
 "\\subsection{Decision procedure}"),

# ------------------------------------------------------------------ small ---
("R18a1", "sentence begins with a numeral",
 "\\num{56.4}\\,\\% of station--substance pairs measured",
 "Across the record, \\num{56.4}\\,\\% of station--substance pairs measured"),

("R18a2", "sentence begins with a numeral",
 "\\num{43.8}\\,\\% of the \\num{696168} assessments against a European standard cannot be determined",
 "Of the \\num{696168} assessments against a European standard, \\num{43.8}\\,\\% cannot be determined"),

("R18a3", "sentence begins with a numeral",
 "\\num{33}\\,\\% of the added substances have a standard below",
 "Of the added substances, \\num{33}\\,\\% have a standard below"),

("R18b", "name CHMO where the gap is first asserted",
 "The same gap appears in an analytical chemistry ontology with no sensor concept at all.",
 "The same gap appears in CHMO, an analytical chemistry ontology with no sensor concept at all (Section~\\ref{sec:related-lab})."),

("R18b2", "the label R18b refers to",
 r"\subsection{Laboratory and analytical vocabularies}",
 "\\subsection{Laboratory and analytical vocabularies}\n\\label{sec:related-lab}"),

("R18c", "cite the article that imposes half-limit substitution",
 "Directive 2009/90/EC requires results below the quantification limit to be set to half the limit",
 "Article~5(1)--(2) of Directive 2009/90/EC requires results below the quantification limit to be set to half the limit"),

("R18d", "'only 27 %' undercuts itself",
 "The choice of band only changes the number of confirmed exceedances, by up to \\num{27}\\,\\%.",
 "The choice of band changes the number of confirmed exceedances by up to \\num{27}\\,\\%, but leaves the undecidable share within \\num{1}~percentage point."),

("R18e", "the table is a sensitivity analysis, and its caption should say so",
 r"\caption{The three readings of Article~4(1) over every assessable station-year.}",
 r"\caption{Sensitivity of the assessment to the uncertainty band derived from Article~4(1) of Directive 2009/90/EC, over every assessable station-year.}"),

("R18f", "leading space in a caption",
 r"\caption{ What \num{21} published vocabulary files",
 r"\caption{What \num{21} published vocabulary files"),

("R18g", "the aggregated release reports annual means, not samples",
 "In Waterbase, almost half of all samples are below the limit of quantification",
 "In Waterbase, almost half of all reported annual means are below the limit of quantification"),

("R18h", "a bare numeral outside \\num (occurs twice)",
 "\\num{21} existing vocabulary files from 15 projects",
 "\\num{21} existing vocabulary files from \\num{15} projects",
 True),   # allow more than one occurrence

("R18i", "Elsevier accepts at most six keywords",
 "ontology \\sep OWL 2 \\sep SOSA/SSN \\sep limit of quantification \\sep\n"
 "environmental quality standards \\sep compliance assessment \\sep\n"
 "Water Framework Directive \\sep open world assumption",
 "ontology \\sep SOSA/SSN \\sep limit of quantification \\sep\n"
 "environmental quality standards \\sep compliance assessment \\sep\n"
 "Water Framework Directive"),

("R18j", "Elsevier section name",
 r"\section{Method}",
 r"\section{Materials and methods}"),
]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    dry = "--dry-run" in sys.argv
    if not path.exists():
        print(f"! {path} not found")
        return 2
    src = path.read_text(encoding="utf-8")

    applied, skipped = [], []
    for item in EDITS:
        eid, note, find, repl = item[0], item[1], item[2], item[3]
        many = len(item) > 4 and item[4]
        n = src.count(find)
        if n == 0:
            skipped.append((eid, note, "anchor not found"))
            continue
        if n > 1 and not many:
            skipped.append((eid, note, f"anchor occurs {n} times; not unique"))
            continue
        src = src.replace(find, repl)
        applied.append((eid, note, f"{n} occurrence(s)"))

    w = max(len(e) for e, _, _ in applied + skipped) if (applied or skipped) else 6
    print(f"\n  APPLIED ({len(applied)})")
    for eid, note, detail in applied:
        print(f"    {eid:<{w}}  {note}  [{detail}]")
    if skipped:
        print(f"\n  SKIPPED ({len(skipped)}) -- these need your eye")
        for eid, note, why in skipped:
            print(f"    {eid:<{w}}  {note}")
            print(f"    {'':<{w}}  -> {why}")

    if dry:
        print("\n  --dry-run: nothing written")
        return 0
    bak = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, bak)
    path.write_text(src, encoding="utf-8")
    print(f"\n  wrote {path}  (previous version kept as {bak.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
