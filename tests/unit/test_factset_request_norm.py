"""FS010 — request normalization + FULL sha256 hashing (FT-01 substrate).

Hand-computable invariants: hash stability under param/id reordering,
injectivity spot checks, deterministic chunking, credential-key refusal,
volatile-field exclusion (vendor batch ids never enter identity).
"""

from __future__ import annotations

import hashlib
import re
import typing
from datetime import UTC, date, datetime

import pytest

from lasr.data.providers.factset.errors import FactSetConfigError
from lasr.data.providers.factset.request_norm import (
    NormalizedRequest,
    PageKey,
    canonical_param_json,
    chunk_ids,
    normalize_id_list,
    request_hash,
)

pytestmark = pytest.mark.unit

_FULL_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _req(**overrides: object) -> NormalizedRequest:
    base: dict[str, object] = {
        "api_family": "symbology",
        "api_version": "v3",
        "endpoint": "/identifier-resolution",
        "verb": "POST",
        "params": {"ids": ["AAA-US", "BBB-US"], "inputSymbolType": "tickerRegion"},
    }
    base.update(overrides)
    return NormalizedRequest(**base)  # type: ignore[arg-type]


class TestRequestHash:
    def test_full_64_hex_never_truncated(self) -> None:
        # D-020(d): FULL sha256 identities.
        assert _FULL_SHA256.match(request_hash(_req()))

    def test_hash_matches_hand_computed_sha256(self) -> None:
        request = _req()
        encoded = canonical_param_json(request.normalized_payload())
        expected = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        assert request_hash(request) == expected

    def test_param_insertion_order_never_changes_hash(self) -> None:
        a = _req(params={"x": 1, "y": 2})
        b = _req(params={"y": 2, "x": 1})
        assert request_hash(a) == request_hash(b)

    def test_distinct_logical_requests_never_collide(self) -> None:
        # Injectivity spot suite (FT-01).
        variants = [
            _req(),
            _req(api_family="fundamentals"),
            _req(api_version="v2"),
            _req(endpoint="/historical-identifier-resolution"),
            _req(verb="GET"),
            _req(params={"ids": ["AAA-US"], "inputSymbolType": "tickerRegion"}),
            _req(page=PageKey(index=0)),
            _req(page=PageKey(index=1)),
            _req(page=PageKey(index=1, cursor="c2")),
        ]
        hashes = [request_hash(v) for v in variants]
        assert len(set(hashes)) == len(hashes)

    def test_default_materialization_distinguishes_absent_key(self) -> None:
        # The builder rule: an explicit default and an absent key are two
        # DIFFERENT identities — builders must always materialize, so one
        # logical request can never hash two ways.
        explicit = _req(params={"adjust": "UNSPLIT", "ids": ["A"]})
        absent = _req(params={"ids": ["A"]})
        assert request_hash(explicit) != request_hash(absent)

    def test_dates_normalize_to_iso(self) -> None:
        by_date = _req(params={"asOfDate": date(2020, 3, 2)})
        by_str = _req(params={"asOfDate": "2020-03-02"})
        assert request_hash(by_date) == request_hash(by_str)

    def test_datetimes_normalize_to_utc_iso(self) -> None:
        stamp = datetime(2020, 3, 2, 15, 30, tzinfo=UTC)
        payload = _req(params={"pitStart": stamp}).normalized_payload()
        params = payload["params"]
        assert isinstance(params, dict)
        assert params["pitStart"] == "2020-03-02T15:30:00+00:00"

    def test_credential_like_param_keys_refused(self) -> None:
        for key in ("Authorization", "api_key", "password", "TOKEN"):
            with pytest.raises(FactSetConfigError, match="credential-like"):
                _req(params={key: "x"})

    def test_nested_credential_keys_refused(self) -> None:
        with pytest.raises(FactSetConfigError, match="credential-like"):
            _req(params={"data": {"apiKey": "x"}})

    def test_unsupported_param_types_refused(self) -> None:
        with pytest.raises(FactSetConfigError, match="unsupported param type"):
            _req(params={"blob": object()})

    def test_endpoint_and_verb_validation(self) -> None:
        with pytest.raises(FactSetConfigError, match="spec path"):
            _req(endpoint="identifier-resolution")
        with pytest.raises(FactSetConfigError, match="GET or POST"):
            _req(verb="DELETE")

    def test_with_page_preserves_logical_identity_fields(self) -> None:
        base = _req()
        paged = base.with_page(PageKey(index=3, cursor="abc"))
        assert paged.params == base.params
        assert paged.page == PageKey(index=3, cursor="abc")
        assert request_hash(paged) != request_hash(base)

    def test_negative_page_index_refused(self) -> None:
        with pytest.raises(FactSetConfigError, match="page index"):
            PageKey(index=-1)


class TestEncoderEquivalencePin:
    """VF-FS010-5: the repo carries a canonical-JSON encoder in
    ``lasr.artifacts.serialization`` and a structurally-forced duplicate in
    ``factset.request_norm`` (the import-rule table forbids a
    providers→artifacts edge). Silent drift between them would silently
    change cache identities — this pin makes drift loud. Tests may import
    both layers; the lift-into-a-shared-layer decision is FS009/architect's
    (DESIGN.md note), this test is only the drift alarm.
    """

    #: Nested fixture spanning the common value surface of both encoders.
    _FIXTURE: typing.ClassVar[dict[str, object]] = {
        "zeta": 1,
        "alpha": {
            "nested": [1, 2.5, True, None, "text"],
            "date": date(2020, 3, 2),
            "datetime": datetime(2020, 3, 2, 15, 30, 45, 123456, tzinfo=UTC),
            "tuple": (1, "two", 3.0),
        },
        "floats": [0.1, 1e-9, 1.5995592731596646e-159, -0.0, 12345678.9],
        "unicode": "münchen — 東京 ✓",
        "empty": {},
        "list_of_maps": [{"b": 2, "a": 1}, {"d": [None, False]}],
    }

    def test_byte_equality_on_nested_fixture(self) -> None:
        from lasr.artifacts.serialization import (
            canonical_json as artifacts_canonical_json,
        )

        ours = canonical_param_json(self._FIXTURE)
        theirs = artifacts_canonical_json(self._FIXTURE)
        assert ours.encode("utf-8") == theirs.encode("utf-8")

    def test_both_encoders_reject_nan(self) -> None:
        from lasr.artifacts.serialization import (
            canonical_json as artifacts_canonical_json,
        )

        payload = {"x": float("nan")}
        with pytest.raises(ValueError, match=r"NaN|not JSON compliant"):
            canonical_param_json(payload)
        with pytest.raises(ValueError, match=r"NaN|not JSON compliant"):
            artifacts_canonical_json(payload)

    def test_key_sorting_parity_regardless_of_insertion(self) -> None:
        from lasr.artifacts.serialization import (
            canonical_json as artifacts_canonical_json,
        )

        a = {"z": 1, "a": 2, "m": {"y": 1, "b": 2}}
        b = {"m": {"b": 2, "y": 1}, "a": 2, "z": 1}
        assert canonical_param_json(a) == artifacts_canonical_json(b)


class TestIdNormalization:
    def test_sorted_and_deduped(self) -> None:
        assert normalize_id_list(["B", "A", "B", " A "]) == ("A", "B")

    def test_blank_id_refused(self) -> None:
        with pytest.raises(FactSetConfigError, match="empty identifier"):
            normalize_id_list(["A", "  "])

    def test_empty_list_refused(self) -> None:
        with pytest.raises(FactSetConfigError, match="empty"):
            normalize_id_list([])

    def test_id_order_never_changes_hash(self) -> None:
        a = _req(params={"ids": list(normalize_id_list(["B", "A"]))})
        b = _req(params={"ids": list(normalize_id_list(["A", "B", "A"]))})
        assert request_hash(a) == request_hash(b)


class TestChunking:
    def test_deterministic_no_loss_no_duplication(self) -> None:
        # FT-06: no id dropped, none duplicated across chunks.
        ids = normalize_id_list([f"ID{i:03d}" for i in range(7)])
        chunks = chunk_ids(ids, 3)
        assert [len(c) for c in chunks] == [3, 3, 1]
        flattened = [i for chunk in chunks for i in chunk]
        assert flattened == list(ids)
        assert len(set(flattened)) == len(flattened)

    def test_chunk_membership_stable_across_input_order(self) -> None:
        a = chunk_ids(normalize_id_list(["C", "A", "B"]), 2)
        b = chunk_ids(normalize_id_list(["B", "C", "A"]), 2)
        assert a == b

    def test_unnormalized_input_refused(self) -> None:
        with pytest.raises(FactSetConfigError, match="normalized"):
            chunk_ids(("B", "A"), 2)

    def test_bad_ceiling_refused(self) -> None:
        with pytest.raises(FactSetConfigError, match="max_per_chunk"):
            chunk_ids(("A",), 0)

    def test_each_chunk_hashes_distinctly(self) -> None:
        ids = normalize_id_list([f"ID{i}" for i in range(4)])
        hashes = {
            request_hash(_req(params={"ids": list(chunk)}))
            for chunk in chunk_ids(ids, 2)
        }
        assert len(hashes) == 2
