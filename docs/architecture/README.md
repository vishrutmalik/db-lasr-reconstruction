# Architecture (G015)

Design set for the DB LASR reconstruction. Read in this order:

1. `system_design.md` — module map for `src/lasr/`, dependency rules, the
   five data layers (raw / canonical / point-in-time / feature /
   training-example) with effective-time + knowledge-time semantics, storage
   layout, goal→module map.
2. `canonical_schemas.md` — typed schemas for every MASTER_PROMPT §14 table
   family, PIT columns, structural CI-invariant enforcement map (G017's
   starting point).
3. `provider_contract.md` — provider interface, per-field-family capability
   flags grounded in G012/G013 findings, error semantics, contract-test
   suite CT-01..15, synthetic LT-scenario interface (G018/G019).
4. `config_system.md` — tagged-provenance config schema, spec guards, full
   worked `nlasr_2012` config, contradiction-register knob index (all 31
   CRs).
5. `training_and_artifacts.md` — weak-learner/boosting/ensemble/walk-forward
   interfaces sized to the seven version specs, artifact & lineage plan,
   determinism rules.
6. `testing_strategy.md` — per-layer test plan binding CI-001..055 and
   LT-001..021 to test locations and goals; determinism/double-run gates.
7. `toolchain_proposal.md` — Python 3.12 via uv, pandas+pydantic stack,
   GitHub Actions matrix (input to G016).

Evidence conventions: `P1-xx`/`E-P2-xx`/`P3-xx`/`E-P4-xx` = evidence rows;
`CR-xxx` = contradiction register; `CI-xxx` = correctness criteria;
`LT-xxx` = leakage scenarios; `OQ-…`/`Qn` = open questions; `A-…` =
assumptions register; `FM-xx`/`gap §n` = G013 field mapping / G012 gap list;
`MP §n` = MASTER_PROMPT.
