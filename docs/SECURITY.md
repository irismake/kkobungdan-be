# 보안 가이드

## 기본 원칙

학습용 프로젝트라도 보안 요구사항은 초기에 명시해야 한다.

## 핵심 규칙

- 비공개 쓰기 경로는 모두 인증을 거친다.
- 권한은 리소스 소유권 또는 관리자 역할 기준으로 검사한다.
- 클라이언트가 보낸 상태 전이는 검증 없이 신뢰하지 않는다.
- 비밀 정보는 소스 코드와 예제 파일에 넣지 않는다.
- 로그에는 개인정보를 최소한으로 남긴다.

## 최소 통제 항목

- JWT 또는 동등한 bearer token 검증
- 서비스 로직에서의 역할 및 소유권 검사
- 명확한 에러 처리를 포함한 입력 검증
- 환경 변수 기반 비밀 정보 로딩
- 민감 상태 변경에 대한 추적 가능성
- 공개 데모 인증은 전용 전화번호와 용도에만 한정하고 일반 사용자 번호나 환경 전체 우회로 확장하지 않는다.

## 전송 구간과 브라우저 통제

- **CORS Origin은 화이트리스트로만 허용한다.** `CORS_ALLOW_ORIGINS` 환경변수에 명시한
  Origin만 받는다. 와일드카드(`*`)는 코드에서 거부한다 — `allow_credentials=True`와 함께
  쓰면 Starlette이 요청 Origin을 그대로 반사해 아무 도메인이나 자격증명을 실어 보낼 수 있다.
  값이 없으면 development 외 환경에서는 기동에 실패한다
- **API는 HTTPS로만 서빙한다.** 80번 포트와 IP 직접 접근은 HTTPS 도메인으로 308
  리다이렉트한다. IP에는 인증서를 발급할 수 없으므로 클라이언트는 도메인을 쓴다.
  `/.well-known/acme-challenge/`만 예외로 열어 둔다 (인증서 갱신 경로)
- **응답 보안 헤더**는 nginx 443 블록에서 붙인다: `Strict-Transport-Security`(HTTPS만),
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`
- **staging API 문서**(`/docs`, `/redoc`, `/openapi.json`)는 nginx basic auth 뒤에 둔다.
  프로덕션은 앱이 404를 반환한다
- **관리자 로그인은 연속 실패 5회에서 10분 잠근다.** 관리자 계정이 하나뿐이라 표적이 명확하다.
  잠금 중에는 올바른 비밀번호도 거절해, 잠금 응답으로 비밀번호 정오답을 구분할 수 없게 한다

## DB 호스팅

DB는 같은 EC2의 MySQL 컨테이너(별도 compose 프로젝트 `orderrun-db`)다.

- **3306은 호스트에 게시하지 않는다.** `docker-compose.mysql.yml`에 `ports:`를 두지 않는다. Docker가 게시한 포트는
  ufw 규칙을 우회한다. 보안그룹에도 3306 인바운드를 두지 않는다
- **DB는 internal 네트워크 `orderrun-db-network`에만 붙는다.** 이 네트워크에는 `app-prod`, `app-staging`만 연결하고
  nginx는 연결하지 않는다. MySQL 컨테이너는 외부로 나가는 경로도 없다
- **계정은 환경별로 나누고 자기 스키마 권한만 준다.** 앱 계정 호스트는 DB 네트워크 대역(`192.168.100.%`)으로 제한한다.
  root는 컨테이너 내부(`localhost`)에서만 쓰고, 백업 계정은 읽기 전용이다
- **MySQL 자격증명은 저장소와 compose 파일에 두지 않는다.** EC2 `~/orderrun-db/secrets/`(700) 아래 600 파일로 두고
  compose `secrets`로 넘긴다. 앱 자격증명은 GitHub Secrets에서 배포 때 `.env.ec2`(600)로 쓴다
- **인스턴스 메타데이터 hop limit은 1이다.** 컨테이너가 EC2 IAM 역할(S3 백업용) 자격증명을 가져가지 못하게 한다

## 갱신 트리거

아래 변화가 생기면 이 문서를 함께 갱신한다.

- 인증 또는 토큰 발급 방식
- 결제 흐름
- 관리자 기능
- 개인정보 수집 또는 보관 정책
- 허용 Origin 목록, nginx 라우팅, 응답 보안 헤더
- DB 호스팅 위치, DB 네트워크, DB 계정 구성
