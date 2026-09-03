# Semantic Mass Balance — the formalism

Status: draft v0.1 · 2026-08-03

This is the scientific core of the paper. Everything else (ontology modules, ABox pipeline,
GIS layers, evaluation) exists to serve this one idea.

---

## 1. Motivation

Existing water-quality ontologies (WaWO+, OPO, SAREF4WATR, the Water Health KG) treat a measurement
as a **point value**. In micropollutant monitoring that assumption is false for most observations:
concentrations fall below the limit of detection (LOD) or between LOD and the limit of quantification
(LOQ). Two consequences are routinely ignored in practice:

1. **Substituting a number for a non-detect fabricates data** (Helsel 2006). Half-LOQ substitution is
   still the norm and it biases every downstream aggregate.
2. **For some analytes LOQ > EQS.** The analytical method literally cannot demonstrate compliance.
   Reporting "compliant" in that case is not a finding — it is an artefact of the method.

The 2018 project's own code already hits this and papers over it: `app_framework.py:131`
`ControlPollutantConcVSeQS` returns red / yellow / green against `maxEQS` / `averageEQS`, and a
neutral grey `#808780` when the pollutant has no EQS at all. The grey box is undocumented and
unreported. **This paper turns that grey box into a formal, reasoned conclusion.**

---

## 2. Load and its interval

For an observation of analyte `a` at station `s` in campaign `t`:

```
L(a,s,t)  =  C(a,s,t) · Q(s,t)          [mass · time⁻¹]
```

with `C` in µg L⁻¹ and `Q` in m³ s⁻¹ → `L` in mg s⁻¹ (report as kg d⁻¹).

Censoring makes `C` an interval rather than a number:

| Reported state | Interval `[C⁻, C⁺]` | Rationale |
|---|---|---|
| `< LOD` | `[0, LOD]` | presence not excluded, magnitude bounded above |
| `[LOD, LOQ)` | `[LOD, LOQ]` | detected, not reliably quantified |
| `≥ LOQ` | `[C(1−u), C(1+u)]` | `u` = combined relative analytical uncertainty |

Hence `L ∈ [C⁻·Q⁻, C⁺·Q⁺]`, with flow uncertainty handled the same way.

> **Design decision.** Intervals, not distributions. Interval arithmetic is *sound* (never claims
> more than the data supports), needs no distributional assumption about non-detects, and maps
> directly onto OWL/SWRL. A probabilistic (ROS/MLE, Helsel 2012) treatment is a natural extension
> and belongs in Discussion, not in the core.

---

## 3. The balance at a reach

A **reach** `r` is a river segment between two topological nodes, taken from
`Erg_river_Hydro.shp` (which carries from-node, to-node and Strahler order).

Let `in(r)` be the set of segments flowing into `r`'s upstream node and `out(r)` the observation at
`r`'s downstream node. The reach balance for analyte `a` in campaign `t`:

```
Δ(r,a,t)  =  L_out(r,a,t)  −  Σ_{i ∈ in(r)} L_i(a,t)
```

Under interval arithmetic:

```
Δ⁻ = L⁻_out − Σ L⁺_in            (most favourable to "balance closed")
Δ⁺ = L⁺_out − Σ L⁻_in            (least favourable)
```

A **tolerance band** `τ(r,a,t)` absorbs legitimate physical effects that are not unaccounted sources:
ungauged lateral inflow, groundwater exchange, in-stream decay/sorption, and flow-gauging error.
`τ` is calibrated on the conservative tracers (§5), not assumed.

---

## 4. The four-valued verdict

```
ConfirmedUnaccountedSource(r,a,t)   ⟺   Δ⁻  >  τ
PossibleUnaccountedSource(r,a,t)    ⟺   Δ⁻ ≤ τ  <  Δ⁺
BalanceClosed(r,a,t)                ⟺   Δ⁺ ≤ τ   ∧   width(Δ) ≤ w_max
UndecidableReach(r,a,t)             ⟺   Δ⁺ ≤ τ   ∧   width(Δ) >  w_max
```

`w_max` is the width beyond which the interval is so wide that "balanced" carries no information —
i.e. censoring dominates. **The distinction between `BalanceClosed` and `UndecidableReach` is the
paper's central epistemic contribution:** an ontology that can only say "compliant / non-compliant"
cannot express *"the data cannot answer this"*, and therefore silently converts analytical
limitation into apparent good news.

The same four-valued treatment applies to compliance:

```
EQSExceedance(o)          ⟺  C⁻(o) > EQS(a)
PossibleEQSExceedance(o)  ⟺  C⁻(o) ≤ EQS(a) < C⁺(o)
EQSCompliant(o)           ⟺  C⁺(o) ≤ EQS(a)
IndeterminateCompliance(o) ⟺  ¬∃EQS(a)  ∨  LOQ(a) > EQS(a)
```

The last disjunct — `LOQ > EQS` — is the "method cannot decide" case. **Empirical verification that
such analytes exist in this dataset is a WP1 gate; if the set is empty, this sub-claim is dropped.**

---

## 5. Validation without extra data

### 5.1 Conservative tracer test (validates topology + flow, before any interpretation)
Cl⁻, SO₄²⁻ and Br⁻ are conservative at reach timescales: no decay, no volatilisation, negligible
sorption. Therefore for these analytes the balance **must** close, and any residual is attributable
to topology error, flow-gauging error, or ungauged inflow — not to chemistry.

Procedure:
1. Compute `Δ` for Cl⁻, SO₄²⁻, Br⁻ over all reaches and campaigns.
2. Calibrate `τ` as an upper quantile (e.g. 95th) of `|Δ|/ΣL_in` from the tracer residuals.
3. Reaches where even tracers fail badly are marked `TopologyUnreliable` and **excluded** from
   micropollutant inference.

This inverts the usual criticism ("river mass balances are noisy") into a quantified, reported
error model. It is the single most important defensive move in the paper.

### 5.2 Seasonal persistence (distinguishes real discharges from artefacts)
Four campaigns: Nov 2017, Feb 2018, May 2018, Aug 2018. A genuine continuous discharge should
appear in most campaigns; a one-off is either an intermittent discharge or an artefact.

Report per flagged reach: persistence `k/4`, and stratify by hydrological condition
(high flow Feb vs. low flow Aug) — dilution behaviour further discriminates point sources
(load roughly constant, concentration dilutes) from diffuse sources (load scales with flow).
**This dilution signature is itself a classification rule and a second original element.**

### 5.3 Independent spatial corroboration
Flagged reaches are matched via GeoSPARQL against candidate sources already available as geometry:
OSB firms and plans (`osbler/`), agricultural irrigation polygons (`tarimalanlari/`), and urban
Corine areas (`urban/`). Agreement is corroboration, not ground truth — state this explicitly.

---

## 6. Why an ontology is required (the "why not just a script?" defence)

A reviewer will ask this. The answer must be structural, not decorative:

1. **Heterogeneous joins over identity.** The same substance appears across five sources under
   different names (campaign sheets, ÇKS list, LOD/LOQ table, ECOSAR output, properties table).
   Reconciliation via CAS/SMILES/`skos:exactMatch` to ChEBI is an identity problem — exactly what
   a knowledge graph is for, and a recurring source of silent error in spreadsheet workflows.
2. **Topology as inference, not as code.** `upstreamOf` is a transitive property; reach containment
   is `geo:sfWithin`. Upstream closure comes from the reasoner, not from a hand-written traversal
   that must be re-verified whenever the network changes.
3. **The verdict is a defined class, not a flag.** Because the four verdicts are OWL class
   definitions over interval bounds, each conclusion carries its own justification and can be
   explained to a regulator (Protégé/`owlready2` explanation). A boolean column cannot.
4. **Provenance is first-class.** PROV-O links each verdict to campaign, analytical method, LOD/LOQ
   version and EQS revision. When the regulation changes, affected conclusions are queryable.
5. **Reuse.** Grounding in SOSA/SSN + GeoSPARQL + QUDT means the model transfers to any basin with
   the same observation structure; the paper's contribution is not "an Ergene script".

---

## 7. Implementation split (what is OWL, what is not)

Honesty here is worth more than an inflated OWL claim. Reviewers of ontology papers punish
overstatement.

| Task | Mechanism | Why |
|---|---|---|
| Taxonomy, disjointness, domain/range | **OWL 2 DL** | classification, consistency |
| Upstream closure, reach containment | **OWL** transitive props + GeoSPARQL | native |
| Interval arithmetic (`Δ⁻`, `Δ⁺`, `τ`) | **SWRL built-ins** / SPARQL `BIND` | OWL cannot do arithmetic |
| Four-valued verdict assignment | **defined classes** over materialised bounds | explainable |
| Data-quality constraints | **SHACL** | closed-world validation OWL cannot express |
| Load computation, tracer calibration | **Python** (deterministic, tested) | numerics belong in code |

**Stated plainly in the paper:** OWL provides identity, topology, classification and explanation;
arithmetic is materialised by rules and code, then *classified* by the ontology. Claiming a reasoner
"computes the mass balance" would be false and a reviewer would catch it.

---

## 8. Open questions

| # | Question | Resolution path |
|---|---|---|
| 1 | Do analytes with `LOQ > EQS` actually occur here? | WP1 gate — join `CKS_FEnCY-2` LOD&LOQ sheet with ÇKS list |
| 2 | Are `Yabataş` and `Ekoton` the same quantity, different providers? | Inspect overlap on the 38 shared stations |
| 3 | Do shapefile node IDs join to the 84 station IDs? | WP4 — this join is the pipeline's main risk |
| 4 | Is 4-campaign flow sufficient, or is continuous gauging needed? | Sensitivity analysis on `τ` |
| 5 | Decay for non-conservative micropollutants — ignore or first-order? | Ignore in core (conservative assumption → `Δ` is a *lower* bound on the unaccounted source); discuss |
| 6 | Which reaches have no downstream station at all? | Coverage map; these are structurally undecidable |

---

## 9. Working title candidates

1. *Semantic mass balance: censoring-aware ontological reasoning for locating unaccounted
   pollution sources in a river basin*
2. *Knowing when you cannot know: a four-valued ontological framework for river pollutant
   load budgets under measurement censoring*
3. *From non-detects to decisions: an ontology-driven mass-balance screening framework for
   micropollutant source attribution in the Ergene basin*
