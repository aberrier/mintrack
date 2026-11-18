#!/usr/bin/env bash
# The stack the browser tests run against, one per worktree: MinTrack on $port serving the built app, the fake TMDB on
# $port+1, database mintrack_e2e_$port in the `just dev-db` container. Started once, then reused while it answers.
#
#   scripts/e2e-stack.sh start   # install, build and start what is missing or stale; prints the port
#   scripts/e2e-stack.sh env     # the variables `npx playwright test` needs, for `eval`
#   scripts/e2e-stack.sh stop    # stop this worktree's processes only
#
# The port defaults to one derived from the worktree path, so parallel worktrees do not collide; set
# MINTRACK_E2E_PORT to choose it.
set -euo pipefail

root=$(git rev-parse --show-toplevel)
port=${MINTRACK_E2E_PORT:-$((8200 + $(printf '%s' "$root" | cksum | cut -d' ' -f1) % 700 * 2))}
tmdb_port=$((port + 1))
state=${TMPDIR:-/tmp}/mintrack-e2e-$port
dist=$root/frontend/dist/frontend/browser
mkdir -p "$state"
[[ -f $state/secret ]] || openssl rand -hex 32 > "$state/secret"

print_env() {
  cat <<EOF
export MINTRACK__DATABASE__HOST=${MINTRACK__DATABASE__HOST:-127.0.0.1} MINTRACK__DATABASE__USER=mintrack
export MINTRACK__DATABASE__PASSWORD=mintrack MINTRACK__DATABASE__NAME=mintrack_e2e_$port
export MINTRACK__SECURITY__SECRET_KEY=$(cat "$state/secret")
export MINTRACK__SERVER__PORT=$port MINTRACK__PROJECT__PUBLIC_URL=http://localhost:$port
export MINTRACK__SERVER__FRONTEND_DIST=$dist
export MINTRACK__TMDB__API_KEY=e2e-key MINTRACK__TMDB__URL=http://127.0.0.1:$tmdb_port/3
export MINTRACK_E2E_BASE_URL=http://localhost:$port MINTRACK_E2E_CLI=$state/mintrack
EOF
}

up() { curl -sf -o /dev/null "http://localhost:$port/api/health"; }

stop() {
  for name in server tmdb; do
    [[ -f $state/$name.pid ]] && kill "$(cat "$state/$name.pid")" 2>/dev/null || true
    rm -f "$state/$name.pid"
  done
}

start() {
  eval "$(print_env)"
  cd "$root/frontend"
  # npm writes node_modules/.package-lock.json on install: newer than the lockfile means nothing to do.
  if [[ ! node_modules/.package-lock.json -nt package-lock.json ]]; then npm ci --no-audit --no-fund > "$state/npm.log"; fi
  if [[ ! -f $dist/index.html ]] || [[ -n $(find src public angular.json ngsw-config.json package-lock.json -newer "$dist/index.html" -print -quit) ]]; then
    npm run build > "$state/build.log" 2>&1 || { tail -30 "$state/build.log"; exit 1; }
  fi
  cd "$root"
  # Reuse the running server unless the backend changed since it started.
  if up && [[ -z $(find src uv.lock -newer "$state/server.pid" -print -quit 2> /dev/null) ]]; then echo "$port"; return; fi
  stop
  docker exec mintrack-dev-postgres createdb -U mintrack "$MINTRACK__DATABASE__NAME" 2> /dev/null || true
  uv run mintrack db migrate > "$state/migrate.log" 2>&1 || { tail -20 "$state/migrate.log"; exit 1; }
  # The venv's executables, run directly: the pid files then name the real processes, and the CLI the specs call
  # skips uv's start-up on every test.
  local venv
  venv=$(uv run --no-sync python -c 'import sys; print(sys.prefix)')
  ln -sf "$venv/bin/mintrack" "$state/mintrack"
  nohup "$venv/bin/uvicorn" tests.fakes.tmdb:app --host 127.0.0.1 --port "$tmdb_port" > "$state/tmdb.log" 2>&1 &
  echo $! > "$state/tmdb.pid"
  nohup "$venv/bin/mintrack" server > "$state/server.log" 2>&1 &
  echo $! > "$state/server.pid"
  for _ in $(seq 60); do up && { echo "$port"; return; }; sleep 0.5; done
  echo "MinTrack did not answer on :$port" >&2
  tail -20 "$state/server.log" >&2
  exit 1
}

case ${1:-start} in
  start) start ;;
  env) print_env ;;
  stop) stop ;;
  *) echo "usage: $0 start|env|stop" >&2; exit 2 ;;
esac
