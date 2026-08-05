import nox

nox.options.reuse_existing_virtualenvs = True
nox.options.sessions = ["install", "ruff", "security", "mypy", "test"]


def setup_test_env(session):
    """Setup test environment variables."""
    session.env["STAGE"] = "test"
    session.env["TEST_DATABASE_URL"] = "postgresql://heof_user:test_secret@localhost:5433/heof_test_db"
    session.env["TEST_REDIS_URL"] = "redis://localhost:6381/0"


@nox.session(name="install")
def install_session(session):
    """Install all dependencies once."""
    setup_test_env(session)
    session.run("poetry", "install", external=True)


@nox.session(name="ruff")
def ruff_session(session):
    """Lint and format code with autofix."""
    setup_test_env(session)
    session.run("poetry", "run", "ruff", "check", "--fix", "app/", "tests/", external=True)
    session.run("poetry", "run", "ruff", "format", "app/", "tests/", "migrations/versions", external=True)


@nox.session(name="security")
def security_session(session):
    """Security checks with bandit."""
    setup_test_env(session)
    session.run("poetry", "run", "bandit", "-r", "app/", external=True)


@nox.session(name="mypy")
def mypy_session(session):
    """Type checking with mypy."""
    setup_test_env(session)
    session.run("poetry", "run", "mypy", "app/", external=True)


@nox.session(name="test")
def test_session(session):
    """Run tests with coverage."""
    setup_test_env(session)
    session.run(
        "poetry", "run", "pytest",
        "--cache-clear",
        "--cov=app/",
        "--cov-report=term-missing",
        "--cov-fail-under=0",
        "--cov-config=pyproject.toml",
        *session.posargs if session.posargs else [],
        external=True
    )


@nox.session(name="all")
def all_session(session):
    """Run all checks for CD/Ci."""
    setup_test_env(session)
    # Install dependencies once
    session.run("poetry", "install", external=True)

    # Run all checks
    session.run("poetry", "run", "ruff", "check", "app/", "tests/", external=True)
    session.run("poetry", "run", "ruff", "format", "--check", "app/", "tests/", "migrations/versions", external=True)
    # session.run("poetry", "run", "mypy", "app/", external=True)
    session.run("poetry", "run", "bandit", "-r", "app/", external=True)
    session.run(
        "poetry", "run", "pytest",
        "--cache-clear",
        "--cov=app/",
        "--cov-report=term-missing",
        "--cov-fail-under=0",
        "--cov-config=pyproject.toml",
        *session.posargs if session.posargs else ["tests/"],
        external=True
    )



@nox.session(name="ruff-check")
def ruff_check_session(session):
    """Ruff check without autofix for pre-commit."""
    setup_test_env(session)
    session.run("poetry", "run", "ruff", "check", "app/", "tests/", external=True)


@nox.session(name="ruff-format-check")
def ruff_format_check_session(session):
    """Ruff format check without autofix for pre-commit."""
    setup_test_env(session)
    session.run("poetry", "run", "ruff", "format", "--check", "app/", "tests/", "migrations/versions", external=True)


@nox.session(name="quick")
def quick_session(session):
    """Quick checks without tests."""
    setup_test_env(session)
    session.run("poetry", "install", "--only=dev", external=True)
    session.run("poetry", "run", "ruff", "check", "--fix", "app/", "tests/", external=True)
    session.run("poetry", "run", "ruff", "format", "app/", "tests/", "migrations/versions", external=True)
    session.run("poetry", "run", "mypy", "app/", external=True)