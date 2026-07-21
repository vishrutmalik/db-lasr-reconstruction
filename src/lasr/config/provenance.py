"""Tagged-provenance leaves: provenance is data, not comments.

# arch: config_system.md §2. Every evidence-bound config leaf is a
``Param[T]`` — value plus provenance class, evidence source, and optional
assumption-register / contradiction-register ids — so the CI-044
completeness test can be mechanical (correctness_criteria.md CI-044).
Purely structural fields (paths, seeds, experiment names, discriminators)
stay untagged plain values.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ConfigModel",
    "Param",
    "Provenance",
]


class Provenance(StrEnum):
    """Evidence class of a config value (# arch: config_system.md §2).

    Mirrors the version specs' provenance tables
    (docs/methodology/versions/*.md §"Parameter provenance").
    """

    EXPLICIT = "EXPLICIT"  # stated by the paper
    EXPLICIT_ABSENCE = "EXPLICIT_ABSENCE"  # paper affirmatively has none
    IMPORTED_FROM_P1 = "IMPORTED_FROM_P1"  # disclosure gap filled per CR rule
    INFERRED = "INFERRED"
    ASSUMED = "ASSUMED"
    MODERNIZED = "MODERNIZED"


class ConfigModel(BaseModel):
    """Base for every config model.

    ``extra="forbid"``: an unknown or misspelled key is a load error, never
    silently ignored (MP §26 hidden-defaults rule; config_system.md §2).
    ``frozen=True``: configs are immutable values once built.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


T = TypeVar("T")


class Param(ConfigModel, Generic[T]):
    """One evidence-bound leaf: ``{value, prov, src, assumption?, cr?}``.

    ``src`` cites the evidence row / spec section / open-question id;
    ``assumption`` names the assumptions-register candidate (A-xxx /
    A-G011-xx); ``cr`` names the contradiction-register entry
    (# arch: config_system.md §2, field-for-field).
    """

    value: T
    prov: Provenance
    src: str = Field(min_length=1)
    assumption: str | None = None
    cr: str | None = None
