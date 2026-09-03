# Progress log

Newest entry first. One entry per working session. Record **decisions and findings**, not activity.

---

## 2026-08-03 — session 13: bug sweep, audit harness, figure system

**Bugs found and fixed (all had reached the manuscript):**

| # | Defect | Consequence | Fix |
|---|---|---|---|
| 1 | `Area_km2` read as segment catchment | it is a *watershed* attribute repeated per segment; naive sum = 804,742 km² for an 11,000 km² basin | use `CArea_km2` (local, 989 values); telescoping self-test at the outlet now closes exactly on 10,967.2 km² |
| 2 | Spatial index binned segments by **vertex** | a long edge was invisible to queries near its midpoint | bin by every cell the edge's bbox spans; ring search terminates only when provably optimal |
| 3 | No basin clipping | pressure layers ship on 3 provincial extents; 44% (1,730 of 3,935 km²) was allocated anyway | allocation radius *solved* so the buffer area equals the basin's own stated area → D = 2,496 m |
| 4 | Same-segment station pairs | 18 of 28 "immediate reaches" were 9 pairs counted in **both** directions, each with zero delta | order by `pos_along_seg_m`; upstream content is position-aware → 20 genuine reaches |
| 5 | Immediacy test too narrow (my own regression) | 72 reaches, one "reach" adding 10,364 km² and all 1,048 firms | immediacy = no station anywhere in the *incremental catchment*, not just on the flow path |
| 6 | `95_numbers_manifest.py` searched its own output | every number trivially "traced" to itself; audit could never fail | exclude `numbers_manifest.md`; 4 untraced numbers surfaced immediately |
| 7 | Flip percentage mixed denominators | 8,585 (all→indeterminate) ÷ 9,210 (compliant) reported as 93.2% | correct transition count: 8,575/9,210 = **93.1%** |
| 8 | Abstract: "6.9% of determinate verdicts remain so" | 6.9% is the *compliant* retention; determinate retention is **13.3%** | both now reported, from recomputation |
| 9 | Ontology count 14 (abstract) vs 18 (results) | — | 17 published + this project's 2018 ontology = 18 files |
| 10 | Stale KG numbers | paper said 617,409 / 618,000 / 156,352; truth 617,394 / 618,060 / 156,338 | rebuilt; staleness check added |
| 11 | fig04 plotted **unverified spreadsheet** thresholds | the paper's own finding is that the spreadsheet is wrong | fig04 now joins `eqs_official.csv` by CAS; 4 untraceable analytes excluded |
| 12 | **No figure was included in the manuscript at all** | 885 lines of text, zero `\includegraphics` | 6 figures inserted with provenance captions |
| 13 | Permissiveness direction inverted in new code | ratio is regulation/spreadsheet, so <1 means *more permissive* | 6 of 11, not 5 |

**New finding (strengthens the paper):** extending the threshold check from the 10
metals to all analytes by CAS found **11 further disagreements**, all organics,
**6 of them more permissive than the law** — Triclosan 177 vs 0.12 µg/L (1,475×),
propetamphos 220×, fenthion 70×. Combined: **18 substances** would have been
assessed against the wrong number. TR LOQ>EQS counts corrected to 15 (AA) and 8 (MAC).

**New:** `scripts/99_audit.py` — recomputes every manuscript claim from
`derived/processed/*.csv` rather than checking string presence, plus staleness and
threshold-provenance checks. **54 pass, 0 fail.**

**Figures:** rebuilt on a journal house style (Arial first — Helvetica resolved to a
`.ttc` collection that will not subset into PDF), Elsevier column widths, palettes
validated with the six computable colour checks. Added `fig06_decision_geometry`,
which carries the ontological argument: a censored result is an interval, a
threshold is a line, and two of the four configurations are undecidable.

**Numbers that changed:** reaches 29→**20**, confirmed onsets 152→**114**,
undecidable 85.5%→**83.5%**, firms 1,107→**1,048** (in-basin), classified
77.4%→**77.6%**.

## 2026-08-03 — Session 12: hostile internal review, and the fixes it forced

Full review in [`06-internal-review.md`](06-internal-review.md). Verdict on the
draft as written: **major revision**. Three of the four major findings are now
addressed.

### MAJOR 1 (fixed) — the headline conflated three different defects

The abstract led with *93.2% of compliant verdicts not supportable*. But 7,685 of
the 8,585 flips (89.5%) came from `unresolved_no_lod` — the detection limit is
not published. **That is incomplete documentation, not censoring**, and a referee
reads it as measuring missing metadata and calling it an epistemic result.

The paper now separates three failures and reports them independently:

| # | Failure | Evidence | About censoring? |
|---|---|---|---|
| F1 | Non-detections stored as zero | 85.2% of micropollutant records | **yes** |
| F2 | Detection limit not published | 175 of 254 analytes | no — documentation |
| F3 | LOQ above the threshold | 14 (TR), 4 neonicotinoids (EU) | no — analytical adequacy |

**The paper now leads with F3's 9.1%**, which no assumption about the laboratory
repairs, and reports the combined 6.9%-remaining figure as an upper bound on the
damage rather than a measurement of censoring. A claim that survives its
strongest objection is worth more than a larger one that does not.

### MAJOR 2 (fixed) — the ontology's necessity was asserted, not shown

The draft claimed none of the quantities could be counted without the ontology.
**That is false and a referee would say so at once**: a `censored` flag plus an
`lod` column in a CSV yields every number in the results — our own scripts are
plain Python over CSV.

New subsection *"Could a column have done this?"* concedes the point and states
the four narrower grounds on which the ontology earns its place: several
regulations over one dataset, preconditions that belong to the threshold rather
than the measurement, per-verdict justification, and transfer to other domains.
It then says which of the four this paper actually demonstrates (the first three)
and marks the fourth as design intent.

### MAJOR 4 (fixed) — detection onset demoted

29 immediate reaches, 85.5% undecidable, seasonal persistence resting on one
substance. Now labelled a methodological demonstration, explicitly not a result,
so the review is not drawn onto the weakest material.

### D19 — Source attribution moved to future work

Chemical fingerprinting for source apportionment is established (PMF, CMB), and
the survey's own authors used core micropollutants as tracers. What would be new
is a knowledge-driven formulation that is *explainable* and *censoring-aware* —
able to answer "undecidable for this reach" where factorisation over
zero-substituted data returns a number. The ingredients exist (176 analytes with
external use categories, 857 classified firms, the directive's own substance
categories) but 29 reaches cannot support the claim. Written up as future work
with a PMF comparison as the natural next study.

### Also corrected
"18 ontologies compared" → **14**. Three of the eighteen were ours and one was
OWL-Time, included only to justify an exclusion.

### Still open from the review
- **MAJOR 3**: no competency questions, no OOPS!, no FOOPS!, no expert validation.
  This is the standard evaluation battery and its absence will be read as the
  artefact never having been exercised.
- **MODERATE 6**: one basin, one laboratory. Waterbase named but unused.
- 10 `\pending` markers remain.

---

## 2026-08-03 — Session 11: the flip analysis — the paper's headline result

### F25 — 93.2% of "compliant" verdicts are not supportable

`scripts/12_flip_analysis.py` assesses the same observations twice: as current
practice does (non-detect = 0, two verdicts available) and with the censoring
represented (non-detect = $[0, \mathrm{LOD}]$, four verdicts available).

Of \num{9900} assessable observation--threshold pairs:

| verdict | standard practice | censoring-aware |
|---|---|---|
| compliant | 9,210 | 635 |
| exceeding | 690 | 680 |
| cannot be determined | **0** | **8,585** |

Causes separate cleanly: 7,685 because no LOD is published, 890 because the
method's LOQ exceeds the standard, 10 reported as exceeding that the method
cannot actually resolve.

**A conservative floor was added deliberately.** The dominant cause is a missing
LOD, and a sceptic may argue a laboratory reporting zero presumably had a limit
well below the standard. That presumption cannot be verified, and where it *can*
be checked — the neonicotinoids — it is false. Granting it in full still leaves
**900 verdicts (9.1%)** that change because LOQ > threshold, which no assumption
about the laboratory repairs. A claim that survives its strongest objection is
worth more than a larger one that does not.

### F26 — Zero substitution understates the winter load by a factor of 197

| campaign | reported (kg/d) | upper bound (kg/d) | ratio |
|---|---|---|---|
| Autumn 2017 | 0.487 | 1.24 | 2.6× |
| **Winter 2018** | **0.0108** | **2.13** | **197×** |
| Spring 2018 | 0.256 | 1.01 | 3.9× |
| Summer 2018 | 0.0294 | 0.795 | 27× |

The ratio is largest in winter, when high flow dilutes concentrations towards the
detection limit and the non-detect share peaks — exactly when substitution is
least defensible and most often applied.

### A real error caught before it reached the paper
The first implementation **summed loads across all stations**. The same water
passes several stations, so the total double-counts it and is not a river load;
it produced figures like 708 kg/day for a pesticide never detected. Loads are now
evaluated at a single station — the gauged one with the largest cumulative
catchment area — and the correction is stated in the script's docstring so the
choice is visible rather than assumed.

### Manuscript state
Abstract and Results now carry the flip result; the largest `\pending` is closed.
`scripts/95_numbers_manifest.py`: **102 numeric claims, 102 traced, 0 untraced**,
9 `\pending{}` markers remaining.

---

## 2026-08-03 — Session 10: the source paper found; full draft written

### F24 — The dataset is already published, and its reporting rule is the mechanism

Emadian, Sefiloglu, Akmehmet Balcioglu and Tezel, *Science of The Total
Environment* **758**:143656 (2021), `10.1016/j.scitotenv.2020.143656`, describes
**this exact survey**: 300 samples, 75 locations, four campaigns August 2017 –
May 2018 (Summer 8–11 Aug, Fall 14–16 Nov, Winter 12–16 Feb, Spring 14–15 May),
direct-injection LC–MS/MS with scheduled MRM. Boğaziçi University Institute of
Environmental Sciences, TÜBİTAK-funded.

The decisive sentence is their methods:

> *"Concentration values that are **higher than LOD** and lower than water
> solubility were reported."*

Below-LOD outcomes were therefore never reported, and in the distributed tables
they appear as zeros. **This is documentary evidence, from the primary source,
of the exact step at which the censoring information leaves the record** — and
it is not an error. For an occurrence study the rule is correct. It simply means
the compliance question cannot be answered from the published table.

### D18 — Position as a methodological follow-up, not a correction

They asked what was *detected* (165 contaminants, 41 "core micropollutants",
clustered by detection frequency). We ask what the *non-detections* establish
and where they establish nothing. Their detection-frequency signal is the same
binary evidence our onset method uses; we add the limit that bounds it and the
threshold it must be compared against. Framed this way the paper is a respectful
extension of a published analysis rather than a critique of it.

**This also resolves WP0.5**: the data holders are identifiable — Tezel and
Akmehmet Balcioglu at Boğaziçi, under a TÜBİTAK grant. Co-authorship and consent
should be sought from them.

### C4 — LOQ > EQS is NOT novel and must not be claimed as such

Searching for prior art found an established literature: WFD Guidance No. 19
requires an analytical method's LOQ to be at or below **30% of the EQS**, and
several papers document member states failing to reach
it~\cite{coquery2005,weisner2022,loos2024}. An earlier framing of this finding as
a discovery is withdrawn.

The corrected — and stronger — framing: *the directive states an explicit
analytical adequacy criterion, and we make it automatically checkable once both
LOQ and EQS are machine-readable.* The criterion is the legislator's, not ours;
the contribution is that the check can now be run at scale and its failures
counted.

### Created
Full manuscript draft: `paper/main.tex` plus eight section files, **4,631 words**.
Title settled: *Not detected is not absent: an ontology-based audit of censored
micropollutant measurements in river basin monitoring*.

`scripts/95_numbers_manifest.py` traces every `\num{}` value in the manuscript to
the artefact that produced it: **74 of 75 traced**, the untraced one being a
figure quoted from Lipiński. 12 `\pending{}` markers remain and are rendered in
red so they cannot survive to submission.

Six papers filed and cited: Emadian 2021 (source dataset), Tokatlı 2023 (basin
context), Coquery 2005, Loos 2024 and Weisner 2022 (WFD analytical adequacy),
Lipiński 2026 (preprocessing sensitivity).
Bibliography: **37 entries, 19 verified DOIs, 0 wrong, 0 unresolved.**

---

## 2026-08-03 — Session 9: 16 ontologies compared; the gap gets its explanation

### D17 — The paper is an audit with a formal method, not an ontology paper

The user's framing, and it is right. Nobody writes *"we built a thermometer"*; they write *"the
patient has a fever, measured with a thermometer we had to build because none existed."*

The contribution is the **empirical finding**: a national monitoring programme produces compliance
conclusions its data cannot support, quantified. CENSO is the **instrument** that makes the count
possible — without a vocabulary that separates *compliant* from *cannot be determined*, not one row
of the results table can be produced, because a closed-world table has no cell for the second.

Section weights shift: ontology engineering 35% → 15%; empirical audit 20% → 40%.

### F22 — Why the gap exists: the field inherited a *sensing* model

Micropollutants cannot be measured by an in-situ sensor. The workflow is
`sosa:Sampling → transport → laboratory analysis`, and the detection limit belongs to the
**analytical run** — its calibration curve, that analyte, that matrix — not to a device. It varies
between runs and laboratories.

SOSA/SSN was designed for sensing, which is why `ssn-system:DetectionLimit` is a `SystemProperty`.
For a sensor that is correct. The water-ontology field inherited that model and never adapted it,
which is the structural reason the limit is "known about the instrument and forgotten about the
measurement". SOSA does provide `Sampling`, `Sampler` and `Sample`, but nothing links the analysis
of a Sample to a detection limit.

Modelled: `censo:AnalyticalRun`, `producedByRun`, `runUsedMethod`, `analysedSample`, and
`censo:MassSpectrometryTransition` (precursor/product ion, retention time) — the level at which
analytical provenance actually lives, and absent from every ontology surveyed.
CENSO now 473 triples, 64 entities; axiom suite still **10/10**.

### F23 — 16 ontologies compared, all parsed from their published files

`eval/gap_table.md` covers SOSA, SSN, SSN-system, GeoSPARQL, QUDT, SAREF, SAREF4WATR, WHOW, DoCE,
InWaterSense (core/regulations/pollutants), WAM-ONTO, SewerNet, ENVO, ExO.

**Only CENSO scores censoring, undecidable, and a detection limit bound to the result.**
WHOW alone represents a value interval on a result. SSN-system alone has a detection limit, on the
sensor. InWaterSense's `hasRangeMinValue` comes from the SSN *meteo* extension — again the sensor's
capability, not the measurement.

A second table now profiles reuse, FAIR status and measurement modality:

| group | ontologies | sampling / sensing terms |
|---|---|---|
| sensing-oriented | SAREF core, SAREF4WATR, InWaterSense core | 0/22, 0/16, 2/27 |
| sampling-oriented | SOSA core, WHOW, DoCE, **CENSO** | 12/10, 10/0, 6/2, **6/0** |

FAIR: **InWaterSense (all three modules) and WAM-ONTO carry 0% labels, no licence and no
versionIRI** — WAM-ONTO has 921 unlabelled entities. Neither is practically reusable.

### Three methodological corrections to the checker itself
1. **Temporal intervals scored as value ranges.** OWL-Time's `Interval` gave SewerNet and
   SAREF4WATR a false "interval result".
2. **Prose scored as vocabulary.** In ENVO (7,208 entities) free-text definitions matched four
   concepts it does not model. Evidence is now graded TERM vs PROSE, and only TERM is scored.
3. **`indetermin` matched *indeterminate root nodule*** — a plant-biology class. The pattern now
   requires the epistemic sense (`indeterminate compliance/status/result/assessment`).

Each would have inflated the comparison in our favour. Recording them because a table that only
ever errs toward the author is not evidence.

---

## 2026-08-03 — Session 8: WHOW narrows the novelty claim, for the better

### The finding that matters

The user supplied `https://w3id.org/whow/onto/water-monitoring`. Unlike WaWO+ and OPO, the Water
Health Open Knowledge Graph **publishes its ontology** at a w3id IRI with content negotiation, so it
could be checked directly rather than through its paper.

It defines a `Range` class with `lowerBound` / `upperBound`, attached to `ObservationValue`. Its own
comment reads:

> *"The class of value intervals. Examples: the value of the observation of the concentration of
> copper is `<10`, meaning between 0 and 10."*

**That is censoring, represented as an interval.** The claim that no water ontology represents
interval-valued results arising from censoring was **false and is withdrawn**. This is the second
novelty claim that verification has had to narrow — and again, verification caught it rather than
review.

### What survives, verified against WHOW's 31 classes / 20 object props / 4 datatype props

| | WHOW | CENSO |
|---|---|---|
| interval-valued result | **yes** | yes |
| detection limit as a first-class entity | — | yes |
| interval linked to the limit that produced it | — | yes |
| censored vs merely imprecise distinguishable | — | yes (4 disjoint statuses) |
| any compliance vocabulary | — | yes |
| undecidable outcome | — | yes |
| threshold applicability conditions | — | yes |

**The WHOW range is anonymous.** Nothing records *why* the interval exists — censoring, measurement
spread, or reporting convention — nothing ties it to the LOD of the method that produced it, and
WHOW has no compliance vocabulary, so "undecidable" cannot even be posed.

### Reframing (D16)

The contribution is **not the interval but its provenance and epistemic status**: which limit
produced it, whether the analyte was detected, and what follows for compliance.

WHOW becomes the closest prior work and the paper **extends** it. That is a stronger and more
credible position than claiming a void — reviewers trust an author who names the nearest competitor
accurately far more than one who does not find it.

### Four more competitors assessed from their papers (`eval/competitor_papers.md`)

| concept | WaWO+ | OPO | Jajaga 2015 | Ahmedi 2016 |
|---|---|---|---|---|
| detection limit | — | — | — | — |
| censoring | — | — | — | — |
| undecidable outcome | — | — | — | — |
| regulatory threshold | 1 | 1 | 3 | 4 |
| rule layer (SWRL) | — | 9 | 13 | — |

All four model thresholds; two carry a rule layer. **Neither thresholds nor rules are claimed as
novel.**

### Bibliography
Added and CrossRef-verified: `calbimonte2012ssw` (IJSWIS 8(1):43–63),
`jajaga2015expert` (MTSR, CCIS 544:89–100), `whow2023onto`.
State: **33 entries · 16 verified DOIs · 0 wrong · 0 unresolved**.

Two housekeeping notes: an exact duplicate of the Helsel PDF was removed, and the Calbimonte file is
the IGI Global **landing page**, not the article — renamed to say so. Its abstract is sufficient for
the single Related Work sentence it supports, so the full text is not needed.

---

## 2026-08-03 — Session 7: primary sources arrive; EU assessment becomes possible

The user supplied every blocking document. Filed under `refs/`:

| File | What it is |
|---|---|
| `refs/papers/Helsel2006_FabricatingData.pdf` | *Chemosphere* 65(11) — the key citation for zero substitution |
| `refs/papers/OlivaFelipe2017_WaWOplus.pdf` | EM&S 89:106–119 — **the closest competitor**, previously absent from the gap table |
| `refs/papers/Wang2020_OPO.pdf` | *Water* 12(3):715 — authors now verified from the PDF |
| `refs/legal/EU-2008-105_consolidated-2026-05-10.pdf` | **2008/105/EC consolidated, in force 10 May 2026** |
| `refs/legal/EU-2013-39.pdf`, `EU-2008-105_original.pdf` | the amending and base directives |

The consolidated text is better than the standalone 2026 directive: it is the current law with every
amendment merged, so one parse yields the whole EQS regime.

### F19 — All four neonicotinoids in the survey are unmeasurable against EU law

`scripts/10_parse_eu_eqs.py` parses Annex I (62 entries; 13 unparsed and reported as such) and
matches 33 measured analytes by CAS.

| substance | LOQ (µg/L) | EU AA-EQS | factor |
|---|---|---|---|
| **Imidacloprid** | 2.065 | 0.0068 | **304×** |
| Clothianidin | 0.4528 | 0.01 | 45× |
| Thiacloprid | 0.2894 | 0.01 | 29× |
| Acetamiprid | 0.08413 | 0.037 | 2× |

This is not a scatter of individual failures: it is **an entire pesticide class**, newly regulated by
the EU, for which the analytical method cannot demonstrate compliance in principle. Under Turkish
YSKY the same substances looked far less severe (imidacloprid 15×), so the divergence between two
regulation packages over the same measurements is itself a result — the case for pluggable
regulation packages, made empirically.

### F20 — The directive supplies an authoritative use classification

Annex I column (3), *Category of substances*, carries values such as
*Pharmaceuticals – anti-inflammatory*, *Pesticides – neonicotinoid*, *Industrial substances*.
Coming from the legislator, this is citable and immune to the circularity objection that an
analyst-authored substance→use mapping invites. It should be preferred over PubChem/CPDat for every
substance the directive covers, with CPDat filling the rest.

### F21 — Cadmium's five hardness classes are explicit in the text

`≤0,08 (Class 1) … 0,25 (Class 5)`. The precondition argument is no longer an inference from
practice but a direct quotation from the law — and this survey measured no hardness, so cadmium is
`censo:PreconditionUnmet` by the regulation's own terms.

### Three parsing bugs, each of which produced a plausible wrong answer
1. **Soft hyphens at line ends** — the PDF breaks words across lines, so a naive join produced
   `neoni cotinoid` and every category label was corrupted.
2. **CAS numbers split across lines** — `138261-41-` / `3` never matched the CAS regex, which is why
   imidacloprid, the single most extreme case in the dataset, was missing from the first run.
3. **Name-only matching** — chemical names diverge between directive, survey and ECOSAR; matching by
   CAS raised coverage from 20 to 33 analytes.

Each was found by asking why an expected result was absent, not by the code failing.

### Bibliography
`wang2020opo` authors added from the PDF. Current state: **14 verified · 0 wrong · 0 unresolved ·
1 accepted with reason**.

### Created
`scripts/10_parse_eu_eqs.py` · `eval/eu_eqs_assessment.md` · `derived/processed/eu_eqs.csv` ·
`refs/legal/` (4 documents) · `refs/papers/` (3 papers)

### Next
- Add WaWO+ and OPO to the gap table now that both papers are available
- Build the two regulation packages (`tr-yskly-2016`, `eu-eqs-2026`) from the verified values
- RIPO domain layer; source-type inference using the directive's own categories

---

## 2026-08-03 — Session 6: a fabricated DOI, and the check that now prevents it

### What happened

The bibliography carried `10.1016/j.envsoft.2016.07.005` for the WaWO+ paper. **That DOI was
invented.** It was marked `note = {VERIFY}`, which does not make it acceptable — a `VERIFY` note is
not a licence to guess a value.

Worse than not resolving, **it resolves**: to *"A comparative study of different machine learning
methods for landslide susceptibility assessment"* (Pham et al., EM&S 84, 2016). A reader clicking
the citation would land on an unrelated paper. A plausible-looking DOI survives review right up to
the moment someone follows it.

Caught by the user, not by me.

### The correct record (CrossRef-verified)

Oliva-Felipe, L., Gómez-Sebastià, I., Verdaguer, M., Sànchez-Marrè, M., Poch, M., Cortés, U.
*Reasoning about river basins: WaWO+ revisited.* **Environmental Modelling & Software 89,
106–119, 2017.** `10.1016/j.envsoft.2016.11.009`

Both the DOI **and** the year were wrong in the original entry.

### Systematic fix

`scripts/09_verify_bibliography.py` resolves **every** DOI in `paper/refs.bib` against the CrossRef
API and compares title, year, journal, volume and pages. One fabrication implies the whole file is
untrustworthy, so it is now checked mechanically rather than by rereading.

It found **6 defective entries out of 15 with DOIs**:

| entry | defect |
|---|---|
| `wawoplus2016` | fabricated DOI resolving to an unrelated paper; wrong year |
| `haller2019ssn` | year 2018 not 2019; registered title is *"The modular SSN ontology…"* |
| `degtyarenko2008chebi` | year 2007 not 2008 |
| `suarez2012neon` | year 2011 not 2012 |
| `water_onto_review` | year 2022 not 2023; pages 21–39 now known |
| `poveda2014oops` | **false positive** — IGI Global deposited the title without its subtitle |

All corrected. Current state: **14 verified · 0 wrong · 0 unresolved · 1 accepted with a written
reason**. The script exits non-zero on any real defect, so it can gate a build.

The `poveda2014oops` case is why the checker has a reasoned allowlist rather than a silent one:
publisher metadata is sometimes the incomplete side, and "fixing" the bib to match it would make
the entry worse.

### Rule recorded in `refs.bib`
> Never write a DOI that has not been resolved. An unverifiable entry carries **no DOI at all**.

### Created
`scripts/09_verify_bibliography.py` · `eval/bibliography_check.md` ·
`derived/interim/crossref_cache/`

---

## 2026-08-03 — Session 5: novelty claim verified and corrected; threshold data found wrong

### The headline: the project's EQS table does not match the law

`scripts/08_verify_thresholds.py` parses the official *Yerüstü Su Kalitesi
Yönetmeliği* (downloaded to `refs/legal/YSKY.pdf`, 2016 amendment RG-10/8/2016-29797,
**Tablo 4 — Belirli Kirleticiler ve Çevresel Kalite Standartları**) and compares it with
`Data/CKS_FEnCY.xlsx` substance by substance.

**7 of 10 measured metals carry the wrong threshold in the project spreadsheet.**

| substance | official AA (µg/L) | spreadsheet AA | factor |
|---|---|---|---|
| Arsenic | 53.0 | 53.0 | match |
| Antimony | 7.8 | 7.8 | match |
| **Boron** | **707** | 6.5 | 109× |
| **Barium** | **680** | 1.3 | 523× |
| **Beryllium** | **2.5** | 0.05 | 50× |
| **Tin** | **13.0** | 0.01 | 1300× |
| **Chromium** | **1.6** | 1.9 | — |
| **Cobalt** | 0.3 | 0.3 (MAC differs: 2.6 vs 2.0) | — |
| **Titanium** | **26.0** | 2.0 | 13× |
| **Vanadium** | **1.6** | 10.0 | 6× |

Every compliance statement derived from the spreadsheet would have been wrong, and
nothing in the workflow would have revealed it. **This is the paper's argument
demonstrated on its own inputs**, and it is a publishable finding in itself:
thresholds carried without provenance or validation are not trustworthy.

Copper is the clearest case: the value flagged as implausible on inspection (0.05 µg/L,
below natural background) is officially **1.6 µg/L river / 1.3 µg/L coastal**.

### Corrections to earlier claims — both were mine, both mattered

**C1 — "SOSA/SSN has no concept of a detection limit" is FALSE and is withdrawn.**
`scripts/07_verify_gap_table.py` downloads each comparison ontology and searches its own
vocabulary. `ssn-system:DetectionLimit` exists. What survives is narrower, verified, and
sharper: it is a subclass of `ssn-system:SystemProperty` — metadata about **what a sensor
can do** — and is never attached to a `sosa:Observation` or its result. Nothing in
SOSA/SSN can state that *a particular measurement fell below the limit*.
**The limit is known about the instrument and forgotten about the measurement.**
The gap table now carries a `LOD bound to` column: SSN-system → *the sensor*;
CENSO → *the result*. That column is the discriminator, not mere presence of the term.

**C2 — "the asterisk in Tablo 4 marks bioavailability-corrected metals" is UNSUPPORTED
and is withdrawn.** Eight metals carry an asterisk (As, B, Co, Cr, Sb, Sn, Ti, V) but
**no footnote explaining it appears anywhere in the published regulation**. Recorded as
unknown. This is itself an instance of the thesis: a threshold whose applicability
conditions are not machine-readable — or not readable at all — cannot support an
automated verdict.

**C3 — the "row misalignment" diagnosis was wrong.** Only vanadium's spreadsheet value
coincides with another official cell. The values come from some other source, plausibly
an earlier regulation version. Stated as unresolved rather than guessed.

### Verified gap table (`eval/gap_table.md`)

| Ontology | entities | LOD bound to | censoring | undecidable |
|---|---|---|---|---|
| SOSA/SSN | 37 | — | — | — |
| SOSA core | 53 | — | — | — |
| QUDT | 239 | — | — | — |
| SAREF core | 131 | — | — | — |
| SAREF4WATR | 144 | — | — | — |
| SSN-system | 44 | the sensor | — | — |
| **CENSO** | 56 | **the result** | **yes** | **yes** |

SAREF4WATR's threshold hits are about **tariffs** (billing) and its interval hits are
**temporal**; it is a water-utility IoT vocabulary, not a quality-assessment one.
Sources cached under `derived/interim/ontology_cache/` so any cell is re-checkable.

### Substance resolution without circularity (`eval/substance_resolution.md`)

Use classes come only from external sources — PubChem CID, ChEBI alignment, and **EPA
CPDat Function Use Categories**. Nothing is authored here, which is what keeps the
land-use validation honest. On a 12-analyte probe: CID 100%, ChEBI 83%, ≥1 use category
83% (e.g. *Flame retardant*, *Coatings*, *Softener and conditioner* — matching the
brominated diphenyl ethers in that slice). Raw responses cached for offline reruns.

Two parser bugs found and fixed, both of which had produced a plausible-looking wrong
answer: PubChem's `StringWithMarkup` is sometimes a dict and sometimes a list (yielded
"no use categories"), and `ParentID` may be a list because these classifications are
DAGs, not trees.

### Created
`scripts/07_verify_gap_table.py` · `scripts/08_verify_thresholds.py` ·
`eval/gap_table.md` · `eval/threshold_verification.md` ·
`derived/processed/eqs_official.csv` (217 official rows) ·
`refs/legal/YSKY.pdf` · `derived/interim/ontology_cache/`

### Still needed from primary sources
- EU 2026 priority-substances directive (EUR-Lex PDF endpoint returns 202; needs another route)
- Directive 2008/105/EC + 2013/39/EU Annex I
- WaWO+ ontology file (EM&S 2016, paywalled) — the closest competitor, currently absent from the gap table
- OPO ontology file (Water 2020; MDPI blocks automated download)
- Helsel 2006, *Chemosphere* 65(11):2434 — key citation for zero substitution

---

## 2026-08-03 — Session 4: CENSO v2, axioms that do work, detection onset runs

### Decisions

**D13 — The 2018 ontology is a design input, not a baseline to be revised.**
It was never published, so there is no self-citation constraint. CENSO stands as an independent
contribution; the earlier work supplies the conceptual seed (analytical-provenance branch, and the
undecidable "grey box" in `ControlPollutantConcVSeQS`) and nothing else. The before/after comparison
is dropped from the evaluation plan — comparing against one's own unpublished draft proves nothing.

**D14 — Concentrations and thresholds are `xsd:decimal`, not `xsd:double`.**
Regulatory limits are published as exact decimals and compliance turns on exact comparison; binary
floating point injects representation error into a legal judgement. Decimal also avoids the
lexical-form fragility that makes `xsd:double` unreliable across RDF toolchains — `owlrl` rejects
every lexical form of `xsd:double`, including canonical ones.

**D15 — The reasoner is pure Python; no JVM.**
`owlrl` computes the OWL 2 RL deductive closure over rdflib, and `pyshacl` covers the closed-world
half. The whole pipeline therefore runs anywhere Python does, which matters more for reproducibility
than access to full DL. Java/HermiT remains optional for DL-profile checking only.

### Findings

**F15 — The axioms catch real defects: 10/10 (`eval/axiom_tests.md`).**
Each case injects a defect present in the source data and asserts it is rejected.

| # | Axiom | Defect caught |
|---|---|---|
| T1 | AllDisjointClasses over detection statuses | record marked both non-detect and quantified |
| T2 | AllDisjointClasses over compliance outcomes | compliant and exceeding asserted together |
| T3 | `CensoredObservation ⊑ ¬∃exceeds.Threshold` | a non-detection reported as an exceedance |
| T4 | AllDisjointProperties over the three comparisons | two mutually exclusive comparisons materialised |
| T5 | `UnresolvedObservation ⊑ ¬∃assessableAgainst` | analyte with no LOD nevertheless assessed |
| T6 | FunctionalProperty on `hasAnalyte` | one row joined to two substances by name matching |
| T7 | **SHACL** `CensoredObservationShape` | half-LOQ substitution on a non-detect |
| T8 | AllDisjointClasses over threshold types | grab sample compared against an annual-average limit |
| T9 | control — well-formed graph | must stay consistent |
| T10 | `owl:hasKey` | duplicated row double-counted in load statistics |

T7 is deliberately outside OWL 2 RL: a functional datatype-property clash is not expressible in the
profile, and it is the shape layer's job. That split is the paper's argument about what OWL does and
does not do, demonstrated rather than asserted.

**F16 — Two false results were caught by the control case, not by inspection.**
A first run reported 8/9 passing while every case was in fact firing on an `xsd:decimal`/`xsd:double`
disjointness artefact inside `owlrl` — zero axioms were actually exercised. The control case (T9)
failed, which is what exposed it. A second run then revealed that the control itself violated
`owl:hasKey`, because its two observations shared analyte, station and campaign. Both are recorded
here because "the reasoner reported consistent" is worthless without a case that must *not* be
consistent.

**F17 — Detection onset produces real results** (`eval/detection_onset.md`), over 29 immediate
reaches × 254 analytes × 4 campaigns = 29,464 comparisons:

| outcome | n | share |
|---|---|---|
| absent at both ends | 21,015 | 71.3% |
| present at both ends | 5,482 | 18.6% |
| disappearance (attenuation) | 1,416 | 4.8% |
| **onset confirmed** | **152** | 0.5% |
| onset possible | 44 | 0.15% |
| **onset undecidable** | **1,152** | 3.9% |

Of 1,348 candidate onsets, **85.5% are undecidable**, almost entirely because the analyte has no
published detection limit. Reporting them would be unfounded; discarding them silently would hide
the gap. They are returned as an explicit verdict — the thesis, measured.

Seasonal persistence is weak: only one substance (Quinalphos) shows onsets in ≥3 campaigns. Report
honestly; do not lean on persistence as a validation.

**F18 — A silent bug nearly invalidated the onset analysis.** The flow series is spelled `Yabatas`
in the sheets while the script matched `Yabataş`; the exact-string constant matched nothing and the
first run reported 0 confirmed onsets with 100% undecidable — a plausible-looking result that was
entirely an encoding artefact. Parameter matching is now diacritic- and case-folded.

### Created
`ontology/censo-core.ttl` v2.0.0 (435+ triples, 56 entities, 6 defined classes, 3 disjointness
blocks, hasKey, 14 restrictions) · `ontology/censo-shapes.ttl` (validation + three materialisation
rules) · `scripts/test_axioms.py` · `scripts/05_detection_onset.py` · `eval/axiom_tests.md` ·
`eval/detection_onset.md`

### Next
1. Curate the substance → use-class mapping from an **external citable source** (ECHA/PubChem use
   categories, ECOSAR class) — never from the analyst, or the land-use validation is circular.
2. RIPO domain layer importing CENSO.
3. Transcribe regulation packages from primary legal texts.
4. Fix the three `04_landuse_allocation.py` bugs.

---

## 2026-08-03 — Session 3: the ontology argument, regulatory audit, CENSO v1.0.0

### Decisions

**D9 — The paper's intellectual core is the OWA/CWA mismatch.**
A relational store operates under the Closed World Assumption: `0.0` asserts *"the concentration is
zero."* A non-detection asserts *"we do not know whether it is present; if it is, it is below LOD."*
That is the Open World Assumption exactly. **Substituting zero is a type error, not a rounding
convention** — the information destroyed is the modality, not the magnitude. The 85.2% figure is the
measured cost. This is simultaneously a CS claim (logical foundation mismatched to measurement
epistemics) and an environmental-science claim (quantified defect in a real regulatory programme),
which is precisely the intersection the target venues want. Full argument in
[`05-why-ontology.md`](05-why-ontology.md).

**D10 — A threshold is a conditional judgement, not a number.**
It applies only when its preconditions hold: matrix, analytical fraction, bioavailability basis,
required covariates, hardness class, regulation version. Existing models store the value and discard
the preconditions, so they report compliance for cases where no assessment is possible. Modelled as
`censo:ApplicabilityCondition`; unmet preconditions yield `censo:PreconditionUnmet`, a subclass of
`IndeterminateCompliance`. **This is the sharpest ontological contribution and it is new.**

**D11 — Regulations are pluggable, versioned packages.**
Thresholds expire; the framework must not. Each regulation is a self-contained module contributing
only individuals (`cereg:RegulationPackage`), so adding or superseding one touches nothing else.
Consequences: one dataset assessable under several regulations at once (divergence is a result);
historic surveys re-assessable under later law; covered-but-unmeasured substances become explicit
`cereg:NotCoveredBySurvey` instead of silently absent.

**D12 — Two-layer split: CENSO (reusable) + RIPO (Ergene application).**
The censored-observation pattern is domain-independent — air quality, food residues, clinical
assays, soil, occupational exposure all share it. Publishing CENSO as the artefact and Ergene as the
validation case is what lifts the work from case study to reusable contribution.

### Findings

**F12 — The EU adopted a new priority-substances directive on 17 Feb 2026.**
(Provisional agreement 23 Sep 2025.) Adds PFAS (24-sum plus TFA), pharmaceuticals, bisphenols,
non-relevant pesticide metabolites, and a **total-pesticide standard of 0.2 µg/L** for surface
waters. Compliance deadline 2039. The project's ÇKS spreadsheet is therefore **two regulatory
generations out of date** — which makes D11 necessary rather than merely elegant, and opens a topical
result: *what would the 2017–2018 survey show under the 2026 rules?*

**F13 — Dataset coverage against the new directive.**
- **12 of 15** newly regulated pharmaceuticals measured (sulfamethoxazole, ciprofloxacin,
  clarithromycin, azithromycin, erythromycin, ofloxacin, norfloxacin, trimethoprim, amoxicillin,
  paracetamol, doxycycline, tetracycline). Not measured: diclofenac, ibuprofen, carbamazepine.
- **Both bisphenols** measured (BPA, TBBPA).
- **Zero PFAS** measured → the 24-PFAS sum is structurally unassessable (`NotCoveredBySurvey`).
- Ibuprofen itself absent but **1- and 2-hydroxyibuprofen (its metabolites) are measured** →
  motivates `cereg:metaboliteOf`.
- A total-pesticide sum is computable, but the pesticide list must be **curated**: a keyword
  heuristic returned 97 substances while wrongly including benzotriazoles, dinitropyrenes and
  ibuprofen metabolites. Not usable until hand-curated.

**F14 — Reviewer-eye audit of the ÇKS thresholds found values that must be verified.**
The spreadsheet is a *secondary source*. Concerns:

| Analyte | Value (µg/L) | Concern |
|---|---|---|
| Cu | AA 0.05 | below natural background and below most LOQs |
| Al | AA 2.2 | background is 10–100 µg/L; exceeded everywhere by construction |
| Sn | AA 0.01, no MAC | implausibly low for total tin |
| Cd | AA 0.25 / MAC 1.5 | corresponds to the most permissive hardness class — **hardness was never measured** |
| Pb, Ni, Cu, Zn | — | EU AA-EQS are **bioavailable**; require hardness + DOC + pH. DOC and hardness absent |
| Hg | AA 0.07 | EU replaced the water AA-EQS with a biota standard in 2013/39/EU |
| Anthracene, Dichlorvos | absent | EU priority substances, measured, no threshold in the file |
| Conventional parameters | no EQS | **correct** — they are assessed against YSKY class boundaries, not EQS. Needs `ClassBoundaryThreshold` |

Each of these becomes a modelled `PreconditionUnmet` / `IndeterminateCompliance` rather than a
silent pass — the paper's argument demonstrated on its own inputs.

### Created — CENSO v1.0.0

| File | Content |
|---|---|
| `ontology/censo-core.ttl` | 276 triples · 47 entities · detection status, interval results, applicability conditions, four-valued compliance |
| `ontology/censo-regulation.ttl` | 181 triples · 27 entities · pluggable versioned packages, group/derived thresholds, metabolite relations |
| `ontology/reg/README.md` | how to add a jurisdiction; verification protocol; design rationale |
| `scripts/validate_ontology.py` | metadata/label/axiom/IRI-hygiene checks; fails on Protégé-default IRIs and missing FAIR metadata |
| `docs/05-why-ontology.md` | the OWA argument, gap table, honest weaknesses, venue positioning, abstract skeleton |

Both modules **pass their own validator**: complete FAIR headers, versionIRI, CC BY 4.0, every
entity labelled, imports declared, logical axioms present.

Against the 2018 baseline: imports 0 → 4 · disjointness 0 → 2 · defined classes 0 → 3 ·
versionIRI/licence absent → present.

### Next
1. Transcribe regulation packages from **primary legal texts** (EU 2013, EU 2026, TR 2016, TR 2023).
   Nothing may be quoted while `transcriptionStatus` is `Unverified`.
2. Build the RIPO domain layer (river topology, pressures, source types) importing CENSO.
3. Curate the substance → use-class mapping as SKOS with provenance.
4. Fix the three `04_landuse_allocation.py` bugs.
5. Implement detection-onset inference.

---

## 2026-08-03 — Session 2: spatial join, land use, concept sharpening, figures

### Decisions

**D6 — The core method is DETECTION ONSET, not interval mass balance.**
The earlier framing failed a self-critique: if 85% of records are censored, interval arithmetic
makes almost every reach `UndecidableReach`, and the framework produces no actionable output.
Reframed: a non-detection is an **upper bound**, and an upper bound is exactly what a source-location
argument needs. If a substance is absent upstream (`< LOD`) and clearly present downstream
(`>> LOQ`), a source exists in that reach, with load at least `(C_down − LOD)·Q`.
Censoring stops being an obstacle and becomes half the signal. Binary detection is also far more
reliable than concentration values near the detection limit.

**D7 — The original method is ontology-mediated source-type inference.**
Chain: reach onset set → substance use class (pharmaceutical, pesticide, biocide, UV filter, musk,
benzotriazole, surfactant, flame retardant) → expected source type (domestic / industrial-sector /
agricultural / hospital) → **tested against independent land-use geometry**. The agreement rate is
the paper's headline quantitative result. This is knowledge-structure work a spreadsheet cannot do,
which answers the "why an ontology at all?" objection.

**D8 — Persistence tier replaces the conservative-tracer-only design.**
No biodegradation half-lives exist in the source data, but LogP (223 substances), Henry's law
constant, water solubility, Max Log Kow and SMILES do. These support a defined class
`MobilePersistentSubstance ≡ Substance ⊓ logP<3 ⊓ henry<1e-5 ⊓ solubility>100 ppm` — the substances
for which a strict load balance is defensible. Connects directly to the EU PMT/vPvM agenda.
Optional strengthening: run EPI Suite BIOWIN over the 222 SMILES for real biodegradation predictions.

### Findings

**F9 — Spatial join works.** (`scripts/03_spatial_join.py` → `eval/spatial_join.md`)
- River network: **989 segments, 990 nodes, clean DAG, single outlet, Strahler 1–5, 4,381 km**
- CRS mismatch confirmed and handled: river + Corine are **EPSG:3035** (ETRS89-LAEA, metres);
  OSB, agriculture and station coordinates are **WGS84**. All transformed to EPSG:3035, which is
  equal-area, so computed areas are valid.
- **69 of 75 stations snap within 500 m**; median 69 m, p25 33 m, p75 116 m.
- 6 stations off-network: 75 (4,576 m), 3 (2,222 m), 51, 69, 37, 72 — need manual review.
- 4 stations disagree on coordinates between campaigns (22, 44, 51, 65).
- **652 ordered upstream/downstream station pairs.**

**F10 — Industrial sector inference from company names works well.**
**857 of 1,107 OSB firms classified (77.4%)**: 244 textile, 130 food, 121 chemical,
121 machinery/automotive, 98 metal, 84 plastic/rubber, 78 leather, 69 wood/paper, 57 mining/stone,
40 energy/waste, 26 pharma/cosmetic, 20 agri-industry, 7 beverage. Consistent with Ergene's known
pollution profile. Multi-sector firms keep all matched labels; unmatched firms stay `unclassified`.

**F11 — No biodegradation column exists** in `Properties_report` or `Toxicity_Ecosar`.
Available fate-relevant fields: LogP, Henry's law constant, water/methanol solubility, MW, exact
mass, purity, SMILES, ECOSAR structural class, Max Log Kow. See D8.

### Known bugs in `scripts/04_landuse_allocation.py` — NOT YET FIXED

Results from this script must **not** be quoted until these are resolved:

1. **`Area_km2` misused.** It is the watershed (`WtrID`) area repeated on every segment, not a
   per-segment local catchment area. Summing it upstream produced 88,942 km² for a basin of
   ~11,000 km². Must aggregate `CArea_km2` over distinct `CatchID` values instead.
2. **Nearest-segment search is not exact.** The ring expansion returns on the first non-empty ring,
   which does not guarantee the true nearest segment. Allocation distances: median 1,205 m,
   p90 16,301 m, max 51,828 m; 724 features beyond 5 km. Needs a correct search plus clipping of
   the Corine layer to the basin.
3. **Only 29 immediate reaches** out of 670 ordered pairs. Partly genuine — stations sit on separate
   tributaries — but the inferential sample is small and must be reported as a limitation, not
   inflated by using non-immediate pairs.

### Created
`scripts/03_spatial_join.py` · `scripts/04_landuse_allocation.py` (buggy, see above) ·
`scripts/90_figures.py` · `paper/outline.md` (English, full section and figure plan) ·
`derived/processed/{segments,network_edges,stations_snapped,pressures,segment_pressures,
station_upstream_pressures,reaches}.csv` · `eval/{spatial_join,landuse_allocation}.md` ·
`paper/figures/fig0{1,2,3,4}.{pdf,svg}`

Figures are **vector only (PDF + SVG), English only**, generated entirely from `derived/processed/*`;
SVG keeps text as text (`svg.fonttype: none`), PDF embeds TrueType (`pdf.fonttype: 42`).

### Next
1. Fix the three bugs above.
2. Implement detection-onset analysis over the immediate reaches — the core method.
3. Curate the substance → use-class mapping (222 micropollutants) as SKOS with provenance.
4. Pin the environment (`environment.yml`); install `rdflib`, `owlready2`, `pyshacl`, `networkx`.

---

## 2026-08-03 — Session 1: baseline audit, data discovery, concept pivot

### Findings

**F1 — `ProjectOwl_v3.owl` is not the real ontology.**
`Data/Sampling/app_framework.py:10` loads
`http://web.itu.edu.tr/altinbagr/ontology/TheOntologyGISDSS.owl`. Downloaded (393 KB).

| Metric | v3 | TheOntologyGISDSS | 2018 slide claim |
|---|---|---|---|
| Classes | 92 | **72** | 71 |
| Object properties | 21 | **26** | 25 |
| Datatype properties | 8 | **23** | 20 |
| Annotation properties | 0 | **2** | 4 |
| Individuals | 53 | **444** | 437 |
| `rdfs:label` | 0 | **363** | — |
| `rdfs:comment` | 0 | **34** | — |
| disjoint / equivalent / inverse / imports / SWRL | 0 | **0** | — |

→ Baseline is `TheOntologyGISDSS.owl`. Labels are largely solved; **logical content is not**.
Both files keep the Protégé default IRI `.../untitled-ontology-15`, so the identity/FAIR problem
stands for both.

**F2 — The dataset is ~100× larger than the 2018 write-up suggested.**
Not one campaign of 802 measurements, but **four campaigns × 84 stations × ~251 parameters ≈ 82,000
measurements**: Nov 2017, Feb 2018, May 2018, Aug 2018.
Parameters: 13 conventional, 18 metals, 220 micropollutants, 2 toxicity endpoints (EC50-5/15),
2 flow series.

**F3 — Flow data exists** (`Yabataş` m³/s at 75 stations, `Ekoton` at 38).
This is what makes a **mass balance** possible; without it the idea would be dead.

**F4 — Station coordinates exist** in every campaign file (`Enlem`/`Boylam` in DMS, plus
`Yükseklik`), for 75 of 84 stations. The earlier "no coordinates" blocker is resolved.

**F5 — Complete GIS stack present** under `Data/ShapeFiles/`: river network with from/to nodes and
Strahler order, main river, OSB industrial firms and plans, agricultural irrigation polygons,
urban Corine CLC12, admin boundaries. Every branch of the ontology's `PointSources`/`AreaSources`
taxonomy has real geometry behind it.

**F6 — A working DSS engine already exists** (1,739 lines of Python).
`tree_algorithm.py` (844 lines) builds a Strahler-ordered segment tree and already propagates
concentration, flow-rate and **mass load** differences, with `flow_correction` and advice/warning
generation. This is far beyond what the slide deck implied — and it is the seed of the paper's core.

**F7 — The novelty is already latent in the old code.**
`app_framework.py:131` `ControlPollutantConcVSeQS` colours red (`>maxEQS`), yellow (`>averageEQS`),
green (below) — and **grey when the pollutant has no EQS**. The "cannot decide" case exists but is
undocumented, unjustified and unreported. Formalising it is the contribution.

**F8 — Data error found** (useful as a SHACL demonstration): in
`November_Sampling-2018_08_01.xlsx`, station 2 latitude is `41°61'25.5"` — 61 arc-minutes is invalid.
The same station reads `41°05'24.5"` in the other three campaigns.

### Decisions

**D1 — Pivot to "semantic mass balance".** Replaces the earlier three-contribution structure with a
single claim: load balance along the river network, computed under interval arithmetic forced by
censoring, yielding a four-valued verdict per reach. See [`03-concept.md`](03-concept.md).
Rationale: one idea instead of three; makes the reasoner do physical rather than taxonomic work,
which answers the "why an ontology at all?" objection that sinks most ontology papers.

**D2 — Two validations, both free.** Conservative tracers (Cl⁻/SO₄²⁻/Br⁻) calibrate the tolerance
band `τ` and validate topology+flow *before* micropollutants are interpreted; seasonal persistence
across four campaigns separates real discharges from artefacts. Together these pre-empt the obvious
reviewer attack that river mass balances are too noisy to be diagnostic.

**D3 — Keep the algorithmic core, rewrite the plumbing.** The Strahler tree and load-propagation
logic in `tree_algorithm.py` is sound; extract it from the PyQt5 GUI into a tested, deterministic
library with a thin CLI. GUI becomes optional.

**D4 — Raise the target.** With four campaigns, flow, full GIS and ~82k measurements, aim
`Ecological Informatics` / `Environmental Modelling & Software` (Q1) first; `ISPRS IJGI` / `Water` /
`Environmental Monitoring and Assessment` (Q2) as fallback.

**D5 — Be explicit about what OWL does and does not do.** OWL supplies identity, topology,
classification and explanation; arithmetic is materialised by SWRL/SPARQL/Python and then classified.
Claiming the reasoner "computes the mass balance" would be false. See `03-concept.md` §7.

### Gate check — PASSED (`scripts/02_censoring_gate.py` → `eval/gate_check.md`)

Extraction (`scripts/01_extract_campaigns.py`) produced **76,651 measurements**,
4 campaigns × 75 geolocated stations × 258 parameters.

**G1 — The zero-substitution problem is real and large.**
76.9% of all chemical measurements (58,176 / 75,675) are recorded as exactly `0.0`;
**85.2% for micropollutants** (56,768 / 66,600). These are non-detects with their censoring
information erased. Every load, mean or sum computed from this table is biased low by an
unknown amount.

**G2 — Censoring is partially recoverable.**
79 of 254 measured chemical analytes have LOD **and** LOQ, covering 38.1% of the zero records.
The remaining 175 analytes are *structurally* undecidable — which is itself a reportable
result and a direct justification for the `UndecidableReach` class.

**G3 — `LOQ > EQS` analytes EXIST. The sub-claim survives.**
14 analytes have LOQ above the annual-average EQS; 7 above the maximum-allowable EQS.
Worst cases:

| Analyte | LOQ (µg/L) | EQS-AA | ratio |
|---|---|---|---|
| Azinphos-methyl | 5.749 | 0.05 | **115×** |
| Imidacloprid | 2.065 | 0.14 | 15× |
| Fenamiphos | 0.163 | 0.01 | 16× |
| Cadusafos | 0.199 | 0.01 | 20× |
| Fenarimol | 0.701 | 0.07 | 10× |

For these substances a "compliant" reading is an artefact of the analytical method, not evidence
of compliance. This is the `IndeterminateCompliance` case, now empirically grounded.

**G4 — Unexpected bonus: the censoring error runs in *both* directions.**
48 analytes report positive values **below their own LOQ** — i.e. unquantifiable values presented
as if quantified. So the dataset simultaneously (a) substitutes zeros for non-detects and
(b) reports sub-LOQ values as point estimates. Both halves of the censoring problem in one
real monitoring programme. This makes the paper's motivation concrete rather than rhetorical.

**G5 — Data-quality defects found** (SHACL demonstration material):
negative concentrations for Be and Sb (physically impossible); invalid latitude
`41°61'25.5"` at station 2 in the November campaign.

### Created
`README.md` (status board) · `docs/03-concept.md` · `docs/04-progress.md` · `paper/refs.bib`
(~30 entries; those needing field checks carry `note = {VERIFY: ...}`) ·
`scripts/01_extract_campaigns.py` · `scripts/02_censoring_gate.py` ·
`derived/processed/{stations,measurements,parameters,analytes}.csv` · `eval/gate_check.md` ·
repo skeleton.

### Environment note
System Python is 3.8.8 with `openpyxl`, `pandas`, `numpy`, `matplotlib`.
**Missing and required:** `rdflib`, `owlready2`, `pyshacl`, `geopandas`, `pyshp`, `networkx`.
Pinned environment to be created in WP-R.

### Next
1. Extraction script: 4 campaign workbooks → tidy CSV; confirm the ~82k figure.
2. **Gate check** — do analytes with `LOQ > EQS` exist? If not, drop that sub-claim (concept §8 Q1).
3. Quantify censoring: fraction of `<LOD` / `[LOD,LOQ)` / `≥LOQ` per analyte class.
4. Test the risky join: shapefile node IDs ↔ 84 station IDs.

### Blocking
**WP0.5 — data rights.** The ECOSAR batch, ÇKS list, LC-MS/MS methods and the campaign data appear
to originate from a funded project. PI consent and co-authorship must be settled before submission;
advisor Dr. Mehmet Tahir Sandıkkaya should be a co-author. Analysis can proceed meanwhile.
