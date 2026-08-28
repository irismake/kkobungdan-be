# API 보안 강화: CORS 화이트리스트, 평문 HTTP 제거, 응답 헤더, 관리자 로그인 잠금, 문서 접근 제한

작성일: 2026-08-27 · 상태: 구현·로컬 검증 완료, 배포 검증 대기

## 배경

프론트엔드 쪽에서 프로덕션 API(`https://api.kkobung-dan.store`)를 직접 호출해 확인한 보안
점검 결과를 받았다. 코드에서 네 건을 재확인했다.

### 1. CORS가 임의 Origin을 반사하면서 자격증명을 허용한다 (심각)

`app/main.py`가 `allow_origins=["*"]`와 `allow_credentials=True`를 같이 쓴다. Starlette
`CORSMiddleware`는 이 조합에서 와일드카드를 쓸 수 없다는 것을 알고 **요청 Origin을 그대로
반사**한다.

```
$ curl -X OPTIONS https://api.kkobung-dan.store/v1/admin/summary -H "Origin: http://evil.test"
access-control-allow-origin: http://evil.test
access-control-allow-credentials: true
```

즉 어떤 도메인이든 자격증명을 포함한 요청을 보내고 응답 본문을 읽을 수 있다. 지금 관리자
웹은 Bearer 헤더 방식이라 쿠키가 자동으로 실리지 않아 즉시 악용 경로는 좁지만, 이 설정은
관리자 API뿐 아니라 **앱 API 전체**에 걸려 있고, 어느 한쪽이라도 쿠키 인증으로 옮기는 순간
계정 탈취 경로가 된다.

### 2. 응답 보안 헤더가 없다

`nginx/templates/` 네 템플릿 어디에도 `Strict-Transport-Security`,
`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`가 없다.

### 3. 관리자 로그인에 시도 제한이 없다

`AdminAuthService.login`은 실패 횟수를 세지 않는다. 관리자 계정이 단 하나
(`ADMIN_USERNAME`)이므로 표적이 명확하고, 공개 인터넷에서 무제한으로 비밀번호를 시도할 수
있다. 전화번호 인증 발송에는 `PHONE_VERIFICATION_SEND_RATE_LIMITED`가 있지만 관리자
로그인에는 대응물이 없다.

### 4. staging에 API 문서가 공개되어 있다

`_api_docs_enabled()`는 `app_env != "production"`일 때 참이다. staging은
`APP_ENV=staging`으로 뜨므로 `http://43.200.56.9/docs`, `/openapi.json`이 인증 없이
200을 반환한다. 관리자 엔드포인트 전체 목록이 공개된 상태다. 프로덕션은 404라 문제없다.

### 5. IP 직접 접근이 평문 HTTP로 API를 서빙한다

2026-08-27 실제 확인 결과:

```
https://staging-api.kkobung-dan.store/v1/health  → 200 (인증서 정상)
http://staging-api.kkobung-dan.store/v1/health   → 301 → https
http://43.200.56.9/v1/health                     → 200 (평문 서빙)
```

도메인 HTTPS는 이미 동작하고 HTTP 도메인 접근도 리다이렉트된다. 남은 구멍은 IP 직접
접근이다. `ec2-https.conf.template`의 80번 `default_server` 블록이 IP와 미지정 host를
`app-staging`으로 그대로 프록시한다. 관리자 아이디·비밀번호와 발급된 토큰이 평문으로
흐르고, HTTPS로 서빙되는 관리자 웹에서는 mixed content로 요청이 차단된다.

### 6. staging 배포가 nginx 설정을 HTTP 전용으로 되돌린다 (잠복)

`staging-deploy.yml`이 `.env.ec2`에
`NGINX_TEMPLATE=./nginx/templates/ec2-staging-http.conf.template`을 하드코딩한다. 이
템플릿에는 **443 server 블록이 없다**. `production-deploy.yml`은 기존 값을 보존하는데
staging은 덮어쓴다.

지금 HTTPS가 도는 이유는 `scripts/deploy.sh`가 `DEPLOY_TARGET`이 있을 때 해당 app 서비스만
재생성하고 nginx는 건드리지 않아서, 예전에 `ec2-https.conf.template`으로 뜬 nginx 컨테이너가
그대로 살아있기 때문이다. 즉 **디스크의 설정과 돌고 있는 설정이 어긋나 있다.**

EC2 재부팅이나 `docker compose up`(타깃 없이) 한 번이면 nginx가 HTTP 전용 설정으로 다시
뜨고 staging HTTPS가 통째로 사라진다. 지금 문제가 안 난 것은 우연이다.

## 결정 내용

### CORS: 환경변수 화이트리스트

허용 Origin을 코드에 하드코딩하지 않는다. 관리자 웹 도메인은 이 저장소에 없고 prod/staging
값이 다르다. `CORS_ALLOW_ORIGINS`를 쉼표 구분 문자열로 받아 목록으로 파싱한다.

- 값이 있으면 그 목록만 `allow_origins`에 넣는다. 와일드카드는 받지 않는다
- `allow_methods`, `allow_headers`도 `["*"]`를 버리고 실제 쓰는 값만 명시한다
- **미설정 시 동작**: `app_env`가 `development`가 아니면 기동 시 `RuntimeError`로 죽인다.
  조용히 빈 목록으로 뜨면 배포 후에야 원인 모를 CORS 오류로 나타난다. 이 PR에서
  워크플로에 값을 같이 넣으므로 배포 중단 위험은 없다. `development`에서는
  `http://localhost:5173`, `http://localhost:3000`을 기본값으로 준다

환경별 실제 값 (2026-08-27 확정):

| 환경 | `CORS_ALLOW_ORIGINS` |
|---|---|
| production | `https://order-run-fe.vercel.app` |
| staging | `http://localhost:5173` |

앱 웹은 prod·staging 모두 존재하지 않는다. **모바일 앱은 네이티브라 `Origin` 헤더를 보내지
않고 CORS 적용 대상이 아니다.** 따라서 이 화이트리스트가 상대하는 것은 관리자 웹 하나뿐이고,
이 변경으로 앱이 깨질 경로는 없다.

staging에 `http://localhost:5173`을 넣는 것은 관리자 웹을 로컬에서 띄워 staging API를
붙이는 현재 개발 방식 때문이다. 로컬 페이지(http)가 staging API(https)를 부르는 것은 mixed
content에 걸리지 않는다 — 차단되는 것은 https 페이지가 http 자원을 부르는 반대 방향이다.

**Vercel preview 배포는 화이트리스트에 넣지 않는다.** `order-run-fe-git-<branch>-*.vercel.app`
형태의 URL은 브랜치마다 바뀌어서 정규식으로밖에 못 받는데, `*.vercel.app`을 통째로 여는 것은
아무나 Vercel에 페이지를 올려 관리자 API를 부를 수 있다는 뜻이라 지금 고치려는 문제로
되돌아간다. preview에서 staging API가 필요해지면 그 URL을 `CORS_ALLOW_ORIGINS`에 추가하면
된다 — 환경변수라 코드 변경 없이 설정만 바꾸면 된다.

`allow_credentials`는 `True`로 **유지한다**. 취약점의 실체는 자격증명 허용이 아니라 임의
Origin 반사이고, 화이트리스트만으로 그 구멍은 막힌다. 관리자 웹이 어딘가에서
`withCredentials`를 켜고 있을 가능성을 이 저장소에서 확인할 수 없으므로, 여기서 끄면 확인
불가능한 회귀를 만든다. 프론트가 쿠키를 전혀 쓰지 않는다는 것이 확인되면 별도로 끈다
(아래 "남는 문제").

### 보안 헤더: nginx 레이어에서 추가

애플리케이션이 아니라 nginx 템플릿에 넣는다. 프록시 앞단이 헤더의 제자리이고, 템플릿 4개가
모든 진입 경로를 덮는다.

| 헤더 | 값 | 적용 범위 |
|---|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | 443 server 블록만 |
| `X-Content-Type-Options` | `nosniff` | 전체 |
| `X-Frame-Options` | `DENY` | 전체 |
| `Referrer-Policy` | `no-referrer` | 전체 |

`add_header`는 `always`를 붙여 4xx/5xx 응답에도 실리게 한다.

**CSP는 이 API에 넣지 않는다.** 이 서버는 JSON을 반환하고, 엄격한 CSP는 Swagger UI(`/docs`)가
CDN에서 자원을 받는 것을 깨뜨린다. 지적사항의 CSP는 관리자 웹 정적 호스팅 쪽 몫이고 그쪽
저장소에서 처리해야 한다. `X-Frame-Options: DENY`가 클릭재킹은 이미 막는다.

HSTS는 443 블록에만 붙인다. HTTP 응답의 HSTS는 브라우저가 무시한다.

### 평문 HTTP 제거: IP 접근을 HTTPS 도메인으로 리다이렉트

`2026-06-12-ec2-prod-staging-split.md`의 "IP 직접 접근은 staging HTTP 유지" 결정을
뒤집는다. 그 결정은 도메인과 인증서가 준비되기 전의 것이고, 지금은
`staging-api.kkobung-dan.store`가 HTTPS로 정상 동작하므로 평문 경로를 남길 이유가 없다.

80번 `default_server` 블록에서 `app-staging` 프록시를 걷어내고 리다이렉트만 남긴다.

- `/.well-known/acme-challenge/`는 **그대로 둔다**. certbot HTTP-01 갱신이 이 경로를 쓴다.
  이걸 같이 막으면 다음 인증서 갱신이 실패하고 HTTPS가 만료로 죽는다
- 나머지 전부 → `https://${STAGING_DOMAIN}$request_uri`

**리다이렉트는 301이 아니라 308을 쓴다.** 301/302는 다수의 HTTP 클라이언트가 POST를 GET으로
바꾸면서 본문을 버린다. API 서버에서 이건 조용한 데이터 유실이다. 308은 메서드와 본문을
보존한다. 이미 배포되어 있는 `http://staging-api...` → https 301 블록은 브라우저에 영구
캐시되었을 수 있으므로 건드리지 않는다.

**IP로는 HTTPS를 제공할 수 없다.** Let's Encrypt 인증서는 도메인에 발급된 것이라
`https://43.200.56.9`는 이름 불일치로 실패한다. 따라서 IP 접근이 가질 수 있는 최종 형태는
리다이렉트뿐이고, **클라이언트는 base URL을 도메인으로 바꿔야 한다.**

> 배포 전 조율 필요: 앱·관리자 웹의 `.env.development.local` 등에서 `http://43.200.56.9`를
> 쓰고 있으면 `https://staging-api.kkobung-dan.store`로 먼저 바꿔야 한다. 308이 전환을
> 받쳐주지만 mixed content로 막히는 브라우저 경로는 리다이렉트로도 못 살린다.

### nginx 템플릿 정리: HTTP 전용 템플릿을 없앤다

디스크 설정과 실행 중 설정이 어긋난 상태를 끝낸다.

- `staging-deploy.yml`이 `NGINX_TEMPLATE`을 덮어쓰지 않게 한다. `production-deploy.yml`과
  같이 기존 값을 보존하고 없으면 `ec2-https.conf.template`을 기본값으로 쓴다
- `docker-compose.ec2.yml`의 기본 템플릿을 `ec2-http.conf.template` →
  `ec2-https.conf.template`으로 바꾼다
- `ec2-staging-http.conf.template`과 `ec2-http.conf.template`을 **삭제한다**. 둘 다 443
  블록 없이 API를 평문으로 서빙하는 템플릿이고, 남겨두면 이번 같은 사고가 반복된다
- `default.conf.template`은 이미지에 baked-in된 폴백이고 로컬 `docker-compose.yml`용이라
  남긴다. 다만 존재하지 않는 `app:8000`을 가리키므로 별도 정리 대상이다 (아래 "남는 문제")

이제 HTTPS 템플릿 하나만 남으므로, 이 계획의 보안 헤더와 basic auth 작업도 그 파일 하나에
집중된다.

### 관리자 로그인: 계정 단위 실패 잠금

Redis가 없는 환경이므로 IP 단위 분산 제한은 불가능하다. 관리자 계정이 하나뿐이니 계정 단위
잠금으로 충분하다.

`users` 테이블에 두 컬럼을 추가한다.

- `admin_login_failed_count` INT NOT NULL DEFAULT 0
- `admin_locked_until` DATETIME NULL

정책: 연속 실패 5회에서 10분 잠금. 성공하면 두 값을 모두 초기화한다. 잠금 중 요청은
비밀번호가 맞더라도 `429`로 거절한다.

새 오류 코드 `ADMIN_LOGIN_LOCKED` (429)를 `ErrorCode`와 `AppError`에 추가한다. 문구는 남은
시간을 노출하지 않는다 — 공격자에게 재시도 타이밍을 알려줄 이유가 없다.

**의도적으로 감수하는 것**: 공격자가 계속 틀린 비밀번호를 넣어 관리자를 상시 잠글 수 있다.
관리자 API가 잠긴다고 앱 서비스가 멈추지는 않고, 잠금 창이 10분이라 정상 관리자는 기다리면
들어간다. 이 서비스 거부를 막으려면 IP 단위 제한이 필요한데 그건 Redis 도입 이후 과제다.

### staging 문서: nginx basic auth

`_api_docs_enabled()` 로직은 건드리지 않는다. staging에서 문서를 볼 수 있어야 한다는 것이
지금 운영 방식이고, 요구는 "아무나 못 보게"이지 "없애기"가 아니다.

nginx에서 `/docs`, `/redoc`, `/openapi.json` 경로에 `auth_basic`을 건다. staging 443 server
블록에만 적용한다 — 프로덕션은 앱이 이미 404를 반환한다.

Swagger UI가 `/openapi.json`을 XHR로 부르므로 세 경로에 모두 같은 realm으로 걸어야 브라우저가
자격증명을 재사용한다. 하나라도 빠지면 문서 페이지는 뜨는데 스펙 로딩만 401로 실패한다.

htpasswd 파일은 저장소에 커밋하지 않는다. GitHub Secret `DOCS_BASIC_AUTH_HTPASSWD`
(htpasswd 형식 한 줄)를 배포 시 EC2의 `~/orderrun/nginx/htpasswd`로 쓰고 nginx 컨테이너에
읽기 전용으로 마운트한다.

## 작업 항목

`http://43.200.56.9`를 쓰는 클라이언트가 없음을 확인했으므로(2026-08-27) 배포 순서 제약은
없다. 전 항목을 한 번에 내보낼 수 있다.

1. `app/core/config.py`: `cors_allow_origins: str = ""` 추가, 쉼표 구분 목록으로 파싱하는
   프로퍼티 추가
2. `app/main.py`: `CORSMiddleware` 설정을 화이트리스트로 교체. 미설정 + 비 development이면
   기동 실패
3. `app/core/errors.py`: `ADMIN_LOGIN_LOCKED` (429) 추가
4. `app/models/user.py` + Alembic `0033`: `admin_login_failed_count`,
   `admin_locked_until` 컬럼과 실패 기록·초기화 메서드
5. `app/services/admin/admin_auth_service.py`, `admin_auth_router.py`: 잠금 검사, 실패
   카운트, `error_responses` 갱신
6. `nginx/templates/ec2-https.conf.template`:
   - 보안 헤더 추가 (HSTS는 443 블록만, 전부 `always`)
   - 80번 `default_server`를 acme-challenge + 308 리다이렉트만 남기고 프록시 제거
   - staging 443 블록의 `/docs`, `/redoc`, `/openapi.json`에 `auth_basic`
7. `nginx/templates/ec2-staging-http.conf.template`, `ec2-http.conf.template` 삭제
8. `docker-compose.ec2.yml`: 기본 `NGINX_TEMPLATE`을 `ec2-https.conf.template`으로 변경,
   nginx 서비스에 htpasswd 파일 마운트 추가
9. `.github/workflows/staging-deploy.yml`: `NGINX_TEMPLATE` 하드코딩 제거하고
   production과 같은 보존 방식으로 변경
10. 두 워크플로: `CORS_ALLOW_ORIGINS` 주입, `DOCS_BASIC_AUTH_HTPASSWD`로 htpasswd 생성
11. 테스트: CORS 화이트리스트 동작, 관리자 로그인 잠금 흐름
12. 문서 갱신: `docs/api-spec/error-codes.md`, `docs/generated/db-schema.md`,
    `docs/SECURITY.md`, `README.md`(URL·환경변수),
    `docs/exec-plans/active/2026-06-12-ec2-prod-staging-split.md`(IP HTTP 유지 결정 철회 명시)

## 구현 메모

- `0033`은 `0024`와 같은 멱등 패턴을 쓴다. `0001_baseline`이 현재 모델 메타데이터로
  `users`를 만들기 때문에 새 DB에는 컬럼이 이미 존재한다. 그냥 `add_column`을 쓰면
  새 DB에서 `Duplicate column name`으로 죽는다
- `DOCS_BASIC_AUTH_HTPASSWD` secret이 비어 있으면 htpasswd가 빈 파일이 되어 문서가 항상
  401이 된다. fail-closed라 위험하진 않지만 문서가 안 열리면 이걸 먼저 확인한다
- `nginx/htpasswd`는 gitignore에 추가했다. 배포 워크플로가 scp 이후에 생성한다

## 검증 기준

- `curl -X OPTIONS <api> -H "Origin: http://evil.test"` 응답에
  `access-control-allow-origin` 헤더가 **없다**
- 허용 목록에 있는 Origin으로는 기존과 동일하게 동작한다
- `CORS_ALLOW_ORIGINS` 없이 `APP_ENV=staging`으로 기동하면 즉시 실패한다
- `curl -I https://api.kkobung-dan.store/v1/health`에 HSTS, nosniff, DENY,
  Referrer-Policy가 모두 있다
- `https://staging-api.kkobung-dan.store/v1/health`도 동일
- `curl -I http://43.200.56.9/v1/health`가 308과
  `Location: https://staging-api.kkobung-dan.store/v1/health`를 반환한다
- `curl -X POST http://43.200.56.9/v1/... -L`이 메서드를 유지한 채 따라간다
- `http://43.200.56.9/.well-known/acme-challenge/test`는 리다이렉트되지 않는다
  (certbot 갱신 경로 보존)
- `certbot renew --dry-run`이 성공한다
- nginx 컨테이너를 강제 재생성해도 HTTPS가 그대로 뜬다
  (`docker compose -f docker-compose.ec2.yml up -d --force-recreate nginx` 후 위 검증 반복)
- 인증 없이 staging `/docs` 호출 시 401, 올바른 basic auth로는 200
- basic auth 통과 후 Swagger UI에서 `/openapi.json`이 401 없이 로드된다
- 프로덕션 `/docs`는 여전히 404
- 관리자 로그인 5회 연속 실패 후 6번째는 올바른 비밀번호여도 429
- 10분 후 정상 로그인되고 `admin_login_failed_count`가 0으로 돌아간다
- 기존 관리자·앱 인증 흐름에 회귀가 없다

## 남는 문제

- **허용 Origin 실제 값**: 관리자 웹과 앱 웹의 도메인을 아직 모른다. 코드는 도메인 없이
  완성되지만, 워크플로에 넣을 실제 값은 배포 전에 확인해야 한다
- **`allow_credentials`**: 관리자 웹이 쿠키를 쓰지 않는 것이 확인되면 `False`로 내리는 것이
  더 안전하다. 프론트 저장소 확인이 필요한 별도 건이다
- **Vercel preview 배포**: 필요해지면 해당 URL을 `CORS_ALLOW_ORIGINS`에 개별 추가한다.
  `*.vercel.app` 와일드카드는 쓰지 않는다
- **관리자 API IP 제한은 하지 않는다**: 관리자가 회사 고정망이나 VPN을 통해서만 접속하지
  않으므로 출발 IP가 고정되지 않는다. `allow`/`deny` 화이트리스트는 관리자를 잠그는 결과만
  낳는다. 이 계획의 계정 잠금과 보안 헤더가 대체 방어이고, 근본 강화책은 IP 제한이 아니라
  관리자 계정의 2단계 인증이다. 별도 안건으로 남긴다
- **IP 단위 rate limit**: Redis 도입 이후 과제. 지금의 계정 잠금은 서비스 거부에 열려 있다
- **`default.conf.template` 정리**: 이미지에 baked-in된 폴백인데 `docker-compose.ec2.yml`에
  없는 `app:8000`을 가리킨다. 마운트가 실패하면 nginx가 이름 해석에 실패한다. 이번 범위 밖
- **관리자 토큰 저장 위치**: 프론트가 `sessionStorage`에 토큰을 둔다. XSS 한 번이면
  탈취된다. 백엔드에서 고칠 수 없고, 고치려면 HttpOnly 쿠키 전환 + CSRF 대책이 필요하다.
  그때 `allow_credentials`와 CORS 화이트리스트가 전제 조건이 되므로 이 계획이 선행 작업이다
