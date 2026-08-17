"""FS010 — capture cache: immutability, checksums, error-evidence policy.

Encodes the D-020(d) rulings as tests: full sha256 identities, gzip
immutable persistence, error responses cached as evidence and NEVER
replayed as success, typed replay miss (FT-10).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lasr.data.providers.factset.cache import ResponseCache, write_capture_set
from lasr.data.providers.factset.envelopes import parse_error_envelope
from lasr.data.providers.factset.errors import (
    FactSetCacheMissError,
    FactSetIntegrityError,
)
from lasr.data.providers.factset.request_norm import (
    NormalizedRequest,
    PageKey,
    request_hash,
)

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
_T1 = datetime(2026, 1, 6, 10, 0, tzinfo=UTC)

_FULL_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _req(endpoint: str = "/identifier-resolution") -> NormalizedRequest:
    return NormalizedRequest(
        api_family="symbology",
        api_version="v3",
        endpoint=endpoint,
        verb="POST",
        params={"ids": ["AAA-US"], "inputSymbolType": "tickerRegion"},
    )


@pytest.fixture
def cache(tmp_path: Path) -> ResponseCache:
    return ResponseCache(tmp_path / "raw")


class TestStoreAndReplay:
    def test_roundtrip_verbatim_bytes(self, cache: ResponseCache) -> None:
        body = b'{"data": [{"requestId": "AAA-US"}]}'
        record = cache.store(_req(), body, http_status=200, retrieval_time=_T0)
        hit = cache.replay(_req())
        assert hit.body == body
        assert hit.record.capture_id == record.capture_id
        assert hit.request_hash == request_hash(_req())

    def test_full_sha256_identities_on_disk(self, cache: ResponseCache) -> None:
        # D-020(d): no 16-hex truncation — directory AND capture names.
        body = b'{"data": []}'
        record = cache.store(_req(), body, http_status=200, retrieval_time=_T0)
        directory = cache.request_dir(_req())
        assert _FULL_SHA256.match(directory.name)
        assert directory.name == request_hash(_req())
        assert directory.parent.name == directory.name[:2]  # fan-out only
        assert _FULL_SHA256.match(record.capture_id)
        capture_file = directory / f"{record.capture_id}.json.gz"
        assert capture_file.exists()
        assert gzip.decompress(capture_file.read_bytes()) == body

    def test_checksum_is_over_uncompressed_bytes(self, cache: ResponseCache) -> None:
        body = b'{"data": [1]}'
        record = cache.store(_req(), body, http_status=200, retrieval_time=_T0)
        assert record.response_sha256 == hashlib.sha256(body).hexdigest()

    def test_replay_miss_is_typed_never_silent(self, cache: ResponseCache) -> None:
        # FT-10.
        with pytest.raises(FactSetCacheMissError, match="replay-mode cache miss"):
            cache.replay(_req())

    def test_identical_response_is_noop_append_only(self, cache: ResponseCache) -> None:
        body = b'{"data": []}'
        r1 = cache.store(_req(), body, http_status=200, retrieval_time=_T0)
        r2 = cache.store(_req(), body, http_status=200, retrieval_time=_T1)
        assert r1.capture_id == r2.capture_id
        assert len(cache.lookup(_req())) == 1

    def test_vendor_drift_appends_never_overwrites(self, cache: ResponseCache) -> None:
        cache.store(_req(), b'{"data": [1]}', http_status=200, retrieval_time=_T0)
        cache.store(_req(), b'{"data": [2]}', http_status=200, retrieval_time=_T1)
        records = cache.lookup(_req())
        assert len(records) == 2
        # Both capture files still on disk (immutable).
        directory = cache.request_dir(_req())
        assert len(list(directory.glob("*.json.gz"))) == 2
        # Latest success serves the most recent append.
        assert cache.replay(_req()).body == b'{"data": [2]}'

    def test_page_addressing_separates_captures(self, cache: ResponseCache) -> None:
        base = _req()
        page0 = base.with_page(PageKey(index=0))
        page1 = base.with_page(PageKey(index=1))
        cache.store(page0, b'{"p": 0}', http_status=200, retrieval_time=_T0)
        cache.store(page1, b'{"p": 1}', http_status=200, retrieval_time=_T0)
        assert cache.replay(page0).body == b'{"p": 0}'
        assert cache.replay(page1).body == b'{"p": 1}'
        with pytest.raises(FactSetCacheMissError):
            cache.replay(base)


class TestErrorEvidencePolicy:
    def test_error_captured_as_evidence(self, cache: ResponseCache) -> None:
        body = b'{"message": "forbidden", "status": "Forbidden"}'
        record = cache.store(
            _req(),
            body,
            http_status=403,
            retrieval_time=_T0,
            error_detail=parse_error_envelope(body),
            entitlement_result="FORBIDDEN",
        )
        assert not record.is_success
        stored = cache.latest_error(_req())
        assert stored is not None
        assert stored.http_status == 403
        assert stored.entitlement_result == "FORBIDDEN"
        assert stored.error_detail is not None
        assert stored.error_detail["envelope_shape"] == "flat"

    def test_error_never_replayed_as_success(self, cache: ResponseCache) -> None:
        # D-020(d): evidence only.
        cache.store(_req(), b'{"message": "x"}', http_status=500, retrieval_time=_T0)
        assert cache.latest_success(_req()) is None
        with pytest.raises(FactSetCacheMissError):
            cache.replay(_req())

    def test_success_after_error_serves_success(self, cache: ResponseCache) -> None:
        cache.store(_req(), b'{"message": "x"}', http_status=429, retrieval_time=_T0)
        cache.store(_req(), b'{"data": []}', http_status=200, retrieval_time=_T1)
        assert cache.replay(_req()).body == b'{"data": []}'
        error = cache.latest_error(_req())
        assert error is not None and error.http_status == 429


class TestIntegrity:
    def test_tampered_capture_quarantined(self, cache: ResponseCache) -> None:
        body = b'{"data": []}'
        record = cache.store(_req(), body, http_status=200, retrieval_time=_T0)
        path = cache.request_dir(_req()) / f"{record.capture_id}.json.gz"
        buf = gzip.compress(b'{"data": ["tampered"]}')
        path.write_bytes(buf)
        with pytest.raises(FactSetIntegrityError, match="checksum mismatch"):
            cache.replay(_req())

    def test_missing_capture_file_quarantined(self, cache: ResponseCache) -> None:
        record = cache.store(
            _req(), b'{"data": []}', http_status=200, retrieval_time=_T0
        )
        (cache.request_dir(_req()) / f"{record.capture_id}.json.gz").unlink()
        with pytest.raises(FactSetIntegrityError, match="missing"):
            cache.replay(_req())

    def test_corrupt_meta_quarantined(self, cache: ResponseCache) -> None:
        cache.store(_req(), b'{"data": []}', http_status=200, retrieval_time=_T0)
        meta = cache.request_dir(_req()) / "meta.json"
        meta.write_text("{not json", encoding="utf-8")
        with pytest.raises(FactSetIntegrityError, match=r"corrupt meta\.json"):
            cache.lookup(_req())


class TestMetaContents:
    def test_meta_records_normalized_request_and_lineage(
        self, cache: ResponseCache
    ) -> None:
        cache.store(
            _req(),
            b'{"data": []}',
            http_status=200,
            retrieval_time=_T0,
            vendor_batch_id="vendor-job-42",
            poll_count=3,
        )
        meta = json.loads(
            (cache.request_dir(_req()) / "meta.json").read_text(encoding="utf-8")
        )
        assert meta["request_hash"] == request_hash(_req())
        assert meta["endpoint"] == "/identifier-resolution"
        assert meta["normalized_request"]["params"]["ids"] == ["AAA-US"]
        capture = meta["captures"][0]
        # Vendor batch id is lineage in meta, never identity.
        assert capture["vendor_batch_id"] == "vendor-job-42"
        assert capture["poll_count"] == 3
        assert capture["retrieval_time"] == "2026-01-05T10:00:00+00:00"


class TestCaptureSets:
    def test_capture_set_digest_stable_and_order_sensitive(
        self, tmp_path: Path
    ) -> None:
        entries = (("a" * 64, "b" * 64), ("c" * 64, "d" * 64))
        digest1, path1 = write_capture_set(tmp_path, entries)
        digest2, _ = write_capture_set(tmp_path, entries)
        assert digest1 == digest2
        assert path1.exists() and path1.name == f"{digest1}.json"
        reversed_digest, _ = write_capture_set(tmp_path, entries[::-1])
        assert reversed_digest != digest1  # ordered list, order matters
