#!/usr/bin/env bash
set -euo pipefail

compose_file="${COMPOSE_FILE:-docker-compose.staging.yml}"
compose_env_file="${COMPOSE_ENV_FILE:-}"
compose_profile="${COMPOSE_PROFILE:-staging}"
deploy_target="${DEPLOY_TARGET:-}"
app_service="${APP_SERVICE_NAME:-app}"
app_container="${APP_CONTAINER_NAME:-orderrun-app-staging}"
wait_timeout="${WAIT_TIMEOUT_SECONDS:-180}"

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
echo "Running database migrations..."
"${compose_cmd[@]}" run --rm -T --no-deps "$app_service" alembic upgrade head

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
