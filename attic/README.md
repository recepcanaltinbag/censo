# Retired material

Nothing here is built, cited, or read by the pipeline. It is kept rather than
deleted because `paper/` and `docs/` were never under version control, so a
deletion would be unrecoverable.

| | |
|---|---|
| `docs/` | Planning and progress notes from when the paper was a single-basin study. Turkish and English, superseded. |
| `eval/` | Reports produced by the retired pipeline. |
| `scripts/` | The single-basin pipeline: campaign extraction, spatial join, land-use allocation, detection onset, mass balance, attenuation chemistry, the flip analysis and the original ABox builder. |
| `processed/` | The tables those scripts produced. |
| `main.tex`, `main-standalone.tex` | The generic `article`-class front-end, retired when the target narrowed to Elsevier. |

The live work is the Waterbase audit and the CENSO ontology; see the top-level
`README.md`. The retired study is not reported in the manuscript, and no number
in the paper comes from anything in this directory — `scripts/99_audit.py`
enforces that every asserted quantity traces to a file the paper ships.
