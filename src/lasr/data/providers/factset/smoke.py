"""FS010 bounded live auth/entitlement smoke (symbology, <=5 requests).

# arch: fs_goals.md FS010 charter — ONE bounded live smoke at completion,
if and only if all gates pass AND credentials are present: symbology
lookup of <=5 well-known ids, cache-first, recorded to the run manifest,
raw responses under ``FACTSET_TRIAL_DATA_ROOT`` (never git).

The runner NEVER reads credential files; env vars only (names in
``sanitize.py``). The live gate stays belt-and-braces: this module flips
the loaded config's ``transport.live`` on (the human invoking the smoke
IS the config half of the consent), but env ``FACTSET_LIVE=1``, the kill
switches, the data-root validation, budgets, and storage caps all still
apply through :func:`build_transport`. Absent credentials → typed
refusal, reported as UNRESOLVED by the caller.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from lasr.data.providers.factset.config import load_trial_config
from lasr.data.providers.factset.errors import (
    FactSetConfigError,
    FactSetEntitlementError,
    FactSetTransportError,
)
from lasr.data.providers.factset.http import HttpSender
from lasr.data.providers.factset.run_manifest import (
    build_run_manifest,
    write_run_manifest,
)
from lasr.data.providers.factset.sanitize import (
    Sanitizer,
    credential_presence,
    resolve_auth,
    validate_trial_data_root,
)
from lasr.data.providers.factset.symbology_models import (
    build_identifier_resolution_request,
    parse_identifier_resolution_response,
)
from lasr.data.providers.factset.transport import build_transport

__all__ = ["run_live_smoke"]

_SMOKE_SAMPLE = "fs010_live_smoke"
_SMOKE_OUTPUT_TYPES = ("fsymSecurityId", "fsymRegionalId", "tickerRegion")
_MAX_SMOKE_IDS = 5


def run_live_smoke(
    *,
    config_path: Path,
    environ: Mapping[str, str],
    repo_root: Path,
    code_revision: str,
    now: datetime,
    run_id: str = "fs010-live-smoke",
    sender: HttpSender | None = None,
) -> dict[str, object]:
    """Execute the bounded smoke; returns a value-free summary mapping.

    Exactly ONE symbology identifier-resolution POST (<=5 ids, cache-first
    — a re-run spends zero quota). The run manifest lands under
    ``<FACTSET_TRIAL_DATA_ROOT>/runs/<run_id>/``.
    """
    config = load_trial_config(config_path)
    smoke = config.samples.get(_SMOKE_SAMPLE)
    if smoke is None or not smoke.ids:
        raise FactSetConfigError(
            f"trial config declares no {_SMOKE_SAMPLE!r} sample block"
        )
    if len(smoke.ids) > _MAX_SMOKE_IDS:
        raise FactSetConfigError(
            f"smoke sample exceeds the charter budget: {len(smoke.ids)} ids"
            f" > {_MAX_SMOKE_IDS}"
        )

    live_config = config.model_copy(
        update={"transport": config.transport.model_copy(update={"live": True})}
    )
    # Typed refusals BEFORE any transport exists: absent credentials or a
    # closed live gate never produce a partial run.
    sanitizer: Sanitizer = resolve_auth(environ).sanitizer()
    transport = build_transport(
        config=live_config,
        environ=environ,
        repo_root=repo_root,
        sender=sender,
    )
    request = build_identifier_resolution_request(
        ids=list(smoke.ids),
        output_symbol_types=list(_SMOKE_OUTPUT_TYPES),
    )

    entitlement = "UNKNOWN"
    error: str | None = None
    resolved_rows = 0
    try:
        response = transport.execute(request)
        rows = parse_identifier_resolution_response(
            response.body, requested_output_types=list(_SMOKE_OUTPUT_TYPES)
        )
        resolved_rows = len(rows)
        entitlement = "ENTITLED"
    except FactSetEntitlementError as exc:
        entitlement = "FORBIDDEN"
        error = sanitizer.clean(str(exc))
    except FactSetTransportError as exc:
        error = sanitizer.clean(str(exc))
        raise
    finally:
        data_root = validate_trial_data_root(
            environ, repo_root=repo_root, require=False
        )
        if data_root is not None:
            manifest = build_run_manifest(
                run_id=run_id,
                config=live_config,
                code_revision=code_revision,
                stats=transport.stats,
                environ=environ,
                started=now,
                finished=now,
                notes=(
                    f"FS010 bounded live smoke; entitlement={entitlement};"
                    f" error={error or 'none'}"
                ),
            )
            write_run_manifest(
                manifest,
                runs_root=data_root / "runs",
                sanitizer=sanitizer,
            )

    return {
        "run_id": run_id,
        "entitlement": entitlement,
        "resolved_rows": resolved_rows,
        "live_calls": transport.stats.live_calls,
        "cache_hits": transport.stats.cache_hits,
        "credential_presence": credential_presence(environ),
        "error": error,
    }
