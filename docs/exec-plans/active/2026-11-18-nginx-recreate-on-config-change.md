# nginx 설정이 바뀌면 배포 때 다시 만들기

> 상태: 진행 중
> 브랜치: `fix/nginx-recreate-on-config-change`
> 관련: [`2026-06-12-ec2-prod-staging-split.md`](./2026-06-12-ec2-prod-staging-split.md) (EC2 한 대에 `app-staging`·`app-prod`·`nginx`), [`2026-11-17-chat-implementation.md`](./2026-11-17-chat-implementation.md) (`/v1/chat/ws` location 추가)

## 문제

- staging 배포는 `orderrun-nginx`가 꺼져 있을 때만 띄우고, 이미 돌고 있으면 그대로 둔다. production 배포는 nginx를 건드리지 않는다.
- nginx 이미지는 `/etc/nginx/templates/*.template`을 **컨테이너가 시작할 때만** 설정 파일로 바꾼다. 템플릿은 디스크에서 바뀌어도 돌던 nginx에는 반영되지 않는다.
- 그래서 채팅의 `/v1/chat/ws` location처럼 nginx 설정을 바꾼 배포는, 누군가 EC2에서 nginx를 직접 다시 만들기 전까지 적용되지 않는다. 잊기 쉽다.

## 목표

- 배포할 때 nginx 설정(템플릿, nginx 이미지, compose의 nginx 서비스 정의)이 바뀌었으면 자동으로 nginx를 다시 만든다. 바뀌지 않았으면 건드리지 않는다.
- 잘못된 설정으로 운영이 멈추지 않게, 다시 만들기 전에 새 설정을 `nginx -t`로 검사한다. 검사에 실패하면 돌던 nginx를 그대로 두고 배포를 실패시킨다.
- staging·production 배포가 같은 nginx 컨테이너를 쓰므로 같은 스크립트를 쓴다.

## 설계

`scripts/refresh-nginx.sh` (EC2의 `~/orderrun`에서 실행):

1. 설정 지문 = `sha256(사용 중인 템플릿 + nginx/Dockerfile + docker compose config nginx)`.
2. nginx가 돌고 있고 지문이 지난번(`~/orderrun/.nginx-config.sha256`)과 같으면 아무것도 하지 않는다.
3. 다르거나(처음 실행 포함) nginx가 꺼져 있으면:
   1. `docker compose build nginx`
   2. `docker compose run --rm --no-deps -T nginx nginx -t` — 같은 템플릿·인증서·네트워크로 설정을 검사한다(포트는 열지 않는다). 실패하면 종료 코드 1, 돌던 nginx는 그대로.
   3. `docker compose up -d --no-deps --force-recreate nginx`
   4. 10초 안에 `Running`이 아니면 로그를 남기고 실패.
   5. 성공하면 지문을 저장한다.

- 다시 만드는 동안 운영·staging 요청이 몇 초 끊긴다. 설정이 바뀐 배포에서만 일어난다.
- 지문 파일이 없는 첫 배포는 "바뀜"으로 보고 한 번 다시 만든다. 채팅 배포의 `/v1/chat/ws`가 이때 적용된다.

워크플로:

- `staging-deploy.yml`: `deploy.sh` 뒤의 "꺼져 있으면 띄우기"를 `refresh-nginx.sh`로 바꾼다.
- `production-deploy.yml`: `deploy.sh` 뒤에 `refresh-nginx.sh`를 추가한다.
- 두 워크플로 모두 스크립트를 EC2로 복사한다.

## 진행

- [x] 스크립트 작성 (`scripts/refresh-nginx.sh`)
- [x] 워크플로 연결 (`staging-deploy.yml`, `production-deploy.yml`)
- [x] 로컬 Docker로 검증 (2026-11-18): 처음 실행(검사 후 띄움) → 그대로 실행(건너뜀, 같은 컨테이너) → 템플릿 변경(검사 후 다시 만듦) → 잘못된 템플릿(`nginx -t` 실패로 exit 1, 돌던 nginx 유지·응답 정상). 로컬 Colima는 `/private/tmp`를 마운트하지 못해 저장소 안 임시 폴더에서 돌렸다
- [ ] staging 배포 로그에서 nginx 다시 만들기 확인, `/v1/chat/ws` 연결 확인

## 검증 방법

- 로컬: 스크래치 디렉터리의 가짜 compose(`nginx` + upstream 대역 `app`)로 위 네 경우를 실행한다.
- staging: 머지 후 배포 로그의 `nginx 설정이 바뀌어 다시 만든다` 줄과 `curl -i -H 'Connection: Upgrade' -H 'Upgrade: websocket' …/v1/chat/ws`(인증 없이 → 앱이 4401로 닫음, nginx 404가 아님)로 확인한다.
