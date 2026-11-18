python_dirs := "src tests"
dev_db := "mintrack-dev-postgres"

# Lint, type-check and test
default: check test

# Install the locked dependencies
install:
    uv sync --locked

# Apply ruff fixes and formatting
format:
    uv run ruff check --fix-only --exit-zero {{ python_dirs }}
    uv run ruff format --quiet {{ python_dirs }}

# ruff, ruff format --check and ty
check:
    uv run ruff check {{ python_dirs }}
    uv run ruff format --check {{ python_dirs }}
    uv run ty check

# pytest (the database tests need `just dev-db`)
test *args:
    uv run pytest {{ args }}

# PostgreSQL on 127.0.0.1:5432 with the defaults of pyproject.toml and .env.example
dev-db:
    docker start {{ dev_db }} 2>/dev/null || docker run --detach --name {{ dev_db }} \
        --env POSTGRES_USER=mintrack --env POSTGRES_PASSWORD=mintrack --env POSTGRES_DB=mintrack \
        --publish 127.0.0.1:5432:5432 postgres:18

# The server with auto-reload
dev:
    uv run mintrack server --reload

# Remove caches and coverage files
clean:
    rm -rf .pytest_cache .ruff_cache .coverage .coverage.* coverage.xml
    find . -name __pycache__ -type d -prune -exec rm -rf {} +
