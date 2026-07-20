# Evidence Matrix

For every material implementation decision: component, source, exact location,
extracted statement, classification (EXPLICIT / INFERRED / ASSUMED /
MODERNIZED), implementation consequence, open ambiguity, code path, test, goal.

Detailed per-paper evidence lives in `docs/evidence/<paper-id>/`; this file is
the cross-cutting index of rows that drive implementation. Populated by
G007–G013.

## Paper IDs

| ID | Source | Verified date |
|----|--------|---------------|
| P1 | The rise of the machines (N-LASR) | 2012-06-05 |
| P2 | The rise of the machines II (N-LASR2) | 2013-01-23 |
| P3 | The rise of the machines, III (LASR / LASR-HC / LASR-HF) | **2014-12-01** |
| P4 | Return of the machines (N-LASR reassessment) | 2020-04-23 |
| W1 | AlphaSense Available Metrics with Consensus v3 | n/a |
| W2 | ASQ Comprehensive Financial Data NVDA v3 | n/a |

## Row sources (federated — D-005)

Per-source evidence rows live in their verified evidence directories and are
NOT duplicated here (single source of truth, no copy drift):

| Source | Rows | File | Verified by |
|--------|------|------|-------------|
| P1 | 48 (P1-01…48) | docs/evidence/p1_nlasr_2012/evidence_rows.md | docs/verification/G007.md (PASS) |
| P2 | 30 | docs/evidence/p2_nlasr2_2013/evidence_rows.md | docs/verification/G008.md (PASS r2) |
| P3 | 38 (P3-01…38) | docs/evidence/p3_lasr_2014/evidence_rows.md | docs/verification/G009.md (PASS) |
| P4 | 34 + 5 CR candidates | docs/evidence/p4_nlasr_2020/evidence_rows.md | docs/verification/G010.md (PASS) |
| W1/W2 | 15 (E-G012-nn) | docs/data/evidence_rows.md | docs/verification/G012.md (pending r2) |

Cross-cutting orchestrator rows:

| # | Component | Source | Location | Statement | Class | Consequence | Ambiguity | Code | Test | Goal |
|---|-----------|--------|----------|-----------|-------|-------------|-----------|------|------|------|
| E-001 | Paper-3 dating | P3 | title page | "Date 1 December 2014" | EXPLICIT | model-version timeline uses 2014-12; filename date rejected | none | n/a | n/a | G004 |
| E-002 | Data provider | W1/W2 | workbook branding & support contact | Templates are AlphaSense financial-data products | EXPLICIT | provider adapter target is AlphaSense | API shape unknown from workbooks | G018 | contract tests | G012 |

# Contradiction Register

| ID | Contradiction | Sources | Resolution | Config | Test |
|----|--------------|---------|-----------|--------|------|
| CR-001 | Filename date `20140101` vs title-page date 1 Dec 2014 for P3 | filename vs P3 p.1 | Use title-page date (D-003) | n/a | n/a |

Cross-paper contradiction candidates collected by research goals (14 from P1,
9 from P2, 9 from P3, 10 from P4, in each dir's contradiction_candidates.md)
are triaged and resolved into this register by G011
(docs/methodology/contradiction_register.md will hold the full resolved set;
this table indexes the resolved outcomes).
