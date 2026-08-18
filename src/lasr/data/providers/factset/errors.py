"""Closed typed error set for the FactSet transport (FS010).

# arch: docs/architecture/factset_integration.md §3.3/§6 (FS002); the
transport never signals failure with empty payloads or silent fallbacks
(provider_contract.md §3 discipline applied below the Protocol). Every
error is a :class:`~lasr.data.providers.base.ProviderError` subclass so
adapters (FS011-16) surface one closed family to callers.

Secret hygiene: no error message in this module may embed credential
VALUES; constructors receive already-sanitized strings (transport passes
everything through :class:`lasr.data.providers.factset.sanitize.Sanitizer`
before raising).
"""

from __future__ import annotations

from lasr.data.providers.base import IntegrityError, ProviderError

__all__ = [
    "FactSetAccessPolicyConflictError",
    "FactSetAuthError",
    "FactSetBatchError",
    "FactSetBudgetExceededError",
    "FactSetCacheMissError",
    "FactSetCapabilityExcludedError",
    "FactSetClientError",
    "FactSetConfigError",
    "FactSetDataRootError",
    "FactSetEntitlementError",
    "FactSetIntegrityError",
    "FactSetKillSwitchError",
    "FactSetRateLimitError",
    "FactSetRequestTooLargeError",
    "FactSetRetryExhaustedError",
    "FactSetServerError",
    "FactSetStorageCapError",
    "FactSetTransportError",
]


class FactSetTransportError(ProviderError):
    """Base class for every FactSet transport/cache error (closed set)."""


class FactSetConfigError(FactSetTransportError):
    """Trial configuration is invalid or internally inconsistent."""


class FactSetCacheMissError(FactSetTransportError):
    """Replay-mode cache miss.

    An ABSENCE condition, not an empty result (FS002 §3.3): replay mode
    never constructs a network client, so a miss is a typed refusal.
    """


class FactSetCapabilityExcludedError(FactSetTransportError):
    """Reviewed access plan refused a request before any runtime evidence."""

    def __init__(
        self, identities: tuple[str, ...], evidence_refs: tuple[str, ...]
    ) -> None:
        self.identities = identities
        self.evidence_refs = evidence_refs
        super().__init__(
            "FactSet access plan refused capability before cache/network: "
            f"{', '.join(identities)}; reviewed references={list(evidence_refs)}"
        )


class FactSetAccessPolicyConflictError(FactSetTransportError):
    """New evidence contradicts a reviewed access-plan disposition."""


class FactSetKillSwitchError(FactSetTransportError):
    """Live execution refused: the kill switch is engaged, or live mode
    was requested without BOTH config ``transport.live=true`` and env
    ``FACTSET_LIVE=1`` (belt-and-braces, FS002 §6.1)."""


class FactSetDataRootError(FactSetTransportError):
    """``FACTSET_TRIAL_DATA_ROOT`` is missing or invalid for live mode.

    Live mode requires the root to exist, be absolute, live OUTSIDE the
    repository and outside any OneDrive/CloudStorage-synced path
    (fs_review_adjudication.md §9 / D-020(d)); a silent local default for
    licensed data is forbidden.
    """


class FactSetBudgetExceededError(FactSetTransportError):
    """A live-call budget (daily total or per-endpoint limit) is exhausted.

    Loud hard stop, never gradual degradation (FS002 §6.4).
    """


class FactSetStorageCapError(FactSetTransportError):
    """Persisting a capture would breach the configured storage cap or the
    free-disk reserve (WP0 storage guard, FS002 §6.4/§9.2)."""


class FactSetAuthError(FactSetTransportError):
    """Authentication failure (HTTP 401) or unusable auth configuration.

    NOT retryable by backoff; re-attemptable only via force-refresh after
    the credentials are fixed (error-cache policy, D-020(d)).
    """


class FactSetEntitlementError(FactSetTransportError):
    """Entitlement refusal (HTTP 403, incl. per-identifier
    ``forbiddenIdentifier`` — FS003 identity_semantics).

    Trial EVIDENCE, cached as such; re-attemptable only via force-refresh.
    """


class FactSetRateLimitError(FactSetTransportError):
    """Rate limit / quota exceedance (HTTP 429 or documented equivalent).

    Retryable class; raised only when retries are exhausted.
    """


class FactSetServerError(FactSetTransportError):
    """Transient server failure (5xx / network timeout). Retryable class;
    raised only when retries are exhausted."""


class FactSetRequestTooLargeError(FactSetTransportError):
    """The symbology 29s-server-timeout shape: HTTP 400 whose BODY says the
    request took too long / try a smaller request (FS003 limits block).

    Classified by body content, never by status alone; the remedy is
    request splitting, not backoff.
    """


class FactSetRetryExhaustedError(FactSetTransportError):
    """Retryable failures persisted beyond the configured retry budget."""


class FactSetClientError(FactSetTransportError):
    """Non-retryable 4xx outside the auth/entitlement/split classes.

    A caller bug or contract misunderstanding; captured as evidence and
    surfaced — never swallowed.
    """


class FactSetBatchError(FactSetTransportError):
    """Async batch protocol failure: vendor-reported terminal failure,
    poll timeout, or a lost batch id (FS002 §6.3)."""


class FactSetIntegrityError(IntegrityError):
    """FactSet payload violates its own documented shape (malformed JSON,
    checksum mismatch on a cached capture). Quarantine, never repair."""
