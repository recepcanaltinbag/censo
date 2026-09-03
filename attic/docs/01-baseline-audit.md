# Baseline ontology audit

Two OWL files exist. Establishing which is the real baseline was the first task, because the 2018
slide deck quotes figures that match neither the file in the project folder nor each other.

---

## 1. Which file is the baseline?

`Data/Sampling/app_framework.py:10` loads:

```python
self.onto = get_ontology("http://web.itu.edu.tr/altinbagr/ontology/TheOntologyGISDSS.owl")
```

That file was still served and has been downloaded to the repository root (393 KB).
**`TheOntologyGISDSS.owl` is the baseline. `ProjectOwl_v3.owl` is an earlier draft.**

| Metric | `ProjectOwl_v3.owl` | **`TheOntologyGISDSS.owl`** | 2018 slide claim |
|---|---|---|---|
| Named classes | 92 | **72** | 71 |
| Object properties | 21 | **26** | 25 |
| Datatype properties | 8 | **23** | 20 |
| Annotation properties | 0 | **2** | 4 |
| Named individuals | 53 | **444** | 437 |
| `rdfs:label` | 0 | **363** | — |
| `rdfs:comment` | 0 | **34** | — |
| `owl:Restriction` | 19 | 23 | — |
| disjointness axioms | **0** | **0** | — |
| equivalent classes | **0** | **0** | — |
| inverse properties | **0** | **0** | — |
| `owl:imports` | **0** | **0** | — |
| SWRL rules | **0** | **0** | — |

The baseline is close to the slide figures. Keep `ProjectOwl_v3.owl` — the v3 → v5 delta makes a
strong before/after evaluation figure (WP6).

---

## 2. What the baseline already does well

- **Labels.** 363 `rdfs:label` and 34 `rdfs:comment`. The v3 criticism ("unreadable to a domain
  expert") is largely resolved.
- **Populated ABox.** 444 individuals, including geolocated `SingularIndustrial` /
  `OrganizedIndustrial` instances.
- **EQS already modelled** as `maxEQS` / `averageEQS` datatype properties on pollutants.
- **Richer domain coverage** than v3: `Toxicity` (EC50-5, EC50-15), `PollutantDomain`,
  `Micro` / `Conventional` / `Metal`, `WaterProperty`, `WaterFlowSecond`, `hasNumericalValue`,
  `Hospital`, `Municipality`.
- **Sensible measurement pattern**: `Observation ─measure→ Measurement ─measurementOf→ Pollutant`,
  with `hasQuantity`, `hasNumericalValue`, `measuredBy`, `makingIn`.

---

## 3. What must change before publication

### 3.1 Identity and FAIR (blocking)
IRI is still the Protégé default:
`http://www.semanticweb.org/recep/ontologies/2018/0/untitled-ontology-15`
— contains a personal username, a placeholder `/0/` month, the literal word "untitled", and is not
dereferenceable. No `owl:versionIRI`, no `owl:versionInfo`, no licence, no creator, no title.
Fails FAIR F1, F2, A1, R1.1.

**Fix:** mint `https://w3id.org/<name>/` with content negotiation; add full `dcterms` metadata,
`owl:versionIRI`, CC BY 4.0.

### 3.2 The ontology is logically inert (the central problem)
Zero disjointness, zero equivalent classes, zero inverses, zero property characteristics beyond one
transitive role, zero rules. A reasoner therefore **infers nothing beyond the asserted taxonomy**,
and reports "consistent" trivially — there is no construct present that *could* produce a
contradiction. Presenting a successful reasoner run as validation would not survive review.

**Fix:** add disjointness partitions, inverse pairs, defined (necessary-and-sufficient) classes for
the four-valued verdicts, and the SWRL/SHACL layer (WP3, WP5).

### 3.3 No standard reuse
Zero `owl:imports`. The ontology re-derives, by hand, vocabularies that are W3C/OGC standards:

| Module in the file | Standard it duplicates |
|---|---|
| `Observation`, `Observer`, `ObservationPoint`, `Device`, `Person`, `observe`, `makingIn` | **SOSA/SSN** |
| `Spatial`, `Point`, `Line`, `Polygon`, `latitude`, `longitude`, `within`, `locatedIn` | **GeoSPARQL** + Basic Geo |
| `UnitOfMeasure`, `Prefix`, `Singular`, `Compound`, `Division`, `Multiplication`, `numerator`, `denominator`, `symbol` | **OM / QUDT** (essentially OM 1.8's vocabulary renamed) |
| `CAS`, `MolecularFormula`, `ExactMass`, `LogP`, `Solubility`, `ChemicalStructure` | **ChEBI / CHEMINF** |
| `River`, `Watershed`, `Catchment`, `Basin`, `RiverSegment` | **HY_Features / INSPIRE** |
| labels, definitions, mappings | **SKOS**, **Dublin Core** |

This is the single most likely reason for rejection at a semantic-web-aware venue.
**Fix:** import SOSA/SSN, GeoSPARQL, QUDT (or OM 2), PROV-O, SKOS; align chemistry via
`skos:exactMatch` to ChEBI. Delete the 35 hand-built unit individuals.

### 3.4 Coordinates are strings
`latitude` / `longitude` / `altitude` are typed `xsd:string`. For a paper whose title contains
"GIS-based", coordinates that are not numerically comparable and not usable by any geospatial
tooling are indefensible.
**Fix:** `xsd:double` plus `geo:asWKT` geometry.

### 3.5 Modelling errors carried over from v3
Verify each against the baseline before fixing — some may already be corrected there:

1. `HeavyMetal` and `Metal` as siblings — heavy metals *are* metals.
2. `Pollutant` children mix two partition criteria (composition vs. provenance) with no disjointness.
3. `Industry` is an orphan root, disconnected from `PollutionSources`.
4. `isA` object property duplicates `rdf:type`.
5. **Attribute-as-class**: `ExactMass`, `LogP`, `Solubility`, `CatchmentArea`, `SegmentLength` are
   classes with no data property — the ontology can say "there exists a LogP" but never *what it is*.
6. `numerator` / `denominator` / `prefix` declared as sub-properties of `observation` — incoherent
   grouping that pollutes any query over `observation`.
7. `isPartOf` is not transitive while `locatedIn` is — mereological containment is exactly where
   transitivity is needed; this looks inverted.
8. `Length ⊑ (measuredBy value kilometre) ⊔ (measuredBy value metre)` hard-codes two units into the
   TBox, making cm/mm/miles unrepresentable.
9. Malformed IRIs in v3: `#1`–`#5` (leading digit), `#'Ergene_River'` (quote characters in the IRI).
10. Typos baked into IRIs: `Compund`, `Theoritical`, `Organometalic`.

### 3.6 Silent wrong inferences (v3; re-test on the baseline)
Because nothing is disjoint, wrong assertions classify cleanly instead of raising an error:

- `'Ergene_River'` is inferred to be a `RiverSegment` (nodes assert `within 'Ergene_River'`, and
  `within` has range `RiverSegment`).
- `Arsenic`, `Barium`, `Beryllium` are inferred to be `Quantity ⊔ UnitOfMeasure` (they carry
  `symbol`, whose domain is that union) — chemical elements classified as units of measure.

Adding the disjointness axioms of §3.2 turns both into genuine inconsistencies that must then be
fixed in the data. **This is the argument for why disjointness matters, and it should appear in the
paper as a worked example.**

---

## 4. Expressivity

v3 sits at roughly `SHOQ(D)` — OWL 2 DL, but outside OWL Lite, EL, QL and RL. The expressivity is
"expensive but empty": full DL complexity is paid for a taxonomy that a SKOS thesaurus would express.
Re-measure the baseline with a reasoner once the environment is pinned.

---

## 5. Verdict

The baseline is a competent domain vocabulary with good lexical coverage and a real populated ABox.
It is **not** a publishable ontology artefact, for three reasons in priority order:

1. no standard reuse (§3.3)
2. no logical content — nothing to reason over (§3.2)
3. non-citable, non-FAIR identity (§3.1)

All three are fixable within WP3. None requires new data.
