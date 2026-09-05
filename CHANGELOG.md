# Changelog

Every entry says what changed, in which files, and **why** — the reason is the
part worth keeping. Newest first. Numbers quoted here are recomputed by
`scripts/99_audit.py`; where an entry states one, the audit checks it.

---

## 2.0.0 — 2026-09-04

**MAJOR, because terms were removed.** Twenty-one of the ninety-three declared
terms are retired: each was either redundant with a vocabulary this ontology
already imports (PROV-O, OWL versioning, ChEBI), a redundant reification of
something already derivable, a class contradicting the ontology's own
open-world commitment, or a class no shipped data could reach. A consumer who
loaded 1.0.0 will break on 2.0.0, and semantic versioning exists to say so.

`https://w3id.org/censo/1.0.0` still resolves to what 1.0.0 was. That had to be
fixed to be true: `scripts/97_assemble_publish.py` read the version out of the
file and copied the current build into `releases/<version>/`, so every run
silently rewrote `releases/1.0.0/` with whatever the vocabulary currently was —
it had already become a 50-class file where 1.0.0 was 58. A release directory is
immutable now, and the assembler refuses rather than overwrites.

The regulation packages move to 2.0.0 with it. Their comment used to justify
staying at 1.0.0 on the grounds that no DOI had been issued and the
permanent-identifier request was open, so no 1.0.0 was in anyone's hands. That
stopped holding once the packages went up at the IRI w3id.org redirects to: this
release removes `cereg:groupCoverage` from every group and adds a
`censo:MatrixCondition` to every threshold, and a consumer of the 1.0.0 files
would break on both.


### FIXED — four unowned numbers, and each one made a different check lie

`scripts/99_audit.py`, `paper/sections/05-results.tex`.

The clean run failed with six errors. Four were the same defect, and this
changelog had already named it: *"An unowned number does not merely go
unchecked: it makes some other check lie, because the near-match detector
attributes it to the nearest computed value."* It happened four more times, all
of them to numbers this correction cycle introduced.

| the check that failed | what it blamed | what was actually loose |
|---|---|---|
| `AL: no flag no limit %` (56.06) | "asserts 54" | §5.9's *"none of CHMO's **54** object properties"* |
| `censored rows carrying a positive value %` (99.41) | "asserts 95" | the 99.4 itself — a real quantity the text never stated, so the detector took the Wilson **95** |
| `decade 1e-2` (17.36) | "asserts 17.9" | §5.6's confidence bound **17.9**, recomputed by nothing |
| `dual: exceeding -> compliant` (5041) | "asserts 4646" | §5.12's SHACL violation count **4,646**, traceable but recomputed by nothing |

Every one is now owned rather than removed, except the CHMO property count,
which came from a cached file and not from a pipeline artefact and is dropped
from the prose:

- **99.4 is asserted**, in §5.1 beside the 55.0 it was being confused with:
  counted over censored rows alone rather than the whole record, where a row is
  flagged at all it almost always carries a substituted number too.
- **`check_reported_intervals()`** recomputes the two Wilson bounds of the
  co-regulated divergence from the same counts, with the same formula the report
  uses, rather than reading them back out of the report.
- **`check_shacl_conformance()`** now puts its violation count through
  `check_claim`, so 4,646 has an owner.
- **`check_graph_matches_population()`** recomputes the materialised sample's
  method-insufficient share, the 17.2 % that §5.4 pairs against the population's
  17.5 % as evidence that expressing the record loses nothing. It was printed by
  stage 23 and checked by nobody.

The two that were not misattribution were real:

- **The gap-table profile moved and the manuscript did not.** Pruning the
  vocabulary removed `MassSpectrometryTransition`, `AnalyticalRun` and
  `analysedSample`, all of which the profiler counts as sampling terminology, so
  CENSO's sampling-to-sensing score fell from 6/0 to **3/0**. Restated.
- **`91_ontology_figure.py` was never registered as a stage**, so the figure
  went stale the moment the ontology changed. Registered after `90_figures.py`.
  Rerunning it fired its own guard —

      not an owl:Class: censo:CensoredAmbiguous
      The figure is a claim about the vocabulary. Fix the spec in this
      script, or the ontology, but do not draw it.

  — which is exactly what it was built to do: the class had been retired and the
  spec still drew it. 45 edges verified.

**192 checks, 162 passed, 0 failed**, one warning: the two author-owned
`\pending{}` markers (Zenodo DOI, tool disclosure) that belong to submission.

### FIXED — the DL consistency check was reading 99.9 % stumps

`scripts/99_audit.py::check_graph_is_consistent`.

The check exists because its absence let a real defect ship: the axiom suite ran
on fixtures, SHACL cannot see a `complementOf` restriction, and between the two
no stage ever put the actual ABox in front of an OWL reasoner. It extracted
observation blocks with

    re.findall(r"wb:obs-\d+ a [^.]*\.", txt)

— *anything but a dot, then a dot*. Every decimal value in an observation
contains a dot, so **39,964 of the 40,000 blocks were cut at their first
number**: after the detection status, and before the compliance outcome, the
comparison property and the bounds. The check written to reason over the real
graph was reasoning over stumps.

It survived because a bare numeral made the truncation *valid*. The text ended
`...resultLowerBound 0.`, and Turtle reads that as the integer 0 followed by a
statement terminator, so the slice parsed, the closure ran, and the check
passed. Typing the literals turned it into `..."0.` — an unterminated string —
and the parser said so on the next run. **A silent wrong answer became a loud
failure**, which is the only reason this is a changelog entry rather than still
shipping.

Blocks are read by line now. The slice covers 162 observations against 9/9
outcome classes, and the `PossibleExceedance` ⊑ `IndeterminateCompliance`
witness count went from **2 to 25** — the truncated blocks rarely reached the
outcome type at all.

### Added — §5.12, because a validation nothing cites is not evidence

`paper/sections/05-results.tex`.

`18_shacl_validate.py` runs the published shapes over the published graph for
over an hour and returned `conforms: False` on every run, and was cited by
nothing: not the manuscript, not the supplementary material, not the audit. The
failure was real — 41,396 literals written as bare Turtle numerals against
shapes requiring `xsd:decimal` — and is now fixed, so the section can report
what the stage actually finds: one violation type, 4,646 observations citing no
analytical method, which is the unresolvable population and a property of the
record rather than of the pipeline.

Reporting a non-conforming validation requires saying which failures are
findings and which are defects, so the audit is given the list rather than a
blanket "must conform" that would have pressured the pipeline into inventing
the missing datum.

### FIXED — two triple counts the manuscript quoted from a smaller graph

`paper/sections/05-results.tex`. The ABox grew when
`censo:conditionSatisfied` began to be asserted, so 465,744 → **501,062** and
the competency-question load 471,582 → **507,708**. Caught by
`95_numbers_manifest.py`, which is what it is for; 123 of 123 numeric claims now
trace to a generated artefact.

### FIXED — the ontology validator failed the one module doing what it asks

`scripts/validate_ontology.py`, `scripts/20_align_external.py`.

Adding `censo-alignment.ttl` put a sixth module in front of the validator and it
stopped the chain at 5/6. Both findings were the validator's own:

- the alignment header carried `owl:versionInfo` and no `owl:versionIRI`, which
  the validator requires for FAIR F2/R1.1. Correct, and now emitted.
- the logical-axiom census counted `equivalentClass`, `disjointWith`,
  `inverseOf`, `FunctionalProperty`, `TransitiveProperty` and `Restriction` —
  and not `owl:sameAs`. So it warned "no logical axioms at all — a reasoner will
  report 'consistent' trivially" over a file whose entire logical content is 30
  identity assertions. A warning that fires on the one module doing the thing it
  asks about is a broken warning. `owl:sameAs` and `owl:equivalentProperty` are
  in the census now.

### Added — the alignment the vocabulary has been claiming since v1.0.0

`scripts/20_align_external.py` → `ontology/censo-alignment.ttl`,
`eval/alignment.md`; gated by `check_alignment()` in `scripts/99_audit.py`.

`censo:Analyte` carried the comment *"Aligned to ChEBI/PubChem with
skos:exactMatch rather than renamed, so that two regulation packages referring
to the same substance resolve to one IRI — the precondition for comparing
them."* The released artefact contained **no alignment triples at all**. The
single occurrence of `skos:exactMatch` anywhere in the ontology was inside that
sentence.

That is the third commitment shipped as prose — after `requiresCondition` and
after `AnalyticalRun` above. §5.7's comparison did work, by joining CAS strings
in Python, which is a different mechanism from the one the vocabulary described.
Now the described mechanism exists:

- **299 of 354** analytes across both packages point at exactly one ChEBI class
  by CAS registry number. **26** resolve to more than one and are deliberately
  left unaligned — ChEBI often models a substance and its conjugate base
  separately, and picking one would be a silent editorial decision inside a file
  meant to be evidence. **29** have no ChEBI entry: C10–13 chloroalkanes,
  tributyltin compounds, brominated diphenylether congeners. That a regulation
  sets a limit on something no chemical ontology names as one substance is a
  finding about the regulation.
- **30 `owl:sameAs` pairs** reconcile the two packages —
  `analyte-eu-Thiacloprid owl:sameAs analyte-tr-Tiakloprid` — so the
  co-regulated stratum is an entailment. The audit requires the entailment to
  cover the join: **all 26** substances the dual-regulation analysis treats as
  co-regulated are reachable through a `sameAs` pair.

**The relations are argued, not defaulted.** `rdfs:seeAlso` to ChEBI, because a
`censo:Analyte` is a `sosa:ObservableProperty` — the concentration *of* a
substance — and a ChEBI class is the substance, whose instances are molecules.
`skos:exactMatch` between them would be a category error dressed as
interoperability, and SKOS mapping properties are defined over `skos:Concept`,
which neither is. Same reasoning for `censo:limitOfDetection` →
`CHMO:0002801`: theirs is an `owl:Class`, a figure of merit of an assay; ours is
an `owl:DatatypeProperty`. `owl:sameAs` is used once, where there is an
identity. The comment on `censo:Analyte` is corrected to say all of this.

The module is **not imported** by `censo-core.ttl` and is not merged into
`censo-full`. A consumer who does not want commitments about ChEBI should not
have to take them — the same reason the regulation packages are separate files —
but it is published at the permanent IRI, because an alignment nobody can
dereference reconciles nothing.

### FIXED — a functional-property axiom the released package violated, invisibly

`ontology/censo-core.ttl`; gated by `check_functional_properties()` in
`scripts/99_audit.py`.

`censo:casNumber` was declared `owl:FunctionalProperty`. Three entries in the
released EU package carry two registry numbers each, because Annex I names more
than one form of a single regulated substance:

| substance | CAS |
|---|---|
| Diclofenac | 15307-86-5 (free acid), 15307-79-6 (sodium salt) |
| Acetamiprid | 135410-20-7, 160430-64-8 |
| Imidacloprid | 105827-78-9, 138261-41-3 |

A regulatory entry is not a single chemical species. **The data were right and
the axiom was wrong**, so the axiom is gone.

It was invisible, and the reason is the now-familiar one. Under DL semantics a
functional datatype property with two distinct literals on one individual is an
inconsistency. OWL 2 RL discharges functionality by deriving `owl:sameAs`
between the two literals and stops — verified here: loading the core, the
vocabulary and the EU package and running the RL closure yields
**0 `owl:Nothing`**. So the audit's own package-consistency check, which asks
exactly that question, passed on every run.

The new gate reads the functional-property declarations out of the vocabulary
and looks for multi-valued subjects directly, over the modules and both
packages: 12 functional properties, 1,611 subject–property pairs. Restoring the
retired axiom in memory makes it report exactly the three entries above, which
is the ablation this project asks of its axiom tests.

This is also what made the `owl:sameAs` alignment safe: merging two analytes
whose CAS sets differ would have produced a clash under the old axiom.

### CHANGED — the vocabulary is 68 terms, not 93, and every one of them does work

`ontology/censo-core.ttl`, `ontology/censo-regulation.ttl`,
`scripts/19_build_regulation_packages.py`, `scripts/23_waterbase_abox.py`,
`scripts/91_ontology_figure.py`, and the manuscript throughout; gated by
`check_no_dead_terms()` in `scripts/99_audit.py`.

**29 of 93 declared terms appeared in no shipped graph, no regulation package,
no shape and no competency question.** Among them were `censo:AnalyticalRun`,
`censo:producedByRun` and `censo:runUsedMethod` — that is, the FIRST of the four
commitments, the one the abstract and five section openings were built around.
`grep AnalyticalRun derived/abox/*.ttl` returned nothing, and had from the
beginning.

This is the same defect as the fourth-commitment entry below, and the audit
could not see either one: a term nobody instantiates makes no *number* wrong,
and 179 checks recompute numbers. `check_no_dead_terms()` closes it
permanently — a declared term must be exercised somewhere a reader can see it,
or be enumerated as abstract with a reason.

**21 terms retired.** The reasons, because "unused" is not by itself one:

- `AnalyticalRun`, `producedByRun`, `runUsedMethod` — **redundant with an
  imported vocabulary.** A run is a `prov:Activity` that `prov:used` a sample
  and generated an observation; the method it executed already carries the
  limits. And no European release reports a run identifier, so minting one per
  aggregated station-year would not simplify but *misstate*: an annual mean
  spans many runs. The commitment is unchanged and now stated as what the
  artefact demonstrates — the limit is declared on the method, as CHMO also
  does, and **carried onto the result** as `censo:resultUpperBound`, which CHMO
  cannot do. The discriminating column is a three-step sequence now: sensor
  (SSN-system) → method (CHMO) → result (here).
- `MassSpectrometryTransition`, `precursorIon`, `productIon`, `retentionTime` —
  instrument detail with no role in the argument. Their own comment boasted the
  level "is absent from every water ontology surveyed" while being absent from
  this one's graph too.
- `derivedFromRecord` — reinvented `prov:wasDerivedFrom`.
- `regulationVersion` — reinvented `owl:versionInfo`, which every package
  already carries.
- `smiles` — structure belongs in ChEBI, which `censo:Analyte` aligns to.
- `calibrationSlope` — where LOD and LOQ are stated the slope they were derived
  from adds nothing; `calibrationR2` stays, because a shape constrains it.
- `analysedSample` — `prov:used` says it.
- `ClassBoundaryThreshold`, `FractionCondition` — real distinctions that no
  package this work ships can instantiate. A class no data can reach is a
  promise, not a term. `FractionCondition`'s argument is kept in §5.4 as the
  next thing the machinery should decide.
- `cereg:Assessment`, `assessedUnder`, `assessmentOutcome` — **redundant
  reification.** The observation already carries `exceeds`/`belowThreshold` per
  threshold and the threshold carries `definedBy` → package, so which
  jurisdiction reached which verdict is derivable without a fourth node.
- `cereg:NotCoveredBySurvey` — **contradicted this ontology's own stated
  design.** The core says the never-measured case is deliberately not a class,
  because under the open world assumption not asserting the observation is how
  one says it was not made.
- `cereg:groupCoverage` — declared as the *fraction* of a group measured,
  domained on the reified assessment, ranged `xsd:double`, and emitted by the
  builder as the integer *count* of declared members, on the group. Three
  mismatches in one triple. Replaced by real `cereg:memberOfGroup` triples,
  from which the count is `COUNT`.
- `inForceUntil`, `complianceDeadline`, `supersedes`, `metaboliteOf`,
  `RelevantMetabolite`, `NonRelevantMetabolite` — emitted by nothing.

**8 terms exercised instead of cut**, and two of those were correctness fixes:

- **`censo:MatrixCondition`, and this one mattered.** Annex I sets four values
  per substance — annual average and maximum allowable, each for inland surface
  waters and for other surface waters — and `10_parse_eu_eqs.py` reads all four
  by column position with 212 hand-checked against the consolidated text. The
  package builder then emitted only the inland pair **and said nothing about
  it.** So the released package published thresholds whose matrix was unstated,
  which is the bare-number failure this vocabulary exists to prevent, in its own
  artefact: benzene is 10 µg/L inland and 8 elsewhere, and a threshold that does
  not say which water it governs cannot be applied. Every threshold now carries
  a matrix condition. Same for the Turkish package's river columns.
- **Not every applicability condition is unsatisfiable**, and discovering that
  averted a disaster. `23_waterbase_abox.py` read *every* `requiresCondition` in
  the package as an unmet precondition, so adding the matrix condition would
  have typed **every assessment in the graph** `censo:PreconditionUnmet` and
  destroyed the 43.8 % decomposition. The test is not whether a condition
  exists but whether the record can supply what it NAMES:
  `censo:requiresCovariate` is that test. The hardness-class and bioavailability
  conditions require hardness, dissolved organic carbon and pH, none of which
  WISE-6 reports — 3 CAS numbers, unchanged. The matrix condition names no
  covariate and is satisfied, because the population is river water and rivers
  are inland surface waters — 61 CAS numbers, and the graph now asserts
  `censo:conditionSatisfied` rather than leaving applicability to be assumed.
  Cross-check after the change: streaming 17.5 % against graph 17.2 %, agree.
- `cereg:memberOfGroup` — 90 membership triples across the four group standards,
  including 75 minted CAS-keyed analytes the regulation names only inside the
  pesticide sum. "Was every member measured", the question that decides an
  aggregate verdict, is answerable by query now instead of only in Python.
- `cereg:TranscriptionStatus`, `cereg:AggregationFunction` — every threshold
  referenced `cereg:VerifiedAgainstPrimarySource` and `cereg:Sum` and neither
  individual was ever typed, so two classes had no instances while their
  instances had no class.
- `cereg:transposes` — the Turkish regulation transposes the European directive.
  That is why two packages are comparable at all and §5.7 rests on it; it was in
  prose and is now one triple in the package.

No headline number moves. `validate_ontology.py` passes 5/5, `test_axioms.py`
10/10, and the streaming/graph cross-check agrees.

### CHANGED — the comparison set reaches outside the water domain, and the patterns stopped favouring us

`scripts/07_verify_gap_table.py`, `scripts/13_separation.py`,
`scripts/99_audit.py`, and the manuscript throughout.

The gap table compared 18 ontologies, **all of them water or sensor domain**,
while `censo-core.ttl` claims applicability to "food safety residues, clinical
assays, soil contaminants, occupational exposure". A domain-independence claim
tested inside one domain is not tested. Added CHMO (the OBO Chemical Methods
Ontology), AFO (the Allotrope Foundation Ontology) and STATO: **21**.

**CHMO declares `limit of detection` (CHMO:0002801) and `limit of
quantification` (CHMO:0002802), both defined from the IUPAC Gold Book.** So the
concept exists, is well defined, and is cited to the authority — and CHMO binds
it to the *method*, as a `figure of merit` of an assay, with none of its 54
object properties relating a limit to a result. This is the result we would most
have expected to lose, and it is now the sharpest row in the table.

Three defects in `detection_limit_binding()` had to be fixed before an OBO
vocabulary could be compared at all:

1. limit entities were found by matching the IRI's **local name only**, which
   finds nothing in `CHMO_0002801`. The row would have reported the concept
   present and its binding unknown, in the same row;
2. the default was `system`, so an ontology whose limit had no informative
   superclass was reported as binding it to a **sensor** — a claim CHMO cannot
   support, having no sensor concept at all. `unclear` is its own value now, and
   the 2018 baseline moved to it;
3. `OBS_TERMS` lumped `AnalyticalMethod` and `Procedure` in with observation and
   result, so a limit on a METHOD scored as bound to the RESULT. Those are
   different claims and the difference is the argument.

**The concept patterns were widened, deliberately in the competitors' favour.**
They had matched our spellings and missed other people's: not `limit of
quantitation` (the pharmacopoeial spelling a laboratory ontology is most likely
to use), not `below detection limit` (the most ordinary phrasing there is), not
`minimum value` spelled out, not `undetermined` or `unresolved` bare, not
`maximum residue level`. Every widening can only add a *yes* to a competitor's
row, because CENSO's cells are already filled — so a claim that survives the
wider matcher is worth something and one that depends on spelling is not.

**It cost a headline.** The collapse claim went from *all 18* to **20 of 21**.
CHMO now separates the two readings, on `ambiguous synonym` — an OBO annotation
property about the quality of a *synonym* — and `unresolved lines`, an NMR
technique. The cell is left standing and the discrepancy published in a new
"Scored **yes**, but not the same concept" section, because narrowing a pattern
until a competitor loses a cell would make the whole table an assertion again.

Two audit consequences:

- the universal moved. "Every vocabulary collapses R1 into R2" was the wrong
  thing to make unfalsifiable-by-audit: it is downstream of a keyword matcher,
  so a generous pattern breaks it without any competitor gaining a capability,
  which creates pressure to narrow patterns until the build passes. The
  universal is now the claim that carries the contribution — **no comparison
  vocabulary carries a censoring status** — and it holds for all 21 under
  patterns admitting `censor`, `left-censor`, `non-detect`, `not quantifiable`
  and `below … limit` bare. STATO is the sharpest negative: censoring is routine
  in survival analysis and STATO declares no term for it and does not mention it
  in a single definition.
- `13_separation.py` fails on an **undeclared** separation rather than on the
  count, against `KNOWN_SEPARATORS`, each entry carrying a reason checkable by
  reading the named term's superclass. That is where a real competitor
  capability would surface.

### FIXED — the shipped report dropped the largest reason a verdict cannot be reached

`scripts/22_waterbase_external.py`; gated by
`check_report_indeterminate_total()` in `scripts/99_audit.py`.

`eval/waterbase_external.md` printed

> Taken together, **173,768 (25.0%) of these assessments are not decidable**

three lines under a table whose rows sum to **304,836 (43.8 %)** — the number
§5.4, the conclusions and the README all state. The sum omitted
`precondition_unmet`, 131,068 assessments, the largest single reason in the
table it was summarising and the one the fourth commitment exists to produce.
It was added to the taxonomy, to the decision procedure and to every count the
manuscript quotes, and not to this one line.

Nothing objected, and the reason is structural rather than careless: 179 checks
audit the **manuscript** — a claim in the LaTeX against a value recomputed from
`derived/processed`. A generated report is neither. `check_numbers_are_shipped()`
asks whether an asserted number occurs in some artefact; it never asks whether
an artefact's own arithmetic is right. So the audit recomputed 43.8 % from the
same CSV, passed, and wrote its report beside one that said 25.0 %.

The new check recomputes the total and requires the report to state it.

### FIXED — the shipped graph contradicted its own shapes, in 41,396 literals

`scripts/23_waterbase_abox.py`, `scripts/19_build_regulation_packages.py`,
`ontology/censo-shapes.ttl`; gated by `check_abox_datatypes()` and
`check_shacl_conformance()` in `scripts/99_audit.py`.

`eval/shacl_validation.md` reported **`conforms: False`** with 37,115
violations of one kind — `Value is not Literal with datatype xsd:decimal` — and
had done so on every run.

The cause is one line: the ABox wrote `censo:resultLowerBound 0`. A bare Turtle
numeral is typed by its lexical form, so `0` is an `xsd:integer` and `0.5` an
`xsd:decimal`, and the graph carried whichever the value happened to produce:
32,898 integer lower bounds, 4,184 upper bounds, 4,047 reported values, 234
quantification limits, and 16 `censo:thresholdValue` in the released EU package
— `censo:thresholdValue 10`, in the file whose whole purpose is to be the
citable exact limit.

**No OWL check can object to this, and that is the point.** `rdfs:range
xsd:decimal` is satisfied by an `xsd:integer`, because integer is *derived from*
decimal. Worse, the core asserts

    CensoredObservation ⊑ resultLowerBound value "0.0"^^xsd:decimal

which is a statement about a literal **term**. `0` is not that term, so all
31,167 censored observations in the graph carried an axiom they could not
satisfy — invisibly, because OWL 2 RL's hasValue check never fired on a literal
it did not match.

`dec()` now emits canonical decimal lexical form and a new `lit()` writes the
typed literal; `disp()` keeps labels reading "2 µg/L" rather than "2.0 µg/L".
`censo:ThresholdShape` and `censo:AnalyticalMethodShape` gained
`sh:datatype xsd:decimal`, so the constraint is now enforceable where it could
not be before.

Not fixed, because it is not ours to fix: **the float32 artefacts are in the
EEA source.** `procedureLOQValue` arrives as `0.009999999776482582` —
exactly `float32(0.01)` — 7,181 times in the first 1.5 M rows alone, along with
`0.10000000149011612` and `0.07999999821186066`. Fifteen observations in the
materialised slice have a limit that is float-noise-below an EQS the record
states as exactly equal to it. No verdict flips today, because the comparison is
strict and the noise happens to fall the safe way; had it fallen the other way
those rows would move from `Compliant` to `MethodInsufficient`. Rounding a
reported measurement is a data-semantics decision and is left to the author, but
the record now says plainly that the release the paper audits stores legal
quantification limits in single precision — which is the ontology's NUMERIC TYPE
argument, found in the wild.

### FIXED — stage 18 validated the artefact and nothing read the answer

`scripts/00_run_all.py` has run `18_shacl_validate.py` from the start. It takes
**82 minutes**, puts the shipped knowledge graph in front of the published
shapes, and returns `conforms: False`. `eval/shacl_validation.md` is cited
**nowhere**: not in the manuscript, not in the supplementary, not in the audit,
and not in the staleness table.

This is the same blind spot the "shipped knowledge graph contradicted its own
ontology" entry below describes closing, one step further along. There the
complaint was that no stage put the real ABox in front of an OWL reasoner. Here
a stage does put it in front of SHACL, the answer is *no*, and no stage reads
it. A failing validation that costs nothing is not a validation.

`check_shacl_conformance()` now fails the build on it, and `check_staleness()`
requires the report to be newer than the shapes, the core and the graph — so a
stale `conforms: True` cannot satisfy the new gate either.

### CHANGED — the vocabulary no longer requires a limit of detection

`ontology/censo-core.ttl`.

`censo:AnalyticalMethod` was declared `owl:cardinality 1` on
`censo:limitOfDetection`. **The shipped graph has zero `limitOfDetection`
triples**, so all 1,159 methods in it violated the axiom.

`censo-shapes.ttl` was relaxed to require *a* limit — of quantification, of
detection, or both — when it emerged that no European release reports a
detection limit and the only graph satisfying the old shape did so by
manufacturing the datum at LOD = LOQ/3. The TBox was not relaxed with it, and
neither validator could see the gap: OWL 2 RL ignores a minimum cardinality in
superclass position, and the relaxed shape accepts the LOQ alone.

What survives is a **disjunction** — at least one of LOD, LOQ — and
`owl:unionOf` in superclass position is outside OWL 2 RL, the profile this
ontology commits to. It therefore lives where it can be enforced, as
`censo:AnalyticalMethodLimitShape`. The `censo:limitUnit` restriction stays.

The header's claim that "cardinality restrictions **reject** observations with
no analyte, no unit or no procedure" is corrected in the same commit. Under the
open world assumption a minimum cardinality entails the existence of a filler
and rejects nothing; it is SHACL that rejects, because it closes the world
locally. The disjointness, exhaustiveness and `owl:hasKey` axioms do reject, and
`scripts/test_axioms.py` still shows each of them failing when removed.

### FIXED — one class, two counts, in two files the manuscript cites

`scripts/test_axioms.py`. T5's rationale counted every outcome whose key starts
with `indeterminate`, which swept in `indeterminate_other` — a **quantified**
row whose value contradicts the limit beside it. Such a row has a detection
status, so it is not a `censo:UnresolvedObservation` and T5's axiom says nothing
about it. The rationale therefore claimed 45,509 for a class
`eval/waterbase_external.md` puts at 45,467. Now filtered to
`indeterminate_unresolved`.

### FIXED — one quantity's name was doing duty for two

`scripts/99_audit.py`, `scripts/94_restate.py`, `README.md`.

2,306,365 station-years report a below-LOQ result carrying a positive number.
Over all 4,190,833 station-years that is **55.0 %**, which is what §5.1 asserts.
Over the 2,320,139 censored ones it is **99.4 %**, which is the denominator the
era table in §5.2 uses for its 99.6 / 99.3. Both are right. They were sharing
one label, `censored rows carrying a positive value %` — under which the audit
computed the first and `94_restate.py` computed the second.

That is worse than an unowned number. `eval/RESTATE.md` is the file this
changelog designates as the authority for repairing prose after a correction,
*expressly* in preference to the audit's near-match pairings; it offered 99.4
for a sentence whose correct value is 55.0. Both are now computed, under names
that say their denominator, in both files. The README's row was labelled for the
second and carried the first; it now names what it counts.

### Added — the vocabulary figure, generated and verified against the TTL

`scripts/91_ontology_figure.py` → `paper/figures/fig09_ontology_graph.{svg,pdf}`,
`eval/ontology_figure.md`.

What CENSO inherits from SOSA/SSN/PROV/QUDT and what it adds, in one diagram,
organised by the four commitments rather than by namespace, with
`ssn-system:DetectionLimit` drawn as the thing being displaced — the limit moves
from the sensor to the analytical run and the result.

The layout is authored, because no force-directed algorithm lays out a semantic
argument. Every **edge** is verified against `censo-core.ttl` and
`censo-regulation.ttl` before the figure is written: 53 of them, plus seven
axioms carried as annotations. A `rdfs:subClassOf` the ontology does not assert,
a property drawn between a domain and a range it does not declare, or a datatype
property shown on the wrong class stops the build. The 2018 project figure in
`attic/` outlived three axiom changes; this one cannot drift, it can only fail
to compile.

### FIXED — the abstract reported the wrong number for the paper's central claim

`paper/sections/00-abstract.tex`; gated by `check_abstract_introduces_nothing()`
in `scripts/99_audit.py`.

The abstract said **4,181** exceedances "affirmable in law". Section 5.4,
Figure 5's caption and the conclusions all say **14,505** — a factor of 3.5, on
the number the whole substitution argument turns on, in the first paragraph a
referee reads.

Three checks looked at it and none objected. `check_verdict_claims()` recomputes
14,505 and finds it in the manuscript, which it is, three times over — just not
in the abstract. `check_numbers_are_shipped()` asks whether a value occurs in
some generated artefact, and 4,181 does: it is the count of `possible_exceedance`
rows a two-valued pipeline calls compliant, an unrelated quantity that happens to
share the digits, so the traceability report certified it against
`mac_exceedance.csv`. A number can be individually well-formed, individually
traceable, and still be the wrong number in the wrong sentence.

The new check is the mirror of `check_conclusions_introduce_nothing()`: an
abstract summarises, so every quantity in it must appear in a section. It also
caught 59,251 and 200,708 — the endpoints of the substitution range — which were
asserted in the abstract and drawn in Figure 5 but never written in the body.
They are now in §5.4, where the argument is made.

### CHANGED — compliance is three-valued, and the third value records why

`ontology/censo-core.ttl`, `ontology/censo-shapes.ttl`,
`scripts/23_waterbase_abox.py`, `scripts/22_waterbase_external.py`, and the
manuscript throughout.

The vocabulary declared four top-level compliance outcomes while the paper's
central number counted three. **43.8 % not decidable** has always been the sum
of `PossibleExceedance`, `MethodInsufficient`, `PreconditionUnmet` and the rows
with no bound at all — that is, `PossibleExceedance` was already being counted
as a species of indeterminacy by the arithmetic and as a peer of `Exceedance` by
the taxonomy. One of the two was wrong, and it was the taxonomy: an interval
straddling the limit decides nothing.

- `censo:PossibleExceedance` is now `rdfs:subClassOf censo:IndeterminateCompliance`.
- `censo:ComplianceOutcome` is the union of **three** classes, not four. The three
  are what the Directive admits: met, not met, or not determinable.
- **Added `censo:BoundNotEstablished`.** Making the parent abstract exposed a
  hole: 45,467 station-years (6.5 %, the largest single reason after the two
  named provisions) were being typed with the bare parent and carried no answer
  to "why". It covers both populations that reach it — no flag and no limit to
  build an interval from, and a value contradicting the limit reported beside
  it — because neither establishes a bound to compare.
- A `sh:SPARQLRule` materialises it, and the **precedence** where two subclasses
  describe one result (Article 3(3b) decides; the row is `MethodInsufficient`)
  is now stated in the ontology instead of buried in the manuscript's
  Limitations.

Not changed: the `owl:AllDisjointProperties` axiom over
`exceeds`/`possiblyExceeds`/`belowThreshold`, which is where exclusivity lives,
per observation–threshold pair. The subclasses are deliberately **not**
disjoint from one another, for the same reason the outcomes are not disjoint at
the class level — one observation may be `MethodInsufficient` against one
jurisdiction's standard and `PossibleExceedance` against another's, which is
what §5.7 depends on.

No headline number moved: 43.8 % and its parts (18.8 / 17.5 / 6.5 / 1.0) are the
same arithmetic on the same four reported fields. What changed is which class
each part is reported under, and that `IndeterminateCompliance` is now reached
by subsumption rather than asserted.

### FIXED — the shipped knowledge graph contradicted its own ontology

`scripts/23_waterbase_abox.py`; gated by `check_graph_is_consistent()` in
`scripts/99_audit.py`.

Found while making the change above. The ABox asserted
`censo:assessableAgainst` on **every** observation including
`censo:UnresolvedObservation`, which the core forbids —

    UnresolvedObservation subClassOf complementOf(assessableAgainst some Threshold)

the same axiom `scripts/test_axioms.py` T5 exercises and passes. 45,467
observations, and loading the graph beside the regulation package that types the
threshold made it **inconsistent**.

Nothing caught it because nothing looked. T5 ran on a hand-written fixture; the
graph was validated with SHACL, which has no complement operator and cannot see
the axiom at all. Between a fixture-based axiom suite and a shape-based graph
validator, no stage ever put the real ABox in front of an OWL reasoner. The new
audit check does, over a slice drawn to cover every outcome class, and fails the
build on a contradiction or on a class the slice cannot find.

The threshold still reaches the observation through the analyte, which is how
the shapes locate it and is the fact that makes such a row assessable in
principle and undecidable in practice.

### FIXED — the threshold table was mis-parsed, and it changed the headline

Fixed in `scripts/10_parse_eu_eqs.py`; gated by
`check_threshold_transcription()` in `scripts/99_audit.py`, which hand-reads ten
substances from the consolidated text and fails the build if the parse does not
reproduce all twenty values. The whole chain has been rerun. What moved:

| | before the fix | after |
|---|---|---|
| station-years with a European standard | 759,257 | **742,591** |
| limit above the standard | 23.6 % | **19.3 %** |
| fails the 30 % criterion | 46.6 % | **36.4 %** |
| not decidable | 38.4 % | **34.3 %** |
| substitution swing | 65,129–230,318 (3.5x) | **60,898–191,415 (3.1x)** |
| maximum-allowable undecidable | 10.9 % | **7.3 %** |
| co-regulated divergence | 18.5 % | **18.1 %** |

The argument is unchanged; the numbers were inflated. `eval/RESTATE.md` carries
every current value, generated from the data. The manuscript still quotes the
pre-fix figures and must be restated against that file — NOT against the
audit's near-match detector, which pairs a computed value with whatever
asserted value happens to be numerically close and crosses quantities when it
does.

One consequence worth noting: the analytical failure across the 2015 boundary
is now 36.3 % to 36.6 %. It does not rise, it does not fall. "Does not move" is
now literally true.

`scripts/10_parse_eu_eqs.py` reads Annex I from the consolidated PDF. The
extraction renders a multi-digit integer with a space between its digits —
benzene's row comes out as

    71-43-2 200-753-7  1 0  8  5 0  5 0

which is `10 | 8 | 50 | 50`, the annual average and maximum allowable for inland
and other surface waters. The tokeniser reads every digit as a separate number
and assigns `aa_inland = 1`, `aa_other = 0`, `mac_inland = 8`. Five of the 63
entries are wrong in this way, all of them by a factor of ten and all of them
high-volume industrial solvents:

| substance | parsed | Annex I |
|---|---|---|
| Benzene | 1.0 | **10** |
| 1,2-Dichloroethane | 1.0 | **10** |
| Dichloromethane | 2.0 | **20** |
| Tetrachloroethylene | 1.0 | **10** |
| Trichloroethylene | 1.0 | **10** |

Separately, Annex I states **no** maximum allowable concentration for
1,2-dichloroethane, dichloromethane, tetrachloroethylene or trichloroethylene —
the cells read "not applicable" — and the parser fills them with the next number
it finds. `scripts/27_mac_exceedance.py` therefore assesses roughly a fifth of
its undecidable samples against a standard that does not exist.

An annual average ten times too strict inflates both legal tests, so the two
headline shares (46.6 % failing the 30 % criterion, 23.6 % with a limit above
the standard) are too high and must be restated after the fix.

THE FIX. Column boundaries survive extraction as runs of **two or more**
spaces, while the spaces inside a number are single. Splitting the tail on
`\\s{2,}` and only then joining digit runs recovers the right fields; verified
by hand against benzene, 1,2-dichloroethane, dichloromethane, anthracene,
cypermethrin, diuron and endosulfan. Scientific-notation rows need care and are
not fixed by that rule alone: chlorpyrifos extracts as
`4,6 × 10 -44,6 × 10 -50,00265,2 × 10 -4` with no separator at all, and the
exponent match is greedy, so those entries must be handled before any splitting.

A hand-checked reference list of known Annex I values belongs in
`scripts/99_audit.py` as a hard gate, so that a mis-parse fails the build
instead of propagating into every count. That is what this defect argues for,
and it is the paper's own thesis turned on its own inputs: a threshold carried
without verification is not trustworthy, and ours was not verified.

### FIXED — the figure of the four-valued assessment drew three values

`90_figures.py` built figure 5 from an `outcomes` tuple that listed every
verdict except `possible_exceedance`. Two consequences, both visible in the
printed figure:

- each substitution bar lost 6,628 exceedances, so the three conventions
  appeared to disagree by a factor of 3.4 where the data give **3.1** — the
  factor the caption, §5.3 and the conclusions all state;
- the CENSO bar spanned 723,618 of 742,591 assessments. The 18,973 missing from
  the right-hand end were the whole `PossibleExceedance` class: the one figure
  whose subject is the fourth outcome was the one place it was not drawn.

Plotted now: 60,898 / 160,702 / 191,415 against the population, and a five-part
CENSO bar that an assertion requires to sum to 742,591 before the figure is
written. The audit gained the three-part decomposition (19.3 % + 12.4 % + 2.6 %)
and a check that the parts sum to the 34.3 % quoted in the same sentence.

### FIXED — "only 3,356 record a change of method" said the opposite of the truth

§5.3 argues the quantification limit belongs to the analytical run and not to
the instrument, from two facts: 56.4 % of multi-year station--substance pairs
report more than one limit, "and only \num{3356} record a change of analytical
method code". The second reads as *the method rarely changed*. The counter that
produced it only ever accumulates a **non-empty** method code, so a pair whose
method field is never filled has an empty set and counts as unchanged.

Measured: of \num{557956} multi-year pairs, only **\num{13654} --- 2.4 % ---
report an analytical method code at all**, and \num{3356} of those that do
report more than one. So where the record says anything about the method, it
changed about a quarter of the time; for 97.6 % of pairs the record does not
say. That is a stronger finding than the sentence it replaces, and it points the
same way: a vocabulary that binds the limit to a sensor cannot express a limit
that moves, and one that binds it to the run at least has somewhere to put the
provenance this record is missing.

The denominator is now stated in the text and recomputed by the audit. Found by
reading the counter rather than the claim --- the claim was internally
consistent, checkable, and reproducible, and still meant the wrong thing.

### FIXED — the fourth commitment was declared and never exercised

A referee found it and it was true: "a threshold is a conditional judgement" is
one of the four commitments the paper claims distinguish CENSO, and the released
packages emitted **zero** `censo:requiresCondition` triples,
`censo:PreconditionUnmet` was instantiated **zero** times, and cadmium --- the
paper's own worked example --- was assessed against a single unconditional
0.08 µg/L across **43,655** station-years. A claimed contribution, present in the
TBox and absent from everything else.

The vocabulary was already right. `HardnessClassCondition` names cadmium in its
own comment; `BioavailabilityCondition` names lead and nickel and says "Absent
those covariates, no compliance statement is possible". The conceptual layer
asserted the claim before the record was read. What was missing was the wiring.

**What was built.** Annex I creates the conditions in two footnotes, quoted:

> (9) "For Cadmium and its compounds (No 6) the EQS values vary depending on the
> hardness of the water as specified in five class categories..."
>
> (12) "These EQS refer to bioavailable concentrations of the substances."

The parser now captures the footnote markers a value or name cell cites --- 
cadmium's is in its NAME cell, so reading value cells alone found nothing for the
one substance whose standard is explicitly conditional. `19_build_regulation_packages.py`
attaches the conditions to the six thresholds they govern (cadmium, lead, nickel
x AA + MAC) with `censo:requiresCovariate` naming hardness, dissolved organic
carbon and pH. `23_waterbase_abox.py` reads them **from the released package**,
not from a list of its own, so the graph and the vocabulary cannot disagree about
when a standard applies. The decision procedure returns `precondition_unmet`
**first** --- before the value, the limit and Article 3(3b) --- because where the
standard is defined on a quantity the record does not report there is no
comparison to make, strict or lenient. Six ordering cases and two controls were
added to the self-test, which now runs 32 cases.

**What the record returns.** WISE-6 reports no hardness, no dissolved organic
carbon and no pH on the row, so neither condition can be evaluated from the
aggregated release. **131,068 assessments --- 18.8 % of every station-year a
European standard reaches --- are `PreconditionUnmet`.** Cadmium, lead and nickel
are among the most reported substances in the record; this is not a marginal
stratum.

And it moves the central claim, in the direction the paper argues:

| quantity | before the fourth commitment | after |
|---|---|---|
| not decidable as reported | 36.7 % (three reasons) | **45.3 % (four)** |
| exceedances the law can affirm | 10,746 | **4,181** |
| exceedances asserted against an inapplicable standard | (counted as affirmed or set aside) | **30,140** |
| `PossibleExceedance` | 18,971 | **6,449** |

So **30,140** of the exceedances a half-limit pipeline reports are asserted
against a standard that is not defined on what was measured --- and a further set
are reported as compliance with it. New §5.5 reports this, and makes the point the
other three commitments cannot: a precondition travels with the *regulation*, not
with the measurement, so a threshold column has nowhere to record that a
threshold was inapplicable and no way to tell that from a threshold that was met.

### FIXED — Annex I was still mis-parsed, and this one moved every headline

Four independent referees converged on the same place, and they were right. Three
distinct defects, all in the four EQS columns the whole paper rests on:

- **Empty cells.** Mercury (21) and hexachlorobenzene (16) have **empty**
  annual-average cells --- their standards are set on biota. Flattened text
  cannot tell an empty cell from a missing one, so reading the row left to right
  put the maximum-allowable values into the annual-average columns and then took
  the biota entry as the maximum allowable. Mercury shipped with a fabricated
  annual average of 0.07 and a **maximum-allowable standard of 11** against a
  true 0.07.
- **Footnote markers inside value cells.** Lead reads `1,2 (12)`. The marker was
  read as the number 12 and shifted every column after it, giving lead a
  maximum-allowable standard of **1.3 against a true 14** --- 10.8x too strict,
  and that column is what the whole maximum-allowable analysis is computed
  against. Nickel the same.
- **Positive exponents.** Carbamazepine's maximum allowable is written
  `1,6 x 10 3` = 1600. The parser read 1.6, then swallowed the next column and
  produced **103160**.

None of this is reachable by regex: the information is **positional**, and
flattening throws the position away. `10_parse_eu_eqs.py` now reads the four
columns by **column position** from `pdftotext -layout`, anchored on each page's
own `AA-EQS AA-EQS MAC-EQS MAC-EQS` labels --- not on the `(1) (2) ... (13)`
index line, which is *centred* over each column while the data is *left-aligned*,
a six-character offset that had benzene's annual average at 8 instead of 10.
Cells are taken whole (runs separated by two or more spaces) so a window boundary
can never cut a value in half. If `pdftotext` is missing the stage **exits**
rather than falling back to the flattened guess.

**The hand-read gate went from 10 substances x 2 columns to 53 Annex I rows x 4
columns: 212 values, all reproduced.** The old gate covered neither of the two
empty-cell rows nor either footnote row, which is how this survived it.

Every count moved. The authoritative values are regenerated by the new
`scripts/94_restate.py` --- written because the audit's near-match detector is
the wrong tool for repairing prose after a large correction: it pairs an asserted
value with whatever recomputed value happens to be near, and reported
"asserts 60898 where the data give 61034" beside "asserts 60898 where the data
give 59251" for two different quantities.

| quantity | was | now |
|---|---|---|
| station-years with a European standard | 742,591 | **696,168** |
| limit above the standard | 19.3 % | **22.2 %** |
| fails the 30 % criterion | 36.4 % | **40.1 %** |
| not decidable as reported | 34.3 % | **36.7 %** |
| exceedances at zero / half / full | 60,898 / 160,702 / 191,415 | **59,251 / 171,285 / 200,708** |
| substitution fold-change | 3.1 | **3.4** |
| exceedances the law can affirm | 10,866 | **10,746** |
| created by the half-LOQ substitution | 99,804 | **112,034** |
| co-regulated verdicts that change | 18.1 % | **17.7 %** |
| MAC: assessable samples | 8,470,300 | **8,148,785** |
| MAC: undecidable | 7.3 % | **10.2 %** |
| metals / organics below LOQ | 47.1 / 76.8 % | **43.8 / 77.3 %** |

### FIXED — "the rest are artefacts of the substitution" was false in both halves

Confirmed by a referee that re-streamed the whole release and reproduced the
verdict table row for row, then by me from the shipped CSV. Three of the four
strata are **identical at every substitution constant**, so 59,251 exceedances
(34.6 % of the half-limit total) cannot be artefacts of the constant, and 30,264
rest on a quantified value above the standard --- not 10,746.

What 10,746 actually is: the exceedances **the law can affirm** --- quantified,
above the standard, from a method meeting the performance criterion, with an
interval that does not straddle it. Corrected in the results, the figure caption,
the abstract, the highlights, the conclusions, the figure title and the README;
the audit now recomputes all five strata separately plus the invariance.

### Added — the record year by year, because a two-era split cannot see a step

The era split answers "was the boundary chosen to suit the answer". It cannot
answer the question a reader of a monitoring paper asks: **is this improving, or
is it still happening.** New `year` scope, `S14_by_year.csv`, and Figure 8.

- **One failure was repaired on a date.** Station-years declaring neither a flag
  nor a limit: **31.8 % in 2012, 0.0 % in 2013**, and 0.0 % for the **12** years
  to 2024. A step, not a trend --- and two years *before* the boundary the paper
  draws, which is why the paper keeps the conservative 2015 split and shows the
  break in the figure.
- **The other two did not move.** The 30 % criterion: **46.3 % in 2006, 47.7 % in
  2024**. Limit above the standard: **28.1 %, 28.2 %**. Substitution at source
  stays between **97.2 %** and **100 %** across every year the record can speak
  about.

Panel (b) carries the denominator, without which panel (a) misleads: before 2005
almost no row records a limit, so the legal criteria read 0 % for want of
anything to test.

### FIXED — three asserted numbers that nothing recomputed

An unowned number does not merely go unchecked: it makes some *other* check lie,
because the near-match detector attributes it to the nearest computed value. The
81.9 % changed-outcome share was reported as a stale Swedish era value seven
points away; 75 (the pesticide group's membership) as another; 18,971 (the
PossibleExceedance total) as a group-completeness denominator. All three are now
recomputed, along with the group member counts, touching counts and completeness
rates. `resolve_pending_claims()` also now does what its docstring always
claimed: an asserted value another check matched exactly is exempt from
re-attribution.

### Corrected — the pesticide-sum group does resolve

5.3 said the basket "cannot be resolved from the legal text at all". Our own
parse resolves **75** members. The finding is stronger stated truthfully: all
four group standards resolve, and completeness falls with basket size ---
heptachlor and its epoxide (2 members) 69.6 %, cyclodiene (4) 88.0 %, PAHs (9)
36.0 %, and the pesticide sum (75) **0.0 %**: not one of the 26,846 station-years
touching that group measures all of it.

### FIXED — the retired single-basin analysis was still speaking, in four places

The handover asked specifically for leftovers from the retired Ergene pipeline
that would only surface on a clean run. Four survived, all in *prose that
nothing recomputes*:

- **`scripts/test_axioms.py`** — T5's rationale read *"1,103 candidate onsets in
  this dataset fall in exactly this category"*. "Candidate onset" is vocabulary
  from `attic/`, and 1,103 is a count from an analysis this paper does not
  report --- shipped in `eval/axiom_tests.md`, the file §5.11 cites as its
  evaluation evidence. It now reads the current record: **92,430 assessments**
  where a European standard exists and no bound is reported, which is exactly
  the segment Figure 5 labels *No limit recorded*. Phrased without a number when
  the data are absent, since the suite must run on the vocabulary alone.
- **`ontology/censo-core.ttl`** — `censo:DetectedObservation`, in the
  **published** vocabulary, was justified by "detection-onset reasoning operates
  on this class". A class in a released ontology defended by an analysis the
  accompanying paper does not contain. Rewritten to stand on what the class is
  for: presence is robust near the limit where magnitude is not.
- **`scripts/26_source_conformance.py`** — the report's prose still described
  **two** violation types where the table now reports one, and told the reader
  *"our own pipeline fills the gap with the conventional LOD = LOQ/3"* --- the
  fabricated datum that was removed. A generated report whose prose is not
  generated outlives the change it describes. Rewritten to say what happened.
- **`scripts/90_figures.py`** — the graphical abstract's docstring said the
  paper "presents [the onset verdicts] as a demonstration resting on 20
  reaches", present tense, of material the paper no longer carries.

And one arithmetic drift in the same class: **`eval/competitor_papers.md`** said
*"Across four papers"* and *"All four model regulatory thresholds and two carry a
SWRL rule layer"* while its own table listed **five** columns and the manuscript
said five. The counts are derived from the scan now: five papers, all five model
thresholds, three carry a rule layer.

`check_no_retired_vocabulary()` scans 103 files outside `attic/` for that
vocabulary and fails on any *undisclosed* mention --- a docstring that says the
comparison was withdrawn is not the defect; a retired quantity presented as this
paper's own is. Verified by planting one in the results section.

### Added — nine gates, each written because something had already slipped past

`99_audit.py` grew from 66 to 80 passing checks in this pass (104 checks run;
the rest are the three-way decomposition, the substance-set equality and the
method-code denominator recorded above). Every gate below exists because a
specific defect had survived into a file a reader receives:

| gate | what had slipped |
|---|---|
| `check_front_matter_numerals` | highlights three corrections out of date, in plain digits the claim checker cannot see |
| `check_bibtex_syntax` | 13 semicolon-separated author lists, one combining accent |
| `check_supplementary_pointers` | — (pre-emptive; found nothing broken, and was itself vacuous until the LaTeX-escaped underscore was handled) |
| `check_benchmark_shape` | a measured result reported nowhere |
| `check_heading_quantifiers` | "Half of European monitoring" over 36.4 % |
| `check_caption_counts` | "the *fourteen* substances", a value in words |
| `check_readme_numbers` | the README's whole headline table |
| `check_no_placeholder_urls` | `repository-code: https://github.com/` |
| `check_section_pointers` | S5 pointed at Section 5.4, S6 at 5.3 |

Each was verified by *breaking* it: introducing the defect it is meant to catch
and confirming the audit fails by name. Three needed that verification to be
found vacuous on the first attempt.

### FIXED — CITATION.cff cited a placeholder and one author

`repository-code: "https://github.com/"` --- the front page of GitHub. It
resolves, so no link checker would ever complain, and a reader following it
learns nothing. Removed until the repository is public, alongside the pending
Zenodo DOI. The abstract there said CENSO binds the *limit of detection* to the
run; corrected to the quantification limit, and the keyword with it. The file
also listed one author where the manuscript lists three with CRediT roles; all
three are now named, matching the manuscript rather than asserting anything new.

`check_no_placeholder_urls()` covers `CITATION.cff`, both READMEs and the
Elsevier front-end. Verified by breaking it.

### FIXED — the repository README was a correction cycle out of date

The first file anyone opens. Its headline table still read **46.6 %**,
**3,382 – 12,042** exceedances, **908** resting on a measurement and **18.5 %**
of co-regulated verdicts, and it introduced the audited record as *"most of it
predating 2015"* --- the sentence the era analysis exists to refute, still in
place in the one file that is read before the paper. It also asserted that
"every one of these is recomputed from source by `scripts/99_audit.py`", which
was false: the audit had only ever read the manuscript.

Corrected, and extended with the era split, the outright-exceedance share and
the maximum-allowable result. `check_readme_numbers()` now requires every bolded
value in that table to equal something recomputed in the same run. Verified by
breaking it: restoring 46.6 % fails the audit by name.

Also corrected there: the download instructions named two releases when the
chain reads three, and pointed at a "see below" section about the disaggregated
release that did not exist; and the whole-chain warning cited the superseded
18.5 %.

**Three of the checks written in this pass were silently vacuous when first
run** --- a regex that ignored LaTeX's escaped underscore and found no
supplementary pointers; a heading check that read Article 4(1)'s 30 % criterion
as the result it constrains; a README block delimiter that matched the table's
own `|---|---|` separator and so saw one value instead of thirteen. Each was
caught by checking the *count* the check reported, not merely that it passed. A
check that passes vacuously is worse than no check, because it is evidence of
something it never looked at.

### Changed — the title and the first keyword said "detection limit"

**This one is an authorial decision, not a defect, and is one edit to revert.**
WISE-6 carries no detection-limit field; Article 3(3b) and Article 4(1) are both
written about the quantification limit; the figures were corrected to `[0, LOQ]`;
and the fabricated `LOD = LOQ/3` was removed from the ABox. The title still
promised detection limits. It now reads *"an ontology for reporting limits"* ---
the umbrella term the censored-data literature this paper builds on uses (Helsel;
§2.1), covering both limits, which is what the ontology models. The first keyword
moved from "limit of detection" to "limit of quantification" for the same reason.

### Added — a caption count spelled out in words is still a value

Figure 4a's caption says "the \emph{fourteen} substances with the highest
share", and N moves with the threshold table and the filter.
`check_caption_counts()` counts the `plotted` rows in each figure's shipped data
and compares against the number *word* in that figure's own caption --- words
only, since folding in the caption's `\num{}` filter values (1000 station-years,
30 %) would let a caption pass by coincidence. Verified by breaking it: with
"thirteen" in the caption the check fails and names the discrepancy.

### FIXED — a heading that survived the number it described

`\paragraph{Half of European monitoring fails the legal performance criterion.}`
sat directly above `\textbf{\num{36.4}\%}`. The heading was written when the
mis-parsed threshold table gave 46.6 % and outlived the correction, because a
heading is prose and prose is not recomputed. Now "More than a third".
`check_heading_quantifiers()` gives each English quantifier the band it can
honestly cover (a quarter 20--30 %, a third 28--40 %, half 45--55 %, nearly all
88--100 %) and compares it against the paragraph's **bolded** value --- the
bolded one specifically, because the first number in that paragraph is the 30 %
of Article 4(1), the criterion rather than the result.

### Added — the introduction previews the two findings it omitted

The contribution sentence listed three shares and stopped, while the results
carry an era split and a second standard defined on a different unit of
observation. Both are now previewed in one sentence. The conclusions gained the
same two results, which they also lacked.

### Typesetting — the measure

`\emergencystretch=3em` plus `hyphenat`'s `htt`: **overfull boxes above 10 pt,
7 → 0.** `emergencystretch` alone leaves three, including one 83 pt (29 mm) box
where `observedPropertyDeterminandCode` cannot be hyphenated. The cost is ~30
"Font shape ... undefined" notices in the log, because Latin Modern has no bold
small-caps typewriter for hyphenat to ask after; pdflatex substitutes a valid
shape and the page is unaffected. A log notice is cheaper than a line in the
margin, and the trade-off is recorded in the preamble.

Verified by compiling: **0 LaTeX errors, 0 undefined references, 0 undefined
citations, 0 BibTeX errors, 0 overfull boxes above 10 pt, 31 pages.** Compiled
against `article` plus a `\num` stub, because `elsarticle.cls` and `siunitx.sty`
are not installed on this machine; everything that breaks a real build breaks
this one too.

### FIXED — the supplementary index was hand-maintained and had drifted

`paper/supplementary/README.md` is the first file a reader of the supplementary
material opens, and it was the one file in that directory nobody generated. It
announced **15** competency questions where there are 20; described S7 as *four*
observations carrying a *detection limit*, when Figure 6 draws three and WISE-6
has no such field; listed "restriction to recent years" as one of the three
robustness adjustments, which §5.8 says explicitly is *not* one; and never
mentioned S12 at all. It is generated now, from a table beside the code that
builds each file, and `--check` covers it.

### Added — the measured reasoning cost is now shipped and reported

Stage 15 has been measuring OWL 2 RL closure and SHACL validation against ABox
size all along, and the result went nowhere: the manuscript asserted closure was
"impractical in pure Python" without the measurement. For a software journal that
is the one number a reader wants against their own hardware. Now
`S13_reasoning_cost.csv`, and §5.10 reports the *shape* — super-linear closure,
validation about an order of magnitude cheaper — deliberately quoting no
seconds, because a timing in the text would fail the audit on every other
machine. `check_benchmark_shape()` verifies both claims against the series
instead: observations ×16 → closure ×38, closure/SHACL 5–13×.

### Typesetting — siunitx grouping

The figures print `742,591`; the text would have printed `742 591`.
`group-separator={,}` now, with `group-minimum-digits` left at 5 on purpose: at
4 the years written as `\num{2015}` would print as `2,015`.

### FIXED — the bibliography did not survive BibTeX

Found by compiling the manuscript, which nothing in the pipeline had done.
`elsarticle.cls` and `siunitx.sty` are not installed here, so the compile ran
against `article` plus a `\num` stub — enough to exercise every failure that
stops a real build.

- **Thirteen entries separated their authors with semicolons.** BibTeX requires
  ` and `; a semicolon-separated list is parsed as *one* name with too many
  commas. **232 BibTeX errors**, and every one of those references would have
  printed as a single mangled string — Kase, Loos, Malaj, Moschet, Schwarzenbach,
  Weisner, Wilkinson, Beketov, Geissen, Ahkola, Coquery, Saka, Lippolis. The
  Crossref check could not see this: it verifies field *values*, not BibTeX
  syntax.
- **One name carried a combining acute accent** (U+0301) instead of the
  precomposed é, which stops `pdflatex` outright under `inputenc`. The whole
  file is now NFC-normalised.
- **Four entries had no author**, so an author-year style prints "(, 2000)":
  Directives 2000/60/EC and 2008/105/EC, the Turkish regulation and the ETSI
  standard. Each now carries its issuing body, as the sibling entries already
  did.
- **`water_onto_review` was credited to "Various".** Crossref returns an empty
  author list for that chapter — Wiley never deposited one — so the placeholder
  would have printed as a citation. It now cites the volume's editors (Mehta,
  Tiwari, Siarry, Jabbar), with the reason in the entry's `note`.

`99_audit.py` gained `check_bibtex_syntax()`: no `;`-separated name list, no
combining mark. Result: 0 BibTeX errors, 0 undefined references, 0 undefined
citations, 30 pages.

### FIXED — the manuscript overran its measure in seven places

Long camelCase identifiers in `\texttt{}` cannot be hyphenated, so a paragraph
holding one overflowed by up to 83 pt (29 mm) —
`observedPropertyDeterminandCode`, `AssessedObservation`. Added
`\emergencystretch=3em` and `hyphenat` with `htt`. The comparison table's nine
columns overran by 24 mm; the generator now emits `\scriptsize` with 3.5 pt
gutters rather than a `\resizebox`, which would have scaled rules and text by
different amounts. **Overfull boxes above 10 pt: 7 → 0.** The caption also now
says why the text counts eighteen ontologies where the table has twenty rows.

### FIXED — figures that ran off their own canvas, and one that argued the wrong way

`save()` deliberately does not use `bbox_inches="tight"`, so anything outside
the axes is *clipped*, not accommodated. Three consequences, all visible only by
rasterising the PDFs and looking at them:

- **Figure 5** lost the right end of its title and its last legend entry once
  the fifth segment was added. Title shortened to two lines, the new entry
  labelled `Possible exceedance`, legend at three columns.
- **The graphical abstract** — the most-reproduced figure in any article —
  still said **LOD** throughout: `[0, LOD]`, an `LOD` gridline, and "CENSO binds
  the detection limit to the analytical run". Waterbase has no detection-limit
  field, both provisions are written about the quantification limit, and
  Figure 6 draws `[0, LOQ]`. Now LOQ throughout. Its footer also ran off both
  edges; the vertical budget was re-cut and the axes now use the whole canvas
  instead of leaving a quarter of the height and a fifth of the width blank.
- **Figure 6b** — the paper's central picture — drew a real case whose
  threshold sits at **4.6 %** of the quantification limit. Geometrically true,
  rhetorically backwards: the line rendered on top of the axis and read as *T
  below the interval*, the opposite of the panel's claim. `23_waterbase_abox.py`
  now prefers an exemplar whose threshold lands between a quarter and
  three-quarters of the limit, keeping the first qualifying row as a fallback so
  the panel cannot vanish. The case is now lead in Italy, LOQ 2, T 1.2
  µg/L, and the threshold visibly crosses the interval.

### FIXED — the fourth outcome was missing from the graph-side verdict table too

`waterbase_verdicts.csv`, written by `23_waterbase_abox.py`, listed five
outcomes and not `possible_exceedance` — the same defect as the figure, in the
table that is figure 5's documented fallback source. Corrected.

### FIXED — the highlights were three corrections out of date

The Elsevier highlights still read 47 %, "908 of 10,065" and 18.5 %. Every one
was superseded by the threshold correction, and **no check could see them**: the
claim checker only reads values inside `\num{}`, and the highlights were written
in plain digits. They now carry \num{36.4}, \num{10866}, \num{160702} and
\num{18.1}, and `99_audit.py` gained `check_front_matter_numerals()`, which
fails if a numeral in the highlights or the abstract is neither inside `\num{}`
nor part of a legal citation.

### Corrected — precision, denominators and attribution

- "18 **published** ontologies" in the abstract, introduction and conclusions:
  the gap table is 17 published vocabularies plus one unpublished baseline, as
  §5.9 already said. Now "18 ontologies parsed".
- Two percentages had no denominator in the text — the MAC audit's
  \num{8470300} assessable samples and the \num{74015} station-years assessable
  under both standards. Both were computed and sitting unquoted in the audit.
- Figure 4a ranks by the **30 %** criterion, so its four 100 % bars are not the
  three substances the adjacent sentence names under the outright criterion.
  The paragraph now names the criterion each belongs to, and the fourth
  substance (clothianidin, a neonicotinoid).
- The Discussion recommended recording the *detection* limit while the
  Conclusions recommended the *quantification* limit. One recommendation now.
- The data statement named only the aggregated release; the paper also reads
  the SpatialObjects and disaggregated releases. All three are named, with the
  Deflate64 caveat.

### Added — the ontology's contribution in the abstract, as numbers

Per the standing request that the abstract carry the contribution numerically:
\num{34.3}\% undecidable over all \num{742591} assessments, \num{18.1}\% of
co-regulated outcomes re-decided by swapping a package with no code change, and
none of \num{18} parsed ontologies recording censoring status. 236 words.

### FIXED — three text claims that the corrected data no longer support

- **Article 3(3b) was attached to the wrong number.** The conclusions read
  "36.4 % … Article 3(3b) sets aside". 36.4 % is the Article 4(1) performance
  criterion; 3(3b) reaches the 19.3 % whose limit exceeds the standard, a figure
  that appeared nowhere in the conclusions. Both are now stated, each under its
  own article.
- **"For four pyrethroid insecticides the figure is 100 %."** Three, after the
  Annex I correction: deltamethrin (1,125/1,125), bifenthrin (1,100/1,100),
  esfenvalerate (1,098/1,098). Cypermethrin fell to 1 of 7,104 when its standard
  stopped being 10× too strict. They are now named, and the audit compares the
  named set against the computed set in both directions — a bare count would
  have survived this substitution unchanged.
- **12.2 % → 12.4 %** for the station-years with no bound at all, so that the
  three components sum to the 34.3 % asserted in the same sentence.

### FIXED — four claims that were false as written

All four are corrected in the text. Three of them became stronger for it.

- **The European package was cited as verified and was not.** The citation
  pointed at `08_verify_thresholds.py`, which parses the Turkish regulation.
  The passage now states the defect that omission allowed — the five mis-parsed
  annual averages — and cites the hand-read gate that now prevents it.
- **"An independent implementation" was not independent.** The graph builder
  imports the decision procedure from the streaming counter, deliberately, so
  the two cannot drift; the agreement is therefore an identity. The paragraph
  now says what the check does establish (expressing the record in the
  vocabulary loses nothing) and what it does not (that the ontology was needed
  to count — it was not).
- **"Cannot be evaluated at any level of effort" was checkable and false.** The
  aggregated release carries `resultMaximumValue`. The text now says the
  maximum-allowable standard can be approached there but not answered, with the
  three reasons.
- **The 28-pesticide basket does not exist in law.** "(28)" in Annex I is a
  footnote marker referring to two other Regulations, not a member count, and
  the parsed 75-member basket had recruited brominated diphenyl ethers, PAHs,
  alkylphenols and PFAS. The completeness rate is withdrawn and replaced by the
  stronger statement: the membership cannot be resolved from the legal text at
  all, so nobody can assess that standard, while a threshold column would
  compare a partial sum against it and return compliance. The two groups Annex I
  does enumerate are reported and audited.

### The chain is green

`24 stage(s) run, 0 skipped, 0 failed in 4209s`, exit 0. The audit runs **141
checks: 114 pass, 0 fail**, 1 warning (the two author-owned `\pending{}`
markers), 26 recorded as computed but not quoted, 0 skipped. All **99** numeric
claims in the manuscript trace to a shipped artefact; **0 untraced**.

The Annex I table is diffed against **53 hand-read rows x 4 columns = 212
values** on every build, from `pdftotext -layout` read by column position.

Compiled: **0 LaTeX errors, 0 undefined references, 0 undefined citations, 0
BibTeX errors, 0 overfull boxes above 10 pt, 32 pages.** Against `article` plus a
`\num` stub -- `elsarticle.cls` and `siunitx.sty` are not installed here --
which exercises everything that breaks a real build.

Body prose 7,249 words (excluding abstract, figures and tables); abstract 248
words; **8 figures**; 14 supplementary files plus 9 per-figure data files; 20
competency questions all answering; 10/10 axiom tests; 5/5 ontology modules
valid.

`eval/RESTATE.md` carries the authoritative value of all 77 quantities the
manuscript states, regenerated from `derived/processed/*.csv`.

### Superseded — the original diagnosis, kept for the record

- `paper/sections/06-discussion.tex` cites
  `scripts/08_verify_thresholds.py` as verifying the European package. It does
  not: it parses `refs/legal/YSKY.pdf`, the Turkish regulation, and in this
  release its comparison is not reproduced at all. The European package is
  parsed by `10_parse_eu_eqs.py` and is verified nowhere — which is how the
  five errors above survived.
- `paper/sections/07-conclusions.tex` describes the streaming counter as "an
  independent implementation". Since `23_waterbase_abox.py` was changed to
  import the decision procedure from `22_waterbase_external.py` — deliberately,
  so the two cannot drift — the agreement between them is now an identity, not
  corroboration. The sentence must say what the check actually is.
- `paper/sections/05-results.tex` says the maximum-allowable standard "cannot
  be evaluated \[on the aggregated release\] at any level of effort". The
  aggregated release carries `resultMaximumValue` and
  `resultQualityMaximumBelowLOQ`. The disaggregated read is still the better
  instrument, but for stated reasons rather than impossibility.
- The group-standard result ("the sum of 28 pesticides: 0 of 26,846
  station-years complete") rests on a parsed 75-member basket that includes
  brominated diphenyl ethers, PAHs, alkylphenols and PFAS. "(28)" in the Annex
  is a footnote marker, not a member count. The membership must be
  reconstructed from the legal text or the result withdrawn.


### Fixed — the chain was broken on a clean unpack

- **`scripts/08_verify_thresholds.py` crashed at stage 2.** The retired
  single-basin survey's `Data/CKS_FEnCY.xlsx` was loaded unconditionally, and
  `Data/` is not redistributed. A previous pass had guarded this script's read
  of `attic/processed/analytes.csv` but not the workbook. The load is now
  guarded and the report says explicitly that the comparison is not reproduced
  and that nothing in the manuscript depends on it. What the stage still does —
  parse `YSKY.pdf` into `derived/processed/eqs_official.csv`, which the Turkish
  regulation package is built from — is unaffected.
- **`scripts/16_export_for_scanners.py` was not in the chain.** It writes
  `ontology/dist/censo-full.{ttl,owl}`; `scripts/97_assemble_publish.py` copies
  those to `publish/site/`, which is what the `w3id.org` IRI serves. Because 16
  was never run by `00_run_all.py`, an edit to `ontology/censo-core.ttl` reached
  neither the distribution nor the published copy — and `97 --check` compares
  the site against the distribution, so both were stale, both agreed, and the
  audit stayed green. Added to `STAGES` immediately before 97, and
  `scripts/99_audit.py` now fails when `ontology/dist/` is older than an
  ontology module.
- **`scripts/09_verify_bibliography.py` and `scripts/14_reasoning_benchmark.py`
  were not in the chain either.** Their reports sat in `eval/` as artefacts no
  stage reproduced, while `99_audit.py` counts everything in `eval/` as shipped
  evidence — the same failure mode that once let the manuscript cite a withdrawn
  survey. Both added to `STAGES`.
- **`Data/waterbase/WISE6_SpatialObjects_DerivedData-csv.zip` was undocumented.**
  Station coordinates come from it; without it `cq12` returns nothing and the
  Europe map has no stations, so "all fifteen competency questions return
  answers" was false on a fresh machine. `README.md` and
  `scripts/22_waterbase_external.py` now name it alongside the aggregated
  release.
- **Four stages died on a genuinely empty tree.** `10_parse_eu_eqs.py`,
  `14_reasoning_benchmark.py`, `17_run_competency_questions.py` and
  `22_waterbase_external.py` created `eval/` and then wrote into
  `derived/processed/`, which on a fresh clone does not exist. Stage 1 failed
  before writing `eu_eqs.csv`, so every threshold comparison downstream ran with
  no thresholds. Invisible for as long as anyone's working tree already had the
  directory from an earlier run — the same shape of defect as the retired-survey
  reads, and only a wipe-and-rebuild surfaces it.
- **`S1_competency_questions.md` and `S4_ontology_comparison.md` said
  "Generated by `scripts/…`" and were generated by nothing.** Someone had copied
  the reports once, by hand, and they had drifted: the shipped S1 claimed
  442,363 triples while the manuscript said 447,209 and the build reported a
  third figure — one quantity, three values, in files a reader receives
  together. `98_supplementary.py` now copies both from `eval/`, and `--check`
  fails when they are stale.
- **Retired-survey residue moved to `attic/`.** `eval/kurtosis_flip.md` and
  `eval/substance_resolution.md` were written by scripts that live in `attic/`,
  so nothing in the chain reproduced them — while `99_audit.py` counts
  everything in `eval/` as evidence that a manuscript number is supported. Also
  moved: `ProjectOwl_v3.owl` (referenced nowhere) and the 11 MB of EPS figures
  from the 2018 GIS-DSS paper that were sitting in the repository root.
  `TheOntologyGISDSS.owl` stays — `07_verify_gap_table.py` assesses it as the
  unpublished baseline in the gap table.
- **`97_assemble_publish.py` read `ontology/dist/censo-full.ttl` seven lines
  before its own missing-sources guard**, so a tree without `dist/` died on an
  uncaught `FileNotFoundError` rather than on the message that tells you to run
  stage 16. Guard moved first.
- **`90_figures.py` iterated `country_confounders.csv` without the `None` guard
  every other read in the file has.** `read_csv` returns `None` for a missing
  file, so whenever stage 25 was skipped or failed while
  `waterbase_summary.csv` was present, figure 3 raised a bare `TypeError` — and
  `main()` iterates the figures in order with no recovery, so figures 4, 5 and 6
  died with it.
- **Stages 17 and 18 were declared as not needing the download** but read
  `derived/abox/censo-waterbase.ttl`, which only stage 23 produces. Without
  `--waterbase` they hard-failed where the design says a stage with a missing
  optional input is skipped. Now marked as needing it.
- **`99_audit.py` staleness did not cover stage 22.** Every counter the paper
  quotes comes out of `waterbase_summary.csv`, and it was the one output in the
  Waterbase chain nothing checked.
- **`17_run_competency_questions.py` told a failing run to execute
  `scripts/15_build_abox.py`** — retired to `attic/` with the single-basin
  survey. It now names `23_waterbase_abox.py`.
- **`95_numbers_manifest.py`'s "How to re-derive everything" block listed eleven
  scripts by hand, six of them retired to `attic/`** — in the shipped file whose
  job is to tell a reader how to reproduce the numbers. Replaced by the one
  command that is actually correct.
- **`LICENSE` carved out "the Ergene survey measurements" and pointed at
  `docs/02-data-inventory.md`**, a path that no longer exists. It now describes
  the data the pipeline actually reads.
- **`paper/outline.md`** was the retired survey's full paper plan, naming the
  basin and a different target journal, sitting inside `paper/`. Moved to
  `attic/`.
- **`requirements.txt`: `Pillow==9.5.0` pinned.** It is transitive, via
  matplotlib and pypdf. Left free, pip resolves it to 10.4, whose
  `PIL/_typing.py` imports `numpy.typing.NDArray` — added in numpy 1.21, and
  numpy is pinned at 1.20.1. `import pypdf` then raises before any stage runs.

### Fixed — the ontology contradicted the manuscript

- **Removed `owl:AllDisjointClasses` over `Exceedance` / `PossibleExceedance` /
  `Compliant` / `IndeterminateCompliance`** (`ontology/censo-core.ttl`). It made
  it an inconsistency for one observation to carry two outcomes — while
  Section 5.3 reports exactly that as a result, and Section 4 stated that no
  such axiom was asserted. A compliance outcome belongs to an
  observation–threshold *pair*, not to an observation: the same measurement may
  be compliant against one jurisdiction's standard and indeterminate against
  another's. `owl:unionOf` (exhaustiveness) and the disjoint comparison
  properties (per-pair exclusivity) remain, so the four-valued logic is still a
  partition — at the level the regulation is written at.
- **Added the three pairwise `owl:propertyDisjointWith` axioms** beside the
  existing `owl:AllDisjointProperties`. Same semantics in OWL 2 — but removing
  the class-level axiom turned `test_axioms.py` T4 red, which showed that
  **`owl:AllDisjointProperties` is not implemented by `owlrl`**: per-pair
  exclusivity had never been enforced in this pipeline, and T4 had been passing
  on the class-level axiom. `owlrl` does implement the pairwise rule
  (`prp-pdw`). An axiom no reasoner in the pipeline evaluates is documentation,
  not a constraint.
- **`scripts/test_axioms.py`**: T2 is now a *control* that must stay consistent —
  one measurement, two jurisdictions, two verdicts — so the removed axiom cannot
  return unnoticed. Also fixed the report's `expected` column, which was
  hard-coded to `T9` and so printed the opposite of what a second control
  asserted. 10/10 pass, T4 now failing on the right axiom.

**Version.** The ontology stays at `1.0.0`. Removing a disjointness axiom and
relaxing a shape are both semantic changes and would normally require a bump —
but `1.0.0` has not been released: there is no DOI yet and the `w3id.org`
redirect request is still open, so nothing resolves to the old file and no
consumer can have it. The first published version will be `1.0.0` with these
changes in it. If that stops being true before submission, bump before
publishing, not after.

### Fixed — values invented by the pipeline and presented as measured

- **Figure 6 has three panels, not four** (`scripts/23_waterbase_abox.py`,
  `scripts/90_figures.py`, `paper/sections/04-methods.tex`). The fourth split
  the undecidable case at the limit of *detection*. Waterbase reports none; the
  one used was this pipeline's own `LOQ/3`, so the boundary between two panels
  of a figure captioned "real observations" came from a constant we chose. Both
  halves are the same case in law and in the vocabulary — censored, threshold
  below the quantification limit, verdict indeterminate — and every provision
  applied here is written about the LOQ. The cases are now `compliant`,
  `cannot_decide`, `quantified_exceedance`; `lod_ug_l` is gone from
  `waterbase_exemplars.csv` and `S7`. `scripts/99_audit.py` gained
  `check_figure_geometry()`, which verifies each panel really has the geometry
  it claims and fails if a detection-limit column reappears.
- **The ABox no longer asserts a `censo:limitOfDetection`.** It wrote `LOQ/3`
  for every method, into a published graph, to satisfy this project's own
  `censo:AnalyticalMethodShape` — a shape that could only be met by
  manufacturing the datum it required. The shape now requires *a* limit
  (`sh:or` over quantification and detection) rather than specifically a
  detection limit, which is what the vocabulary actually claims and what the law
  regulates. `cq07`, `cq14` and `cq15` asked for the detection limit and now ask
  for the quantification limit — more correct in each case, since the upper
  bound of a non-detection is set from the LOQ. `cq04`'s header claimed to
  exercise `censo:CensoredAmbiguous`; it does not, and now says so.
  `censo:CensoredAmbiguous` stays in the vocabulary: the concept is real even
  where no European release supplies the datum.

  The "a method must state a limit" constraint is its own shape,
  `censo:AnalyticalMethodLimitShape`, rather than an `sh:or` on
  `AnalyticalMethodShape`. SHACL attaches a shape's `sh:message` to every
  violation that shape raises, so declaring it at node level made a method with
  its quantification limit *below* its detection limit report, additionally,
  that it had failed to state a limit — which it plainly had. A constraint whose
  failure message describes a different failure is worse than no message.
  Verified on five fixtures: LOQ only conforms, LOD only conforms, neither
  fails, LOQ &lt; LOD fails with exactly one message, no unit fails with its own.

### Added — the record is not one era

- **`scripts/22_waterbase_external.py` gained `scope="era"` and
  `scope="era_country"`**, plus `censored` / `censored_with_value` counters
  computed exactly as `scripts/26_source_conformance.py` computes them.
  `scripts/98_supplementary.py` ships `S10_by_era.csv` and
  `S11_era_by_country.csv`.

  This exists because the manuscript asserted that the release "mostly predates
  2015" and drew a limitation from it. **48.8 % of the river record is dated
  2015 or later** — 2,043,731 of 4,190,833 station-years, the largest block
  being 2020–2024. The three failures do not move together across the boundary:

  | | before 2015 | 2015 onwards |
  |---|---|---|
  | neither flag nor limit | 49.7 % | 0.0 % |
  | LOQ above the EQS | 25.6 % | 21.9 % |
  | fails the 30 % criterion | 44.8 % | 48.0 % |
  | censored rows carrying a positive value | 99.6 % | 99.3 % |

  The record-keeping defect is solved; the analytical defect is *worse* in the
  recent record; substitution is unchanged. It is not survivorship: all eight
  authorities reporting after 2015 also report before it, and every one of them
  went to 0.0 %. The era layer carries the per-country cross-tab so that
  comparison is reproducible rather than asserted.

### Measured — the disaggregated release, and what it cannot supply

96,597,294 rows streamed (28.5 GB, Deflate64 — Python's `zipfile` cannot read
it; `7z` can). The release has 28 columns and carries **no measurement
uncertainty and no limit of detection**. So:

- `censo:PossibleExceedance` cannot be exercised from any EEA release, not only
  from the aggregated one. Article 4(1) of Directive 2009/90/EC sets two minimum
  performance criteria in one sentence — LOQ at or below 30 % of the standard,
  *and* measurement uncertainty of 50 % or below (k = 2) at the standard. The
  first is counted across 4,190,833 station-years; the second cannot be counted
  at all, because the reporting schema has nowhere to put it.
- Figure 6's detection-limit panel could not have been grounded in measured data
  even with the larger release.

The headline numbers stay on the aggregated release: an annual-average standard
is defined against an annual mean, which is exactly one aggregated row.
