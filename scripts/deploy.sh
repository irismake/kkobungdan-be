#!/usr/bin/env bash
set -euo pipefail

compose_file="${COMPOSE_FILE:-docker-compose.staging.yml}"
compose_env_file="${COMPOSE_ENV_FILE:-}"
compose_profile="${COMPOSE_PROFILE:-staging}"
deploy_target="${DEPLOY_TARGET:-}"
app_service="${APP_SERVICE_NAME:-app}"
app_container="${APP_CONTAINER_NAME:-orderrun-app-staging}"
wait_timeout="${WAIT_TIMEOUT_SECONDS:-180}"
migration_timeout="${MIGRATION_TIMEOUT_SECONDS:-600}"

if [[ ! -f "$compose_file" ]]; then
  echo "Compose file not found: $compose_file" >&2
  exit 1
fi

case "$deploy_target" in
  "")
    ;;
  staging)
    app_service="${APP_SERVICE_NAME:-app-staging}"
    app_container="${APP_CONTAINER_NAME:-orderrun-app-staging}"
    compose_profile="${COMPOSE_PROFILE:-}"
    ;;
  prod|production)
    app_service="${APP_SERVICE_NAME:-app-prod}"
    app_container="${APP_CONTAINER_NAME:-orderrun-app-prod}"
    compose_profile="${COMPOSE_PROFILE:-}"
    ;;
  *)
    echo "Unsupported DEPLOY_TARGET: $deploy_target. Use prod or staging." >&2
    exit 1
    ;;
esac

compose_cmd=(docker compose)
if [[ -n "$compose_env_file" ]]; then
  compose_cmd+=(--env-file "$compose_env_file")
fi
compose_cmd+=(-f "$compose_file")
if [[ -n "$compose_profile" ]]; then
  compose_cmd+=(--profile "$compose_profile")
fi

wait_for_health() {
  local container="$1"
  local elapsed=0

  while (( elapsed < wait_timeout )); do
    if ! docker inspect "$container" >/dev/null 2>&1; then
      sleep 5
      elapsed=$((elapsed + 5))
      continue
    fi

    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || echo "missing")"
    case "$status" in
      healthy|running)
        return 0
        ;;
      unhealthy|exited|dead)
        echo "Container $container reported status: $status" >&2
        return 1
        ;;
    esac

    sleep 5
    elapsed=$((elapsed + 5))
  done

  echo "Timed out waiting for $container to become healthy" >&2
  return 1
}

# 배포마다 직전 이미지가 dangling 상태로 남고 빌드 캐시가 쌓여 EC2 디스크가 가득 찬다.
# pull 전에 정리해 공간을 먼저 확보한다. 실행 중인 컨테이너가 쓰는 이미지는 태그가
# 붙어 있어 dangling 대상이 아니므로 지워지지 않는다.
prune_docker_storage() {
  docker image prune -f || true
  docker builder prune -f || true
}

echo "Disk usage before deploy:"
df -h / | tail -1
prune_docker_storage

"${compose_cmd[@]}" pull "$app_service"

# 마이그레이션을 새 앱보다 먼저 돌린다. 새 이미지가 아직 없는 컬럼을 읽어
# 요청이 실패하는 구간을 없애기 위해서다. 실패하면 돌던 앱을 그대로 두고 멈춘다.
#
# 무한정 기다리지 않도록 timeout으로 감싼다. alembic/env.py가 세션 lock_wait_timeout을
# 짧게 잡아 락 대기는 거기서 먼저 끊기지만, DB 커넥션 자체가 안 열리는 경우처럼 그 앞에서
# 멈추는 상황까지는 못 잡는다. 2026-08-27 배포가 여기서 2시간 11분 매달렸다.
echo "Running database migrations..."
migration_status=0
timeout --signal=TERM --kill-after=30s "$migration_timeout" \
  "${compose_cmd[@]}" run --rm -T --no-deps "$app_service" alembic upgrade head || migration_status=$?

if (( migration_status != 0 )); then
  if (( migration_status == 124 || migration_status == 137 )); then
    echo "마이그레이션이 ${migration_timeout}초 안에 끝나지 않아 중단했다." >&2
    echo "DB에서 'SHOW FULL PROCESSLIST'로 'Waiting for table metadata lock'을 확인할 것." >&2
    echo "정상적으로 오래 걸리는 마이그레이션이면 MIGRATION_TIMEOUT_SECONDS를 늘려 다시 실행한다." >&2
  else
    echo "마이그레이션이 실패했다 (exit ${migration_status}). 배포를 중단한다." >&2
  fi
  echo "돌던 앱은 그대로 두었다." >&2
  exit 1
fi

if [[ -n "$deploy_target" ]]; then
  "${compose_cmd[@]}" up -d --build --remove-orphans "$app_service"
else
  "${compose_cmd[@]}" up -d --build --remove-orphans
fi

if ! wait_for_health "$app_container"; then
  "${compose_cmd[@]}" logs --tail=100 "$app_service" || true
  exit 1
fi

# 새 이미지로 교체되며 dangling이 된 직전 이미지를 즉시 회수한다.
prune_docker_storage
echo "Disk usage after deploy:"
df -h / | tail -1

"${compose_cmd[@]}" ps
