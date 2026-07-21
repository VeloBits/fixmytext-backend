"""Tests for the standard error envelope schemas."""

from fixmytext_shared.schemas import ErrorResponse, HTTPErrorEnvelope


class TestErrorResponse:
    def test_field_defaults_to_none(self):
        err = ErrorResponse(code="invalid_input", message="Text must not be empty")
        assert err.field is None

    def test_model_dump_shape(self):
        err = ErrorResponse(code="invalid_input", message="Too long", field="text")
        assert err.model_dump() == {
            "code": "invalid_input",
            "message": "Too long",
            "field": "text",
        }


class TestHTTPErrorEnvelope:
    def test_wraps_multiple_errors_with_request_id(self):
        envelope = HTTPErrorEnvelope(
            errors=[
                ErrorResponse(code="a", message="A"),
                ErrorResponse(code="b", message="B", field="x"),
            ],
            request_id="req-1",
        )
        assert [e.code for e in envelope.errors] == ["a", "b"]
        assert envelope.request_id == "req-1"

    def test_request_id_optional(self):
        envelope = HTTPErrorEnvelope(errors=[ErrorResponse(code="a", message="A")])
        assert envelope.request_id is None

    def test_validates_from_plain_dict(self):
        envelope = HTTPErrorEnvelope.model_validate(
            {"errors": [{"code": "quota_exhausted", "message": "Upgrade required"}]}
        )
        assert envelope.errors[0].code == "quota_exhausted"
        assert envelope.errors[0].field is None
