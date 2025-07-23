import re

from fastapi import status
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
import pyotp
import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.auth.utils.pwd_utils import get_password_hash
from app.main import app
from app.models import Race, User
from app.settings import settings

test_engine = create_engine(settings.DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def install_test_extensions():
    """Install required PostgreSQL extensions for testing"""
    try:
        with test_engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gin"))
            conn.commit()
            print("PostgreSQL extensions installed successfully")
    except Exception as e:
        print(f"Warning: Could not install PostgreSQL extensions: {e}")


@pytest.fixture(scope="session", autouse=True)
def prepare_database():
    install_test_extensions()

    settings.Base.metadata.create_all(bind=test_engine)
    yield
    settings.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    session = TestingSessionLocal()
    try:
        for table in reversed(settings.Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session, redis_test):
    with TestClient(app, base_url="http://testserver/api") as c:
        yield c


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver/api") as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def redis_test():
    redis_client = Redis(
        host=settings.TEST_REDIS_HOST,
        port=settings.TEST_REDIS_PORT,
        db=settings.TEST_REDIS_DB,
        decode_responses=True,
    )
    await redis_client.flushdb()
    yield redis_client
    await redis_client.flushdb()
    await redis_client.aclose()


@pytest.fixture
def create_user(db_session):
    def _create_user(
        username="testuser",
        email="test@example.com",
        password="testpassword123",
        role="player",
    ):
        existing_user = db_session.query(User).filter_by(email=email).first()
        if existing_user:
            return existing_user

        user = User(
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            role=role,
        )

        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        return user

    return _create_user


@pytest.fixture
def test_user(create_user):
    return create_user()


@pytest.fixture
def test_admin(create_user):
    return create_user(
        username="admin",
        email="admin@admin.com",
        password="default_password",
        role="found_father",
    )


def generate_test_otp_from_uri(otp_uri):
    secret_match = re.search(r"secret=([A-Z0-9]+)", otp_uri)
    if secret_match:
        secret = secret_match.group(1)
        totp = pyotp.TOTP(secret)
        return totp.now()
    raise Exception("Could not extract OTP secret from URI")


def generate_test_otp(secret):
    totp = pyotp.TOTP(secret)
    return totp.now()


def handle_2fa_flow(client, response, user=None):
    if "access_token" in response.json():
        return response.json()["access_token"]

    if "temp_token" in response.json():
        temp_token = response.json()["temp_token"]

        if "otp_uri" in response.json():
            otp_uri = response.json()["otp_uri"]
            otp_code = generate_test_otp_from_uri(otp_uri)
        else:
            if not user:
                raise ValueError("User object required for 2FA verification")
            otp_code = generate_test_otp(user.otp_secret)

        verify_response = client.post("/auth/2fa/verify", json={"otp_code": otp_code, "temp_token": temp_token})

        if verify_response.status_code == status.HTTP_200_OK:
            return verify_response.json()["access_token"]
        else:
            raise Exception(f"2FA verification failed: {verify_response.json()}")

    raise Exception("Unexpected login response format")


@pytest.fixture
def get_auth_token(client):
    def _get_auth_token(user, password):
        response = client.post("/auth/login", json={"email": user.email, "password": password})

        if response.status_code != status.HTTP_200_OK:
            raise Exception(f"Login failed: {response.json()}")

        access_token = handle_2fa_flow(client, response, user)
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token)

    return _get_auth_token


@pytest.fixture
def test_user_token(get_auth_token, test_user):
    return get_auth_token(test_user, "testpassword123")


@pytest.fixture
def test_admin_token(get_auth_token, test_admin):
    return get_auth_token(test_admin, "default_password")


@pytest.fixture
def create_race(db_session):
    """Factory fixture for creating races in database"""

    def _create_race(
        name="Test name",
        description="Test description",
        size="Средний",
        is_playable=True,
    ):
        existing_race = db_session.query(Race).filter_by(name=name).first()
        if existing_race:
            return existing_race

        race = Race(
            name=name,
            description=description,
            size=size,
            is_playable=is_playable,
        )

        db_session.add(race)
        db_session.commit()
        db_session.refresh(race)

        return race

    return _create_race


@pytest.fixture
def test_race(create_race):
    """Default test race"""
    return create_race()
