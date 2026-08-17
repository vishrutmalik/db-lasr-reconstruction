"""FactSet provider package (FS010: shared transport + trial config).

# arch: docs/architecture/factset_integration.md §1.3 (A2) — everything
here sits strictly BELOW the unchanged DataProvider Protocol. FS010 owns
the transport/cache/config/control layer; family adapters (symbology.py,
fundamentals.py, ...) arrive with FS011-16 on FS009-verified manifests.

Import surface for the adapter goals (FS011/FS024 interface):

- ``build_transport`` / ``FactSetTransport.execute`` — cache-first request
  execution (replay or live);
- ``NormalizedRequest`` + family builders (``symbology_models``) — request
  identity; never hand-build wire payloads in adapters;
- ``load_trial_config`` — the single configuration entry point;
- the typed error set in ``errors``.
"""

from lasr.data.providers.factset.cache import (
    CachedResponse,
    CaptureRecord,
    ResponseCache,
    write_capture_set,
)
from lasr.data.providers.factset.config import (
    FactSetTrialConfig,
    load_trial_config,
    trial_config_hash,
)
from lasr.data.providers.factset.request_norm import (
    NormalizedRequest,
    PageKey,
    chunk_ids,
    normalize_id_list,
    request_hash,
)
from lasr.data.providers.factset.transport import (
    BatchOutcome,
    FactSetTransport,
    build_transport,
    live_gate_open,
)

__all__ = [
    "BatchOutcome",
    "CachedResponse",
    "CaptureRecord",
    "FactSetTransport",
    "FactSetTrialConfig",
    "NormalizedRequest",
    "PageKey",
    "ResponseCache",
    "build_transport",
    "chunk_ids",
    "live_gate_open",
    "load_trial_config",
    "normalize_id_list",
    "request_hash",
    "trial_config_hash",
    "write_capture_set",
]
