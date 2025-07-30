from datetime import datetime, timedelta, timezone
import re
import uuid

from fastapi import status
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from jose import jwt
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


@pytest.fixture(
    params=[
        ("player_user", "player@example.com", "player_password", "player"),
        ("keeper_user", "keeper@example.com", "keeper_password", "keeper"),
        ("found_father_user", "found@example.com", "found_password", "found_father"),
    ]
)
def user(request, create_user):
    username, email, password, role = request.param
    user = create_user(username=username, email=email, password=password, role=role)
    user._test_password = password
    return user


@pytest.fixture
def user_token(user, generate_jwt_token):
    return generate_jwt_token(user.email, token_type="access")


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


@pytest.fixture
def generate_jwt_token():
    def _generate_jwt_token(email: str, token_type: str, expires_in_minutes: int = 30):
        payload = {
            "sub": email,
            "jti": str(uuid.uuid4()),
            "token_type": token_type,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes),
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    return _generate_jwt_token


@pytest.fixture
def refresh_token(user, generate_jwt_token):
    return generate_jwt_token(user.email, token_type="refresh", expires_in_minutes=60 * 24 * 30)


@pytest.fixture
def registration_data():
    return {
        "username": "testuser",
        "email": "testuser@example.com",
        "password": "TestPassword123",
        "role": "player",
        "phone": "+1234567890",  # not necessarily
        "bio": "Some short bio",  # not necessarily
    }


@pytest_asyncio.fixture
async def reg_id(async_client: AsyncClient, registration_data):
    response = await async_client.post("/registrations/", json=registration_data)
    assert response.status_code == 200
    return response.json()["registration_id" : str(uuid.uuid4())]


@pytest.fixture
def user_with_2fa(create_user, db_session):
    user = create_user(email="twofa@example.com", password="twopass", role="player")
    user.otp_secret = pyotp.random_base32()
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    user._test_password = "twopass"
    return user
