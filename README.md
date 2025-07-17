# Slavbor World Backend API

Slavbor World Backend API is a web application with a RESTful API backend built using **FastAPI** and **PostgreSQL**. It is designed to manage D&D Slavbor world data. The project is containerized using **Docker** and **Docker Compose**.

## 📋 Requirements

- Docker & Docker Compose
- Python 3.10+ (for development outside containers)
- PostgreSQL 15
- Redis (used for caching and logout)
- Optional: pgAdmin for easy DB visualization

## ⚙️ Environment Configuration

Create your `.env` file using the provided `.env.example` as a template:

```bash
# Application Stage
STAGE=local

# Prod DB
POSTGRES_DB=slavbor_db
POSTGRES_USER=slavbor_user
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=slavbor_db
POSTGRES_PORT=5432

# Tests
TEST_DATABASE_HOST=slavbor_test_db
TEST_REDIS_HOST=slavbor_test_redis

# Redis
REDIS_HOST=slavbor_redis
REDIS_PORT=6379
REDIS_DB=0

# JWT
SECRET_KEY=your_secret_key
ALGORITHM=your_algorithm

# Admin credentials
ADMIN_LOGIN=your_admin_mail
ADMIN_PASSWORD=your_admin_password

# pgAdmin
PGADMIN_DEFAULT_EMAIL=admin@admin.com
PGADMIN_DEFAULT_PASSWORD=your_password
```

## 🐳 Running with Docker

### Build and run containers

```bash
docker-compose up --build
```

The FastAPI backend will be accessible at: http://localhost:8000

PgAdmin (if configured) will be available at: http://localhost:5050

### Run database migrations

Database migrations are applied automatically on startup, but you can run them manually:

```bash
docker exec -it slavbor_fastapi_app alembic upgrade head
```

## 🚀 Development

### Local Development Setup

**With Poetry (recommended):**
```bash
# Install Poetry if not installed
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Activate virtual environment
poetry shell

# Start services
docker-compose up -d
```

Start project
```bash
docker-compose up -d 
```

#### In Docker:

```bash
# Enter container
docker exec -it slavbor_fastapi_app bash

# Then 
nox

# Or for only testing
nox -s test
```

## 🗄️ Database Management

### Working with Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## 📚 API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/api/ping

## 🛠️ Development Tools

- **Poetry** - Dependency management
- **Ruff** - Lightning-fast linter and formatter
- **MyPy** - Static type checking
- **Bandit** - Security linting
- **Pytest** - Testing framework
- **Nox** - Testing automation
- **Alembic** - Database migrations
- **Docker** - Containerization

## 📄 License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.