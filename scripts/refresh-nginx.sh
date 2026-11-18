#!/usr/bin/env bash
# nginx 설정이 바뀌었으면 검사한 뒤 다시 만들고, 꺼져 있으면 띄운다.
# (docs/exec-plans/active/2026-11-18-nginx-recreate-on-config-change.md)
#
# nginx 이미지는 템플릿을 컨테이너가 시작할 때만 설정 파일로 바꾸므로, 템플릿이 바뀌어도
# 돌던 nginx에는 반영되지 않는다. staging·production 배포가 같은 nginx를 쓰므로 둘 다 이 스크립트를 부른다.
set -euo pipefail

compose_file="${COMPOSE_FILE:-docker-compose.ec2.yml}"
env_file="${COMPOSE_ENV_FILE:-.env.ec2}"
container="${NGINX_CONTAINER:-orderrun-nginx}"
service="${NGINX_SERVICE:-nginx}"
state_file="${NGINX_STATE_FILE:-.nginx-config.sha256}"
default_template="${NGINX_DEFAULT_TEMPLATE:-./nginx/templates/ec2-https.conf.template}"

compose=(docker compose -f "$compose_file")
if [[ -f "$env_file" ]]; then
  compose=(docker compose --env-file "$env_file" -f "$compose_file")
fi

template="$(grep -E '^NGINX_TEMPLATE=' "$env_file" 2>/dev/null | cut -d= -f2- || true)"
template="${template:-$default_template}"
if [[ ! -f "$template" ]]; then
  echo "nginx 템플릿이 없다: $template" >&2
  exit 1
fi

# 설정에 영향을 주는 것: 템플릿, nginx 이미지(Dockerfile), compose의 nginx 서비스 정의(환경변수·볼륨 포함)
current_hash="$(
  {
    cat "$template"
    cat nginx/Dockerfile 2>/dev/null || true
    "${compose[@]}" config "$service"
  } | sha256sum | cut -d' ' -f1
)"
previous_hash="$(cat "$state_file" 2>/dev/null || true)"
running="$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || echo false)"

if [[ "$running" == "true" && "$current_hash" == "$previous_hash" ]]; then
  echo "nginx 설정 변경 없음. 그대로 둔다."
  exit 0
fi

if [[ "$running" == "true" ]]; then
  echo "nginx 설정이 바뀌어 다시 만든다. (템플릿: $template)"
else
  echo "nginx가 돌고 있지 않아 띄운다. (템플릿: $template)"
fi

"${compose[@]}" build "$service"

# 새 설정을 먼저 검사한다. 같은 템플릿·인증서·네트워크로 검사하고 포트는 열지 않는다.
# 실패하면 돌던 nginx를 그대로 두고 배포를 실패시킨다.
if ! "${compose[@]}" run --rm --no-deps -T "$service" nginx -t; then
  echo "새 nginx 설정 검사(nginx -t)에 실패했다. 돌던 nginx는 그대로 두었다." >&2
  exit 1
fi

"${compose[@]}" up -d --no-deps --force-recreate "$service"

for _ in $(seq 1 10); do
  if [[ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || echo false)" == "true" ]]; then
    echo "$current_hash" > "$state_file"
    echo "nginx를 새 설정으로 띄웠다."
    exit 0
  fi
  sleep 1
done

echo "nginx가 10초 안에 뜨지 않았다." >&2
"${compose[@]}" logs --tail=50 "$service" || true
exit 1
