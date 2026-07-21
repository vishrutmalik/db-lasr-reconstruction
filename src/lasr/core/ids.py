"""Identity spine: internal security ids and identifier vocabulary.

Internal ids are minted by us because no ISIN/CUSIP/SEDOL/FIGI exists in the
provider surface (# arch: canonical_schemas.md §1.1, FM-02). The row models
for ``securities`` / ``identifier_map`` live in ``lasr.data.schemas``
(layering: schemas import core, never the reverse); this module owns the
shared vocabulary and the deterministic minting helper.
"""

from __future__ import annotations

import hashlib
from datetime import date
from enum import StrEnum
from typing import TypeAlias

from lasr.core.errors import IdentityError

__all__ = [
    "SECURITY_ID_PREFIX",
    "IdScheme",
    "IssuerId",
    "SecurityId",
    "UniverseId",
    "mint_security_id",
]

#: Opaque, stable internal id, e.g. ``SEC-0f3a9c21d47b``
#: (# arch: canonical_schemas.md §1.1).
SecurityId: TypeAlias = str
#: Groups share classes of one issuer (# arch: canonical_schemas.md §1.1).
IssuerId: TypeAlias = str
#: Universe key, e.g. ``russell3000`` (# arch: canonical_schemas.md §6.3).
UniverseId: TypeAlias = str

SECURITY_ID_PREFIX = "SEC"


class IdScheme(StrEnum):
    """Identifier schemes for provider identifiers, effective-dated.

    # arch: canonical_schemas.md §1.2 (``identifier_map.id_scheme``).
    """

    TICKER = "ticker"
    PROVIDER_NATIVE = "provider_native"
    ISIN = "isin"
    CUSIP = "cusip"
    SEDOL = "sedol"
    FIGI = "figi"


def mint_security_id(ticker: str, exchange: str, first_seen: date) -> SecurityId:
    """Mint the local-file adapter's internal security id.

    Minting policy (# arch: canonical_schemas.md §1.1, assumption
    A-ARCH-01): ``hash(ticker, exchange, first_seen_date)``. Deterministic
    and normalization-invariant (case/whitespace) so re-ingestion re-mints
    the identical id (idempotent reruns, MP §15). The collision rule is
    recorded in the dataset manifest by the canonical builder (G020).

    Synthetic providers assign ids from their own truth and do not call
    this helper.
    """
    ticker_norm = ticker.strip().upper()
    exchange_norm = exchange.strip().upper()
    if not ticker_norm or not exchange_norm:
        raise IdentityError(
            "mint_security_id requires non-empty ticker and exchange "
            f"(got ticker={ticker!r}, exchange={exchange!r})"
        )
    payload = f"{ticker_norm}|{exchange_norm}|{first_seen.isoformat()}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{SECURITY_ID_PREFIX}-{digest[:12]}"
