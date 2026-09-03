# Internal review, written as a hostile Q1 referee

Target: *Ecological Informatics* / *Environmental Modelling & Software*.
Reviewed: draft v0.1 (2026-08-03), `paper/main.tex` + eight sections.

**Recommendation as it stands: major revision.** The empirical core is strong and
the verification discipline is unusual and welcome. But the headline number is
constructed in a way that will not survive scrutiny, the necessity of the
ontology is asserted rather than demonstrated, and the standard evaluation
battery for an ontology contribution is absent.

---

## MAJOR 1 — The headline figure conflates three different defects

The abstract leads with *93.2% of compliant verdicts are not supportable*. Table
"Where the verdicts go" then shows that **7,685 of the 8,585 flips (89.5%) are
caused by `unresolved_no_lod`** — the detection limit is not published for that
analyte.

That is not censoring. It is **incomplete documentation**. The laboratory
certainly had a limit; it simply is not in the file the authors received. A
referee reads this as: *the authors have measured how much metadata is missing
and called it an epistemic finding.*

The paper actually contains three distinct failures and should say so:

| # | Failure | Evidence | Is it about censoring? |
|---|---|---|---|
| F1 | Non-detections stored as zero | 85.2% of micropollutant records | **yes** |
| F2 | Detection limit not published | 175 of 254 analytes | no — documentation |
| F3 | LOQ above the regulatory threshold | 14 (TR), 4 neonicotinoids (EU) | no — analytical adequacy |

Each is real and each is publishable. Merging them into one percentage makes the
largest claim rest on the weakest component.

**Required.** Report the three separately. Lead with the figure that survives the
strongest objection — the 9.1% floor caused by F3, which no assumption about the
laboratory can repair — and present 93.2% as the upper bound of a range, with
the dominant cause named in the same sentence.

---

## MAJOR 2 — The necessity of the ontology is not demonstrated

The paper asserts that without a vocabulary separating *compliant* from *cannot
be determined*, none of the reported quantities can be counted. That is not
true, and a referee will say so immediately: **a single `censored` boolean column
and a `lod` column in a relational table would yield every number in Section 5.**
The analysis scripts are in fact plain Python over CSV files.

This is the weakest point in the manuscript and it is load-bearing, because the
title says *ontology-based*.

The defensible claims are narrower:

1. **Multiple regulations over the same observations.** The Turkish and European
   assessments differ, and pluggable packages make that a re-query rather than a
   re-implementation. A flag column does not give this.
2. **Preconditions.** Hardness class, bioavailability covariates and analytical
   fraction are conditions on a *threshold*, not on a measurement. Representing
   them requires the threshold to be an object with structure.
3. **Explainability.** A defined class yields a justification for each verdict;
   a boolean does not.
4. **Reuse.** The pattern transfers to air quality, food residues and clinical
   assays. A column in one team's spreadsheet does not.

**Required.** State the objection explicitly and answer it with these four
points, and remove the overclaim that the numbers are otherwise uncomputable.
Better still: report which of the four the paper actually demonstrates, and
concede the rest as design intent.

---

## MAJOR 3 — No ontology evaluation in the accepted sense

The axiom test suite is genuinely good and I have not seen its like in this
literature. But an ontology contribution is expected to report:

* **competency questions** with the SPARQL that answers them — absent;
* **OOPS!** pitfall scan — absent;
* **FOOPS!** FAIR assessment — absent;
* some form of **expert or user validation** — absent.

Their absence will be read as the artefact not having been exercised. The
reasoning benchmark added at the end is necessary but not sufficient.

**Required.** At minimum, a competency-question table and an OOPS!/FOOPS! report.

---

## MAJOR 4 — Reach-level inference is underpowered and should be demoted

Twenty-nine immediate reaches, 85.5% of candidate onsets undecidable, and
seasonal persistence resting on a single substance. The section is honest about
this, which is to its credit, but it cannot support a Results-level claim. As
written it invites a referee to spend the review on the weakest material.

**Required.** Move detection onset to a short methodological demonstration, or
remove it and publish it separately when the inferential unit is larger.

---

## MODERATE 5 — Threshold transcription errors are a data-management finding

The seven-of-ten metal discrepancy is striking and worth reporting, but it is a
finding about one project's spreadsheet, not about censoring or about
representation. The link to the contribution — that thresholds should carry
provenance and a machine-readable verification status — is asserted in one
sentence and should be argued.

Note also that the authors could not identify the source of the divergent values.
An unexplained discrepancy is weaker evidence than an explained one, and the
paper should not lean on it.

## MODERATE 6 — One basin, one laboratory, one reporting convention

Every number describes a single survey processed by a single group. The
representational claim is general; the evidence is not. Waterbase is named in the
limitations but not used. Without at least one external dataset the
generalisation is an assumption.

## MINOR

* The kurtosis test returns a negative result (1 of 54). Reporting it is correct
  and I commend it, but the framing should make clear it is a *test of the
  paper's own thesis that the thesis partly failed*, not a minor detail.
* "18 ontologies compared" — three are the authors' own and one is OWL-Time,
  included only to justify an exclusion. The honest count of comparison
  ontologies is 14.
* Load bounds are computed at a single station chosen by catchment area. Whether
  that station is representative is not argued.
* Nine `\pending` markers remain.

---

## What is strong and should be protected

* The three-way separation of F1/F2/F3 once made explicit is a genuine
  contribution and I am not aware of it being reported together elsewhere.
* The neonicotinoid finding is sharp, checkable and policy-relevant.
* The verification discipline — every number traced to a script, a bibliography
  checked against CrossRef, a gap table derived by parsing files rather than
  reading abstracts, and six of the authors' own errors caught and documented —
  is better than the norm in this literature and should be foregrounded as
  method, not hidden in an appendix.
* The sensing-versus-sampling explanation of why the gap exists is the paper's
  best conceptual moment and is currently buried in the discussion.
