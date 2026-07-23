"""Tagged-provenance leaf mechanics (config_system.md §2; CI-044 substrate).

Provenance is data, not comments: every evidence-bound leaf is a
``Param[T]`` with a provenance class and evidence source. Unknown keys are
load errors (MP §26 hidden-defaults rule).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lasr.config import Param, Provenance

pytestmark = pytest.mark.unit


class TestProvenanceEnum:
    def test_vocabulary_pinned_to_config_system_s2(self) -> None:
        # config_system.md §2 enumerates exactly these six classes.
        assert {p.value for p in Provenance} == {
            "EXPLICIT",
            "EXPLICIT_ABSENCE",
            "IMPORTED_FROM_P1",
            "INFERRED",
            "ASSUMED",
            "MODERNIZED",
        }

    def test_values_are_strings(self) -> None:
        assert Provenance("EXPLICIT") is Provenance.EXPLICIT


class TestParam:
    def test_minimal_tagged_leaf(self) -> None:
        p = Param[int].model_validate(
            {"value": 30, "prov": "EXPLICIT", "src": "P1-17", "cr": "CR-010"}
        )
        assert p.value == 30
        assert p.prov is Provenance.EXPLICIT
        assert p.src == "P1-17"
        assert p.assumption is None
        assert p.cr == "CR-010"

    def test_assumption_register_id_carried(self) -> None:
        p = Param[str].model_validate(
            {
                "value": "point_in_time",
                "prov": "ASSUMED",
                "src": "P1-31 ambiguity",
                "assumption": "A-G011-02",
            }
        )
        assert p.assumption == "A-G011-02"

    def test_unknown_key_rejected(self) -> None:
        # extra="forbid": a misspelled key is a load error (config_system.md §2).
        with pytest.raises(ValidationError, match="extra_forbidden"):
            Param[int].model_validate(
                {"value": 30, "prov": "EXPLICIT", "src": "P1-17", "sorce": "typo"}
            )

    def test_src_is_mandatory_and_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            Param[int].model_validate({"value": 30, "prov": "EXPLICIT"})
        with pytest.raises(ValidationError):
            Param[int].model_validate({"value": 30, "prov": "EXPLICIT", "src": ""})

    def test_prov_is_mandatory_and_closed(self) -> None:
        with pytest.raises(ValidationError):
            Param[int].model_validate({"value": 30, "src": "P1-17"})
        with pytest.raises(ValidationError):
            Param[int].model_validate({"value": 30, "prov": "STATED", "src": "P1-17"})

    def test_frozen(self) -> None:
        p = Param[int].model_validate({"value": 30, "prov": "EXPLICIT", "src": "P1-17"})
        with pytest.raises(ValidationError):
            p.value = 20  # type: ignore[misc]

    def test_typed_value_enforced(self) -> None:
        with pytest.raises(ValidationError):
            Param[int].model_validate(
                {"value": "thirty", "prov": "EXPLICIT", "src": "P1-17"}
            )

    def test_nullable_value_parametrization(self) -> None:
        # CR-014: turnover_limit is Param[float | None] — explicitly null
        # for nlasr_2020, a tagged absence rather than a missing key.
        p = Param[float | None].model_validate(
            {"value": None, "prov": "EXPLICIT_ABSENCE", "src": "E-P4-32"}
        )
        assert p.value is None

    def test_json_round_trip(self) -> None:
        p = Param[float].model_validate(
            {"value": 0.075, "prov": "EXPLICIT", "src": "E-P2-20"}
        )
        dumped = p.model_dump(mode="json")
        assert dumped == {
            "value": 0.075,
            "prov": "EXPLICIT",
            "src": "E-P2-20",
            "assumption": None,
            "cr": None,
        }
        assert Param[float].model_validate(dumped) == p
