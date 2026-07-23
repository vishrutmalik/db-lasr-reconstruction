# Real-data onboarding runbook (G039)

Operator procedure for the day real AlphaSense materials arrive — filled
template pulls, new template versions, or API credentials. Engineering
reference (read first): `docs/data/real_data_integration.md` (cited below
as "integration guide"); probe definitions are its §3.

Governing rules, restated once:

- Nothing is trusted until probed: no capability flag flips, no assumption
  status changes, no runnability claim upgrades without a recorded probe
  result (integration guide §3 rule).
- No secrets and no proprietary data in git — ever (MP §2.2 list;
  `input_manifest.md` "Git tracking policy").
- Control files (`input_manifest.md`, `assumptions_register.md`,
  `decisions.md`) change only through the orchestrator-reviewed PR process
  (MP §3.5 shared-files discipline).

## 0. Preconditions

1. Dev environment per `docs/runbooks/dev_setup.md` (uv-managed CPython
   3.12; virtualenv OUTSIDE the OneDrive tree).
2. `openpyxl` available for workbook inspection (the system Python 3.9 +
   user-installed openpyxl used by G012 is sufficient —
   `input_manifest.md` "Tooling notes").
3. You know the current provider record: integration guide §1.2 (all PIT/
   vintage/estimate-history/corporate-action/delisting/membership/borrow/
   bid-ask/screening/publication flags `false`; MARKET_DAILY
   `history_start=None`, `basis=UNKNOWN`).

## 1. Where materials go

### 1.1 Data files (template pulls, new workbook versions)

- Location: `inputs/data_templates/` — git-ignored (`.gitignore`;
  MP §2.2). The two v3 workbooks already there are the G012 evidence base;
  never overwrite them.
- Naming for probe artifacts (suggested; whatever is used goes in the
  manifest): `<template>_<TICKER>_<YYYYMMDD>_VPnn.xlsx`, one file per probe
  execution.
- Commit only metadata: filename, SHA-256, size, sheet inventory, parsing
  status (`input_manifest.md` policy: "only this metadata is committed").

### 1.2 Credentials (if an API arrives)

- Location: `.env` at the repo root. Git-ignores it by pattern (`.env`,
  `.env.*`, with only `!.env.example` allowed back in — `.gitignore`).
- Variable NAMES (never values) are declared in the committed
  `.env.example` (landed with G018): `LASR_LOCAL_TEMPLATE_ROOT` (root
  directory of workbook template extracts for the local-file provider) and
  the reserved future-API names `LASR_API_BASE_URL` / `LASR_API_KEY` /
  `LASR_API_SECRET` — all unset until a real adapter lands
  (`provider_contract.md` §4.3: auth-from-environment, values never
  logged). Any new name goes into `.env.example` via PR before use.
- Only `config` (and `cli`) may read environment variables
  (`system_design.md` §4 rule); CT-14 enforces that no credential value
  appears in frames, logs, or manifests.
- Never put credential values in: shell command lines (history), YAML
  configs, issue/PR text, commit messages, manifest files, or probe
  artifacts.

## 2. Verify what arrived (before any probe)

1. Hash every new file: `shasum -a 256 <file>`. Compare against
   `input_manifest.md`; identical hash = nothing new; new hash = new
   manifest row (step 4).
2. Parse with openpyxl; capture the sheet inventory (names + dimensions).
3. Diff the shape against `docs/data/workbook_schema/` (W1/W2 catalogs).
   Any structural change — new sheets, new columns, a changed
   `Data!N2:O3` version list — is itself a finding: record it before
   relying on it. A changed version-type list feeds VP-04 directly.

## 3. Run the probes

Definitions, expected-if-true / expected-if-false, and gate consequences:
integration guide §3. Probes are manual template operations (set controls,
let the add-in populate, save-as) — there is no ingestion CLI for this
yet. The merged local-file adapter
(`src/lasr/data/providers/local_file.py`, `LocalFileProvider`) reads
CSV/JSON **template extracts**, not xlsx: probe workbooks are evidence
files first; loading them through the adapter additionally requires the
xlsx→extract conversion per the extract layout in the module docstring
(shim deferred pending the openpyxl dependency grant, G043).

Recommended order (cheapest, highest-gate first):

| Order | Probe | Operator action (template controls) | Save as |
|---|---|---|---|
| 1 | VP-01 daily OHLV | request dated daily panels for `OPEN`/`HIGH`/`LOW`/`VOLUME` (TM-sheet mechanism, window ≥1y, ≥2 tickers) | one file per ticker |
| 2 | VP-03 history depth | step TM `Start Date` back: 2020→2010→2000→1990→1987; plus the fundamental-anchor leg (try to anchor the FY grid in the past) | one file per window step |
| 3 | VP-02 TR codes | request `Total Return` / `Total Return Index` as dated panels | one file |
| 4 | VP-04 restatement | (a) inspect live template version-type options; (b) pull the same fiscal period on two dates spanning a known restatement, diff | both pulls, dated |
| 5 | VP-05/06/07 secondary | FX code; consensus statistic type (provider docs / support query — FP J3:J4 contact); split-date `CLOSE` comparison | as applicable |

Execution discipline per probe:

- Record ticker, window, template controls used, and pull date/time —
  these become the manifest row's request parameters.
- A per-cell error string (the `VL40` pattern, E-G012-12) is a RESULT —
  capture it verbatim; do not retry until it disappears.
- An outcome matching neither expected branch is recorded as a new
  NOT_ESTABLISHED finding (integration guide §3 preamble), not force-fit.

## 4. Record results

For every probe execution, in one PR (orchestrator-reviewed):

1. **`input_manifest.md`** — new row(s) in the data-templates table:
   filename, SHA-256, size, sheets, plus probe ID and one-line outcome.
2. **Evidence** — add the outcome with exact cell citations to the
   integration guide's gate table context (its §3), quoting the observed
   cells the way G012's evidence rows do (`docs/data/evidence_rows.md`
   format). Final E-numbering is the orchestrator's merge step.
3. **`assumptions_register.md` status flips** — only where the probe
   licenses it:
   - **A-001** (`latest_filing` only): its own "On real data" field says to
     query for vintage/revision endpoints and update this guide. VP-04
     true-branch ⇒ record the evidence, then update A-001's
     status-on-real-data and the capability record; VP-04 false-branch ⇒
     A-001 stands with additional positive evidence — note that too.
   - **A-002** (publication lag TBD): flips only if per-period report/
     filing dates or documented lag metadata appear (gap §3 says none in
     the templates). No template probe currently targets it; written
     provider documentation, archived into `inputs/`, is the only
     upgrade path.
4. **Capability record deltas** — `history_start`, field-coverage
   additions, `corporate_action_basis`, `supports_vintages`: change the
   adapter's declared record (`LocalFileProvider._build_capabilities()` in
   `src/lasr/data/providers/local_file.py`; `provider_contract.md` §4.2
   table is the normative source to amend in the same PR) citing the
   manifest rows from step 1. CT-01 requires every flag's note to cite a
   source — the probe row is that source.

Never recorded = never happened: an unrecorded probe result licenses
nothing.

## 5. Who may flip what

| Change | Allowed trigger | Vehicle |
|---|---|---|
| `history_start` (MARKET_DAILY) | VP-03 recorded result | PR amending capability record + manifest |
| field coverage += `OPEN`/`HIGH`/`LOW`/`VOLUME` | VP-01 recorded result | same |
| FM-18 preferred alternative → (a) | VP-02 recorded result | PR updating `field_mapping.md` FM-18 note |
| `supports_vintages` | VP-04 true-branch recorded result | PR + A-001 update; CT-11 activates |
| `corporate_action_basis` (per action type/window) | VP-07 recorded result | PR; CT-15 guard stays for the rest |
| anything in integration guide §1.3's absent list | new data source or archived written provider documentation — no template probe can flip these | new goal via orchestrator |

Verbal/marketing claims from any provider flip nothing.

## 6. Go-forward snapshot archive (VP-04 false-branch)

If VP-04 confirms latest-restatement-only (the expected outcome per
`Data!N2:O3`), the only PIT path forward is our own archiving — "new data
collection, not provider capability" (`field_mapping.md` §5.4):

1. Schedule recurring pulls (FS/RA/FP surfaces + consensus grid) at a fixed
   cadence; cadence is a config/decision entry (`decisions.md`), not ad hoc.
2. Store each pull as an immutable raw snapshot per the L-RAW layout —
   `data/raw/<provider>/<family>/<snapshot_id>/` with manifest
   (`system_design.md` §5); retrieval_time in the manifest becomes the
   knowledge_time at ingestion (D-009).
3. Label the resulting datasets honestly: vintages exist only from archive
   start; nothing is backfilled. This unblocks go-forward estimate/
   fundamental revision features years from now, never historical
   reconstruction.

## 7. Go/no-go per model version

"Go" = faithful backtest on real data per that version's spec. Current
state for all seven: **NO-GO on AlphaSense alone** (feature_coverage §9
uniform verdict); the synthetic provider remains the primary source for
end-to-end runs (feature_coverage §8). Universal preconditions for any
version's go: a PIT index-membership source, corporate-action/delisting
data, and VP-03-demonstrated depth (integration guide §4.2).

| Version | Go additionally requires | Probe gates |
|---|---|---|
| `nlasr_2012` | R3000 PIT 1987–2012; S&P 500 TR; estimate-revision history (sentiment style); depth to 1987 | VP-02/03 |
| `nlasr2_2013` | + effective-dated GICS; Russell 1000 TR+constituents; FX (regional) | VP-02/03/05 |
| `lasr_2014` | + short interest/float; risk-free series; float shares (or documented MCAP-proxy deviation) | VP-02/03 |
| `lasr_hc_2014` | identical to `lasr_2014` (no new data inputs) | VP-02/03 |
| `lasr_hf_2014` | **VP-01 pass is mandatory** (daily OHLC+volume); until then synthetic-only | VP-01 first |
| `nlasr_2020` | MSCI World PIT 1996–2020; GICS history incl. 10→11; MSCI World TR; depth to ~1991; daily volume | VP-01/03 |
| `modernized` | VP-04 true (as-reported vintages + publication timestamps) or a second provider; delisting returns; borrow history — M-05 contradicts `latest_filing` semantics, so AlphaSense-alone is a permanent no-go | VP-04 |

Intermediate milestone that needs no external data: the local-file adapter
has landed (`src/lasr/data/providers/local_file.py`, G018); once ingestion
(G020) and the xlsx→extract shim land, a **real-data plumbing run** —
current snapshot + TM panel through L-RAW → L-CANON with
`SNAPSHOT_STAMPED`/`RETRO_WINDOW` grades (integration guide §2.4, D-011)
— is a valid "go" for plumbing only, and must be labelled as such (A-003
discipline applies to real snapshots too: plumbing, not investment
merit).

## 8. Failure handling

- Malformed/corrupt workbook: quarantine, never repair
  (`provider_contract.md` §3 `IntegrityError`; quality gate is G021's).
  Keep the corrupt file (hashed, manifest-flagged) as evidence.
- Provider surface changed shape (step 2.3 diff non-empty): stop; record;
  the workbook_schema catalogs and adapter field tables must be revised
  before any probe result is interpreted.
- Ambiguous probe outcome: NOT_ESTABLISHED stands; log an open question;
  do not average two interpretations into a flag flip.
