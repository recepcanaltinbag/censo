# Paper outline

**All paper content is in English. All figures are vector (PDF/SVG), never raster.**

Target: `Ecological Informatics` (Q1) → fallback `Water` / `ISPRS IJGI` / `Environmental
Monitoring and Assessment` (Q2). Word budget ≈ 11,000–12,000.

---

## Working title

**Reasoning about what cannot be measured: an ontology-driven framework linking micropollutant
detection patterns, land use and river topology in the Ergene Basin**

Alternatives:
- *Detection-pattern reasoning: ontology-mediated source-type inference for micropollutants under measurement censoring*
- *Knowing when you cannot know: four-valued ontological inference for river pollution source attribution*

---

## One-sentence contribution

An OWL 2 DL ontology plus rule layer that turns **non-detections into evidence** — using the
downstream-monotonicity of detection along a river network, together with substance-to-land-use
knowledge, to localise and type micropollutant sources, while explicitly marking the reaches where
the data cannot support any conclusion.

---

## Structure and word budget

| § | Section | Words | Key content |
|---|---|---|---|
| 1 | Introduction | 1,200 | micropollutants; censoring destroys information; source attribution is the practical need; gap; contributions list |
| 2 | Related work | 1,400 | water ontologies (WaWO+, OPO, SAREF4WATR, WHOW KG); SOSA/SSN, GeoSPARQL, QUDT; censored environmental data (Helsel); source apportionment; **Table 1 = gap table** |
| 3 | Study area and data | 1,300 | Ergene basin; 4 campaigns × 75 stations × 251 parameters; ÇKS/EQS; ECOSAR; LOD/LOQ; GIS layers; **Table 2 = data inventory** |
| 4 | Ontology | 2,000 | LOT methodology; competency questions; module structure; reuse; **defined classes**; persistence/mobility tier; substance→use→source chain |
| 5 | Inference layer | 1,300 | detection-onset formalism; dilution test; four-valued verdict; SWRL/SHACL split; what OWL does and does not do |
| 6 | Results | 2,000 | censoring quantification; onset map; source-type inference; agreement with land use; seasonal persistence |
| 7 | Evaluation | 1,200 | OOPS!/FOOPS! before-after; CQ coverage; reasoner performance; ablation; expert check |
| 8 | Discussion | 1,000 | what the framework can and cannot claim; policy relevance (PMT/vPvM, WFD); transferability |
| 9 | Conclusions | 400 | |
| — | Data/code availability, CRediT, funding | 200 | Zenodo DOI, w3id ontology IRI |

---

## Section 1 — Introduction

Beats, in order:

1. Micropollutants (pharmaceuticals, pesticides, biocides, UV filters, benzotriazoles, flame
   retardants) are ubiquitous in surface waters and regulated through EQS under the EU WFD, with
   Türkiye transposing them as ÇKS.
2. Monitoring produces very high non-detection rates. Reporting practice substitutes zero or
   half-LOQ, which fabricates data (Helsel 2006). **Our dataset: 76.9% of chemical measurements —
   85.2% of micropollutants — are recorded as exactly 0.0.**
3. Worse, for some substances the analytical method cannot demonstrate compliance at all:
   **14 analytes here have LOQ above their annual-average EQS; Azinphos-methyl by a factor of 115.**
   A "compliant" reading is then an artefact of the method.
4. The practical question is not "is this station compliant" but "**where is this substance coming
   from**". Answering it requires joining chemistry, hydrological topology and land use — three data
   worlds with incompatible identifiers.
5. Gap: existing water ontologies model observations as point values and do not represent detection
   limits, censoring status, or the epistemic state "undecidable". None link substances to source
   types through a use-class chain.
6. Contributions (numbered, explicit):
   - a modular OWL 2 DL ontology reusing SOSA/SSN, GeoSPARQL, QUDT, PROV-O and SKOS, with
     defined classes for censoring and compliance states including `IndeterminateCompliance`;
   - **detection-onset reasoning**, which uses non-detections as upper bounds and therefore extracts
     signal from the 85% of records normally discarded;
   - a substance → use-class → source-type inference chain, validated against independent land-use
     geometry;
   - a reproducible pipeline and a published knowledge graph for a 4-campaign, 75-station,
     251-parameter basin dataset.

---

## Section 2 — Related work · **Table 1 (gap table)**

Rows: WaWO+ · OPO · Ahmedi & Jajaga · SAREF4WATR · WHOW KG · SOSA/SSN alone · **this work**
Columns: standard reuse · spatial topology · analytical provenance (LOD/LOQ) · **censoring
semantics** · regulatory thresholds · ecotoxicity · land-use coupling · rule layer · public ABox ·
FAIR publication

Our row should be the only one filled in the censoring and land-use columns. If it is not, the
novelty claim must be revised — check honestly.

---

## Section 4 — Ontology

- **Name / IRI**: `https://w3id.org/<name>/` with content negotiation; `owl:versionIRI`; CC BY 4.0.
- **Modules**: `core` (observation, censoring, compliance) · `space` (network, reach, catchment) ·
  `chem` (substance identity, properties, use class) · `analytics` (LOD/LOQ, MRM) ·
  `regulatory` (EQS) · `ecotox` (ECOSAR, PNEC) · `pressure` (land use, industry sectors).
- **Reuse**: `sosa:Observation`, `sosa:FeatureOfInterest`; `geo:asWKT`, `geo:sfWithin`;
  QUDT units; `prov:wasDerivedFrom`; `skos:exactMatch` → ChEBI/PubChem.
- **Key defined classes**:
  - censoring: `CensoredObservation`, `EstimatedObservation`, `QuantifiedObservation`
  - compliance: `EQSExceedance`, `PossibleEQSExceedance`, `EQSCompliant`, `IndeterminateCompliance`
  - fate tier: `MobilePersistentSubstance` (low LogP, low Henry, high solubility) —
    the substances for which a strict load balance is defensible
  - onset: `OnsetReach`, `AttenuationReach`, `UndecidableReach`
  - source type: `DomesticSignature`, `IndustrialSignature`, `AgriculturalSignature`,
    `HospitalSignature` — defined over the reach's onset set
- **Competency questions**: 20–25, each mapped to a SPARQL query in `queries/` and to at least one
  axiom. See `docs/05-competency-questions.md`.

---

## Section 5 — Inference layer

Detection-onset formalism, dilution test, four-valued verdict, and an explicit table of
**what is OWL, what is SWRL/SHACL, what is Python** (see `docs/03-concept.md` §7).
State plainly that the reasoner does not perform arithmetic; it classifies materialised bounds.
Overstating this is the fastest way to lose a semantic-web reviewer.

---

## Section 6 — Results (the figures)

| # | Figure | Content | Source |
|---|---|---|---|
| F1 | Graphical abstract | data layers → KG → reasoning → source-type map | `scripts/90_figures.py` |
| F2 | Study area | basin, river network by Strahler order, 75 stations, OSB/agri/urban layers | `90_figures.py` |
| F3 | Censoring profile | % zero-recorded by substance group; LOD/LOQ coverage | `90_figures.py` |
| F4 | LOQ vs EQS | 14 analytes where LOQ > EQS, log scale, ratio annotated | `90_figures.py` |
| F5 | Ontology modules | module/import diagram | drawn, exported SVG→PDF |
| F6 | Detection-onset map | reaches coloured by onset count, sized by pressure delta | pending |
| F7 | Source-type agreement | predicted source type vs land use, confusion matrix | pending |
| F8 | Seasonal persistence | onset stability across 4 campaigns | pending |
| F9 | Evaluation | OOPS! before/after, reasoner timing | pending |

| # | Table | Content |
|---|---|---|
| T1 | Gap table vs existing ontologies |
| T2 | Dataset inventory |
| T3 | Ontology metrics (baseline vs v5) |
| T4 | Competency questions → SPARQL → result |
| T5 | Reach-level source-type inference results |

---

## Section 8 — Discussion: limitations to state plainly

Reviewers punish concealment far more than limitation. State all of these:

1. **Only 29 immediate reaches** — stations sit on separate tributaries, so the reach-level
   inferential sample is small. Report it; do not inflate by using non-immediate pairs.
2. **Nearest-segment allocation** of land use is first-order; catchment polygons were unavailable.
   Sensitivity to the allocation rule must be shown.
3. **ECOSAR toxicity is QSAR-predicted**, not measured.
4. **Sector inference from company names** is a heuristic (77.4% coverage); unclassified firms are
   not forced into a class.
5. **Four snapshot campaigns**, not continuous monitoring; flow is instantaneous.
6. **No biodegradation half-lives** in the source data; the persistence tier is derived from LogP,
   Henry's constant and solubility. BIOWIN predictions from SMILES would strengthen this.
7. Attribution is **topological proximity, not a hydraulic transport model**.
8. Agreement with land use is corroboration, **not ground truth**.

---

## Author / admin checklist (blocking for submission)

- [ ] Data rights and PI consent; co-author list and order (advisor Dr. M. T. Sandıkkaya)
- [ ] Mint w3id IRI; publish ontology with WIDOCO documentation
- [ ] Zenodo DOI for ontology + ABox + code + queries
- [ ] Resolve the August campaign year (sheet says 2017, filename says 2018)
- [ ] Verify all `note = {VERIFY}` entries in `refs.bib`
- [ ] CRediT statement, data availability statement, funding statement
