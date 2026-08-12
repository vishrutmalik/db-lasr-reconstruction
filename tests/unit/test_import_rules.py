"""Architecture import-rule enforcement (G017).

Encodes the system_design.md §4 dependency table ("an arrow means may
import; anything not listed is forbidden") as an AST walk over ``import``
statements, including the hard prohibitions:

- ``models.*`` never imports ``data.providers`` / ``data.canonical`` /
  ``data.point_in_time`` (models sneaking non-PIT reads around L-TX, CI-001);
- ``features``/``targets`` never import ``data.canonical`` directly
  (vintage-bypass joins, CI-002 / LT-010 / LT-013);
- ``data.providers`` never imports ``data.canonical``+ (providers
  "helpfully" normalizing — fabrication risk, MP §16);
- nothing imports ``cli`` (hidden entry-point state);
- challenger-extra libraries (sklearn/xgboost) import only under
  ``models.challengers`` (pyproject §4: never imported by the core).

The scanner is exercised against mutation-style negative controls built in
temp trees (never by editing src): each forbidden edge must be *detected*,
proving the test fails if such an import is ever introduced.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"

#: system_design.md §4 — package -> lasr packages it may import.
#: Keys own their subtrees (longest-prefix match); importing within one's
#: own rule family is always allowed. "lasr" and "lasr.data" are pure
#: namespaces: their empty sets force their __init__ modules to stay free
#: of lasr imports, which is what makes importing them harmless.
_L0_2 = frozenset({"lasr.core", "lasr.config", "lasr.artifacts", "lasr.data.schemas"})
_L0_3 = _L0_2 | {"lasr.data.providers"}
_L0_4 = _L0_3 | {"lasr.data.ingestion", "lasr.data.canonical"}
_L0_5 = _L0_4 | {"lasr.data.point_in_time", "lasr.data.quality"}
_L0_7 = _L0_5 | {"lasr.features", "lasr.targets", "lasr.models"}
_L0_9 = _L0_7 | {"lasr.validation", "lasr.portfolio", "lasr.costs"}
_L0_10 = _L0_9 | {"lasr.backtesting"}

RULES: dict[str, frozenset[str]] = {
    "lasr": frozenset(),  # root __init__: namespace only
    "lasr.core": frozenset(),  # Level 0
    "lasr.config": frozenset({"lasr.core"}),  # Level 1
    "lasr.artifacts": frozenset({"lasr.core"}),
    "lasr.data": frozenset(),  # namespace only
    "lasr.data.schemas": frozenset({"lasr.core", "lasr.config"}),  # Level 2
    # G019: the synthetic generator is a Level-3 sibling of providers —
    # it emits raw-shaped ROWS (never frames) and may not import providers;
    # the synthetic provider adapter (lasr.data.providers.synthetic_provider)
    # wraps it, so providers gain the synthetic edge (one direction only).
    "lasr.data.synthetic": frozenset({"lasr.core", "lasr.config", "lasr.data.schemas"}),
    "lasr.data.providers": frozenset(  # Level 3
        {"lasr.core", "lasr.config", "lasr.data.schemas", "lasr.data.synthetic"}
    ),
    "lasr.data.ingestion": _L0_3,  # Level 4
    "lasr.data.canonical": _L0_3,
    "lasr.data.point_in_time": _L0_4,  # Level 5
    "lasr.data.quality": _L0_4,
    "lasr.features": _L0_2 | {"lasr.data.point_in_time"},  # Level 6
    "lasr.targets": _L0_2 | {"lasr.data.point_in_time"},
    "lasr.models": frozenset(  # Level 7: types only
        {"lasr.core", "lasr.config", "lasr.data.schemas"}
    ),
    "lasr.validation": _L0_7,  # Level 8
    "lasr.portfolio": _L0_2,  # Level 9
    "lasr.costs": _L0_2,
    "lasr.backtesting": _L0_9,  # Level 10
    "lasr.reporting": _L0_10,  # Level 11 (read-only artifact interfaces)
    # Level 12 (G029): run assembly imports everything below it; only the
    # CLI (and tests) import the pipeline.
    "lasr.pipeline": _L0_10 | {"lasr.reporting"},
    "lasr.cli": _L0_10 | {"lasr.reporting", "lasr.pipeline"},  # Level 12
}

#: Namespace-only packages: importable by anyone because their own rule row
#: (empty set) keeps their __init__ modules free of lasr imports.
NAMESPACE_PACKAGES = frozenset({"lasr", "lasr.data"})

#: Challenger-extra libraries: importable only under this subtree.
CHALLENGER_ONLY = {
    "sklearn": "lasr.models.challengers",
    "xgboost": "lasr.models.challengers",
}


def _module_name(path: Path, src_root: Path) -> str:
    rel = path.relative_to(src_root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _owning_rule(module: str) -> str | None:
    """Longest RULES key that prefixes ``module`` on a dot boundary.

    Namespace keys own only themselves: a module in an unmapped subpackage
    (e.g. ``lasr.services.api``) must NOT inherit the root namespace row —
    it gets flagged as unmapped instead.
    """
    best: str | None = None
    for key in RULES:
        if module == key:
            return key
        if (
            key not in NAMESPACE_PACKAGES
            and module.startswith(key + ".")
            and (best is None or len(key) > len(best))
        ):
            best = key
    return best


def _imported_names(tree: ast.Module, module: str, is_package: bool) -> set[str]:
    """Absolute names imported by ``module`` (relative imports resolved)."""
    package = module if is_package else module.rsplit(".", 1)[0]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                parts = package.split(".")
                if node.level - 1 > len(parts):
                    continue  # malformed; import would fail at runtime anyway
                kept = parts[: len(parts) - (node.level - 1)]
                base = ".".join(kept + ([node.module] if node.module else []))
            if base:
                names.add(base)
            # `from X import y` may bind submodule X.y: check both.
            names.update(
                f"{base}.{alias.name}" if base else alias.name
                for alias in node.names
                if alias.name != "*"
            )
    return names


def scan_violations(src_root: Path) -> list[str]:
    """Walk every module under ``src_root/lasr`` and report rule breaches."""
    violations: list[str] = []
    for path in sorted((src_root / "lasr").rglob("*.py")):
        module = _module_name(path, src_root)
        importer_rule = _owning_rule(module)
        if importer_rule is None:  # unmapped package: fail loudly
            violations.append(f"{module}: no import rule declared for its package")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in sorted(_imported_names(tree, module, path.name == "__init__.py")):
            top = name.split(".")[0]
            if top in CHALLENGER_ONLY:
                allowed_under = CHALLENGER_ONLY[top]
                if not (
                    module == allowed_under or module.startswith(allowed_under + ".")
                ):
                    violations.append(
                        f"{module}: imports challenger-extra {name!r} outside "
                        f"{allowed_under} (toolchain_proposal.md §4)"
                    )
                continue
            if top != "lasr":
                continue
            imported_rule = _owning_rule(name)
            if imported_rule is None or imported_rule in NAMESPACE_PACKAGES:
                continue
            if imported_rule == importer_rule:
                continue  # within one rule family
            if imported_rule not in RULES[importer_rule]:
                violations.append(
                    f"{module}: imports {name!r} — {importer_rule} may not "
                    f"import {imported_rule} (system_design.md §4)"
                )
    return violations


def _build_tree(root: Path, files: dict[str, str]) -> Path:
    """Materialize a fake src tree for mutation-style negative controls."""
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    # ensure package __init__ files exist along every path
    for rel in list(files):
        parent = (root / rel).parent
        while parent != root:
            init = parent / "__init__.py"
            if not init.exists():
                init.write_text("", encoding="utf-8")
            parent = parent.parent
    return root


class TestRealTreeIsClean:
    def test_no_import_rule_violations_in_src(self) -> None:
        assert scan_violations(SRC_ROOT) == []


class TestHardProhibitionsEncoded:
    """Guard the RULES table itself: weakening it trips a named test."""

    def test_models_import_surface_is_types_only(self) -> None:
        assert RULES["lasr.models"] == {
            "lasr.core",
            "lasr.config",
            "lasr.data.schemas",
        }

    def test_features_targets_reach_data_only_via_pit(self) -> None:
        for pkg in ("lasr.features", "lasr.targets"):
            assert "lasr.data.point_in_time" in RULES[pkg]
            assert "lasr.data.canonical" not in RULES[pkg]
            assert "lasr.data.providers" not in RULES[pkg]
            assert "lasr.data.ingestion" not in RULES[pkg]

    def test_providers_never_import_canonical_or_beyond(self) -> None:
        for banned in (
            "lasr.data.canonical",
            "lasr.data.ingestion",
            "lasr.data.point_in_time",
            "lasr.data.quality",
        ):
            assert banned not in RULES["lasr.data.providers"]

    def test_nothing_imports_cli(self) -> None:
        for pkg, allowed in RULES.items():
            if pkg != "lasr.cli":
                assert "lasr.cli" not in allowed, pkg

    def test_namespace_packages_import_nothing(self) -> None:
        assert RULES["lasr"] == frozenset()
        assert RULES["lasr.data"] == frozenset()


class TestScannerNegativeControls:
    """Each forbidden edge is planted in a temp tree and must be caught —
    the mutation-style proof that the rule has teeth."""

    def test_models_importing_providers_detected(self, tmp_path: Path) -> None:
        root = _build_tree(
            tmp_path,
            {"lasr/models/sneaky.py": "from lasr.data.providers import feed\n"},
        )
        violations = scan_violations(root)
        assert violations  # detected (module and submodule candidates)
        assert all("lasr.models.sneaky" in v for v in violations)
        assert all("lasr.data.providers" in v for v in violations)

    def test_models_importing_pit_detected(self, tmp_path: Path) -> None:
        root = _build_tree(
            tmp_path,
            {"lasr/models/nlasr/kernel.py": "import lasr.data.point_in_time\n"},
        )
        assert any("lasr.data.point_in_time" in v for v in scan_violations(root))

    def test_targets_importing_canonical_detected(self, tmp_path: Path) -> None:
        """The vintage-bypass join (CI-002/LT-010) is structurally caught."""
        root = _build_tree(
            tmp_path,
            {"lasr/targets/builder.py": "from lasr.data.canonical import tables\n"},
        )
        assert any("lasr.data.canonical" in v for v in scan_violations(root))

    def test_relative_import_evasion_detected(self, tmp_path: Path) -> None:
        root = _build_tree(
            tmp_path,
            {"lasr/features/registry.py": "from ..data import canonical\n"},
        )
        assert any("lasr.data.canonical" in v for v in scan_violations(root))

    def test_cli_import_detected(self, tmp_path: Path) -> None:
        root = _build_tree(
            tmp_path,
            {"lasr/portfolio/mapper.py": "import lasr.cli\n"},
        )
        assert any("lasr.cli" in v for v in scan_violations(root))

    def test_providers_normalizing_detected(self, tmp_path: Path) -> None:
        root = _build_tree(
            tmp_path,
            {
                "lasr/data/providers/local.py": (
                    "from lasr.data.canonical import normalize\n"
                )
            },
        )
        assert any("lasr.data.canonical" in v for v in scan_violations(root))

    def test_challenger_extra_outside_challengers_detected(
        self, tmp_path: Path
    ) -> None:
        root = _build_tree(
            tmp_path,
            {"lasr/features/fancy.py": "import sklearn.linear_model\n"},
        )
        assert any("challenger-extra" in v for v in scan_violations(root))

    def test_unmapped_package_detected(self, tmp_path: Path) -> None:
        root = _build_tree(tmp_path, {"lasr/services/api.py": "import os\n"})
        assert any("no import rule" in v for v in scan_violations(root))

    def test_legal_edges_pass(self, tmp_path: Path) -> None:
        """Positive control: allowed imports produce no violations."""
        root = _build_tree(
            tmp_path,
            {
                "lasr/models/scorer.py": (
                    "from lasr.core import TimingRecord\n"
                    "from lasr.data.schemas import TrainingExampleRow\n"
                ),
                "lasr/features/registry.py": (
                    "from lasr.data.point_in_time import store\n"
                ),
                "lasr/models/challengers/xgb.py": "import xgboost\n",
                "lasr/models/nlasr/kernel.py": (
                    "from lasr.models import boosting\n"  # within one family
                ),
                "lasr/cli/main.py": "import lasr.backtesting\n",
            },
        )
        assert scan_violations(root) == []
