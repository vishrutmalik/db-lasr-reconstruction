"""FS024 notebook scaffold: structure, safety, replay execution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = REPO_ROOT / "notebooks" / "factset_api_trial.ipynb"


def _load_notebook() -> dict[str, object]:
    payload = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_sections_one_through_four_and_live_default_are_explicit() -> None:
    notebook = _load_notebook()
    cells = notebook["cells"]
    assert isinstance(cells, list)
    text = "\n".join("".join(cell["source"]) for cell in cells)
    for section in range(1, 5):
        assert f"## {section}." in text
    assert "LIVE_PULL = False" in text
    assert "VF-FS010-3/RT-FS010-4" in text
    assert "api_keys.txt" not in text
    assert "httpx" not in text


def test_code_cells_execute_top_to_bottom_in_empty_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notebook = _load_notebook()
    cells = notebook["cells"]
    assert isinstance(cells, list)
    data_root = tmp_path / "trial_data"
    data_root.mkdir()
    monkeypatch.setenv("FACTSET_TRIAL_DATA_ROOT", str(data_root))
    monkeypatch.chdir(REPO_ROOT)

    namespace: dict[str, object] = {}
    for cell in cells:
        assert isinstance(cell, dict)
        if cell.get("cell_type") == "code":
            source = cell.get("source")
            assert isinstance(source, list)
            exec(compile("".join(source), str(NOTEBOOK), "exec"), namespace)

    report = namespace["REPORT"]
    assert report.live_calls == 0  # type: ignore[union-attr]
    assert len(report.probes) == 15  # type: ignore[union-attr]
