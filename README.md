# CENSO — an ontology for censored environmental measurements

Working repository for the paper *"Not detected is not absent: an ontology for
reporting limits and undecidable compliance in micropollutant monitoring."*

The ontology is published at **<https://w3id.org/censo/>** (CC BY 4.0); the
code here is MIT.

---

## The claim, in one sentence

> A non-detection is an **upper bound** and an **open-world** statement, stored
> in **closed-world** systems. Recording it as `0` is not a rounding convention
> but a type error: what is destroyed is the *modality*, not the magnitude.
> CENSO carries the quantification limit onto the **result** rather than leaving it on
> the instrument, which makes *"I cannot decide"* a first-class, queryable
> outcome — one that EU law already requires and that no two-valued schema can
> express.

## What the record shows

Audited over the EEA Waterbase aggregated release — 4,190,833 river
station-years, 637 substances, 37 reporting countries. **48.8 % of the record
is dated 2015 or later**, so the audit is split at that boundary rather than
treated as one era:

| | |
|---|---|
| samples below the quantification limit | **44.9 %** |
| station-years with neither a censoring flag nor a limit | **25.5 %** |
| — before 2015 → 2015 onwards | **49.7 %** → **0.0 %** |
| assessments made with a method failing the legal LOQ criterion | **40.1 %** |
| below-quantification assessments whose limit exceeds the standard | **17.5 %** |
| station-years reporting below the limit *and* a positive value for it | **55.0 %** |
| exceedances a substituting pipeline reports, depending only on the rule | **59,251 – 200,708** |
| of those, created by the half-LOQ substitution alone | **112,034** |
| exceedances the law can affirm | **14,505** |
| assessments where a precondition of the standard is unmet | **18.8 %** |
| co-regulated verdicts that change when the regulation package is swapped | **17.7 %** |
| individual samples undecidable against the maximum-allowable standard | **9.7 %** |

The record-keeping failure is solved; the analytical failure is not, and
substitution at source has not moved.

Every one of these is recomputed from source by `scripts/99_audit.py`, which
fails if any claim in the manuscript cannot be reproduced — and, since these
same values were left stale here for a whole correction cycle, the audit now
checks this table too.

---

## Reproducing it

```bash
# 0. two non-Python prerequisites, both checked by step 1 below
#    poppler-utils  -> pdftotext, REQUIRED: Annex I is read by column position
#                      from `pdftotext -layout`, and stage 1 exits rather than
#                      fall back to flattened text, which cannot tell an empty
#                      cell from a missing one
#    p7zip-full     -> 7z, needed only for the disaggregated release, which is
#                      a Deflate64 archive Python's zipfile cannot open
sudo apt install poppler-utils p7zip-full        # Debian/Ubuntu

# 1. can this machine do it?  (fails loudly if either is absent)
python scripts/01_check_environment.py

# 2. get the data (not redistributed here — 165 MB, no registration needed)
#    https://www.eea.europa.eu/en/datahub/datahubitem-view/fbf3717c-cd7b-4785-933a-d0cf510542e1
#    put these in Data/waterbase/ :
#      WISE6_AggregatedData-csv.zip              162 MB  the measurements
#      WISE6_SpatialObjects_DerivedData-csv.zip    3 MB  station coordinates
#      WISE6_DisaggregatedData-csv.zip           1.6 GB  optional, see below
#    Without the second, stations carry no geometry: the map figure is empty
#    and one competency question returns nothing. The third is needed only for
#    the maximum-allowable standard, which is defined against an individual
#    sample and cannot be evaluated on annual means; without it stage 9 skips
#    itself with a message and the rest of the chain is unaffected. It is a
#    Deflate64 archive, which Python's zipfile cannot open — the pipeline falls
#    back to 7z or bsdtar.

# 3. rebuild everything, in dependency order
python scripts/00_run_all.py --waterbase Data/waterbase/WISE6_AggregatedData-csv.zip
```

The last stage is the audit. A run ending in `0 failed` means the text, the
figures, the per-figure data and the supplementary tables all agree with the
source data.

**Always run the whole chain, never one script.** Partial regeneration has
corrupted the manuscript more than once — a figure quoting 19.3 % while the
corrected regulation packages gave 18.1 %; figures older than the table behind
them; a bar chart drawing three of the four outcomes the caption named. Each script was individually correct; only the order was wrong. That is
what `00_run_all.py` and the staleness checks exist to prevent.

```bash
python scripts/00_run_all.py --list          # every stage and what it needs
python scripts/00_run_all.py --from 90       # resume partway
```

## Layout

```
ontology/     censo-core, censo-regulation, censo-shapes,
              censo-alignment (ChEBI + CHMO), reg/{eu,tr}   ← the artefact
queries/      20 competency questions, each tied to an axiom
scripts/      the pipeline; 00_run_all.py runs them in order
derived/      generated — processed tables, the knowledge graph
eval/         generated — every report the paper cites
paper/        main-elsevier.tex + sections/, figures/, supplementary/
publish/      what w3id.org and GitHub Pages serve
attic/        retired: the single-basin pipeline this paper no longer reports
```

## What is deliberately not here

- **`Data/`** — the Waterbase release is the EEA's to distribute and is one
  download away. The pipeline prints the URL when the file is absent.
- **`refs/`** — the legal texts are free from EUR-Lex and the Resmî Gazete, the
  papers from their publishers. We cite them; we do not redistribute them.
- **`derived/abox/`, `derived/interim/`** — regenerable, and large.

## Reproducibility, concretely

- Every number in the paper is produced by a script and written under `eval/`;
  none is typed by hand.
- `scripts/99_audit.py` **recomputes** each claim from the processed data rather
  than checking that the value appears somewhere. It also enforces that no
  quantity is asserted which no shipped supplementary file supports, and that
  the conclusions introduce no quantity an earlier section does not.
- Figures are drawn from tables that ship beside them in
  `paper/supplementary/figure_data/`, one file per figure.
- Pure Python: OWL 2 RL entailment via `owlrl`, closed-world validation via
  `pyshacl`. No JVM, no external reasoner. Dependencies pinned in
  `requirements.txt`.
- Deterministic: fixed seeds, sorted iteration, paths relative to the
  repository root — nothing is hard-coded to a home directory. One stage,
  `15_foops.py`, needs the network; it caches the service response under
  `eval/` and falls back to it, so an offline run still produces the report.
- The novelty claim is checked as an **entailment**, not as a term list.
  `scripts/13_separation.py` takes one real record, writes down the three
  readings it admits, translates each into every comparison vocabulary, and
  reports which vocabularies can still tell them apart (`eval/separation.md`).
  The build fails on an **undeclared** separation — a vocabulary that tells the
  readings apart for a reason not written down in `KNOWN_SEPARATORS` — and if
  merging two readings in CENSO ever stops being a contradiction. It does not
  fail on the count: the concept patterns are deliberately generous, so a
  matcher can credit a competitor with a family on a term meaning something
  else, and making that fail the build would create pressure to narrow patterns
  until the answer came out right. The universal that *is* enforced is the one
  the contribution rests on: no comparison vocabulary carries a censoring
  status.
- **No dead terms.** `check_no_dead_terms()` fails the build on any declared
  class or property that appears in no shipped graph, package, shape or
  competency question. Abstract parents and covering unions are enumerated with
  a reason each rather than inferred. This exists because the same defect
  happened twice: two of the four commitments the paper claims shipped as terms
  in the TBox that nothing instantiated.

## Citing

See `CITATION.cff`. The ontology and both regulation packages are versioned at
2.0.0 under <https://w3id.org/censo/>; <https://w3id.org/censo/1.0.0> still resolves to what 1.0.0 was.
