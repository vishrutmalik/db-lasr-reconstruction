"""FS010 — dual error-envelope parsing + response classification.

Fixtures are hand-synthesized to the documented SHAPES (FS003 D-7: never
copied from spec examples; FS002 §8.1: never from live captures).
"""

from __future__ import annotations

import json

import pytest

from lasr.data.providers.factset.envelopes import (
    ResponseClass,
    classify_response,
    parse_error_envelope,
)

pytestmark = pytest.mark.unit


def _flat_body(message: str) -> bytes:
    # Shape of FS003 `errorResponse` (flat), values synthesized.
    return json.dumps(
        {
            "status": "Bad Request",
            "timestamp": "2026-01-05 10:00:00.000",
            "path": "/symbology/v3/identifier-resolution",
            "message": message,
            "subErrors": [
                {
                    "object": "identifierResolution",
                    "field": "ids",
                    "message": "size must be between 1 and 100",
                    "rejectedValue": [],
                }
            ],
        }
    ).encode()


def _errors_array_body(title: str, code: str = "invalid-input") -> bytes:
    # Shape of FS003 `errorResponseHistorical` (JSON:API errors[]).
    return json.dumps(
        {
            "errors": [
                {
                    "id": "00000000-1111-2222-3333-444444444444",
                    "code": code,
                    "links": {"about": "/historical-identifier-resolution"},
                    "title": title,
                }
            ]
        }
    ).encode()


class TestEnvelopeParsing:
    def test_flat_shape_parsed(self) -> None:
        detail = parse_error_envelope(_flat_body("validation failed"))
        assert detail.envelope_shape == "flat"
        assert detail.messages == ("validation failed",)
        assert detail.codes == ("Bad Request",)
        assert detail.sub_errors == ("ids: size must be between 1 and 100",)

    def test_errors_array_shape_parsed(self) -> None:
        detail = parse_error_envelope(_errors_array_body("bad symbol type"))
        assert detail.envelope_shape == "errors_array"
        assert detail.messages == ("bad symbol type",)
        assert detail.codes == ("invalid-input",)

    def test_unparseable_body_recorded_not_raised(self) -> None:
        assert parse_error_envelope(b"<html>gateway</html>").envelope_shape == (
            "unparseable"
        )
        assert parse_error_envelope(b"\xff\xfe").envelope_shape == "unparseable"
        assert parse_error_envelope(b"[1,2]").envelope_shape == "unparseable"


class TestClassification:
    def test_2xx_is_success(self) -> None:
        for status in (200, 201, 202):
            klass, detail = classify_response(status, b"{}")
            assert klass is ResponseClass.SUCCESS
            assert detail is None

    def test_429_and_5xx_are_retryable(self) -> None:
        for status in (429, 500, 502, 503, 504):
            klass, _ = classify_response(status, b"{}")
            assert klass is ResponseClass.RETRYABLE, status

    def test_undeclared_5xx_still_retryable(self) -> None:
        klass, _ = classify_response(599, b"{}", retryable_statuses={429})
        assert klass is ResponseClass.RETRYABLE

    def test_29s_timeout_as_400_classified_by_body_flat(self) -> None:
        # FS003: HTTP 400 + "The request took too long. Try again with a
        # smaller request." — split, never a plain client error.
        body = _flat_body(
            "The request took too long. Try again with a smaller request."
        )
        klass, detail = classify_response(400, body)
        assert klass is ResponseClass.SPLIT_REQUIRED
        assert detail is not None and detail.envelope_shape == "flat"

    def test_29s_timeout_as_400_classified_by_body_errors_array(self) -> None:
        body = _errors_array_body(
            "The request took too long. Try again with a smaller request."
        )
        klass, _ = classify_response(400, body)
        assert klass is ResponseClass.SPLIT_REQUIRED

    def test_plain_400_is_client_not_split(self) -> None:
        klass, _ = classify_response(400, _flat_body("ids must not be empty"))
        assert klass is ResponseClass.CLIENT

    def test_split_marker_outside_400_does_not_promote(self) -> None:
        # Body text alone never overrides the auth/entitlement classes.
        body = _flat_body("The request took too long. smaller request")
        assert classify_response(401, body)[0] is ResponseClass.AUTH
        assert classify_response(403, body)[0] is ResponseClass.ENTITLEMENT

    def test_401_auth_403_entitlement(self) -> None:
        assert classify_response(401, b"{}")[0] is ResponseClass.AUTH
        assert classify_response(403, b"{}")[0] is ResponseClass.ENTITLEMENT

    def test_manifest_driven_retryable_set(self) -> None:
        # FS002 §6.4: the manifest's error_statuses are the retryable set.
        klass, _ = classify_response(418, b"{}", retryable_statuses={418})
        assert klass is ResponseClass.RETRYABLE
        klass2, _ = classify_response(429, b"{}", retryable_statuses={418})
        assert klass2 is ResponseClass.CLIENT
