# RDS → EC2 내부 MySQL 컨테이너 이전

작성일: 2026-09-29 · 상태: **완료.** STAGING·PROD 모두 EC2 MySQL로 전환했다. 같은 날 사용자가 RDS를 중지해 두 환경이
RDS 없이 동작하는 것을 확인한 뒤 삭제했다(콘솔 작업, 최종 스냅샷은 사용자가 관리). 삭제 후에도 두 환경의 조회·쓰기와
매시 백업이 정상임을 확인했다. 이제 RDS로 되돌리는 rollback은 없고, 복구 수단은 S3 백업(`RELIABILITY.md`)과 RDS 최종
스냅샷이다. 남은 정리는 기술부채 트래커 TD-013, TD-014, TD-016~TD-018에 옮겼다.

정리(같은 날): RDS 최종 덤프 두 개를 S3 `mysql/rds-final/`에 보관하고(체크섬 확인, 수명주기 약 30일) EC2의
`~/migration`, `~/orderrun-db/rollback/`(RDS 비밀번호·호스트, prod env 백업)과 `hwangdaesun/orderrun` 이미지, 쓰지 않는
`mysql:8.0` 이미지(1.1GB)를 지웠다.
MySQL 헬스체크를 자격증명 있는 ping으로 바꿔 재생성했다(10초 만에 healthy, 두 앱 자동 재연결, `Aborted_connects` 증가 0).
아래 본문의 rollback 절차와 rollback 파일 경로는 이 시점부터 유효하지 않다.

### 2차(PROD) 실행 기록 (2026-09-29, UTC)

| 단계 | 결과 |
| --- | --- |
| PROD Secret 검증 | 운영 prod 컨테이너 env를 `~/orderrun-db/rollback/prod-env.backup`(600)에 백업. 임시 브랜치 워크플로로 새 저장소 PROD Secret 13개를 EC2 안에서 해시 비교 → 전부 same. 브랜치 삭제 |
| Docker Hub PROD 전환 | `main` 그대로 Production Deploy 수동 실행 → `orderrun/orderrun:prod`. DB=RDS 유지, env 전부 동일, 로그인·조회·쓰기(RDS 반영)·SNS(STS)·FCM(토큰 발급)·로그 정상 |
| staging → main merge | PR #2 merge commit → 자동 배포. app-prod DB 네트워크 연결, DB=RDS 유지, `.env.ec2` 600 |
| PROD DB 이전 | 리허설 PASS → 05:41:24 app-prod 중지 → 05:41:37 검증 PASS(17테이블 105행, 해시·스키마·메타데이터·alembic·FK) → 05:41:47 `PROD_MYSQL_HOST`=`orderrun-mysql` → 05:44:12 재배포. 중단 약 3분 |
| 전환 후 | env는 `DB_HOST`만 변경, 데모 로그인 쓰기 EC2에만 반영, RDS 전체 세션 0, RDS·EC2 차이는 테스트 쓰기(인증 1행, 데모 사용자 1행, AUTO_INCREMENT)뿐 |
| PROD 백업 | 매시 타이머 활성, 즉시 1회 백업 → S3 업로드, 로컬·S3 sha256 일치, 임시 DB 복원 후 행 수·내용 해시 일치 |

검증 중 고친 것: RDS 세션 수 쿼리가 `CURRENT_USER()`(user@host)를 계정명과 비교해 항상 0을 반환하고 있었다.
`SUBSTRING_INDEX(CURRENT_USER(),'@',1)`로 고친 뒤 RDS 연결 중인 prod에서 1, staging에서 0을 확인했다.

Rollback(PROD): prod 계정 비밀번호는 RDS와 같으므로 `PROD_MYSQL_HOST`만 `~/orderrun-db/rollback/prod-rds-host` 값으로
되돌리고 Production Deploy를 수동 실행한다. 전환 이후 쓰기가 있었다면 EC2 → RDS 역방향 복사가 먼저다(8장 R-B).

### 1차(STAGING) 기록

### 1차 실행 기록 (2026-09-29, UTC)

| 단계 | 결과 |
| --- | --- |
| Docker Hub | Staging Deploy 수동 실행으로 `orderrun/orderrun:staging` build → push → EC2 private pull(읽기 전용 토큰) → deploy. 첫 두 번은 `STG_EC2_SSH_KEY` 복구 형식 오류(원문 PEM)로 SSH 단계 실패, base64 한 줄로 재설정 후 성공 |
| 복구 Secret 검증 | 배포 전후 staging 컨테이너 env 27개를 해시로 비교 → 전부 동일 |
| MySQL 구성 | `~/orderrun-db`, `orderrun-mysql`(8.4.8) healthy, internal 네트워크 192.168.100.0/24, 외부 볼륨, 3306 미게시, root@localhost만. conf.d 디렉터리가 umask 077로 700이 되어 첫 기동 실패 → 755로 수정 |
| 네트워크 연결 | PR #1 squash merge → Staging Deploy. app-staging만 DB 네트워크 연결, DB는 RDS 유지, `.env.ec2` 600 |
| 리허설 | 덤프 1초·복원 2초·검증 6초. 데이터·행 수 일치, `SHOW CREATE TABLE`의 `CHARACTER SET utf8mb4` 표시 차이만 발견(메타데이터 동일) → 검증에서 정규화 |
| 최종 전환 | 04:51:26 staging 중지 → 04:51:39 검증 PASS(20테이블 548행, 해시·스키마·메타데이터·alembic·FK 고아 0) → 04:51:54 `STG_MYSQL_HOST`(repo scope) = `orderrun-mysql` → 04:54:06 재배포 완료. 중단 약 2분 40초 |
| 전환 후 | env는 `DB_HOST`만 변경, EC2 MySQL에 192.168.100.3 연결, RDS의 staging 연결 0, 오류 로그 0. 데모 로그인 쓰기가 EC2에만 반영(RDS 불변) |
| 백업 | AWS CLI 설치, IAM Role 목록·업로드·읽기 성공, 삭제 거부(의도). staging 타이머 활성(매일 18:30 UTC), prod 타이머 설치만. 수동 1회 백업 → S3 업로드 → 복원 테스트 행 수 일치 |

| staging 비밀번호 교체 | 05:13~05:17. EC2에서 무작위 48자 생성 → `RETAIN CURRENT PASSWORD`로 이중 비밀번호 → `STG_MYSQL_PASSWORD`(repo scope)를 EC2에서 파이프로 설정 → 재배포 → `DISCARD OLD PASSWORD`. env는 `DB_PASSWORD`만 변경, 기존(RDS 마스터) 비밀번호 거부·새 비밀번호 허용, 폐기 후 새 연결 정상, 데모 로그인 쓰기가 EC2에만 반영. 중단 없음 |

Rollback(STAGING): 비밀번호를 교체했으므로 HOST와 PASSWORD를 함께 되돌린다. 값은 EC2 `~/orderrun-db/rollback/`(700)의
600 파일에서 파이프로만 넘긴다. RDS를 삭제할 때 이 디렉터리도 지운다.

```bash
E="ssh -i ~/.ssh/orderun-ec2.pem ubuntu@43.200.56.9"
$E 'cat ~/orderrun-db/rollback/stg-rds-host'     | gh secret set STG_MYSQL_HOST     --repo irismake/kkobungdan-be
$E 'cat ~/orderrun-db/rollback/stg-rds-password' | gh secret set STG_MYSQL_PASSWORD --repo irismake/kkobungdan-be
gh workflow run staging-deploy.yml --repo irismake/kkobungdan-be --ref staging
```

전환 이후 staging 쓰기는 RDS에 없다. RDS STAGING 스키마는 읽기만 했고 그대로다. 되돌린 뒤 다시 EC2로 올 때는
staging 비밀번호를 새로 발급한다(현재 값은 GitHub Secret과 `.env.ec2`에만 있다).

GitHub Free 플랜(private 저장소)이라 Environment 승인자와 브랜치 보호를 쓸 수 없다. 지금은 `main` push가 곧 PROD
배포다. 대안으로 production 워크플로를 수동 실행(`workflow_dispatch`) 전용으로 바꾸는 안을 검토한다.

남은 일: Slack webhook 파일(`backup-alert.env`) 작성과 알림 테스트, S3 수명주기 30일 규칙 콘솔 확인(EC2 역할은 조회 권한 없음),
production 배포 트리거 결정, IMDS hop limit 1.

1차에서 계획과 달라진 점:

- MySQL은 RDS와 같은 `8.4.8`로 고정했다. RDS가 비엄격 `sql_mode`(`NO_ENGINE_SUBSTITUTION`)라 EC2도 같게 맞췄다.
  스키마 기본 콜레이션은 `utf8mb4_unicode_ci`(서버 기본은 `utf8mb4_0900_ai_ci`)다.
- staging 앱은 RDS **마스터 계정**을 쓰고 있었다. 이번 승인 범위가 `STG_MYSQL_HOST`뿐이라, EC2에는 같은 이름·비밀번호에
  **staging 스키마 권한만** 가진 계정을 만들었다. 비밀번호 교체는 후속 작업이다.
- 백업은 환경별 systemd 템플릿 유닛(`orderrun-mysql-backup@<env>`)으로 나눴다. staging 일 1회는 활성, prod 매시는
  설치만 하고 비활성이다. S3 키에는 DB 이름 대신 환경 이름을 쓰고, 보관 기간은 버킷 수명주기 약 30일이다.
- Docker Hub namespace는 `DOCKER_USERNAME` Secret 교체만으로 `orderrun/orderrun`으로 바뀐다(코드 변경 없음).
  STAGING에서 build → push → private pull → deploy를 먼저 검증했다.

이 문서의 compose·설정·스크립트는 모두 **초안**이다. 저장소의 `docker-compose.ec2.yml`, 워크플로,
`scripts/`는 아직 수정하지 않았고, EC2·RDS·GitHub Secrets도 건드리지 않았다.

## 목표

비용 절감을 위해 AWS RDS MySQL만 제거하고, 같은 EC2 안에 MySQL 컨테이너를 추가해 prod/staging DB를
옮긴다. EC2·nginx·도메인·HTTPS·GitHub Actions·Docker Hub·SNS 구조는 그대로 둔다.

```
EC2 1대 (43.200.56.9)
├─ orderrun-nginx         (compose 프로젝트 orderrun, 기존 그대로)
├─ orderrun-app-prod      (기존 그대로 + DB 네트워크 연결)
├─ orderrun-app-staging   (기존 그대로 + DB 네트워크 연결)
└─ orderrun-mysql         (신규, compose 프로젝트 orderrun-db)
   ├─ <PROD_DB>  (현재 기본값 prod_orderun)
   └─ <STG_DB>
```

## 범위

- MySQL 8.x 컨테이너 추가 (별도 compose 프로젝트, 내부 전용 네트워크, 외부 볼륨)
- 앱 컨테이너 2개를 DB 네트워크에 연결 (`docker-compose.ec2.yml` 네트워크 한 줄씩)
- STAGING 먼저, PROD 나중 순서의 데이터 이전과 검증
- RDS로 돌아가는 rollback 절차
- mysqldump → gzip → S3 일일 백업과 복원 테스트
- 관련 문서(보안·신뢰성·기술부채) 갱신

## 비범위

- RDS·보안그룹·서브넷그룹 삭제 (관찰 기간 이후 별도 승인)
- 인스턴스 타입 변경 실행 (필요성 판단만 한다)
- 앱 코드 변경, 워크플로 구조 변경, nginx 변경
- 마이그레이션 전용 DB 계정 분리 (지금은 앱 계정이 Alembic DDL도 돌린다. 기술부채로 기록)
- Secrets Manager/SSM 도입

---

## 1. 현재 구조 (분석 결과)

### 1.1 배포 토폴로지

| 구성 | 정의 | 비고 |
| --- | --- | --- |
| compose 프로젝트 | `~/orderrun/docker-compose.ec2.yml` → 프로젝트명 `orderrun` (디렉터리명) | 워크플로가 매 배포마다 이 파일을 scp로 덮어쓴다 |
| `orderrun-app-prod` | `app-prod` 서비스, 이미지 `${DOCKER_IMAGE}` (`<docker user>/orderrun:prod`) | `expose: 8000`만, 호스트 포트 없음 |
| `orderrun-app-staging` | `app-staging` 서비스, 이미지 `${DOCKER_IMAGE}` (`:staging`) | 동일 |
| `orderrun-nginx` | `nginx/` 빌드, 80/443 게시 | app에 `depends_on` 없음 → 앱 배포가 nginx를 재생성하지 않음 |
| `certbot` | `profiles: [ssl]`, 수동 실행 | 인증서는 볼륨 `orderrun_letsencrypt`(프로젝트 접두사 포함) |
| 네트워크 | `orderrun-ec2-network` (bridge) | nginx·앱 2개가 같이 붙어 있음 |
| 호스트 마운트 | `~/orderrun/keys` (FCM 키 파일, ro), `~/orderrun/logs/{prod,staging}/app`, `logs/nginx` | |
| DB | AWS RDS MySQL 1대, prod/staging 스키마 분리 | EC2 → RDS는 VPC 내부 3306 |

nginx 라우팅 ([ec2-https.conf.template](../../../nginx/templates/ec2-https.conf.template)):
80 기본(IP 포함) → `https://staging-api…`로 308, 80 도메인 → 301 HTTPS, 443 `api.kkobung-dan.store` →
`app-prod:8000`, 443 `staging-api.kkobung-dan.store` → `app-staging:8000` (문서 경로 basic auth).
인증서 1장(SAN 2개), 파일명은 `PROD_DOMAIN` 기준.

로컬 전용 파일: `docker-compose.yml`(로컬 MySQL 8.0 + Redis), `docker-compose.test.yml`(테스트 MySQL 8.0,
3307), `docker-compose.staging.yml`(구 staging 구성, 현재 워크플로 미사용).

### 1.2 CI/CD 흐름

| 워크플로 | 트리거 | build | deploy |
| --- | --- | --- | --- |
| [production-deploy.yml](../../../.github/workflows/production-deploy.yml) | `main` push, 수동 | `:prod`, `:prod-<sha>` (linux/amd64) | `environment: production`(승인) → scp → `.env.ec2` 재생성 → `deploy.sh DEPLOY_TARGET=prod` → HTTPS health·문서 404·컨테이너 healthy 검증 |
| [staging-deploy.yml](../../../.github/workflows/staging-deploy.yml) | `staging` push(이미 main에 있는 커밋이면 skip), 수동 | `:staging`, `:staging-<sha>` | `environment: staging` → scp → `.env.ec2` 재생성 → `deploy.sh DEPLOY_TARGET=staging` → nginx 미기동 시 기동 → smoke test |

[deploy.sh](../../../scripts/deploy.sh): 이미지 prune → 대상 서비스 `pull` → `compose run --rm --no-deps <svc> alembic upgrade head`
(600초 timeout, 실패 시 구 앱 유지) → `up -d --build --remove-orphans <svc>` → health 대기 → prune.

### 1.3 환경변수 전달 경로

```
GitHub Secrets (STG_* / PROD_*)
  → 워크플로 heredoc이 EC2 ~/orderrun/.env.ec2 를 "통째로" 새로 씀
  → docker compose --env-file .env.ec2 보간 (${PROD_MYSQL_HOST} 등)
  → 컨테이너 env DB_HOST / DB_PORT / DB_USERNAME / DB_PASSWORD / DB_NAME
  → app/core/config.py Settings → mysql+pymysql://…?charset=utf8mb4
  → app/core/database.py 엔진 (pool_size 5, max_overflow 10, pre_ping)
  → alembic/env.py 도 같은 URL (lock_wait_timeout 60초)
```

### 1.4 DB 연결 설정 추적

| Secret | 워크플로 위치 | `.env.ec2` 변수 | 컨테이너 env (docker-compose.ec2.yml) | 구분 | RDS 제거 후 |
| --- | --- | --- | --- | --- | --- |
| `PROD_MYSQL_HOST` | production-deploy.yml:145 | `PROD_MYSQL_HOST` | `app-prod` `DB_HOST` (:61) | PROD | **값 변경** → `orderrun-mysql` |
| `PROD_MYSQL_PORT` | production-deploy.yml:146 | `PROD_MYSQL_PORT` | `DB_PORT` (:62, 기본 3306) | PROD | 유지 (지금 3306이 아니면 3306으로) |
| `PROD_MYSQL_DATABASE` | production-deploy.yml:149 | `PROD_MYSQL_DATABASE` | `DB_NAME` (:65, 기본 `prod_orderun`) | PROD | 유지 (같은 이름으로 복원) |
| `PROD_MYSQL_USER` | production-deploy.yml:147 | `PROD_MYSQL_USER` | `DB_USERNAME` (:63) | PROD | 조건부 (설계 결정 D5) |
| `PROD_MYSQL_PASSWORD` | production-deploy.yml:148 | `PROD_MYSQL_PASSWORD` | `DB_PASSWORD` (:64) | PROD | 조건부 (D5) |
| `STG_MYSQL_HOST` | staging-deploy.yml:172 | `STAGING_MYSQL_HOST` | `app-staging` `DB_HOST` (:10) | STG | **값 변경** → `orderrun-mysql` |
| `STG_MYSQL_PORT` | staging-deploy.yml:173 | `STAGING_MYSQL_PORT` | `DB_PORT` (:11) | STG | 유지 |
| `STG_MYSQL_DATABASE` | staging-deploy.yml:176 | `STAGING_MYSQL_DATABASE` | `DB_NAME` (:14) | STG | 유지 |
| `STG_MYSQL_USER` | staging-deploy.yml:174 | `STAGING_MYSQL_USER` | `DB_USERNAME` (:12) | STG | 조건부 (D5) |
| `STG_MYSQL_PASSWORD` | staging-deploy.yml:175 | `STAGING_MYSQL_PASSWORD` | `DB_PASSWORD` (:13) | STG | 조건부 (D5) |

반대편 워크플로는 상대 환경 값을 자리표시자로 쓴다 (production-deploy.yml:129-133 `staging-not-managed-by-production`,
staging-deploy.yml:192-196 `prod-not-configured`). 이 부분은 바꿀 필요가 없다.
`docker-compose.staging.yml:35-39`는 접두사 없는 `MYSQL_*`를 쓰지만 현재 워크플로가 쓰지 않는다.

### 1.5 이 계획을 좌우하는 현재 구조의 특성

1. **`.env.ec2`는 마지막에 돌린 워크플로의 것이다.** prod 배포 뒤에는 `STAGING_*`가, staging 배포 뒤에는
   `PROD_*`(JWT 포함)가 자리표시자다. `DOCKER_IMAGE`도 마지막 배포 태그 하나뿐이다. 그래서 EC2에서
   `docker compose up -d`(서비스 미지정)를 수동으로 치면 반대편 앱이 잘못된 값·이미지로 재생성된다.
   수동 운영 절차는 이 점을 전제로 짜야 한다.
2. **compose 파일은 브랜치마다 다르다.** prod 배포는 `main`의, staging 배포는 `staging`의
   `docker-compose.ec2.yml`을 덮어쓴다. 전환 기간에 두 버전이 번갈아 깔린다.
3. **`up -d --remove-orphans`.** 프로젝트 `orderrun`에 속했는데 현재 compose 파일에 없는 컨테이너는 지워진다.
   MySQL을 이 프로젝트에 넣었다가 한쪽 브랜치 파일에 mysql 서비스가 없으면, 그 브랜치 배포가 **DB
   컨테이너를 삭제한다.**
4. **health는 DB를 보지 않는다** ([app/main.py](../../../app/main.py) `/v1/health`는 고정 응답). 빈 DB에 붙어도
   `alembic upgrade head`가 빈 스키마를 만들고 앱은 healthy로 뜬다(관리자 계정도 새로 생성됨). 전환 검증은
   반드시 **데이터**를 봐야 한다.
5. **두 워크플로에 `concurrency` 설정이 없다.** 같은 EC2에 동시에 배포될 수 있다. 이전 작업 중에는 머지를 멈춘다.
6. **앱은 DATETIME에 naive UTC를 직접 쓴다** (`app/core/time.py` `utcnow_naive`). SQL `NOW()` 사용은 앱 코드에
   없고, 레거시 마이그레이션(0006)의 `server_default=now()`만 서버 타임존 영향을 받는다.
7. **`cryptography`가 직접 의존성이다** (pyproject). MySQL 8의 기본 인증 `caching_sha2_password`를 PyMySQL이
   처리할 수 있다.
8. `FCM_CREDENTIALS_JSON`은 워크플로가 쓰지 않는다. 두 환경 모두 EC2의 `~/orderrun/keys/orderrun-firebase-key.json`
   파일 경로(`FCM_CREDENTIALS_PATH`)를 쓴다.

---

## 2. 설계 결정

### D1. MySQL은 별도 compose 프로젝트(`orderrun-db`)로 둔다

사용자 요청의 논리 구조(앱 2 + mysql + nginx, app/db 네트워크 분리, mysql-data 볼륨)는 그대로 두고, **파일과
프로젝트만 분리**한다.

- `docker-compose.ec2.yml`에 넣으면 1.5의 2·3번 때문에 한쪽 브랜치 배포가 DB 컨테이너를 orphan으로 지울 수 있다.
- DB 수명주기를 앱 배포에서 떼어 낸다. 앱 배포가 MySQL을 재시작하는 경로가 아예 없어진다.
- EC2의 `~/orderrun-db/`에 두고 워크플로는 이 디렉터리를 건드리지 않는다. `up`도 수동으로만 한다.
- 교차 프로젝트라 앱에 `depends_on: mysql`을 걸 수 없다. 재부팅 때 앱이 MySQL보다 먼저 떠도 괜찮은지 확인했다.
  `_ensure_admin_account`는 예외를 삼키고, 엔진은 lazy 연결 + `pool_pre_ping`, 스케줄러 잡은 다음 주기에
  다시 돈다. MySQL이 올라오면 자동으로 정상화된다.

### D2. DB 네트워크는 사전 생성한 `internal` 네트워크, 고정 서브넷

- `docker network create --internal --subnet 192.168.100.0/24 orderrun-db-network`
- `internal`: MySQL 컨테이너는 인터넷으로 나가지도 들어오지도 못한다. 앱은 `orderrun-ec2-network`로 계속
  외부(SNS·FCM·Slack)에 나간다.
- nginx는 붙이지 않는다. nginx → mysql 경로가 없다.
- 서브넷을 고정해 DB 계정 호스트를 `'…'@'192.168.100.%'`로 제한한다. **VPC CIDR과 겹치지 않는지 확인 필요**
  (기본 VPC는 172.31.0.0/16).
- 두 compose 프로젝트 모두 `external: true`로 참조만 한다. 어느 쪽 `down`도 네트워크를 지우지 않는다.

### D3. 데이터는 외부(named) 볼륨 `orderrun-mysql-data`

- 사전에 `docker volume create`로 만들고 compose에서는 `external: true`. `docker compose down -v`로도 지워지지 않는다.
- `deploy.sh`는 image/builder prune만 하므로 영향 없다. `docker system prune --volumes`는 운영에서 금지한다.

### D4. MySQL 8.4 LTS, 패치 태그 고정

- 업스트림 MySQL 8.0은 2026-04 EOL이라 보안 패치가 없다. 8.4는 LTS다.
- RDS가 8.0이면 8.0 → 8.4 논리 이전이 된다. 로컬 `pytest`를 `mysql:8.4`로 한 번 돌리고, STAGING 리허설로 검증한다.
- 8.4는 `default_authentication_plugin` 옵션이 없고 `mysql_native_password`가 기본 비활성이다. 새로 만드는 계정은
  `caching_sha2_password`를 쓰고, PyMySQL + `cryptography`로 접속 가능하다(1.5의 7번).
- 참고: AWS 공지상 RDS for MySQL 8.0 표준 지원은 2026-07-31에 끝났다. RDS가 8.0이면 Extended Support 요금이
  이미 붙고 있을 수 있다. 청구서에서 확인한다.

### D5. 이전 기간에는 DB 이름·계정·비밀번호를 RDS와 똑같이 만든다

- 그러면 GitHub Secrets에서 `*_MYSQL_HOST`만 바뀌고, rollback도 HOST 하나만 되돌리면 된다.
- 예외: 지금 prod/staging이 **같은 DB 계정**을 쓰거나 RDS **마스터 계정**을 앱이 쓰고 있다면, EC2 쪽에서는 분리된
  계정을 새로 만들고 `*_MYSQL_USER`/`*_MYSQL_PASSWORD`도 바꾼다. 이 경우 rollback을 위해 **바꾸기 전 값을
  비밀번호 관리자에 보관**한다(GitHub Secret은 덮어쓰면 다시 읽을 수 없다).
- 비밀번호 교체는 RDS 삭제 후 별도로 한다. 새 비밀번호는 영숫자만 쓴다(`openssl rand -hex 24`). `.env.ec2`가
  compose 보간을 거치므로 `$` 같은 문자가 깨질 수 있다.

### D6. 계정 분리

| 계정 | 호스트 | 권한 | 용도 |
| --- | --- | --- | --- |
| `root` | `localhost`만 (`MYSQL_ROOT_HOST=localhost`) | 전체 | 컨테이너 내부 운영 작업 |
| `<PROD_USER>` | `192.168.100.%` | `<PROD_DB>`.*에만 DML + DDL | app-prod + prod 마이그레이션 |
| `<STG_USER>` | `192.168.100.%` | `<STG_DB>`.*에만 DML + DDL | app-staging + staging 마이그레이션 |
| `orderrun_backup` | `localhost` | 두 DB에 `SELECT, SHOW VIEW, TRIGGER, EVENT, LOCK TABLES` | 백업 |

### D7. Secret 파일

- MySQL 스택: compose `secrets:`(파일)과 공식 이미지의 `MYSQL_ROOT_PASSWORD_FILE`을 쓴다. 파일은
  `~/orderrun-db/secrets/`(700), 각 600. compose 파일, `docker inspect` env, 저장소에 비밀번호가 없다.
- 앱: 기존 방식 유지(GitHub Secrets → `.env.ec2`). 개선 여지는 9장 참고.

---

## 3. 변경안 (미적용 초안)

### 3.1 `docker-compose.ec2.yml` (수정)

앱 두 개에 DB 네트워크만 추가한다. nginx·환경변수·볼륨은 그대로다.

```diff
   app-staging:
     ...
     networks:
       - orderrun-network
+      - db
 ...
   app-prod:
     ...
     networks:
       - orderrun-network
+      - db
 ...
 networks:
   orderrun-network:
     name: orderrun-ec2-network
     driver: bridge
+  # MySQL 전용 내부 네트워크. docker-compose.mysql.yml(프로젝트 orderrun-db)과 공유한다.
+  # nginx는 붙이지 않는다. 네트워크는 EC2에서 한 번 수동 생성한다.
+  db:
+    name: orderrun-db-network
+    external: true
```

주의: 네트워크가 없으면 두 앱의 배포(`compose run`/`up`)가 모두 실패한다. **4.2(DB 스택 기동)를 먼저** 한다.

### 3.2 `docker-compose.mysql.yml` (신규)

```yaml
# EC2 내부 MySQL. 앱 배포(GitHub Actions)와 수명주기를 분리하기 위해 별도 compose 프로젝트로 둔다.
# EC2의 ~/orderrun-db/ 에 수동 배치하고 수동으로만 up 한다. 워크플로는 이 파일을 복사하지 않는다.
#   cd ~/orderrun-db && docker compose -f docker-compose.mysql.yml up -d
name: orderrun-db

services:
  mysql:
    image: mysql:8.4  # 적용 시 8.4.N 패치 태그로 고정한다. 이전 작업의 클라이언트 이미지도 같은 태그를 쓴다
    container_name: orderrun-mysql
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD_FILE: /run/secrets/mysql_root_password
      # 공식 이미지는 기본으로 root@'%'도 만든다. 컨테이너 내부 소켓 접속만 허용한다.
      MYSQL_ROOT_HOST: localhost
      TZ: UTC
    secrets:
      - mysql_root_password
      - mysql_root_cnf
      - mysql_backup_cnf
    volumes:
      - mysql-data:/var/lib/mysql
      - ./mysql/conf.d:/etc/mysql/conf.d:ro
    # ports: 를 두지 않는다. Docker가 게시한 포트는 ufw 규칙을 우회한다.
    networks:
      - db
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "--silent"]
      interval: 10s
      timeout: 5s
      retries: 6
      start_period: 60s
    # 기본값(10초 후 SIGKILL)이면 종료 때마다 InnoDB 크래시 복구를 탄다.
    stop_grace_period: 60s
    mem_limit: 768m  # t3.small(2GiB) 기준. 인스턴스 사양 확정 후 조정
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

networks:
  db:
    name: orderrun-db-network
    external: true

volumes:
  mysql-data:
    name: orderrun-mysql-data
    external: true

secrets:
  mysql_root_password:
    file: ./secrets/mysql_root_password
  mysql_root_cnf:
    file: ./secrets/root.cnf
  mysql_backup_cnf:
    file: ./secrets/backup.cnf
```

### 3.3 `mysql/conf.d/orderrun.cnf` (신규)

```ini
# orderrun MySQL 서버 설정. 5.2의 RDS 조회 값과 맞춘 뒤 적용한다.
[mysqld]
character-set-server = utf8mb4
collation-server     = utf8mb4_0900_ai_ci   # RDS @@collation_server 값으로 맞춘다
# 앱은 DATETIME에 naive UTC를 쓴다. NOW() 기본값도 UTC가 되게 RDS 기본값(UTC)과 맞춘다.
default-time-zone    = '+00:00'
# sql_mode = <RDS @@GLOBAL.sql_mode 값>   # RDS가 8.x 기본값과 다르면 명시한다
skip-name-resolve
# 앱 2개 × (pool 5 + overflow 10) = 30, 마이그레이션·백업·운영 세션 여유
max_connections      = 60

# 메모리: t3.small(2GiB) 기준. 1GiB 인스턴스에 이 값 그대로 쓰면 안 된다(7장).
innodb_buffer_pool_size = 256M
# TD-012 락 추적(performance_schema.metadata_locks)에 필요하다. 1GiB에 남는다면 OFF를 검토한다.
performance_schema      = ON
table_open_cache        = 400
tmp_table_size          = 16M
max_heap_table_size     = 16M

# MySQL 8.x는 binlog가 기본으로 켜져 있고 보관 기간이 30일이다. 작은 디스크를 채우지 않게 3일로 줄인다.
binlog_expire_logs_seconds = 259200
max_binlog_size            = 100M

[client]
default-character-set = utf8mb4
```

`lower_case_table_names`는 초기화 시점에만 정할 수 있다. RDS 값이 0(리눅스 기본)이 아니면 **최초 기동 전에** 맞춘다.

### 3.4 EC2 1회 준비 명령

```bash
mkdir -p ~/orderrun-db/{mysql/conf.d,secrets,backups}
chmod 700 ~/orderrun-db/secrets ~/orderrun-db/backups
# 로컬에서 docker-compose.mysql.yml, mysql/conf.d/orderrun.cnf 를 ~/orderrun-db/ 로 scp

openssl rand -hex 24 > ~/orderrun-db/secrets/mysql_root_password
chmod 600 ~/orderrun-db/secrets/mysql_root_password
# root.cnf 는 에디터로 작성한다 (heredoc으로 입력하면 셸 히스토리에 남는다)
#   [client]
#   user=root
#   password=<mysql_root_password 와 같은 값>
# backup.cnf 는 4.3에서 백업 계정을 만든 뒤 같은 형식으로 작성한다 (user=orderrun_backup)
chmod 600 ~/orderrun-db/secrets/*.cnf

docker network create --driver bridge --internal --subnet 192.168.100.0/24 orderrun-db-network
docker volume create orderrun-mysql-data

cd ~/orderrun-db && docker compose -f docker-compose.mysql.yml up -d
docker inspect -f '{{.State.Health.Status}}' orderrun-mysql   # healthy
docker port orderrun-mysql                                     # 출력이 없어야 한다
sudo ss -lntp | grep ':3306' || echo "host 3306 not listening (OK)"
```

### 3.5 DB·계정 생성 SQL

```bash
docker exec -it -e MYSQL_HISTFILE=/dev/null orderrun-mysql \
  mysql --defaults-extra-file=/run/secrets/mysql_root_cnf
```

```sql
-- 문자셋/정렬은 5.2 SCHEMATA 조회 값으로 맞춘다
CREATE DATABASE `<PROD_DB>` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE `<STG_DB>`  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- deploy.sh가 같은 계정으로 alembic을 돌리므로 DDL 권한이 필요하다.
-- GRANT의 DB 이름에서 '_'는 와일드카드다. 이스케이프한다 (prod_orderun → prod\_orderun).
CREATE USER '<PROD_USER>'@'192.168.100.%' IDENTIFIED BY '<PROD_MYSQL_PASSWORD 값>';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES,
      CREATE TEMPORARY TABLES, LOCK TABLES, CREATE VIEW, SHOW VIEW
  ON `prod\_orderun`.* TO '<PROD_USER>'@'192.168.100.%';

CREATE USER '<STG_USER>'@'192.168.100.%' IDENTIFIED BY '<STG_MYSQL_PASSWORD 값>';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES,
      CREATE TEMPORARY TABLES, LOCK TABLES, CREATE VIEW, SHOW VIEW
  ON `<STG_DB 이스케이프>`.* TO '<STG_USER>'@'192.168.100.%';

CREATE USER 'orderrun_backup'@'localhost' IDENTIFIED BY '<백업 비밀번호>';
GRANT SELECT, SHOW VIEW, TRIGGER, EVENT, LOCK TABLES ON `prod\_orderun`.* TO 'orderrun_backup'@'localhost';
GRANT SELECT, SHOW VIEW, TRIGGER, EVENT, LOCK TABLES ON `<STG_DB 이스케이프>`.* TO 'orderrun_backup'@'localhost';

SHOW GRANTS FOR '<PROD_USER>'@'192.168.100.%';
SHOW GRANTS FOR '<STG_USER>'@'192.168.100.%';
```

RDS에서 조회한 트리거·루틴·이벤트가 있으면(5.2), 복원 계정에 `TRIGGER`, `CREATE ROUTINE`, `EVENT` 권한과
DEFINER 계정 처리가 추가로 필요하다. 없으면 위 권한으로 충분하다.

---

## 4. 이전 절차

### 4.0 공통 명령

작업 디렉터리 `~/migration`(700)에 RDS 접속 옵션 파일 `rds.cnf`(600)를 에디터로 만든다. 비밀번호를
명령줄에 넣지 않는다(`ps`·히스토리 노출).

```ini
[client]
host=<RDS endpoint>
port=<RDS port>
user=<RDS 마스터 또는 덤프 권한 계정>   # 덤프는 읽기만 한다
password=<...>
```

```bash
MYSQL_IMAGE=mysql:8.4        # orderrun-mysql 과 같은 태그
DB=<STG_DB 또는 PROD_DB>
TS=$(date -u +%Y%m%dT%H%M%SZ)
rds() { docker run --rm -i -v ~/migration:/work:ro "$MYSQL_IMAGE" mysql --defaults-extra-file=/work/rds.cnf -N -B "$@"; }
ec2() { docker exec -i orderrun-mysql mysql --defaults-extra-file=/run/secrets/mysql_root_cnf -N -B "$@"; }
```

**덤프 (RDS, 읽기 전용).** 임시 클라이언트 컨테이너는 기본 bridge 네트워크라 RDS에 닿는다
(`orderrun-mysql`은 internal 네트워크라 밖으로 못 나간다).

```bash
docker run --rm -v ~/migration:/work:ro "$MYSQL_IMAGE" \
  mysqldump --defaults-extra-file=/work/rds.cnf \
    --single-transaction --quick \
    --routines --triggers --events \
    --hex-blob --no-tablespaces --set-gtid-purged=OFF \
    --default-character-set=utf8mb4 \
    "$DB" \
  | gzip > ~/migration/${DB}-${TS}.sql.gz

gzip -t ~/migration/${DB}-${TS}.sql.gz
zcat ~/migration/${DB}-${TS}.sql.gz | tail -n 1        # "-- Dump completed on ..." 이어야 한다
sha256sum ~/migration/${DB}-${TS}.sql.gz > ~/migration/${DB}-${TS}.sql.gz.sha256
```

| 옵션 | 이유 |
| --- | --- |
| `--single-transaction` | InnoDB 일관 스냅샷, 락 없음. PROD는 앱을 멈춘 뒤라 어차피 일관적이다 |
| `--routines --triggers --events` | 없으면 빈 출력이다. 이벤트가 없고 덤프 계정에 EVENT 권한이 없으면 `--events`를 뺀다 |
| `--hex-blob` | 바이너리 컬럼 안전 |
| `--no-tablespaces` | 8.0.21+에서 PROCESS 권한 없는 계정의 오류 방지 |
| `--set-gtid-purged=OFF` | RDS GTID 상태를 새 서버에 주입하지 않는다 |
| DB 이름만 지정 (`--databases` 안 씀) | `CREATE DATABASE`/`USE`가 없어 원하는 DB에 복원할 수 있다(복원 테스트에 필요) |

**복원 (EC2 MySQL).** `DROP`은 반드시 `docker exec orderrun-mysql` 대상이다. `rds.cnf`로 절대 실행하지 않는다.

```bash
ec2 -e "DROP DATABASE IF EXISTS \`$DB\`; CREATE DATABASE \`$DB\` CHARACTER SET utf8mb4 COLLATE <RDS 값>;"
zcat ~/migration/${DB}-${TS}.sql.gz | docker exec -i orderrun-mysql \
  mysql --defaults-extra-file=/run/secrets/mysql_root_cnf --default-character-set=utf8mb4 "$DB"
```

DB를 지워도 계정 GRANT는 남는다. 덤프 머리말의 `/*!40014 SET FOREIGN_KEY_CHECKS=0 */`, `UNIQUE_CHECKS=0`,
`TIME_ZONE='+00:00'`이 테이블 순서·FK 문제를 처리하므로 **머리말을 지우거나 편집하지 않는다.** 대신 FK 검사가
꺼진 채로 적재되므로 적재 뒤 고아 행 검사(아래)를 한다.

**검증.**

```bash
# (1) 테이블 목록과 정확한 행 수 (information_schema.TABLE_ROWS는 추정치라 쓰지 않는다)
for t in $(rds -e "SELECT table_name FROM information_schema.tables WHERE table_schema='$DB' AND table_type='BASE TABLE' ORDER BY 1"); do
  a=$(rds -e "SELECT COUNT(*) FROM \`$DB\`.\`$t\`"); b=$(ec2 -e "SELECT COUNT(*) FROM \`$DB\`.\`$t\`")
  [ "$a" = "$b" ] && s=OK || s=MISMATCH; printf '%s\t%s\t%s\t%s\n' "$s" "$t" "$a" "$b"
done

# (2) 데이터 내용 해시: 같은 클라이언트·같은 옵션으로 PK 순 덤프를 떠서 비교
opts="--no-create-info --skip-extended-insert --order-by-primary --skip-dump-date --skip-comments --skip-triggers --no-tablespaces --set-gtid-purged=OFF --hex-blob --default-character-set=utf8mb4"
docker run --rm -v ~/migration:/work:ro "$MYSQL_IMAGE" mysqldump --defaults-extra-file=/work/rds.cnf --single-transaction $opts "$DB" | sha256sum
docker exec orderrun-mysql mysqldump --defaults-extra-file=/run/secrets/mysql_root_cnf --single-transaction $opts "$DB" | sha256sum
# 다르면 두 출력을 파일로 떠서 diff 한다 (한 줄 = 한 행)

# (3) 스키마 비교 (AUTO_INCREMENT 값은 정규화)
sopts="--no-data --skip-dump-date --skip-comments --no-tablespaces --set-gtid-purged=OFF --routines --triggers"
docker run --rm -v ~/migration:/work:ro "$MYSQL_IMAGE" mysqldump --defaults-extra-file=/work/rds.cnf $sopts "$DB" | sed -E 's/ AUTO_INCREMENT=[0-9]+//' > ~/migration/schema-rds.sql
docker exec orderrun-mysql mysqldump --defaults-extra-file=/run/secrets/mysql_root_cnf $sopts "$DB" | sed -E 's/ AUTO_INCREMENT=[0-9]+//' > ~/migration/schema-ec2.sql
diff ~/migration/schema-rds.sql ~/migration/schema-ec2.sql && echo "schema identical"
```

```sql
-- (4) 앱 수준 확인 (양쪽에서 같은 값이어야 한다)
SELECT version_num FROM alembic_version;                         -- 현재 head: 0034_dedupe_fcm_tokens
SELECT status, COUNT(*) FROM proposals GROUP BY status ORDER BY 1;
SELECT status, COUNT(*) FROM offers    GROUP BY status ORDER BY 1;
SELECT status, COUNT(*) FROM refunds   GROUP BY status ORDER BY 1;
SELECT MAX(created_at), MAX(updated_at) FROM proposals;
SELECT COUNT(*) FROM users WHERE deleted = 0;
-- STORED 생성 컬럼(0034)이 올바로 재계산됐는지. 0이어야 한다
SELECT COUNT(*) FROM user_fcm_tokens WHERE fcm_token_hash <> SHA2(fcm_token, 256);
-- CHECK 제약(0030)이 넘어왔는지. RDS와 개수가 같아야 한다
SELECT COUNT(*) FROM information_schema.CHECK_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = '<DB>';

-- (5) FK 고아 행 검사 쿼리 생성 → 출력된 쿼리를 실행해 모두 0인지 확인 (단일 컬럼 FK 기준)
SELECT CONCAT('SELECT ''', k.TABLE_NAME, '.', k.COLUMN_NAME, ''' fk, COUNT(*) orphans FROM `', k.TABLE_SCHEMA, '`.`', k.TABLE_NAME,
              '` c LEFT JOIN `', k.REFERENCED_TABLE_SCHEMA, '`.`', k.REFERENCED_TABLE_NAME, '` p ON c.`', k.COLUMN_NAME,
              '` = p.`', k.REFERENCED_COLUMN_NAME, '` WHERE c.`', k.COLUMN_NAME, '` IS NOT NULL AND p.`',
              k.REFERENCED_COLUMN_NAME, '` IS NULL;')
FROM information_schema.KEY_COLUMN_USAGE k
WHERE k.TABLE_SCHEMA = '<DB>' AND k.REFERENCED_TABLE_NAME IS NOT NULL;
```

**API 확인** (`BASE`는 대상 환경 도메인). 데모 로그인은 인증 레코드 생성·로그인 시각 갱신으로 **DB 쓰기까지** 확인한다.

```bash
BASE=https://staging-api.kkobung-dan.store
curl -fsS "$BASE/v1/health"
curl -fsS -X POST "$BASE/v1/auth/login/send" -H 'Content-Type: application/json' -d '{"phone":"01000000000"}'
TOKEN=$(curl -fsS -X POST "$BASE/v1/auth/login/confirm" -H 'Content-Type: application/json' \
  -d '{"phone":"01000000000","code":"123456"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["accessToken"])')
curl -fsS "$BASE/v1/user/detail"   -H "Authorization: Bearer $TOKEN"
curl -fsS "$BASE/v1/proposal"      -H "Authorization: Bearer $TOKEN"
curl -fsS "$BASE/v1/proposal/own"  -H "Authorization: Bearer $TOKEN"
# 관리자: POST $BASE/v1/admin/auth/login 후 GET $BASE/v1/admin/summary (비밀번호는 프롬프트로 입력)
# 전환 전에 받아 둔 토큰이 전환 후에도 통하는지도 본다 (JWT secret·사용자 행이 그대로여야 통과)
docker logs --since 15m orderrun-app-staging 2>&1 | grep -iE 'OperationalError|Traceback|ERROR' | tail -20
```

연결 확인:

```sql
-- EC2 MySQL: 앱 계정이 192.168.100.x 에서 붙어 있어야 한다
SELECT user, host, db, command FROM information_schema.PROCESSLIST WHERE user NOT IN ('system user','event_scheduler');
-- RDS: 전환한 환경의 계정 연결이 없어야 한다 (CloudWatch DatabaseConnections로도 본다)
SELECT user, host, db FROM information_schema.PROCESSLIST WHERE db = '<DB>';
```

### 4.1 Phase 0 — 사전 점검과 용량 확보

5장의 점검 명령을 돌리고 7장 기준으로 용량을 결정한다. 인스턴스 타입 변경·EBS 확장은 **사용자 승인 후** 별도
작업으로 한다.

### 4.2 Phase 1 — DB 스택 기동 (서비스 영향 없음)

3.4 → 3.5 순서로 실행한다. 이 시점에 앱은 아무도 새 MySQL을 쓰지 않는다.

### 4.3 Phase 2 — 앱 네트워크 연결 배포 (동작 변화 없음)

3.1 변경을 PR로 올려 staging → main 순서로 평소처럼 배포한다. 두 앱이 DB 네트워크에 붙지만 DB_HOST는
여전히 RDS다.

확인:

```bash
docker exec orderrun-app-staging python -c "import socket; print(socket.gethostbyname('orderrun-mysql')); socket.create_connection(('orderrun-mysql', 3306), 3); print('tcp ok')"
docker exec orderrun-nginx getent hosts orderrun-mysql || echo "nginx cannot resolve mysql (OK)"
```

prod 쪽 네트워크 연결은 PROD 전환 배포 때 같이 되기도 하지만, 미리 무해하게 한 번 거쳐 두면 점검 창의 변수가 줄어든다.

### 4.4 Phase 3 — STAGING 이전

**리허설 (영향 없음, staging 앱은 RDS 사용 중):** 4.0 덤프 → 복원 → 검증(1)~(5)을 한 번 돌리고 각 단계
소요 시간을 기록한다. 로컬에서 `mysql:8.0`(RDS와 같은 버전) 컨테이너에 EC2 덤프를 복원해 역방향(rollback) 호환도 확인한다.

**전환 (staging 15~30분 중단):**

1. 클라이언트 개발자에게 공지. `staging`/`main` 머지 동결(동시 배포 방지)
2. 쓰기 중단: `docker stop orderrun-app-staging` (스케줄러 잡도 함께 멈춘다)
3. RDS에 staging 계정 연결이 없는지 확인 (4.0 연결 확인)
4. 최종 덤프 → EC2 복원 → 검증 (1)~(5)
5. GitHub Secrets(`staging` Environment 또는 repo): `STG_MYSQL_HOST=orderrun-mysql`
   (D5 예외면 `STG_MYSQL_USER`/`STG_MYSQL_PASSWORD`도)
6. Actions → Staging Deploy → Run workflow (`staging` 브랜치). `deploy.sh`가 새 DB에 `alembic upgrade head`
   (no-op)를 돌린 뒤 app-staging을 새 env로 올린다
7. API 확인·연결 확인. `docker exec orderrun-app-staging printenv DB_HOST` 로 호스트만 확인한다
   (`env` 전체를 찍지 않는다. 비밀번호가 보인다)
8. 3~7일 관찰. 이 기간에 5장 백업 가동과 첫 복원 테스트를 마친다

### 4.5 Phase 4 — 백업 가동

6장을 적용하고 첫 백업이 S3에 올라가는지, 실패 알림이 오는지(일부러 실패시켜) 확인한다. 첫 복원 테스트를 한다.

### 4.6 Phase 5 — PROD 이전

**사전 (D-7 ~ D-1):**

- STAGING이 안정적으로 돌고 백업·복원 테스트가 통과했다
- PROD 리허설: RDS prod 읽기 전용 덤프 → EC2 `<PROD_DB>` 복원 → 검증, 소요 시간 측정 (복원본은 전환 때 새로 만든다)
- 점검 공지(목표 30분, 예약 60분), 머지 동결, 디스크 여유 확인
- (승인 시) 점검 직전 RDS 수동 스냅샷

**점검 창:**

| T | 작업 |
| --- | --- |
| +0 | `docker stop orderrun-app-prod` → prod API 502, 스케줄러 정지. RDS에 prod 계정 연결이 없는지 확인 |
| +2 | 최종 덤프 → `Dump completed`·sha256 확인 |
| +5 | EC2 `<PROD_DB>` 재생성 → 복원 |
| +8 | 검증 (1)~(5). 하나라도 어긋나면 **여기서 중단하고 R-A** (RDS는 손대지 않은 상태) |
| +15 | GitHub Secrets(`production` Environment): `PROD_MYSQL_HOST=orderrun-mysql` (D5 예외면 USER/PASSWORD도) |
| +16 | Actions → Production Deploy → Run workflow(`main`) → 승인. 워크플로 자체 검증(health, 문서 404, staging health, healthy) 통과 확인 |
| +28 | API 확인(prod 데모 로그인·목록·관리자 summary), 로그 확인, 연결 확인. 앱이 healthy가 되는 순간 트래픽이 들어오므로 **이 시점부터 새 DB에 실데이터가 쌓인다** |
| +30 | 점검 종료 공지. 10분 뒤 결제 리마인더 잡, 1시간 뒤 만료 취소 잡 로그 확인 |

### 4.7 Phase 6 — 관찰과 RDS 정리 (별도 승인)

1. 1~2주 관찰. 이 기간 RDS는 **켜 둔다**(rollback 대기). CloudWatch `DatabaseConnections`가 0인지 본다
2. RDS **중지** (최대 7일 뒤 자동 재시작되므로 재중지하거나 다음 단계로)
3. 최종 스냅샷을 남기고 RDS 삭제. 필요 시 스냅샷은 1~3개월 뒤 삭제(또는 S3의 최종 덤프로 대체)
4. RDS 보안그룹·서브넷그룹·파라미터그룹 정리

---

## 5. 사전 점검 (읽기 전용)

### 5.1 EC2

```bash
uname -m                                  # x86_64 여야 한다 (CI가 linux/amd64만 빌드)
nproc; free -h; swapon --show
df -h /; df -i /; lsblk
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
docker stats --no-stream
docker system df
docker network ls
docker network inspect orderrun-ec2-network -f '{{json .IPAM.Config}}'
docker volume ls
docker version --format '{{.Server.Version}}'; docker compose version   # compose v2.3+ (top-level name)
du -sh ~/orderrun/logs
ls -l ~/orderrun/.env.ec2 ~/orderrun/.env.ec2.bak                        # 권한 확인 (600이어야 함)
TOKEN=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-type; echo
curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/iam/info; echo   # 인스턴스 역할 유무
uptime; cat /etc/os-release | head -3; timedatectl | grep -i 'time zone'
sudo dmesg -T | grep -iE 'out of memory|killed process' | tail   # 과거 OOM 흔적
systemctl is-enabled docker
crontab -l; sudo crontab -l; systemctl list-timers --no-pager | head -20   # 기존 호스트 작업(인증서 갱신 등)
```

AWS 콘솔: 인스턴스 타입, **Elastic IP 연결 여부**, VPC CIDR, IMDS hop limit, EBS 크기·타입, 보안그룹 인바운드.

### 5.2 RDS (EC2에서 4.0의 `rds` 함수로 조회)

```sql
SELECT VERSION(), @@character_set_server, @@collation_server, @@global.time_zone, @@system_time_zone,
       @@GLOBAL.sql_mode, @@lower_case_table_names, @@max_allowed_packet, @@transaction_isolation,
       @@explicit_defaults_for_timestamp, @@gtid_mode, @@innodb_buffer_pool_size, @@max_connections;

SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA WHERE SCHEMA_NAME NOT IN ('mysql','sys','information_schema','performance_schema');

SELECT TABLE_SCHEMA, TABLE_NAME, ENGINE, TABLE_COLLATION,
       ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) AS mb
FROM information_schema.TABLES WHERE TABLE_SCHEMA IN ('<PROD_DB>','<STG_DB>') ORDER BY 1, 2;

SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA IN ('<PROD_DB>','<STG_DB>') AND COLLATION_NAME IS NOT NULL
GROUP BY 1, 2, 3, 4, 5 HAVING COLLATION_NAME <> (SELECT DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA s WHERE s.SCHEMA_NAME = TABLE_SCHEMA);

SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA IN ('<PROD_DB>','<STG_DB>') AND DATA_TYPE = 'timestamp';   -- 있으면 tz 영향 대상

SELECT 'routine', ROUTINE_SCHEMA, ROUTINE_NAME, DEFINER FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA IN ('<PROD_DB>','<STG_DB>')
UNION ALL SELECT 'trigger', TRIGGER_SCHEMA, TRIGGER_NAME, DEFINER FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA IN ('<PROD_DB>','<STG_DB>')
UNION ALL SELECT 'event', EVENT_SCHEMA, EVENT_NAME, DEFINER FROM information_schema.EVENTS WHERE EVENT_SCHEMA IN ('<PROD_DB>','<STG_DB>')
UNION ALL SELECT 'view', TABLE_SCHEMA, TABLE_NAME, DEFINER FROM information_schema.VIEWS WHERE TABLE_SCHEMA IN ('<PROD_DB>','<STG_DB>');

SELECT CONSTRAINT_SCHEMA, COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA IN ('<PROD_DB>','<STG_DB>') GROUP BY 1;

SELECT user, host, plugin FROM mysql.user WHERE user NOT LIKE 'rds%' AND user NOT LIKE 'mysql.%';   -- 마스터 계정 필요
SHOW GRANTS FOR '<앱 계정>'@'%';
SELECT version_num FROM `<PROD_DB>`.alembic_version;
SELECT version_num FROM `<STG_DB>`.alembic_version;
```

CloudWatch(최근 2주): `DatabaseConnections`, `FreeableMemory`, `CPUUtilization`, `FreeStorageSpace`, Read/Write IOPS.
Billing: RDS 인스턴스·스토리지·백업·Extended Support 항목.

### 5.3 GitHub

- `PROD_MYSQL_*`/`STG_MYSQL_*`가 repo secret인지 Environment secret인지(둘 다 있으면 Environment가 우선)
- `PROD_EC2_HOST`와 `STG_EC2_HOST`가 같은 호스트인지
- `production` Environment 승인 규칙

---

## 6. 백업 설계

### 6.1 구조

```
systemd timer (매일 03:30 KST)
  → mysql-backup.sh
     → docker exec orderrun-mysql mysqldump (orderrun_backup 계정, secret 파일)
     → gzip → gzip -t, "Dump completed" 확인
     → ~/orderrun-db/backups (로컬 3일)
     → aws s3 cp (인스턴스 역할)
     → 디스크 사용률 검사
  실패 시 → OnFailure → Slack 알림
S3 수명주기 규칙이 오래된 객체를 지운다 (EC2에는 삭제 권한이 없다)
```

cron 대신 **systemd timer**를 쓴다. `Persistent=true`로 꺼져 있던 동안 놓친 실행을 부팅 후 따라잡고,
로그가 journald에 남고(`journalctl -u orderrun-mysql-backup`), `OnFailure=`로 실패 알림을 붙이기 쉽다.
cron은 실패가 조용히 묻힌다.

### 6.2 `scripts/mysql-backup.sh` (신규 초안)

```bash
#!/usr/bin/env bash
# EC2 내부 MySQL 논리 백업: mysqldump → gzip → S3. systemd timer(orderrun-mysql-backup.timer)가 호출한다.
# 설정은 EnvironmentFile(~/orderrun-db/backup.env)로 받고, DB 자격증명은 컨테이너 안의 secret 파일만 쓴다.
set -euo pipefail
umask 077

container="${MYSQL_CONTAINER:-orderrun-mysql}"
backup_dir="${BACKUP_DIR:-/home/ubuntu/orderrun-db/backups}"
s3_uri="${BACKUP_S3_URI:?BACKUP_S3_URI is required}"           # 예: s3://<bucket>/mysql
databases="${BACKUP_DATABASES:?BACKUP_DATABASES is required}"   # 공백 구분: "<PROD_DB> <STG_DB>"
local_retention_days="${LOCAL_RETENTION_DAYS:-3}"
disk_alert_percent="${DISK_ALERT_PERCENT:-85}"

ts="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"

for db in $databases; do
  out="${backup_dir}/${db}-${ts}.sql.gz"
  partial="${out}.partial"

  # pipefail이라 mysqldump가 실패하면 파이프 전체가 실패한다.
  docker exec "$container" mysqldump \
    --defaults-extra-file=/run/secrets/mysql_backup_cnf \
    --single-transaction --quick \
    --routines --triggers --events \
    --hex-blob --no-tablespaces --set-gtid-purged=OFF \
    --default-character-set=utf8mb4 \
    "$db" | gzip -c > "$partial"

  # 잘린 덤프를 정상 백업으로 올리지 않는다. mysqldump는 끝까지 썼을 때만 마지막 줄을 남긴다.
  gzip -t "$partial"
  if ! zcat "$partial" | tail -n 1 | grep -q '^-- Dump completed'; then
    echo "덤프가 끝까지 쓰이지 않았다: ${db}" >&2
    exit 1
  fi
  mv "$partial" "$out"

  aws s3 cp "$out" "${s3_uri%/}/daily/${db}/$(basename "$out")" --only-show-errors
  echo "backup ok: ${db} $(du -h "$out" | cut -f1)"
done

find "$backup_dir" -name '*.partial' -delete
find "$backup_dir" -name '*.sql.gz' -mtime "+${local_retention_days}" -delete

# 디스크가 차면 MySQL이 멈춘다. 백업은 끝났어도 실패로 끝내 OnFailure 알림을 태운다.
usage="$(df --output=pcent / | tail -1 | tr -dc '0-9')"
if (( usage >= disk_alert_percent )); then
  echo "디스크 사용률 ${usage}% (기준 ${disk_alert_percent}%)" >&2
  exit 1
fi
```

`~/orderrun-db/backup.env` (600):

```
BACKUP_S3_URI=s3://<bucket>/mysql
BACKUP_DATABASES=<PROD_DB> <STG_DB>
BACKUP_ALERT_WEBHOOK_URL=<운영 알림용 Slack webhook>
```

### 6.3 systemd 유닛 (신규 초안)

```ini
# /etc/systemd/system/orderrun-mysql-backup.service
[Unit]
Description=OrderRun MySQL backup to S3
Wants=network-online.target
After=network-online.target docker.service
OnFailure=orderrun-mysql-backup-alert.service

[Service]
Type=oneshot
User=ubuntu
EnvironmentFile=/home/ubuntu/orderrun-db/backup.env
ExecStart=/home/ubuntu/orderrun-db/mysql-backup.sh
Nice=10
IOSchedulingClass=idle
TimeoutStartSec=30min
```

```ini
# /etc/systemd/system/orderrun-mysql-backup.timer
[Unit]
Description=Daily OrderRun MySQL backup

[Timer]
# 03:30 KST. prod를 6시간마다로 올리려면 *-*-* 00/6:30:00 UTC
OnCalendar=*-*-* 18:30:00 UTC
RandomizedDelaySec=10min
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/orderrun-mysql-backup-alert.service
[Unit]
Description=Alert on OrderRun MySQL backup failure

[Service]
Type=oneshot
EnvironmentFile=/home/ubuntu/orderrun-db/backup.env
ExecStart=/bin/sh -c 'curl -fsS -m 10 -H "Content-Type: application/json" --data "{\"text\":\"[orderrun] MySQL 백업 실패: $(hostname). journalctl -u orderrun-mysql-backup 확인\"}" "$BACKUP_ALERT_WEBHOOK_URL"'
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now orderrun-mysql-backup.timer
sudo systemctl start orderrun-mysql-backup.service      # 즉시 1회 실행
journalctl -u orderrun-mysql-backup -n 50 --no-pager
systemctl list-timers orderrun-mysql-backup.timer
```

### 6.4 보관 주기와 삭제 정책

| 대상 | 위치 | 보관 | 삭제 주체 |
| --- | --- | --- | --- |
| prod 일일 | `s3://<bucket>/mysql/daily/<PROD_DB>/` | 30일 | S3 수명주기 규칙 |
| staging 일일 | `s3://<bucket>/mysql/daily/<STG_DB>/` | 7일 | S3 수명주기 규칙 |
| 이전 버전(versioning) | 버킷 전체 | 7일 | 수명주기 noncurrent 만료 |
| 미완료 multipart | 버킷 전체 | 1일 | 수명주기 |
| 로컬 사본 | `~/orderrun-db/backups` | 3일 | 스크립트 `find -mtime` |

- 장기(월간·연간) 보관은 기본으로 두지 않는다. 탈퇴 정책([withdrawal-policy.md](../../domains/user-auth/withdrawal-policy.md))은
  개인정보를 즉시 hard delete하는데, 백업은 그 데이터를 보관 기간만큼 들고 있다. 30일은 RDS 자동 백업과
  비슷한 수준이다. 더 길게 가져가려면 개인정보 처리방침과 먼저 맞춘다.
- 덤프 크기가 MB 단위라 S3 비용은 월 수십 원 수준이다.

### 6.5 S3 버킷과 IAM 최소 권한

버킷: Block Public Access 전부 켬, 기본 암호화 SSE-S3, Versioning 켬, TLS가 아닌 요청 거부 버킷 정책.

EC2 인스턴스 역할(액세스 키를 디스크에 두지 않는다):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadWriteBackupObjects",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::<bucket>/mysql/*"
    },
    {
      "Sid": "ListBackupPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::<bucket>",
      "Condition": { "StringLike": { "s3:prefix": ["mysql/*"] } }
    }
  ]
}
```

- `DeleteObject`/`DeleteObjectVersion`은 주지 않는다. 호스트가 뚫려도 백업을 지울 수 없고, versioning 덕에
  덮어써도 이전 버전이 남는다. 삭제는 수명주기 규칙만 한다.
- `GetObject`는 복원 테스트용이다. 이 호스트는 이미 라이브 DB를 갖고 있으니 새로 노출되는 것은 없다.
- IMDS hop limit이 1이면 컨테이너는 이 역할 자격증명을 가져가지 못한다(호스트의 백업 스크립트만 사용).
  SNS는 앱이 명시적 키로 호출하므로(`app/services/sms_service.py`) 역할 추가의 영향을 받지 않는다.
- 호스트에 AWS CLI v2 설치가 필요하다.

### 6.6 복원 테스트 (월 1회 + 첫 백업 직후)

같은 서버의 임시 DB에 복원한다(두 번째 mysqld를 띄우지 않아 메모리 부담이 없다). 덤프에 `USE`가 없어서
지정한 DB에만 들어간다.

```bash
f=$(aws s3 ls s3://<bucket>/mysql/daily/<PROD_DB>/ | sort | tail -1 | awk '{print $4}')
aws s3 cp "s3://<bucket>/mysql/daily/<PROD_DB>/$f" ~/migration/restore-test.sql.gz
ec2 -e "DROP DATABASE IF EXISTS restore_check; CREATE DATABASE restore_check CHARACTER SET utf8mb4 COLLATE <값>;"
zcat ~/migration/restore-test.sql.gz | docker exec -i orderrun-mysql \
  mysql --defaults-extra-file=/run/secrets/mysql_root_cnf restore_check
ec2 -e "SELECT version_num FROM restore_check.alembic_version; SELECT COUNT(*) FROM restore_check.users; SELECT COUNT(*) FROM restore_check.proposals;"
ec2 -e "DROP DATABASE restore_check;"
rm -f ~/migration/restore-test.sql.gz
```

결과(파일명, 행 수, 소요 시간)를 이 계획의 검증 기록에 남긴다.

### 6.7 보조 안전망 (선택)

AWS Data Lifecycle Manager로 EBS 루트 볼륨 일일 스냅샷(7일 보관). 크래시 일관 스냅샷이라 InnoDB 복구를
타지만 호스트 전체 복구 수단이 하나 더 생긴다.

---

## 7. EC2 리소스 판단

### 실측 결과 (2026-09-29, 읽기 전용 점검)

| 항목 | 값 |
| --- | --- |
| 인스턴스 | **t3.micro** (2 vCPU, 메모리 911MiB), x86_64, Ubuntu 24.04.4, ap-northeast-2, 가동 164일 |
| 메모리 | used 510MiB, **available 401MiB**, buff/cache 414MiB |
| swap | `/swapfile` 2GiB, **MySQL 없이 이미 324MiB 사용** |
| 프로세스(RSS+swap) | uvicorn 118MiB·87MiB(대부분 swap으로 밀려난 상태), dockerd 78MiB, containerd 40MiB |
| 메모리 압박 | 점검 시점 PSI 0, swap in/out 0 (평시 유휴) |
| 디스크 | 29G 중 7.9G 사용, 21G 여유 — 충분, 확장 불필요 |
| Docker | 29.1.3, compose 5.1.3, 컨테이너 3개 healthy |
| IAM 인스턴스 역할 | **없음** (S3 백업 전에 생성·연결 필요) |
| 부수 발견 | `~/orderrun/.env.ec2`, `.env.ec2.bak`, `.env`, `.env.save` 권한 664(다른 사용자 읽기 가능), 용도 불명 파일 `1` |

**판정: 부족.** MySQL 8.4를 최소 설정(buffer pool 128M, performance_schema OFF)으로 올려도 250~350MiB가
필요한데 여유가 400MiB이고, 이미 swap을 쓰고 있다. 배포 때는 마이그레이션 컨테이너와 이미지 풀이 더 올라온다.
InnoDB 버퍼가 swap으로 밀리면 DB 응답이 급격히 느려지고, 그 영향이 같은 호스트의 prod 앱까지 번진다.
요청 조건("부족하면 중단하고 필요한 사양만 보고")에 따라 1차 작업을 멈췄다.

**필요 사양: t3.small (2 vCPU, 2GiB) 이상.** 같은 x86_64라 현재 이미지를 그대로 쓴다. t3a.small(AMD)도
호환되고 조금 더 싸다(서울 리전 요금표 확인). 디스크와 swap은 지금 그대로 충분하다.

### 메모리 추정 (계획 시점)

| 구성 | 추정 RSS |
| --- | --- |
| OS + snap/ssm 에이전트 + dockerd/containerd | 250~350MB |
| app-prod (uvicorn 1 worker, firebase-admin·boto3·APScheduler) | 150~250MB |
| app-staging | 150~250MB |
| nginx | ~10MB |
| **배포 중 일시:** `compose run` 마이그레이션 컨테이너 + 이미지 pull/압축 해제 | +150~250MB |
| MySQL 8.4 (buffer pool 256M, performance_schema ON) | 450~600MB |
| MySQL 8.4 (buffer pool 128M, performance_schema OFF) | 250~350MB |

- **1GiB(t3.micro/t2.micro)**: MySQL 없이도 배포 순간 700~1,100MB를 쓴다. MySQL을 더하면 swap 없이는 OOM
  가능성이 높다. 리눅스 OOM killer는 보통 가장 큰 프로세스인 mysqld를 죽이고, 그러면 prod와 staging이 **동시에**
  멈춘다. 최소 설정(128M, PS OFF) + swap 2GB로 버틸 수는 있어도 TD-012 락 추적을 포기해야 하고 여유가 없다.
- **2GiB(t3.small)이 현실적인 최소다.** 3.3 설정 기준 합계는 평시 1.1~1.5GB, 배포 중 1.3~1.7GB로 들어간다.
  swap 1~2GB를 안전망으로 추가한다(`vm.swappiness=10`).
- 비용 방향: t3.micro → t3.small은 EC2 시간 단가가 약 2배다(월 약 $10 증가 수준, 서울 리전 요금표로 확인).
  RDS 인스턴스·스토리지·백업(+ 해당 시 Extended Support) 절감액이 이보다 크면 이전의 의미가 있다.
- Graviton(t4g)이 더 싸지만 CI가 `linux/amd64`만 빌드하므로 멀티아키 빌드 전에는 쓸 수 없다.
- t3는 CPU 크레딧 기반이다. 평균 CPU가 baseline(t3.small 20%)을 넘는지 CloudWatch `CPUCreditBalance`로 본다.

### 디스크

- 기존 배포가 디스크를 채운 적이 있다(`deploy.sh` prune 주석). MySQL 데이터 + binlog(3일) + 로컬 백업(3일)이
  더해진다. 디스크가 차면 MySQL이 멈춘다. **gp3 20GB 이상**을 권장한다.
- EBS 크기 변경은 온라인으로 된다. Ubuntu는 보통 cloud-init이 부팅 때 파티션·파일시스템을 늘리지만, 안 되면
  `growpart` + `resize2fs`를 쓴다.

### 인스턴스 타입 변경 시 주의 (지금은 하지 않는다)

- stop/start가 필요하다. prod와 staging이 **같이 3~5분 멈춘다.** 별도 점검 창에서 한다.
- **Elastic IP가 없으면 공인 IP가 바뀐다.** DNS(두 도메인 → 43.200.56.9), `PROD_EC2_HOST`/`STG_EC2_HOST`
  Secret, nginx `EC2_PUBLIC_IP`가 모두 깨진다. 변경 전에 EIP 연결을 확인한다.
- EBS 확장을 먼저 해 두면 타입 변경 재부팅 때 파일시스템 확장이 같이 된다.

---

## 8. Rollback

rollback 판단 기준은 **"새 DB가 실요청을 처리했는가"**다. GitHub Secret은 덮어쓰면 다시 읽을 수 없으므로,
전환 전에 RDS endpoint(콘솔에서 확인 가능)와, D5 예외라면 기존 USER/PASSWORD를 비밀번호 관리자에 보관한다.

### R-A. 새 DB가 요청을 받기 전 (무손실)

점검 창 +8 검증 실패, 배포 실패(마이그레이션·health) 등. RDS는 동결 이후 그대로다.

1. GitHub Secret `PROD_MYSQL_HOST`(D5 예외면 USER/PASSWORD도)를 RDS 값으로 되돌린다
2. Actions → Production Deploy → Run workflow(`main`) → 승인
3. `deploy.sh`가 RDS에 `alembic upgrade head`(no-op)를 돌리고 app-prod를 RDS로 다시 올린다
4. API 확인 → 점검 종료. 약 10분

### R-B. 새 DB가 이미 요청을 처리한 뒤 (역방향 복사)

RDS로 바로 돌리면 전환 이후 데이터(결제·요청·지원)가 사라진다. 역방향으로 복사한 뒤 되돌린다.

1. `docker stop orderrun-app-prod` (쓰기 중단)
2. (승인) RDS 수동 스냅샷 — 되돌리기 직전 상태 보존
3. EC2 덤프: `docker exec orderrun-mysql mysqldump --defaults-extra-file=/run/secrets/mysql_root_cnf <4.0 덤프 옵션> <PROD_DB> | gzip > ~/migration/rollback-<ts>.sql.gz`
4. RDS 복원: `zcat … | docker run --rm -i -v ~/migration:/work:ro mysql:<RDS 버전> mysql --defaults-extra-file=/work/rds.cnf <PROD_DB>`
   (덤프의 `DROP TABLE IF EXISTS`+`CREATE`가 테이블을 교체한다. 8.4 → 8.0 호환은 4.4 리허설에서 미리 확인한다)
5. 4.0 검증 (1)(2)를 반대 방향으로 실행
6. R-A의 1~4
7. 약 20~30분. **PROD DB 변경이므로 실행 시점에 사용자 승인 필요**

### R-C. STAGING

staging 데이터 손실을 감수할 수 있으면 R-A만 한다(`STG_MYSQL_HOST` 복구 → Staging Deploy 수동 실행).

### 비상 수동 경로 (CI를 쓸 수 없을 때만)

`.env.ec2`는 마지막에 배포한 환경의 값만 온전하다(1.5의 1번). 먼저 확인한다.

```bash
cd ~/orderrun
grep -q 'prod-not-configured' .env.ec2 && echo "중단: 마지막 배포가 staging이라 PROD 값이 없다. 워크플로로 되돌린다"
cp -p .env.ec2 .env.ec2.pre-rollback
# 에디터로 PROD_MYSQL_HOST (필요 시 USER/PASSWORD)만 RDS 값으로 수정
COMPOSE_FILE=docker-compose.ec2.yml COMPOSE_ENV_FILE=.env.ec2 DEPLOY_TARGET=prod ./deploy.sh
```

이후 **반드시 GitHub Secret도 같은 값으로 맞춘다.** 안 그러면 다음 prod 배포가 EC2 MySQL로 다시 붙어 두 DB에 쓰기가 갈라진다.

### Rollback이 가능한 기간

RDS를 켜 둔 1~2주가 rollback 창이다. RDS를 삭제한 뒤의 복구 수단은 S3 백업(6장)뿐이다.

---

## 9. 보안 점검

| 항목 | 이 계획의 처리 |
| --- | --- |
| 3306 외부 공개 금지 | mysql 서비스에 `ports:` 없음. `internal` 네트워크. 적용 후 `docker port`, `ss -lntp`로 확인 |
| Security Group | EC2 SG에 3306 인바운드가 **필요 없다.** 있으면 제거 대상(현재 여부 확인). RDS SG는 RDS 삭제 때 같이 정리. 80/443/22는 그대로 |
| Docker 내부 통신만 | `orderrun-db-network`에 mysql·app-prod·app-staging만. nginx 미연결. 계정 호스트를 `192.168.100.%`로 제한 |
| root 외부 사용 금지 | `MYSQL_ROOT_HOST=localhost`로 root@'%' 미생성. 운영 작업은 `docker exec` + 소켓 |
| PROD/STAGING 계정 분리 | 가능. 스키마별 GRANT(D6). 지금 RDS에서 공용 계정이면 이번에 분리한다(D5 예외) |
| compose에 평문 Secret 금지 | MySQL: `secrets:` 파일 + `MYSQL_ROOT_PASSWORD_FILE`, 파일 600, 디렉터리 700. 앱: 기존 `.env.ec2` 방식 유지(compose 파일에는 변수 참조만 있음) |
| nginx/HTTPS 유지 | 가능. nginx 템플릿·인증서 볼륨·프로젝트명(`orderrun`)을 바꾸지 않는다. 프로젝트명을 바꾸면 `orderrun_letsencrypt` 볼륨이 새로 잡혀 인증서를 잃는다 |
| 덤프 파일 | 개인정보 포함. `~/migration`(700), 작업 후 삭제. 로컬 PC로 옮기지 않는다 |

기존 구조에서 발견한 개선 여지 (이번 범위 밖, 별도 PR 권장):

- 워크플로가 `.env.ec2`를 기본 umask로 만든다(대개 644). `sed -i.bak`가 남기는 `.env.ec2.bak`에도 모든 Secret이
  있다. heredoc 앞에 `umask 077`, `.bak` 제거 또는 `chmod 600`
- 두 deploy 잡에 `concurrency: { group: ec2-deploy, cancel-in-progress: false }`
- `docker inspect`로 앱 컨테이너 env(DB 비밀번호 포함)가 보인다. 단일 운영자 호스트라 현재 수용 가능

---

## 10. GitHub Secrets 영향

| 분류 | Secret |
| --- | --- |
| **유지 (값도 그대로)** | `DOCKER_USERNAME`, `DOCKER_PASSWORD`, `PROD_EC2_HOST`/`USERNAME`/`SSH_KEY`, `STG_EC2_HOST`/`USERNAME`/`SSH_KEY`, `PROD_JWT_SECRET`, `STG_JWT_SECRET`, `AWS_SNS_REGION`, `AWS_SNS_ACCESS_KEY_ID`, `AWS_SNS_SECRET_ACCESS_KEY`, `ADMIN_USERNAME`, `ADMIN_INITIAL_PASSWORD`, `PROD_ADMIN_ALERT_SLACK_WEBHOOK_URL`, `STG_ADMIN_ALERT_SLACK_WEBHOOK_URL`, `LETSENCRYPT_EMAIL`, `DOCS_BASIC_AUTH_HTPASSWD`, `FCM_CREDENTIALS_JSON`(워크플로 미사용, 그대로 둔다), `PROD_MYSQL_PORT`, `STG_MYSQL_PORT`, `PROD_MYSQL_DATABASE`, `STG_MYSQL_DATABASE` |
| **값 변경** | `PROD_MYSQL_HOST`, `STG_MYSQL_HOST` → `orderrun-mysql` |
| **조건부 값 변경** | `*_MYSQL_USER`, `*_MYSQL_PASSWORD` — prod/staging 공용 계정이거나 RDS 마스터 계정을 쓰는 경우만(D5) |
| **삭제 가능** | 없음. DB Secret은 모두 워크플로가 계속 참조한다. 워크플로 밖에서 RDS 전용으로 저장해 둔 Secret이 있으면 RDS 삭제 후 정리 |
| **신규** | GitHub에는 없음. MySQL root·백업 비밀번호는 EC2 `~/orderrun-db/secrets/`와 비밀번호 관리자에만 둔다 |

JWT Secret을 바꾸면 모든 사용자가 강제 로그아웃된다. 사용자 행이 그대로 복사되므로 JWT를 유지하면 기존
로그인이 이어진다(4.0 API 확인에서 검증). `ADMIN_INITIAL_PASSWORD`는 관리자 계정이 없을 때만 쓰이고, 복원된
DB에는 이미 계정이 있다. FCM 키는 Secret이 아니라 EC2 `~/orderrun/keys/` 파일이므로 호스트를 교체할 때만 신경 쓰면 된다.

---

## 11. 작업 분해와 수정 파일 (승인 후)

| 파일 | 변경 | 필수 |
| --- | --- | --- |
| `docker-compose.ec2.yml` | 앱 2개에 외부 네트워크 `db` 추가 (3.1) | 필수 |
| `docker-compose.mysql.yml` | 신규 (3.2) | 필수 |
| `mysql/conf.d/orderrun.cnf` | 신규 (3.3) | 필수 |
| `scripts/mysql-backup.sh` | 신규 (6.2) | 필수 |
| `scripts/systemd/orderrun-mysql-backup.{service,timer}`, `orderrun-mysql-backup-alert.service` | 신규 (6.3) | 필수 |
| `scripts/mysql-verify-copy.sh` | 4.0 검증 (1)(2)(3)을 스크립트로 묶어 점검 창의 수작업 실수를 줄인다 | 권장 |
| `docker-compose.test.yml` | `mysql:8.0` → 운영과 같은 `mysql:8.4` | 권장 |
| `.github/workflows/*.yml` | 필수 변경 없음. `concurrency`, `umask 077`은 별도 PR 권장 | 선택 |
| `scripts/deploy.sh`, `nginx/*`, `app/*` | 변경 없음 | — |
| `docs/design-docs/ec2-mysql-hosting.md` | 설계 결정 D1~D7 영구 기록 | 필수 |
| `docs/SECURITY.md` | DB 네트워크·3306·계정 규칙 | 필수 |
| `docs/RELIABILITY.md` | 백업·RPO·복원 테스트 기준 | 필수 |
| `docs/exec-plans/active/2026-06-12-ec2-prod-staging-split.md` | RDS 언급에 이 계획 링크 | 필수 |
| `docs/exec-plans/tech-debt-tracker.md` | 12장 리스크 중 남는 것 | 필수 |

## 12. 예상 작업 시간

| 단계 | 소요 | 서비스 영향 |
| --- | --- | --- |
| 사전 점검 (5장) | 1시간 | 없음 |
| 용량 확보 (EBS 확장, 필요 시 타입 변경, swap) | 30~60분 | 타입 변경 시 prod+staging 3~5분 |
| 코드·문서 PR | 3~4시간 + 리뷰 | 없음 |
| DB 스택 기동·계정 (4.2) | 30~60분 | 없음 |
| 네트워크 연결 배포 (4.3) | 30분 | 없음 |
| STAGING 리허설 + 전환 (4.4) | 2~2.5시간 | staging 15~30분 |
| S3·IAM·백업 타이머·첫 복원 테스트 (4.5) | 1.5~2시간 | 없음 |
| STAGING 관찰 | 3~7일 | — |
| PROD 리허설 | 30~60분 | 없음 |
| PROD 점검 창 (4.6) | 목표 30분 / 예약 60분 | prod 점검 중단 |
| 관찰 후 RDS 정리 (4.7) | 30분 (1~2주 후) | 없음 |

실작업 약 1.5~2일, 달력 기준 2~3주.

## 13. 검증 기준

- `docker compose -f docker-compose.ec2.yml config`, `docker compose -f docker-compose.mysql.yml config` 통과
- `bash -n scripts/mysql-backup.sh` 통과
- 로컬 `mysql:8.4`에서 `alembic upgrade head` 성공, `pytest` 신규 실패 없음(TD-010 기존 1건 제외)
- 각 환경 전환 후: 행 수 전부 OK, 데이터 해시 일치, 스키마 diff 없음, 고아 행 0, alembic 버전 일치,
  API 확인(데모 로그인 쓰기 포함) 통과, RDS 쪽 해당 계정 연결 0
- `docker port orderrun-mysql` 빈 출력, 호스트 3306 미청취, nginx에서 `orderrun-mysql` 이름 해석 실패
- 백업: S3 객체 생성, 실패 알림 수신 확인, 복원 테스트 통과

## 14. 남은 리스크

| 리스크 | 영향 | 대응 |
| --- | --- | --- |
| 단일 호스트 장애점 | EC2가 죽으면 앱과 DB가 같이 멈춘다. EBS를 잃으면 마지막 백업 이후 데이터 손실(RPO 24시간, RDS는 PITR 5분) | 명시적으로 수용할지 결정. DB가 작아 prod 백업을 6시간·1시간 주기로 올리는 비용이 낮다. EBS 스냅샷(6.7) |
| 메모리 부족/OOM | mysqld가 죽으면 prod·staging 동시 중단 | t3.small 이상, swap, `mem_limit`, 3.3 튜닝 |
| 디스크 가득 참 | MySQL 정지 | 20GB+, binlog 3일, 로컬 백업 3일, 백업 스크립트의 사용률 알림 |
| Secret 불일치 | Secret을 안 바꾸고 배포하면 RDS로 다시 붙어 쓰기가 갈라진다 | Secret 변경 → 워크플로 배포 순서 고정. 관찰 후 RDS 중지로 오접속을 "실패"로 드러냄 |
| 빈 DB 함정 | 복원 전에 HOST를 바꾸면 빈 스키마로 healthy하게 뜬다 | 복원·검증 → Secret 변경 순서. 데이터 기반 검증 |
| 동시 배포 | 두 워크플로가 같은 `.env.ec2`·호스트를 동시에 만짐 | 이전 기간 머지 동결, `concurrency` 추가 권장 |
| 8.0 → 8.4 차이 | 인증·옵션·동작 차이 | 로컬 pytest(8.4), STAGING 리허설, 역방향 복원 확인 |
| 같은 서버의 staging 부하 | staging 작업이 prod 성능에 영향 | 지금 RDS도 같은 인스턴스다. 필요 시 staging 계정 `MAX_USER_CONNECTIONS` 제한 |
| 백업이 조용히 실패 | 복구 수단 없음 | OnFailure 알림, 월간 복원 테스트 |
| 백업 속 개인정보 | 탈퇴자 정보가 보관 기간 동안 남음 | 30일 이하, 장기 보관 없음 |
| 운영 부담 이전 | 패치·모니터링·용량 관리를 직접 해야 한다 | 분기별 이미지 패치 태그 갱신, 백업 알림으로 최소 감시 |

## 15. 결정 사항

2026-09-29 사용자가 권장안 전체를 채택했다. 1차 작업 범위는 STAGING 이전까지이고, PROD 전환 전에는 반드시 멈춰
다시 승인을 받는다. 우선순위가 낮은 개선(concurrency, 월간 복원 자동화, 추가 문서 정비)은 후속 작업이다.

### 15.1 STAGING 작업 전

| # | 결정 | 채택 | 남은 입력 |
| --- | --- | --- | --- |
| 1 | 작업 수행 방식 | Claude가 SSH로 EC2 명령 실행. 비밀번호가 드러나는 단계는 사용자가 입력하거나 화면에 출력하지 않는 방식으로 생성 | — |
| 2 | 사양 부족 시 | 중단 후 보고 → **7장 실측 결과 부족 판정, t3.small 이상 필요** | 인스턴스 타입 변경 승인·일시, Elastic IP 연결 확인 |
| 3 | MySQL 버전 | 8.4 LTS (패치 태그 고정) | RDS 엔진 버전 확인 |
| 4 | STAGING DB 계정 | RDS와 같은 이름·비밀번호 재사용 → `STG_MYSQL_HOST`만 변경. 공용·마스터 계정이면 새 계정 | 현재 계정 구성 확인 |
| 5 | 덤프용 RDS 계정 | RDS 마스터(읽기만). `rds.cnf`는 사용자가 작성하고 작업 후 삭제 | — |
| 6 | DB 네트워크 서브넷 | `192.168.100.0/24` | VPC CIDR 비중첩 확인 |
| 7 | S3 백업 기반 | 버킷 신규 생성 + EC2 인스턴스 역할 신규 생성·연결 (현재 역할 없음) | 버킷 이름, 리전(ap-northeast-2 권장) |
| 8 | 백업 실패 알림 | 관리자 운영 알림과 분리된 별도 Slack webhook | webhook URL (EC2에만 저장) |
| 9 | STAGING 전환 일시 | — | 일시, 공지 대상, 머지 동결 기간 |
| 10 | 전환 중 쓰기 중단 | staging 앱 중지, 15~30분 중단 | — |
| 11 | `STG_MYSQL_HOST` 변경 | 사용자가 GitHub UI에서 변경 | repo/Environment 수준 확인 |
| 12 | 코드 반영 범위 | `staging` 브랜치까지. 커밋·PR 생성 허용. `main` 반영은 PROD 준비 때 | — |
| 13 | 쓰기 테스트 | 데모 로그인(인증 레코드 생성·로그인 시각 갱신)까지. 테스트 요청 생성은 선택 | — |

### 15.2 PROD 전환 승인 시점 (권장안, 승인 때 재확인)

- PROD 전환 자체는 별도 승인. 점검 목표 30분, 예약 60분
- PROD DB 계정 재사용. 바꾸게 되면 기존 값을 비밀번호 관리자에 먼저 보관
- PROD 백업 주기 6시간 이하
- 점검 직전 RDS 수동 스냅샷
- 미정: 점검 중 응답(502 유지 vs nginx 점검 응답), rollback 기준·결정권자, 역방향 복사(R-B) 사전 승인, 단일 장애점 수용, EBS 스냅샷 추가

### 15.3 RDS 정리 시점 (권장안)

- 관찰 1~2주 후 RDS 중지 → 최종 스냅샷 → 삭제(별도 승인)
- 백업 보관 prod 30일, staging 7일, 장기 보관 없음
- 미정: 최종 스냅샷 보관 기간, DB 비밀번호 교체 시점

### 15.4 후속 작업

워크플로 `concurrency`, `.env.ec2` 계열 파일 권한(현재 664)과 `.env.ec2.bak` 정리, 월간 복원 테스트 자동화,
문서 정비(설계 문서·SECURITY·RELIABILITY), `docker-compose.test.yml` 8.4 전환, 마이그레이션 전용 계정,
DB 연결 health 엔드포인트, 메모리·디스크 모니터링, MySQL 이미지 패치 주기
