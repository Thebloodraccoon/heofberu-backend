"""Unit tests for the global exception handlers (standard error envelope, no data leaks)."""

import logging

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.core.exceptions import (
    AppError,
    RecordAlreadyExistsError,
    RecordIdsInvalidError,
    RecordInUseError,
    RecordNotFoundError,
    ServiceUnavailableError,
)
from app.middleware.error_handler import setup_error_handlers


class Login(BaseModel):
    email: str
    password: str = Field(min_length=8)


class _DriverError(Exception):
    def __init__(self, message: str, sqlstate: str | None = None, constraint_name: str | None = None):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.constraint_name = constraint_name


def _integrity(sqlstate: str | None, message: str = "boom") -> IntegrityError:
    return IntegrityError("INSERT INTO t VALUES (:v)", {"v": "secret-value"}, _DriverError(message, sqlstate, "uq_t"))


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    setup_error_handlers(app)

    @app.post("/login")
    async def login(data: Login):
        return {"ok": True}

    @app.get("/app-error")
    async def app_error():
        raise AppError("custom failure", details={"k": "v"})

    @app.get("/not-found")
    async def not_found():
        raise RecordNotFoundError("Thing", "5")

    @app.get("/exists")
    async def exists():
        raise RecordAlreadyExistsError("Thing", "name", "x")

    @app.get("/ids")
    async def ids():
        raise RecordIdsInvalidError("Thing", [1, 2])

    @app.get("/in-use")
    async def in_use():
        raise RecordInUseError("Thing", 5)

    @app.get("/unavailable")
    async def unavailable():
        raise ServiceUnavailableError()

    @app.get("/http")
    async def http_error():
        raise HTTPException(status_code=418, detail="teapot", headers={"X-Hint": "tea"})

    @app.get("/integrity/{sqlstate}")
    async def integrity(sqlstate: str):
        raise _integrity(None if sqlstate == "none" else sqlstate)

    @app.get("/integrity-text")
    async def integrity_text():
        raise _integrity(None, 'null value in column "x" violates not-null constraint')

    @app.get("/db")
    async def db_error():
        raise OperationalError("SELECT secret FROM users", {"p": "hunter2"}, _DriverError("connection lost"))

    @app.get("/pool")
    async def pool():
        raise PoolTimeoutError("QueuePool limit reached")

    @app.get("/crash")
    async def crash():
        raise RuntimeError("internal detail")

    return TestClient(app, raise_server_exceptions=False)


def error_of(response):
    return response.json()["error"]


@pytest.mark.unit
class TestAppErrorFamily:
    def test_app_error_uses_its_status_message_and_details(self, client):
        response = client.get("/app-error")

        assert response.status_code == 500
        assert error_of(response)["type"] == "AppError"
        assert error_of(response)["message"] == "custom failure"
        assert error_of(response)["details"] == {"k": "v"}
        assert "timestamp" in error_of(response)

    @pytest.mark.parametrize(
        ("path", "status", "type_name"),
        [
            ("/not-found", 404, "RecordNotFoundError"),
            ("/exists", 400, "RecordAlreadyExistsError"),
            ("/ids", 400, "RecordIdsInvalidError"),
            ("/in-use", 409, "RecordInUseError"),
            ("/unavailable", 503, "ServiceUnavailableError"),
        ],
    )
    def test_data_layer_errors_keep_their_status_and_type(self, client, path, status, type_name):
        response = client.get(path)

        assert response.status_code == status
        assert error_of(response)["type"] == type_name
        assert error_of(response)["status_code"] == status

    def test_data_layer_errors_are_app_errors(self):
        assert issubclass(RecordNotFoundError, AppError)
        assert issubclass(RecordInUseError, AppError)


@pytest.mark.unit
class TestHttpHandler:
    def test_keeps_status_and_headers(self, client):
        response = client.get("/http")

        assert response.status_code == 418
        assert response.headers["x-hint"] == "tea"
        assert error_of(response)["type"] == "HTTPException"
        assert error_of(response)["message"] == "teapot"

    def test_unknown_route_is_enveloped(self, client):
        response = client.get("/nope")

        assert response.status_code == 404
        assert error_of(response)["type"] == "HTTPException"

    def test_method_not_allowed_keeps_allow_header(self, client):
        response = client.put("/crash")

        assert response.status_code == 405
        assert "GET" in response.headers["allow"]
        assert error_of(response)["status_code"] == 405


@pytest.mark.unit
class TestRequestValidation:
    def test_returns_envelope_with_field_errors(self, client):
        response = client.post("/login", json={"email": "a@b.c", "password": "short"})

        assert response.status_code == 422
        error = error_of(response)
        assert error["type"] == "RequestValidationError"
        fields = {item["field"] for item in error["details"]["validation_errors"]}
        assert "body.password" in fields
        assert set(error["details"]["validation_errors"][0]) == {"field", "message", "type"}

    def test_never_echoes_submitted_input(self, client):
        response = client.post("/login", json={"email": "a@b.c", "password": "hunter2"})

        assert response.status_code == 422
        assert "hunter2" not in response.text

    def test_never_logs_submitted_input(self, client, caplog):
        with caplog.at_level(logging.DEBUG):
            client.post("/login", json={"email": "a@b.c", "password": "hunter2"})

        assert "hunter2" not in caplog.text

    def test_missing_body_is_enveloped(self, client):
        response = client.post("/login")

        assert response.status_code == 422
        assert error_of(response)["message"] == "Validation failed"


@pytest.mark.unit
class TestDatabaseHandler:
    @pytest.mark.parametrize(
        ("sqlstate", "message"),
        [
            ("23505", "Record with this data already exists"),
            ("23503", "Referenced record does not exist"),
            ("23502", "Required field cannot be empty"),
            ("23514", "Value violates a database constraint"),
            ("none", "Database integrity constraint violation"),
        ],
    )
    def test_integrity_error_message_comes_from_sqlstate(self, client, sqlstate, message):
        response = client.get(f"/integrity/{sqlstate}")

        assert response.status_code == 400
        assert error_of(response)["message"] == message

    def test_postgres_not_null_text_is_detected_without_sqlstate(self, client):
        response = client.get("/integrity-text")

        assert error_of(response)["message"] == "Required field cannot be empty"

    def test_other_database_errors_are_generic_500(self, client):
        response = client.get("/db")

        assert response.status_code == 500
        assert error_of(response)["message"] == "Database operation failed"
        assert "secret" not in response.text
        assert "hunter2" not in response.text

    def test_pool_exhaustion_is_503(self, client):
        response = client.get("/pool")

        assert response.status_code == 503

    def test_logs_do_not_contain_sql_or_parameters(self, client, caplog):
        with caplog.at_level(logging.DEBUG):
            client.get("/integrity/23505")

        assert "secret-value" not in caplog.text
        assert "INSERT INTO" not in caplog.text


@pytest.mark.unit
class TestUnhandled:
    def test_unhandled_exception_is_generic_500(self, client):
        response = client.get("/crash")

        assert response.status_code == 500
        assert error_of(response)["message"] == "Internal server error"
        assert "internal detail" not in response.text
