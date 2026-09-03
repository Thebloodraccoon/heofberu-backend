"""Unit tests for ErrorResponse (Pydantic model) and get_timestamp."""

from datetime import datetime, timezone

from app.core.exceptions import AppError, ErrorResponse, get_timestamp


class TestGetTimestamp:
    def test_returns_utc_isoformat(self):
        ts = get_timestamp()

        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None
        assert parsed.tzinfo == timezone.utc

    def test_ends_with_offset_not_literal_z(self):
        ts = get_timestamp()
        assert "+" in ts or ts.endswith("Z") is False


class TestErrorResponse:
    def test_is_pydantic_model(self):
        resp = ErrorResponse(error_type="not_found", message="nope", status_code=404)
        assert hasattr(resp, "model_dump")

    def test_model_dump_returns_flat_dict(self):
        resp = ErrorResponse(error_type="not_found", message="nope", status_code=404)
        data = resp.model_dump()
        assert data["error_type"] == "not_found"
        assert data["message"] == "nope"
        assert data["status_code"] == 404
        assert data["details"] is None
        assert data["request_id"] is None

    def test_optional_fields_defaults(self):
        resp = ErrorResponse(error_type="t", message="m", status_code=500)
        assert resp.details is None
        assert resp.request_id is None

    def test_ignores_unknown_fields(self):
        resp = ErrorResponse(error_type="t", message="m", status_code=500, bogus="nope")
        assert resp.model_dump().get("bogus") is None

    def test_to_dict_envelope_structure(self):
        resp = ErrorResponse(error_type="rate_limit", message="slow down", status_code=429)
        d = resp.to_dict()

        assert "error" in d
        inner = d["error"]
        assert inner["type"] == "rate_limit"
        assert inner["message"] == "slow down"
        assert inner["status_code"] == 429
        assert "timestamp" in inner
        assert "details" not in inner
        assert "request_id" not in inner

    def test_to_dict_includes_details_when_set(self):
        resp = ErrorResponse(error_type="t", message="m", status_code=400, details={"field": "name"})
        d = resp.to_dict()
        assert d["error"]["details"] == {"field": "name"}

    def test_to_dict_includes_request_id_when_set(self):
        resp = ErrorResponse(error_type="t", message="m", status_code=500, request_id="abc-123")
        d = resp.to_dict()
        assert d["error"]["request_id"] == "abc-123"

    def test_to_dict_timestamp_is_valid_iso(self):
        resp = ErrorResponse(error_type="t", message="m", status_code=500)
        ts = resp.to_dict()["error"]["timestamp"]
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None


class TestAppError:
    def test_status_code_and_message(self):
        err = AppError("something broke")
        assert err.status_code == 500
        assert err.message == "something broke"
        assert str(err) == "something broke"

    def test_optional_details(self):
        err = AppError("fail", details={"key": "val"})
        assert err.details == {"key": "val"}

    def test_subclass_status_code(self):
        class Custom400(AppError):
            status_code = 400

        err = Custom400("bad request")
        assert err.status_code == 400
