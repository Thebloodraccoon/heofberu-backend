from contextlib import asynccontextmanager

from redis.asyncio import Redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.settings.base import *  # noqa: F403

# Test Database settings
TEST_DATABASE_USER = "slavbor_user"
TEST_DATABASE_PASSWORD = "test_secret"  # nosec B105
TEST_DATABASE_HOST = os.getenv("TEST_DATABASE_HOST", "localhost")
TEST_DATABASE_PORT = 5432
TEST_DATABASE_NAME = "slavbor_test_db"
DATABASE_URL = (
    f"postgresql://{TEST_DATABASE_USER}:{TEST_DATABASE_PASSWORD}@{TEST_DATABASE_HOST}:{TEST_DATABASE_PORT}/"
    f"{TEST_DATABASE_NAME}"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Test Redis settings
TEST_REDIS_HOST = os.getenv("TEST_REDIS_HOST", "localhost")
TEST_REDIS_PORT = 6379
TEST_REDIS_DB = 0


@asynccontextmanager
async def get_redis():
    redis_client = Redis(
        host=TEST_REDIS_HOST,
        port=TEST_REDIS_PORT,
        db=TEST_REDIS_DB,
        decode_responses=True,
    )
    try:
        yield redis_client
    finally:
        await redis_client.aclose()


# MAIL CONF
MAIL_SERVER = "localhost"
MAIL_PORT = 25
MAIL_USERNAME = "test@example.com"  # nosec B105
MAIL_PASSWORD = "test_password"  # nosec B105
MAIL_FROM = "test@example.com"  # nosec B105
MAIL_USE_TLS = False
MAIL_START_TLS = False
MAIL_SUPPRESS_SEND = True