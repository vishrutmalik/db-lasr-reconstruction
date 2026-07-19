# db-lasr-reconstruction

Reconstruction, validation, and modernization framework for Deutsche Bank's
machine-learning stock-selection models (N-LASR 2012 → N-LASR2 2013 → LASR /
LASR-HC / LASR-HF 2014 → N-LASR 2020), built to run end-to-end on
schema-compliant synthetic data so that the only missing dependency at
completion is real historical data / provider credentials.

**Governing specification:** [MASTER_PROMPT.md](MASTER_PROMPT.md)

## Project state (durable memory)

| File | Purpose |
|------|---------|
| [goals.md](goals.md) | dependency-aware goal queue + statuses |
| [progress.md](progress.md) | session-independent status snapshot |
| [decisions.md](decisions.md) | architectural decision record |
| [assumptions_register.md](assumptions_register.md) | explicit, configurable assumptions |
| [evidence_matrix.md](evidence_matrix.md) | implementation-decision ↔ evidence index + contradiction register |
| [input_manifest.md](input_manifest.md) | verified inventory of proprietary inputs (git-ignored files) |
| [coordination/](coordination/) | agent assignments, integration queue |

## Proprietary inputs

Research PDFs and AlphaSense workbooks are **never committed**. Place them
under `inputs/papers/` and `inputs/data_templates/` per the READMEs there;
verify against hashes in `input_manifest.md`.

## Status

Bootstrap phase. See `progress.md`.
