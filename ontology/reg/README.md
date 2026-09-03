# Regulation packages

Each file here is a **self-contained, versioned regulation package**. Adding, amending or
superseding a regulation never requires touching `censo-core.ttl`, `censo-regulation.ttl` or the
domain layer — you drop in a new file and load it.

That is the whole point: thresholds expire, the framework should not.

---

## Why packages instead of hard-coded values

| Problem with hard-coded thresholds | What packages give you |
|---|---|
| Ontology is obsolete the day a directive is amended | Add a file, keep everything else |
| One dataset, one verdict | Assess the same data under **several** packages at once; the divergence is a result |
| Historic surveys locked to historic rules | Re-assess a 2018 survey under a 2026 directive |
| Substances a regulation covers but the survey never measured vanish silently | Become explicit `cereg:NotCoveredBySurvey` |
| No audit trail | Every threshold cites `cereg:sourceDocument` and carries a `cereg:transcriptionStatus` |

---

## Planned packages

| File | Package | Status |
|---|---|---|
| `tr-yskly-2016.ttl` | Yerüstü Su Kalitesi Yönetmeliği, as amended 2016 — **the version the project's ÇKS spreadsheet reflects** | ⬜ to transcribe |
| `tr-yskly-2023.ttl` | YSKY as amended 1 Feb 2023 (RG 32091) — current Turkish law | ⬜ to transcribe |
| `eu-eqs-2013.ttl` | Directive 2008/105/EC as amended by 2013/39/EU | ⬜ to transcribe |
| `eu-eqs-2026.ttl` | 2026 update: PFAS (24-sum + TFA), pharmaceuticals, bisphenols, pesticide metabolites, total-pesticide 0.2 µg/L | ⬜ to transcribe |

> **None are transcribed yet, deliberately.** Values must be taken from the primary legal text, not
> from the project spreadsheet. See "Verification" below — this is a blocking task, not a detail.

---

## Anatomy of a package

```turtle
@prefix censo: <https://w3id.org/censo/> .
@prefix cereg: <https://w3id.org/censo/reg/> .
@prefix ex:    <https://w3id.org/censo/reg/eu-eqs-2026/> .

<https://w3id.org/censo/reg/eu-eqs-2026> a owl:Ontology ;
    owl:imports <https://w3id.org/censo/reg/> ;
    owl:versionInfo "2026-02-17" .

ex:package a cereg:RegulationPackage ;
    rdfs:label "EU environmental quality standards, 2026 update"@en ;
    cereg:jurisdiction "EU" ;
    cereg:legalReference "…as published in the Official Journal…" ;
    cereg:sourceDocument <https://eur-lex.europa.eu/…> ;
    cereg:inForceFrom  "2026-..-.."^^xsd:date ;
    cereg:complianceDeadline "2039-12-31"^^xsd:date ;
    cereg:supersedes <https://w3id.org/censo/reg/eu-eqs-2013/package> .

# --- a per-substance threshold -------------------------------------------
ex:atrazine-aa a censo:AnnualAverageThreshold ;
    censo:appliesToAnalyte  chebi:CHEBI_15930 ;      # aligned, not renamed
    censo:thresholdValue    0.6 ;
    censo:thresholdUnit     unit:MicroGM-PER-L ;
    censo:requiresCondition ex:inlandSurfaceWater ;
    cereg:transcriptionStatus cereg:Unverified .      # until checked against OJ

# --- a group threshold: the aggregate is what is regulated ---------------
ex:pesticides-total a cereg:GroupThreshold , censo:AnnualAverageThreshold ;
    cereg:appliesToGroup        ex:pesticidesGroup ;
    cereg:aggregationFunction   cereg:Sum ;
    cereg:requiresCompleteGroup false ;
    censo:thresholdValue        0.2 ;
    censo:thresholdUnit         unit:MicroGM-PER-L .

ex:pfas-24-sum a cereg:GroupThreshold ;
    cereg:appliesToGroup        ex:pfas24Group ;
    cereg:aggregationFunction   cereg:Sum ;
    cereg:requiresCompleteGroup true .   # partial sums are NOT assessable
```

Note `requiresCompleteGroup`. For the 24-PFAS sum it is `true`, so a survey that measured no PFAS
yields `cereg:NotCoveredBySurvey` rather than a comfortable zero. This single flag is the difference
between honest and misleading reporting.

---

## Adding a jurisdiction

1. `cp _template.ttl <code>.ttl` — code as `<iso2>-<instrument>-<year>`.
2. Fill in the `cereg:RegulationPackage` header, including `cereg:sourceDocument`.
3. Add thresholds. Reuse analyte IRIs; **never mint a new IRI for a substance that already exists** —
   align with `skos:exactMatch` to ChEBI/PubChem instead.
4. Declare applicability conditions explicitly. A metals threshold almost always needs
   `censo:FractionCondition` (dissolved) and often `censo:BioavailabilityCondition` or
   `censo:HardnessClassCondition`. Omitting them makes the package silently over-permissive.
5. Set `cereg:transcriptionStatus` honestly — `cereg:Unverified` until someone has compared the file
   against the legal text line by line.
6. Validate: `python scripts/validate_ontology.py ontology/reg/<code>.ttl`.

---

## Verification protocol (blocking before publication)

The project's ÇKS spreadsheet is a **secondary source** and a reviewer-eye audit already found
values that need checking against the primary text:

| Analyte | Value in spreadsheet (µg/L) | Concern |
|---|---|---|
| Cu | AA 0.05 | Below typical natural background and below most LOQs. Implausible as a whole-water standard. |
| Al | AA 2.2 | Background Al in surface water is 10–100 µg/L; this threshold would be exceeded everywhere by construction. |
| Sn | AA 0.01, no MAC | Unusually low for total tin; possibly a tributyltin value mis-assigned. |
| Cd | AA 0.25 / MAC 1.5 | Corresponds to the **most permissive hardness class**. Hardness was not measured, so the applicable class is unknown. |
| Pb, Ni, Cu, Zn | — | EU AA-EQS are **bioavailable** concentrations requiring hardness + DOC + pH normalisation. Hardness and DOC were not measured. |
| Hg | AA 0.07 | The EU water AA-EQS was replaced by a biota standard in 2013/39/EU. |
| Anthracene, Dichlorvos | absent | EU priority substances, measured in the survey but carrying no threshold in the spreadsheet. |

Every one of these becomes a modelled `censo:PreconditionUnmet` or `censo:IndeterminateCompliance`
rather than a silent pass — which is exactly the paper's argument, demonstrated on its own inputs.

**Rule: no value enters a package without `cereg:sourceDocument` pointing at the legal text, and no
analysis quotes a threshold whose `transcriptionStatus` is still `cereg:Unverified`.**

---

## Design decisions worth knowing

**Thresholds are individuals, not classes.** They are instances of `censo:Threshold` subclasses, so
adding a regulation adds only ABox content. No TBox change, no reasoner surprises, no risk of
breaking existing inferences.

**Analytes live in the domain layer, not in packages.** A package references analytes; it does not
define them. This keeps two packages covering the same substance pointing at the same IRI, which is
what makes cross-regulation comparison meaningful.

**Conditions are first-class.** A threshold with unmet preconditions yields *no verdict*, not a
default pass. This is the modelling claim: a threshold is a conditional judgement, not a number.

**Packages are additive.** Loading two packages never causes conflict, because verdicts are always
relative to a `cereg:Assessment` that names its package.
