#!/usr/bin/env bash
# The stack the browser tests run against, one per worktree: MinTrack on $port serving the built app, the fake TMDB on
# $port+1, the fake TVmaze on $port+2, database mintrack_e2e_$port in the `just dev-db` container. Started once, then
# reused while it answers.
#
#   scripts/e2e-stack.sh start   # install, build and start what is missing or stale; prints the port
#   scripts/e2e-stack.sh env     # the variables `npx playwright test` needs, for `eval`
#   scripts/e2e-stack.sh stop    # stop this worktree's processes only
#
# The port defaults to one derived from the worktree path, so parallel worktrees do not collide; set
# MINTRACK_E2E_PORT to choose it. Logs, pid files and the secret key live in .e2e/ (gitignored), readable by the
# owner only.
set -euo pipefail
umask 077

root=$(git rev-parse --show-toplevel)
port=${MINTRACK_E2E_PORT:-$((8200 + $(printf '%s' "$root" | cksum | cut -d' ' -f1) % 600 * 3))}
tmdb_port=$((port + 1))
tvmaze_port=$((port + 2))
state=$root/.e2e
dist=$root/frontend/dist/frontend/browser
mkdir -p "$state"
[[ -f $state/secret ]] || openssl rand -hex 32 > "$state/secret"

# What each process of the stack runs, checked before killing a pid that may since belong to another process.
declare -A commands=(
  [server]="mintrack server"
  [tmdb]="uvicorn tests.fakes.tmdb:app"
  [tvmaze]="uvicorn tests.fakes.tvmaze:app"
)

print_env() {
  local name value
  while IFS='=' read -r name value; do
    printf 'export %s=%q\n' "$name" "$value"
  done <<EOF
MINTRACK__DATABASE__HOST=${MINTRACK__DATABASE__HOST:-127.0.0.1}
MINTRACK__DATABASE__USER=mintrack
MINTRACK__DATABASE__PASSWORD=mintrack
MINTRACK__DATABASE__NAME=mintrack_e2e_$port
MINTRACK__SECURITY__SECRET_KEY=$(cat "$state/secret")
MINTRACK__SERVER__PORT=$port
MINTRACK__SERVER__FORWARDED_ALLOW_IPS=127.0.0.1,::1
MINTRACK__PROJECT__PUBLIC_URL=http://localhost:$port
MINTRACK__SERVER__FRONTEND_DIST=$dist
MINTRACK__TMDB__API_KEY=e2e-key
MINTRACK__TMDB__URL=http://127.0.0.1:$tmdb_port/3
MINTRACK__TVMAZE__URL=http://127.0.0.1:$tvmaze_port
MINTRACK_E2E_BASE_URL=http://localhost:$port
MINTRACK_E2E_CLI=$state/mintrack
EOF
}

answers() { curl -s -o /dev/null --max-time 2 "$1"; }

# The pid of this worktree's process `name`, if it still runs that process.
ours() {
  local pid
  [[ -f $state/$1.pid ]] || return 1
  pid=$(cat "$state/$1.pid")
  [[ $(ps -o args= -p "$pid" 2> /dev/null) == *"${commands[$1]}"* ]] && echo "$pid"
}

up() {
  ours server > /dev/null && ours tmdb > /dev/null && ours tvmaze > /dev/null &&
    curl -sf -o /dev/null --max-time 2 "http://localhost:$port/api/health"
}

stop() {
  local name pid pids=()
  for name in "${!commands[@]}"; do
    if pid=$(ours "$name"); then
      kill "$pid" 2> /dev/null || true
      pids+=("$pid")
    fi
    rm -f "$state/$name.pid"
  done
  # Their ports are free once they have exited.
  for pid in "${pids[@]}"; do
    for _ in $(seq 50); do kill -0 "$pid" 2> /dev/null || break; sleep 0.1; done
  done
}

start_process() {
  local name=$1
  shift
  nohup "$@" > "$state/$name.log" 2>&1 &
  echo $! > "$state/$name.pid"
}

start() {
  eval "$(print_env)"
  cd "$root/frontend"
  # npm writes node_modules/.package-lock.json on install: newer than the lockfile means nothing to do.
  if [[ ! node_modules/.package-lock.json -nt package-lock.json ]]; then
    npm ci --no-audit --no-fund > "$state/npm.log" 2>&1 || { tail -30 "$state/npm.log" >&2; exit 1; }
  fi
  if [[ ! -f $dist/index.html ]] || [[ -n $(find src public angular.json ngsw-config.json package-lock.json -newer "$dist/index.html" -print -quit) ]]; then
    npm run build > "$state/build.log" 2>&1 || { tail -30 "$state/build.log" >&2; exit 1; }
  fi
  cd "$root"
  # Reuse the running stack unless the backend or the fakes changed since it started.
  if up && [[ -z $(find src tests/fakes uv.lock -newer "$state/server.pid" -print -quit 2> /dev/null) ]]; then
    echo "$port"
    return
  fi
  stop
  for taken in "$port" "$tmdb_port" "$tvmaze_port"; do
    if answers "http://127.0.0.1:$taken/"; then
      echo "Port $taken answers, but not with this worktree's stack: stop what runs there or set MINTRACK_E2E_PORT" >&2
      exit 1
    fi
  done
  docker exec mintrack-dev-postgres createdb -U mintrack "$MINTRACK__DATABASE__NAME" 2> /dev/null || true
  uv run mintrack db migrate > "$state/migrate.log" 2>&1 || { tail -20 "$state/migrate.log" >&2; exit 1; }
  # The venv's executables, run directly: the pid files then name the real processes, and the CLI the specs call
  # skips uv's start-up on every test.
  local venv
  venv=$(uv run --no-sync python -c 'import sys; print(sys.prefix)')
  ln -sf "$venv/bin/mintrack" "$state/mintrack"
  start_process tmdb "$venv/bin/uvicorn" tests.fakes.tmdb:app --host 127.0.0.1 --port "$tmdb_port"
  start_process tvmaze "$venv/bin/uvicorn" tests.fakes.tvmaze:app --host 127.0.0.1 --port "$tvmaze_port"
  start_process server "$venv/bin/mintrack" server
  for _ in $(seq 60); do
    if up && answers "http://127.0.0.1:$tmdb_port/" && answers "http://127.0.0.1:$tvmaze_port/"; then
      echo "$port"
      return
    fi
    sleep 0.5
  done
  echo "The stack did not answer on :$port, :$tmdb_port and :$tvmaze_port" >&2
  for name in "${!commands[@]}"; do
    echo "--- $name.log" >&2
    tail -20 "$state/$name.log" >&2
  done
  exit 1
}

case ${1:-start} in
  start) start ;;
  env) print_env ;;
  stop) stop ;;
  *) echo "usage: $0 start|env|stop" >&2; exit 2 ;;
esac
