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

## Rows

| # | Component | Source | Location | Statement | Class | Consequence | Ambiguity | Code | Test | Goal |
|---|-----------|--------|----------|-----------|-------|-------------|-----------|------|------|------|
| E-001 | Paper-3 dating | P3 | title page | "Date 1 December 2014" | EXPLICIT | model-version timeline uses 2014-12; filename date rejected | none | n/a | n/a | G004 |
| E-002 | Data provider | W1/W2 | workbook branding & support contact | Templates are AlphaSense financial-data products | EXPLICIT | provider adapter target is AlphaSense | API shape unknown from workbooks | G018 | contract tests | G012 |

(further rows added by research goals)

# Contradiction Register

| ID | Contradiction | Sources | Resolution | Config | Test |
|----|--------------|---------|-----------|--------|------|
| CR-001 | Filename date `20140101` vs title-page date 1 Dec 2014 for P3 | filename vs P3 p.1 | Use title-page date (D-003) | n/a | n/a |

(cross-paper methodology contradictions added by G011)
