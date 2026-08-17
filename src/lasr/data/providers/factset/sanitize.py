"""Credential resolution, presence checks, sanitized logging (FS010).

Env-var NAMES are documented here (FS002 §6.1); VALUES never appear in
code, logs, telemetry, captures, manifests, or error messages. Modules in
this package never read ``os.environ`` implicitly: every function below
takes an explicit ``environ`` mapping, passed in by the process entry
point (config ownership rule, system_design.md §4) — tests pass dicts.

| Env var                     | Meaning                                    |
|-----------------------------|--------------------------------------------|
| ``FACTSET_AUTH_MODE``       | ``basic`` (primary, FS003 D-2) or          |
|                             | ``oauth_config`` (unimplemented in FS010)  |
| ``FACTSET_USERNAME``        | username-serial (basic mode)               |
| ``FACTSET_API_KEY``         | API key (basic mode)                       |
| ``FACTSET_OAUTH_CONFIG_PATH`` | OAuth2 ConfidentialClient config path,   |
|                             | outside the repo (SDK pattern)             |
| ``FACTSET_LIVE``            | must be ``"1"`` for live mode, in ADDITION |
|                             | to config ``transport.live=true``          |
| ``FACTSET_KILL_SWITCH``     | ``"1"`` refuses live mode regardless       |
| ``FACTSET_TRIAL_DATA_ROOT`` | root for ALL trial data; REQUIRED in live  |
|                             | mode, validated outside repo + OneDrive    |
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from lasr.data.providers.factset.errors import (
    FactSetAuthError,
    FactSetDataRootError,
)

__all__ = [
    "ENV_API_KEY",
    "ENV_AUTH_MODE",
    "ENV_KILL_SWITCH",
    "ENV_LIVE",
    "ENV_OAUTH_CONFIG_PATH",
    "ENV_TRIAL_DATA_ROOT",
    "ENV_USERNAME",
    "FactSetAuthConfig",
    "Sanitizer",
    "credential_presence",
    "resolve_auth",
    "validate_trial_data_root",
]

logger = logging.getLogger(__name__)

ENV_AUTH_MODE = "FACTSET_AUTH_MODE"
ENV_USERNAME = "FACTSET_USERNAME"
ENV_API_KEY = "FACTSET_API_KEY"
ENV_OAUTH_CONFIG_PATH = "FACTSET_OAUTH_CONFIG_PATH"
ENV_LIVE = "FACTSET_LIVE"
ENV_KILL_SWITCH = "FACTSET_KILL_SWITCH"
ENV_TRIAL_DATA_ROOT = "FACTSET_TRIAL_DATA_ROOT"

#: Path fragments that mark a cloud-synced location (D-020(d): licensed
#: raw data must not land in the repo or any OneDrive/CloudStorage path).
_FORBIDDEN_ROOT_FRAGMENTS = ("onedrive", "cloudstorage")

_REDACTED = "***REDACTED***"


class Sanitizer:
    """Redacts known secret VALUES from any outbound string.

    Constructed once with the resolved secrets; applied to every log
    message, telemetry field, error message, and manifest string the
    transport emits (CT-14/FT-03 discipline below the provider).
    """

    def __init__(self, secrets: tuple[str, ...]) -> None:
        # Longest-first so overlapping secrets redact completely.
        self._secrets = tuple(sorted((s for s in secrets if s), key=len, reverse=True))

    def clean(self, text: str) -> str:
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, _REDACTED)
        return text

    def clean_tree(self, value: object) -> object:
        """Recursively sanitize a JSON-like tree (telemetry/manifest use)."""
        if isinstance(value, str):
            return self.clean(value)
        if isinstance(value, Mapping):
            return {str(k): self.clean_tree(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [self.clean_tree(v) for v in value]
        return value


@dataclass(frozen=True)
class FactSetAuthConfig:
    """Resolved auth material. ``repr`` never exposes values."""

    mode: str
    username: str = field(repr=False, default="")
    api_key: str = field(repr=False, default="")
    oauth_config_path: str = field(repr=False, default="")

    def sanitizer(self) -> Sanitizer:
        return Sanitizer((self.username, self.api_key, self.oauth_config_path))

    def __str__(self) -> str:  # defense in depth: str() is value-free too
        return f"FactSetAuthConfig(mode={self.mode!r})"


def credential_presence(environ: Mapping[str, str]) -> dict[str, bool]:
    """Presence-only check (never values): safe to log and to record in
    run manifests / reports (fs_goals HARD RULES)."""
    return {
        name: bool(environ.get(name, "").strip())
        for name in (
            ENV_AUTH_MODE,
            ENV_USERNAME,
            ENV_API_KEY,
            ENV_OAUTH_CONFIG_PATH,
            ENV_LIVE,
            ENV_TRIAL_DATA_ROOT,
        )
    }


def resolve_auth(environ: Mapping[str, str]) -> FactSetAuthConfig:
    """Build the typed auth config from env-var NAMES.

    Basic mode (primary per FS003 D-2) requires ``FACTSET_USERNAME`` +
    ``FACTSET_API_KEY``. ``oauth_config`` mode is documented but not
    implemented by FS010 — requesting it is a typed refusal, never a
    silent fallback to basic.
    """
    mode = environ.get(ENV_AUTH_MODE, "basic").strip() or "basic"
    if mode == "oauth_config":
        raise FactSetAuthError(
            "FACTSET_AUTH_MODE=oauth_config is documented but not implemented"
            " by the FS010 transport; use basic (FS003 D-2 primary scheme)"
        )
    if mode != "basic":
        raise FactSetAuthError(
            f"unknown FACTSET_AUTH_MODE {mode!r}; expected 'basic' or 'oauth_config'"
        )
    username = environ.get(ENV_USERNAME, "").strip()
    api_key = environ.get(ENV_API_KEY, "").strip()
    if not username or not api_key:
        missing = [
            name
            for name, value in ((ENV_USERNAME, username), (ENV_API_KEY, api_key))
            if not value
        ]
        raise FactSetAuthError(
            "basic auth requires env vars "
            + " and ".join(missing)
            + " (names only; values are never logged)"
        )
    return FactSetAuthConfig(mode="basic", username=username, api_key=api_key)


def validate_trial_data_root(
    environ: Mapping[str, str],
    *,
    repo_root: Path,
    require: bool,
) -> Path | None:
    """Validate ``FACTSET_TRIAL_DATA_ROOT`` per D-020(d).

    Live mode (``require=True``): the variable is REQUIRED, must be an
    absolute existing directory, must lie OUTSIDE the repository, and its
    resolved path must not contain 'OneDrive' or 'CloudStorage' (case-
    insensitive) — no silent local default for licensed data. Replay mode
    returns ``None`` when unset (tests/replay use explicit tmp roots).
    """
    raw = environ.get(ENV_TRIAL_DATA_ROOT, "").strip()
    if not raw:
        if require:
            raise FactSetDataRootError(
                f"{ENV_TRIAL_DATA_ROOT} is required in live mode; a silent"
                " local default for licensed vendor data is forbidden"
                " (D-020(d))"
            )
        return None
    root = Path(raw)
    if not root.is_absolute():
        raise FactSetDataRootError(f"{ENV_TRIAL_DATA_ROOT} must be an absolute path")
    resolved = root.resolve()
    resolved_repo = repo_root.resolve()
    if resolved == resolved_repo or resolved_repo in resolved.parents:
        raise FactSetDataRootError(
            f"{ENV_TRIAL_DATA_ROOT} must lie OUTSIDE the repository"
            " (raw vendor responses never enter git — fs_goals HARD RULES)"
        )
    lowered = str(resolved).lower()
    if any(fragment in lowered for fragment in _FORBIDDEN_ROOT_FRAGMENTS):
        raise FactSetDataRootError(
            f"{ENV_TRIAL_DATA_ROOT} must not point into a OneDrive/"
            "CloudStorage-synced location (D-020(d))"
        )
    if require and not resolved.is_dir():
        raise FactSetDataRootError(
            f"{ENV_TRIAL_DATA_ROOT} must name an existing directory in live"
            " mode (create it explicitly; the transport never invents a"
            " storage location)"
        )
    return resolved
