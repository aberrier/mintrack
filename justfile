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

# The Angular dev server on :4200, proxying /api to just dev
dev-frontend:
    cd frontend && npx ng serve

# Browser tests against this worktree's stack, started or reused (`just e2e --project=phone`, `just e2e --last-failed`)
e2e *args: dev-db
    bash scripts/e2e-stack.sh start > /dev/null
    eval "$(bash scripts/e2e-stack.sh env)" && cd frontend && npx playwright test {{ args }}

# Stop this worktree's browser-test stack
e2e-stop:
    bash scripts/e2e-stack.sh stop

# Build the Docker image as ghcr.io/aberrier/mintrack:edge, which docker-compose.yml runs with MINTRACK_VERSION=edge
image:
    docker build --tag ghcr.io/aberrier/mintrack:edge --build-arg COMMIT=$(git rev-parse --short HEAD) .

# Set the version on a clean tree, commit it and tag vX.Y.Z locally (`just release 1.4.2`, from master) or a release
# candidate vX.Y.Z-rc.N (`just release 1.4.2-rc.1`, from any branch); pushing is up to you
[positional-arguments]
release version:
    #!/usr/bin/env bash
    set -euo pipefail
    version=$1
    fail() { echo "$1" >&2; exit 1; }
    number='(0|[1-9][0-9]*)'
    branch=$(git branch --show-current)
    if [[ "$version" =~ ^$number\.$number\.$number-rc\.([1-9][0-9]*)$ ]]; then
        python_version="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}.${BASH_REMATCH[3]}rc${BASH_REMATCH[4]}"
    elif [[ "$version" =~ ^$number\.$number\.$number$ ]]; then
        python_version=$version
        [[ "$branch" == master ]] || fail "Releases are cut from master; release candidates from any branch."
    else
        fail "The version is X.Y.Z, such as 1.4.2, or X.Y.Z-rc.N, such as 1.4.2-rc.1."
    fi
    [[ -n "$branch" ]] || fail "Check out a branch first."
    [[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail "Commit or stash the changes first."
    ! git rev-parse --quiet --verify "refs/tags/v$version" > /dev/null || fail "The tag v$version exists."
    uv version --no-sync "$python_version"
    (cd frontend && npm version "$version" --no-git-tag-version > /dev/null)
    git commit --quiet --message "chore: release $version" -- pyproject.toml uv.lock frontend/package.json frontend/package-lock.json
    git tag --annotate "v$version" --message "MinTrack $version"
    echo "Tagged v$version. Publish it with: git push --atomic origin $branch v$version"
