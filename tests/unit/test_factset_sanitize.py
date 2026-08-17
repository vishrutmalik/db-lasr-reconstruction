"""FS010 — credential resolution, presence checks, data-root validation.

Secret-hygiene invariants (fs_goals HARD RULES / CT-14 discipline): values
never appear in reprs, error messages, or sanitized trees; the data root
is validated outside the repo and outside OneDrive/CloudStorage paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lasr.data.providers.factset.errors import (
    FactSetAuthError,
    FactSetDataRootError,
)
from lasr.data.providers.factset.sanitize import (
    ENV_API_KEY,
    ENV_AUTH_MODE,
    ENV_LIVE,
    ENV_TRIAL_DATA_ROOT,
    ENV_USERNAME,
    Sanitizer,
    credential_presence,
    resolve_auth,
    validate_trial_data_root,
)

pytestmark = pytest.mark.unit

_CANARY_USER = "CANARY-USER-1234567"
_CANARY_KEY = "CANARY-KEY-abcdefghij"


class TestResolveAuth:
    def test_basic_auth_resolved(self) -> None:
        auth = resolve_auth({ENV_USERNAME: _CANARY_USER, ENV_API_KEY: _CANARY_KEY})
        assert auth.mode == "basic"
        assert auth.username == _CANARY_USER
        assert auth.api_key == _CANARY_KEY

    def test_missing_credentials_error_names_vars_not_values(self) -> None:
        with pytest.raises(FactSetAuthError) as excinfo:
            resolve_auth({ENV_USERNAME: _CANARY_USER})
        message = str(excinfo.value)
        assert ENV_API_KEY in message
        assert _CANARY_USER not in message

    def test_oauth_mode_is_typed_refusal_not_fallback(self) -> None:
        with pytest.raises(FactSetAuthError, match="not implemented"):
            resolve_auth(
                {
                    ENV_AUTH_MODE: "oauth_config",
                    ENV_USERNAME: _CANARY_USER,
                    ENV_API_KEY: _CANARY_KEY,
                }
            )

    def test_unknown_mode_refused(self) -> None:
        with pytest.raises(FactSetAuthError, match="unknown FACTSET_AUTH_MODE"):
            resolve_auth({ENV_AUTH_MODE: "kerberos"})

    def test_repr_and_str_never_leak_values(self) -> None:
        auth = resolve_auth({ENV_USERNAME: _CANARY_USER, ENV_API_KEY: _CANARY_KEY})
        for rendered in (repr(auth), str(auth)):
            assert _CANARY_USER not in rendered
            assert _CANARY_KEY not in rendered


class TestCredentialPresence:
    def test_presence_only_booleans(self) -> None:
        presence = credential_presence(
            {ENV_USERNAME: _CANARY_USER, ENV_API_KEY: "", ENV_LIVE: "1"}
        )
        assert presence[ENV_USERNAME] is True
        assert presence[ENV_API_KEY] is False
        assert presence[ENV_LIVE] is True
        assert presence[ENV_TRIAL_DATA_ROOT] is False
        for value in presence.values():
            assert isinstance(value, bool)  # never the value itself


class TestSanitizer:
    def test_redacts_all_secrets_in_strings_and_trees(self) -> None:
        sanitizer = Sanitizer((_CANARY_USER, _CANARY_KEY))
        dirty = f"user={_CANARY_USER} key={_CANARY_KEY} ok=1"
        clean = sanitizer.clean(dirty)
        assert _CANARY_USER not in clean and _CANARY_KEY not in clean
        assert "***REDACTED***" in clean
        tree = {"a": [f"x {_CANARY_KEY}"], "b": {"c": _CANARY_USER}, "n": 3}
        clean_tree = sanitizer.clean_tree(tree)
        assert _CANARY_KEY not in str(clean_tree)
        assert _CANARY_USER not in str(clean_tree)

    def test_empty_secrets_are_ignored(self) -> None:
        assert Sanitizer(("",)).clean("text") == "text"


class TestTrialDataRoot:
    def test_required_in_live_mode(self, tmp_path: Path) -> None:
        with pytest.raises(FactSetDataRootError, match="required in live mode"):
            validate_trial_data_root({}, repo_root=tmp_path, require=True)

    def test_optional_when_not_required(self, tmp_path: Path) -> None:
        assert validate_trial_data_root({}, repo_root=tmp_path, require=False) is None

    def test_relative_path_refused(self, tmp_path: Path) -> None:
        with pytest.raises(FactSetDataRootError, match="absolute"):
            validate_trial_data_root(
                {ENV_TRIAL_DATA_ROOT: "relative/dir"},
                repo_root=tmp_path,
                require=True,
            )

    def test_inside_repo_refused(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        inside = repo / "data" / "factset"
        inside.mkdir(parents=True)
        with pytest.raises(FactSetDataRootError, match="OUTSIDE the repository"):
            validate_trial_data_root(
                {ENV_TRIAL_DATA_ROOT: str(inside)},
                repo_root=repo,
                require=True,
            )

    def test_repo_root_itself_refused(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        with pytest.raises(FactSetDataRootError, match="OUTSIDE the repository"):
            validate_trial_data_root(
                {ENV_TRIAL_DATA_ROOT: str(repo)}, repo_root=repo, require=True
            )

    @pytest.mark.parametrize("fragment", ["OneDrive", "onedrive", "CloudStorage"])
    def test_cloud_synced_roots_refused(self, tmp_path: Path, fragment: str) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        cloudy = tmp_path / fragment / "factset_data"
        cloudy.mkdir(parents=True)
        with pytest.raises(FactSetDataRootError, match="OneDrive"):
            validate_trial_data_root(
                {ENV_TRIAL_DATA_ROOT: str(cloudy)}, repo_root=repo, require=True
            )

    def test_missing_directory_refused_in_live_mode(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        with pytest.raises(FactSetDataRootError, match="existing directory"):
            validate_trial_data_root(
                {ENV_TRIAL_DATA_ROOT: str(tmp_path / "nope")},
                repo_root=repo,
                require=True,
            )

    def test_valid_external_root_accepted(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        root = tmp_path / "trial_data"
        root.mkdir()
        resolved = validate_trial_data_root(
            {ENV_TRIAL_DATA_ROOT: str(root)}, repo_root=repo, require=True
        )
        assert resolved == root.resolve()
