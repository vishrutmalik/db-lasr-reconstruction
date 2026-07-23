# Provider contract — interface, capability flags, contract tests (G015)

Consumers: G018 (contract + local-file adapter + API stub), G019 (synthetic
provider + generator), G039 (real-data integration guide). Grounding:
MP §16 capability list; provider reality per `docs/data/pit_assessment.md`
(A-001: `latest_filing` is the only version type), `gap_list.md`
(consequences section), `field_mapping.md` (FM-xx rows).

Principles:

1. **One contract, three implementations** (MP §16): synthetic, local-file
   (AlphaSense workbook-template shaped), generic API stub. Every current and
   future provider passes the same contract-test suite (§5).
2. **Capabilities are declared, verified, and honest.** A provider's
   capability record is part of its output; contract tests verify behavior
   matches declaration. Missing capability ⇒ typed error, never silent
   degradation (MP §26 "silent fallback behaviour").
3. **Providers emit raw-shaped frames only.** Canonicalization (id minting,
   unit normalization, vintage assembly) is L-CANON's job
   (`system_design.md` §4 rule). Providers never fabricate fields
   (MP §14: "do not claim unavailable fields are supplied").
4. **No fake endpoints, no committed credentials** (MP §16). Credentials come
   from environment variables read only by `config` (rule table,
   `system_design.md` §4); the API stub defines the auth surface without any
   real endpoint.

---

## 1. Field families and the capability record

Field families (the unit at which capabilities are declared — matches the
gap-list structure):

```python
class FieldFamily(str, Enum):
    SECURITY_MASTER = "security_master"        # gap §1
    MARKET_DAILY = "market_daily"              # gap §2
    FUNDAMENTALS = "fundamentals"              # gap §3
    ESTIMATES = "estimates"                    # gap §4
    CORPORATE_ACTIONS = "corporate_actions"    # gap §5
    CLASSIFICATIONS = "classifications"        # gap §6
    UNIVERSE_MEMBERSHIP = "universe_membership"# gap §8
    BORROW = "borrow"                          # gap §7
    FX = "fx"                                  # gap §6 (FX row)
    CALENDAR = "calendar"                      # gap §7
```

```python
class RevisionSupport(str, Enum):
    NONE = "none"                  # single current value, no history of values
    LATEST_ONLY = "latest_only"    # history retrievable but latest-restated only
    FULL_VINTAGES = "full_vintages"# as-known-on-date vintages retrievable

class CorporateActionBasis(str, Enum):
    UNADJUSTED = "unadjusted"
    ADJUSTED = "adjusted"
    UNKNOWN = "unknown"            # FM-17: AlphaSense basis NOT_ESTABLISHED

@dataclass(frozen=True)
class FamilyCapability:
    available: bool
    supports_pit: bool                     # true knowledge timestamps exist
    revision_support: RevisionSupport
    history_start: date | None             # None = not established (depth caveat,
                                           # field_mapping.md "Global depth caveat")
    fields: frozenset[str]                 # canonical field names servable
    corporate_action_basis: CorporateActionBasis  # market family only
    notes: str                             # gap/FM citations

@dataclass(frozen=True)
class ProviderCapabilities:
    provider_name: str
    provider_version: str
    families: Mapping[FieldFamily, FamilyCapability]
    # cross-family flags (gap_list.md consequences list, verbatim set):
    supports_universe_screening: bool      # gap §1: single-ticker templates
    supports_publication_timestamps: bool  # gap §3
    supports_delistings: bool              # gap §1
    supports_bid_ask: bool                 # gap §2
    supports_borrow: bool                  # gap §7
    supports_index_membership: bool        # gap §8
    supports_estimate_history: bool        # gap §4
    supports_vintages: bool                # pit_assessment verdict (A-001)
```

`supports_pit=False` for a **revision-prone** family (fundamentals, estimates,
classifications) forces the ingestion layer to stamp
`knowledge_time = retrieval_time` and grade the dataset `SNAPSHOT_STAMPED`
(`system_design.md` §2); nothing downstream may upgrade the grade.
Market-price families retrieved as retrospective daily windows are graded
`RETRO_WINDOW` with bar `knowledge_time` = close of event date per D-009,
PROVIDED the adjustment basis passes VP-07/CT-15 — prices are publicly knowable
at the bar close and are not restated the way filings are. (D-011; resolves the
§1-vs-system_design §2 conflict found by G039.) If the basis check FAILS, the
dataset downgrades to SNAPSHOT_STAMPED (leak-safe: retrieval stamping is
strictly later than bar close) and the downgrade MUST be recorded in the
dataset manifest — binds G020/G021 (D-015; G018 verification amendment 2).

### §3 amendment (D-015)
`UnknownProviderIdError` joins the closed error set: entity-resolution failures
must raise, never return an empty frame (empty-frame-as-absence is the silent
failure §3 forbids). Accepted by G018 verification.

> **D-013 note (2026-07-22):** §4.3's concrete API-stub/replay description is
> descoped — the Protocol + capability records + CT suite are the generic API
> interface; replay mode is a design REQUIREMENT on future real adapters, not
> shipped code. §5's suite path is `tests/integration/test_provider_contract.py`.

## 2. Provider interface (typed stub)

Methods mirror MP §16's capability list one-to-one. All return raw-shaped
`DataFrame`s conforming to per-family raw schemas (G017 defines these
alongside the canonical schemas; raw schema = canonical columns minus
minted/derived ones, plus provider-native identifiers).

```python
class DataProvider(Protocol):
    def capabilities(self) -> ProviderCapabilities: ...

    # MP §16 "load" methods --------------------------------------------------
    def fetch_security_master(
        self, ids: Sequence[ProviderId] | None = None) -> DataFrame: ...
    def fetch_prices(
        self, ids: Sequence[ProviderId], start: date, end: date,
        fields: Sequence[str] = ("close", "market_cap")) -> DataFrame: ...
    # Default fields narrowed to the evidence-demonstrated set (FM-11/31; G013).
    # open/high/low/volume are LISTED_ONLY (FM-12/13/14): explicit requests for
    # them MUST raise FieldUnavailableError (CT-07) until VP-01 passes. (D-012)
    def fetch_corporate_actions(
        self, ids: Sequence[ProviderId], start: date, end: date) -> DataFrame: ...
    def fetch_fundamentals(
        self, ids: Sequence[ProviderId], metrics: Sequence[str],
        start: date, end: date,
        vintage: Literal["latest", "as_reported", "all"] = "latest"
    ) -> DataFrame: ...
    def fetch_estimates(
        self, ids: Sequence[ProviderId], metrics: Sequence[str],
        start: date, end: date) -> DataFrame: ...
    def fetch_classifications(
        self, ids: Sequence[ProviderId], schemes: Sequence[str]) -> DataFrame: ...
    def fetch_market_metrics(   # ADV, multiples, technical raw material
        self, ids: Sequence[ProviderId], metrics: Sequence[str],
        start: date, end: date) -> DataFrame: ...
    def fetch_borrow(
        self, ids: Sequence[ProviderId], start: date, end: date) -> DataFrame: ...
    def fetch_universe_membership(
        self, universe_id: str, start: date, end: date) -> DataFrame: ...
    def fetch_fx_rates(
        self, pairs: Sequence[tuple[str, str]], start: date, end: date
    ) -> DataFrame: ...
    def fetch_trading_calendar(
        self, calendar_id: str, start: date, end: date) -> DataFrame: ...

    # MP §16 "report" methods ------------------------------------------------
    def available_history(self, family: FieldFamily) -> tuple[date | None, date | None]:
        """(earliest, latest) established; None where NOT_ESTABLISHED."""
    def field_coverage(self, family: FieldFamily) -> frozenset[str]: ...
    # revision/PIT support reported via capabilities()
```

Notes:

- `vintage="as_reported"`/`"all"` MUST raise `CapabilityError` when
  `supports_vintages` is false — this is the A-001 guard in interface form.
- `ProviderId` is the provider-native identifier type (ticker+exchange for
  the local-file adapter, synthetic id for the generator). Mapping to
  `security_id` happens in L-CANON (FM-02).

## 3. Error semantics (typed, closed set)

```python
class ProviderError(Exception): ...
class CapabilityError(ProviderError):
    """Request requires a capability the provider declares false.
    NEVER caught-and-defaulted by callers; surfaces to the user."""
class FieldUnavailableError(ProviderError):
    """Requested field not in field_coverage(family)."""
class HistoryUnavailableError(ProviderError):
    """Window outside available_history(family). Partial windows are NOT
    silently truncated: provider returns what exists ONLY when the caller
    passes the window returned by available_history; otherwise raises."""
class IntegrityError(ProviderError):
    """Provider payload violates its own raw schema (malformed workbook,
    corrupt file). Ingestion quarantines, never repairs (G021)."""
```

Behavioral rules: no method returns an empty frame to signal absence
(empty results for a genuinely empty-but-valid query are fine; absence of
capability/field/history is an exception); no method mutates provider state;
repeated identical calls return identical frames (CT-04).

## 4. The three required providers

### 4.1 Synthetic provider (G019)

- Declares every flag true; every family `FULL_VINTAGES`;
  `corporate_action_basis = UNADJUSTED` (emits raw prices + explicit
  actions). It is the only provider that can serve the full seven-version
  reconstruction (feature_coverage.md Fact 1/Fact 2 make AlphaSense-only
  faithful backtests impossible).
- Backed by the scenario generator (§6): all data is generated under a named
  scenario config + seed and shipped with sidecar ground truth.

### 4.2 Local-file provider (AlphaSense-template shaped; G018)

Reads workbook-shaped files from `inputs/data_templates/` (and future user
drops). Capability record is **fixed by G012/G013 evidence** — these
defaults are normative for G018 and each cites its source:

| Capability | Value | Source |
|---|---|---|
| `supports_pit` (all families) | `false` | pit_assessment verdict; A-001 |
| `supports_vintages` | `false` | `Data!N2:O3` = `latest_filing` only |
| `supports_estimate_history` | `false` | gap §4 |
| `supports_corporate_actions` (family available) | `false` | gap §5 |
| `supports_delistings` | `false` | gap §1 |
| `supports_index_membership` | `false` | gap §8 |
| `supports_borrow` / `supports_bid_ask` | `false` | gap §7 / §2 |
| `supports_universe_screening` | `false` | gap §1 (single-ticker templates) |
| `supports_publication_timestamps` | `false` | gap §3 (FM-10) |
| MARKET_DAILY | `available=true`, `revision=LATEST_ONLY`, `history_start=None`, `basis=UNKNOWN` | TM panel RETRO_DAILY; FM-11/17; depth NOT_ESTABLISHED |
| FUNDAMENTALS | `available=true`, `revision=LATEST_ONLY`, FY-5..FY+2 window note | E-G012-06; FM-09 |
| ESTIMATES | `available=true` (current snapshot), `revision=NONE` | gap §4; FM-46 |
| SECURITY_MASTER / CLASSIFICATIONS | `available=true` (current snapshot), `revision=NONE` | FM-01/03/33 SNAPSHOT |
| FX / CALENDAR | `available=false` / derived-with-note | FM-24 / FM-08 |

### 4.3 Generic API provider (stub; G018)

- Abstract base implementing auth-from-environment (variable names declared
  in config, values never logged), request/response logging metadata, and
  retry policy hooks — with `NotImplementedError` fetches. Purpose: pin the
  integration surface for G039 without inventing endpoints (MP §16 "never
  create fake production endpoints").
- Ships with a `replay` mode: given recorded raw snapshots, serves them back
  through the contract — this is how future real-API adapters get contract
  tests without live credentials in CI.

## 5. Contract-test suite (G018; `tests/integration/providers/`)

Parameterized over all registered providers; capability-conditional tests
skip-with-reason only when the capability is declared false AND the test
verifies the refusal path instead. IDs are stable; every future provider
must pass CT-01..15 unmodified.

| ID | Test | Asserts |
|---|---|---|
| CT-01 | capability record completeness | every `FieldFamily` present; flags populated; notes cite a source |
| CT-02 | capability honesty (positive) | for each `available=true` family, fetch returns a raw-schema-conformant frame |
| CT-03 | capability honesty (negative) | for each false flag, the corresponding call raises `CapabilityError` (e.g. `vintage="as_reported"` on local-file) |
| CT-04 | determinism / idempotence | identical calls → identical frames (hash equality after canonical sort) |
| CT-05 | raw schema conformance | dtypes, nullability, closed enums, UTC timestamps |
| CT-06 | history bounds | requests outside `available_history` raise `HistoryUnavailableError`; no silent truncation |
| CT-07 | field coverage honesty | requesting an uncovered field raises `FieldUnavailableError`; `field_coverage` matches what fetches actually return |
| CT-08 | no fabrication | fields the family does not cover are absent/null, never synthesized (spot-checked against declared coverage) |
| CT-09 | id stability | same entity → same `ProviderId` across calls |
| CT-10 | knowledge-time discipline | if `supports_pit=false`, returned frames carry NO knowledge_time column (stamping is ingestion's job); if true, knowledge_time non-null and ≥ event time (U3) |
| CT-11 | vintage semantics | if `FULL_VINTAGES`: `vintage="all"` returns append-only history; `latest` equals max-knowledge row (CI-002 source-side) |
| CT-12 | empty-vs-error distinction | valid-but-empty query returns empty conformant frame; absence conditions raise |
| CT-13 | immutability of inputs | provider never writes outside its own cache dir; input files unchanged (hash before/after) |
| CT-14 | credential hygiene | no credential value appears in frames, logs, or manifests (canary env var test) |
| CT-15 | corporate-action basis declared | market frames' basis matches `corporate_action_basis`; UNKNOWN forces canonical layer to require explicit action data or config acknowledgment before return computation (FM-17 guard) |

## 6. Synthetic scenario interface (G019 — additional, beyond the contract)

Per `leakage_tests.md` (G019 rule): "every scenario is a named generator
config; every embedded truth is machine-readable; every teeth-check ablation
is generated alongside."

```python
@dataclass(frozen=True)
class ScenarioConfig:
    scenario_id: str                # "LT-001".."LT-021" or "baseline"
    seed: int
    n_securities: int = 500
    n_years: int = 15
    frequency: Literal["monthly", "weekly"] = "monthly"
    params: Mapping[str, float]     # scenario-specific knobs (embedded IC,
                                    # regime durations, hazard rates, ...)

@dataclass(frozen=True)
class ScenarioBundle:
    datasets: Mapping[FieldFamily, DatasetRef]   # raw-layer-ready outputs
    sidecar: SidecarTruth                        # machine-readable ground truth
    ablations: Mapping[str, DatasetRef]          # "teeth" variants, e.g.
        # LT-010 "latest_vintage" flat table; LT-016 "current_membership";
        # LT-012 "unpurged" fold spec input

class SyntheticProvider(DataProvider):
    def generate(self, scenario: ScenarioConfig) -> ScenarioBundle: ...
    def scenario_catalog(self) -> frozenset[str]:   # must cover LT-001..021
```

`SidecarTruth` contents (schema owned by G019, consumed by
`tests/leakage/`): embedded per-feature IC paths, regime/crisis/switch
dates, delisting events + analytic survivorship uplift (LT-009), seeded
data-error list (LT-021), oracle references (LT-014/017), expected
per-quantile payoffs (LT-006), and the scenario's pass-band parameters —
tests "derive bands from the sidecar, not hard-coded constants"
(leakage_tests preamble).

Generator realism requirements trace to MP §17's list (multiple
countries/sectors, membership churn, listings/delistings, corporate actions,
publication lags, restatements, missing values, estimate revisions, factor
structure, regimes, liquidity variation, borrow, deliberate errors) — each
is a generator module toggled by `ScenarioConfig.params`, all emitting
FULL_VINTAGES data with true knowledge times.

## 7. What providers do NOT do

- No caching layers with invalidation logic (premature; a raw snapshot IS
  the cache). No async. No connection pooling. No retries in synthetic/local
  providers.
- No universe construction (that is `data.point_in_time`'s builder over
  membership intervals — §6.3 of `canonical_schemas.md`).
- No return computation, no adjustment application, no currency conversion —
  L-CANON derivations, testable once, not per provider.
