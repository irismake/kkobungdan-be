# 관리자 인증·인가

작성일: 2026-08-22 · 상태: 구현 완료 · 선행: `2026-08-22-admin-web-api.md`(D3 미착수분)

## 배경

관리자 웹 API 21개 경로가 무인증으로 열려 있다. 비마스킹 계좌번호를 반환하는
`GET /v1/admin/refund/{id}`와 `GET /v1/admin/payout/{id}`가 여기 포함된다.

## 결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| 로그인 수단 | **아이디 / 비밀번호** | 관리자 웹에 SMS 인증을 태우면 매 로그인마다 문자 비용과 지연이 생긴다. `users.password_hash`는 이미 있는 컬럼이다 |
| 계정 저장소 | **`users` 테이블 + `is_admin`** | 관리자가 늘어나도 구조를 다시 짜지 않는다 |
| 아이디 컬럼 | `users.admin_username` 신설(NULL 허용, UNIQUE) | 휴대폰 번호를 아이디로 재사용하면 앱 로그인과 충돌한다. 관리자 행에만 값이 있다 |
| 초기 비밀번호 | 환경변수 `ADMIN_INITIAL_PASSWORD` | 평문이 저장소에 남지 않는다 |
| 계정 생성 시점 | **앱 기동 시 보증(idempotent)** | 마이그레이션에 비밀번호를 넣지 않기 위해서다. 이미 있으면 건드리지 않는다 |
| 해시 | `bcrypt` 직접 사용 | passlib 1.7.4는 설치된 bcrypt 5.x와 호환되지 않는다(`ValueError: password cannot be longer than 72 bytes`). 얇은 래퍼를 직접 둔다 |
| 토큰 | **기존 JWT 그대로** | 관리자 전용 토큰 종류를 새로 만들지 않는다. 권한 판정은 토큰 클레임이 아니라 DB의 `is_admin`으로 한다 |
| 리프레시 | 기존 `POST /v1/auth/refresh` 재사용 | `sub`로 사용자를 찾아 재발급하므로 관리자에게도 그대로 동작한다 |

관리자 계정은 휴대폰이 없어 SMS 로그인 경로로는 토큰을 받을 수 없다.
반대로 일반 사용자는 `is_admin`이 거짓이라 관리자 API에 접근할 수 없다.

## 스키마 변경

| 테이블 | 변경 |
|---|---|
| `users` | `is_admin BOOLEAN NOT NULL DEFAULT 0` |
| `users` | `admin_username VARCHAR(50) NULL`, UNIQUE `uk_users_admin_username` |

베이스라인이 현재 모델 메타데이터로 테이블을 만들기 때문에 마이그레이션은 컬럼 존재 여부를 확인한 뒤 추가한다.

## 엔드포인트

### 신규

`POST /v1/admin/auth/login` — 인증 불필요
- Body: `{ username, password }`
- Response: `AuthTokenResponse`(기존 스키마 재사용)
- Error: `401 ADMIN_CREDENTIALS_INVALID`(아이디·비밀번호 어느 쪽이 틀렸는지 구분하지 않는다), `400 VALIDATION_ERROR`

### 보호

`/v1/admin/*`의 기존 21개 경로 전부에 `require_admin` 의존성을 건다.
- 토큰 없음 → `401 INVALID_TOKEN`
- 토큰은 유효하지만 관리자가 아님 → `403 FORBIDDEN`

`/v1/admin/auth/login`만 별도 라우터로 분리해 의존성을 걸지 않는다.

## 파일 계획

| 파일 | 작업 |
|---|---|
| `alembic/versions/0024_add_user_admin_columns.py` | 신규 |
| `app/core/password.py` | 신규 — bcrypt 해시·검증 |
| `app/core/security.py` | `require_admin` 의존성 추가 |
| `app/core/config.py` | `admin_username`, `admin_initial_password` |
| `app/core/errors.py` | `ADMIN_CREDENTIALS_INVALID` |
| `app/models/user.py` | `is_admin`, `admin_username` |
| `app/schemas/admin.py` | `AdminLoginRequest` |
| `app/services/admin/admin_auth_service.py` | 신규 — 계정 보증, 로그인 |
| `app/api/v1/admin/admin_auth_router.py` | 신규 — 로그인 경로 |
| `app/api/v1/admin/admin_router.py` | 라우터 의존성 + 401/403 응답 문서화 |
| `app/main.py` | 기동 시 관리자 계정 보증 |
| `tests/*` | 인가 테스트 신규, 기존 관리자 테스트에 관리자 헤더 |

## 하지 않는 것

- 로그인 시도 제한(brute force 방어) — 별도 작업으로 남긴다. 아래 "남은 일" 참조
- 관리자 비밀번호 변경 API
- 감사 로그

## 검증 결과 (2026-08-22)

- 관리자 경로 8개에 대해 무인증 401 / 일반 사용자 403 / 관리자 200을 각각 확인 (`tests/test_admin_auth_integration.py` 33건)
- 로그인 성공, 비밀번호 오류, 없는 아이디, 관리자 아님을 모두 `401 ADMIN_CREDENTIALS_INVALID`로 확인
- 계정 보증 멱등성 확인 — 환경변수 비밀번호를 바꿔도 기존 계정을 덮어쓰지 않는다
- `pytest` 전체 266건 통과
- `alembic upgrade head` → `downgrade 0023` → `upgrade head` 왕복 확인
- OpenAPI에 admin operation `security: [{HTTPBearer: []}]`가 붙고 로그인 경로만 열려 있음을 확인

## 운영 준비

로컬은 `.env`에 아래를 넣으면 기동 시 관리자 계정이 만들어진다.

```
ADMIN_USERNAME=admin
ADMIN_INITIAL_PASSWORD=<강한 비밀번호>
```

비밀번호는 계정을 처음 만들 때만 읽는다. 이후 환경변수를 바꿔도 계정 비밀번호는 그대로다.

### 배포 배선 (2026-08-22 추가)

| 위치 | 변수 |
|---|---|
| `docker-compose.ec2.yml` | `STAGING_ADMIN_USERNAME` / `STAGING_ADMIN_INITIAL_PASSWORD`, `PROD_ADMIN_*` |
| `docker-compose.staging.yml` | `ADMIN_USERNAME` / `ADMIN_INITIAL_PASSWORD` |
| 두 워크플로 공통 | `secrets.ADMIN_USERNAME` / `secrets.ADMIN_INITIAL_PASSWORD` |

**GitHub Secrets 등록은 수동 작업이다.** 비어 있으면 앱은 뜨지만 관리자 계정이 만들어지지 않아
로그인할 계정이 없다.

시크릿은 환경별로 나누지 않고 한 쌍만 둔다. 스테이징과 프로덕션에 같은 아이디·비밀번호로
로그인하기 위해서다. `AWS_SNS_*`가 이미 같은 방식으로 두 환경을 공유한다.
계정 행 자체는 DB가 분리돼 있어 환경마다 따로 만들어진다.

### 마이그레이션 순서

`scripts/deploy.sh`가 앱을 띄운 **뒤에** `alembic upgrade head`를 돌리고 있었다.
이번 변경은 `users`에 컬럼을 추가하는데 그 테이블은 모든 인증 요청이 읽는다. 새 이미지가
아직 없는 컬럼을 읽어 요청이 실패하는 구간이 생기고, 첫 배포에서는 관리자 계정 보증도 실패한다.

`docker compose run --rm -T --no-deps <app> alembic upgrade head`로 **앱보다 먼저** 돌리도록 바꿨다.
마이그레이션이 실패하면 돌던 앱을 그대로 둔 채 배포가 멈춘다. `run`은 `container_name`을 무시하고
`<project>-<service>-run-<hash>` 컨테이너를 만든 뒤 `--rm`으로 지운다.

## 남은 일

- **로그인 시도 제한 없음** — 단일 계정에 아이디/비밀번호라 무차별 대입에 노출된다.
  `auth_phone_verifications`의 `attempt_count` 같은 시도 기록이나 nginx 레벨 rate limit이 필요하다
- 관리자 비밀번호 변경 API 없음. 지금은 DB를 직접 고쳐야 한다
- 관리자 행위 감사 로그 없음. `adminNote`와 `*_by_admin_id`에만 흔적이 남는다
