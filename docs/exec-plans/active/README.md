# 진행 중 계획

이 디렉터리에는 현재 실행 중인 계획 문서를 둔다.

## 현재 active 계획

- [`2026-06-02-firebase-config-integration.md`](./2026-06-02-firebase-config-integration.md): Firebase 설정 연동과 키 파일 보안 정리
- [`2026-06-12-ec2-prod-staging-split.md`](./2026-06-12-ec2-prod-staging-split.md): EC2 단일 호스트에서 Redis 없이 prod/staging FastAPI와 Nginx 라우팅 분리
- [`2026-08-18-list-sort-order.md`](./2026-08-18-list-sort-order.md): 홈 최신순 정렬과 내 활동 배지 순 정렬
- [`2026-08-22-admin-web-api.md`](./2026-08-22-admin-web-api.md): 관리자 웹 요청·지원·분쟁·환불·지급 API 구축
- [`2026-08-22-admin-auth.md`](./2026-08-22-admin-auth.md): 관리자 웹 인증·인가
- [`2026-08-24-refund-lifecycle.md`](./2026-08-24-refund-lifecycle.md): 환불 수명주기와 분쟁 종결 상태 개편
- [`2026-08-25-admin-user-list-api.md`](./2026-08-25-admin-user-list-api.md): 관리자 사용자 목록 조회 API
- [`2026-08-27-api-security-hardening.md`](./2026-08-27-api-security-hardening.md): CORS 화이트리스트, 평문 HTTP 제거, 보안 응답 헤더, 관리자 로그인 잠금, staging 문서 접근 제한
- [`2026-08-27-admin-ops-alert.md`](./2026-08-27-admin-ops-alert.md): 분쟁 접수·미션 완료 시 관리자에게 Slack 운영 알림 발송
- [`2026-11-14-tdd-harness.md`](./2026-11-14-tdd-harness.md): 저장소 전체 TDD 하네스(규칙·검증 스크립트·PR 검증) 도입, 첫 적용 기능은 채팅
- [`2026-11-18-nginx-recreate-on-config-change.md`](./2026-11-18-nginx-recreate-on-config-change.md): 배포 때 nginx 설정이 바뀌었으면 검사 후 다시 만들기(staging·production 공통 스크립트)

## 운영 규칙

권장 파일명 형식:

- `YYYY-MM-DD-short-title.md`

계획이 완료되거나 중단되면 `../completed/`로 옮기고 관련 트래커를 함께 갱신한다.
