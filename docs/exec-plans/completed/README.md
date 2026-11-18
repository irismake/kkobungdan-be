# 완료된 계획

이 디렉터리에는 완료되었거나 보관용으로 전환된 실행 계획을 둔다.

완료 문서에는 최소한 아래 정보를 남긴다.

- 원래 목표
- 실제 반영 내용
- 검증 근거
- 남은 리스크 또는 후속 부채

## 현재 보관 항목

- [`user-auth/`](./user-auth/): User/Auth 마이그레이션 기준 문서 묶음
- [`proposal/`](./proposal/): Proposal 마이그레이션 기준 문서 묶음
- [`terms-agreement/`](./terms-agreement/): Terms Agreement 마이그레이션 기준 문서 묶음
- [`2026-07-01-user-service-responsibility-refactor.md`](./2026-07-01-user-service-responsibility-refactor.md): 사용자 인증·프로필·탈퇴 서비스 책임 분리
- [`2026-07-01-api-router-domain-packages.md`](./2026-07-01-api-router-domain-packages.md): API 라우터 도메인 패키지화와 버전별 조립
- [`2026-08-16-verification-send-rate-limit.md`](./2026-08-16-verification-send-rate-limit.md): 인증번호 재발송 5분 대기 제거와 5분당 3회 발송 제한 전환
- [`2026-08-16-payment-expired-cancel-notification.md`](./2026-08-16-payment-expired-cancel-notification.md): 24시간 미입금 자동 취소 시 요청자 알림 발송
- [`2026-08-16-missing-payment-match-notifications.md`](./2026-08-16-missing-payment-match-notifications.md): 입금 확인·미션 시작·입금 독촉 알림 3건 구현
- [`2026-08-18-notification-copy-revision.md`](./2026-08-18-notification-copy-revision.md): 알림 문구 개정(행님/꼬붕 호칭, 수행비 표기) 반영
- [`2026-08-20-error-code-client-mapping.md`](./2026-08-20-error-code-client-mapping.md): 에러 응답 봉투 전면 적용, 메시지 한국어화·용어 통일, 클라이언트 매핑 문서화
- [`2026-08-20-login-send-user-not-found.md`](./2026-08-20-login-send-user-not-found.md): 로그인 인증번호 발송의 미가입 번호 응답을 401 `INVALID_CREDENTIALS`에서 404 `USER_NOT_FOUND`로 전환
- [`2026-08-22-mission-entity.md`](./2026-08-22-mission-entity.md): 미션 엔티티 도입과 관리자 분쟁 판정·정산·환불 기록
- [`2026-08-24-admin-response-name-fields.md`](./2026-08-24-admin-response-name-fields.md): 미션·신고 관리자 응답에 행님·꼬붕·신고자 이름 노출
- [`2026-08-24-openapi-nullable-examples.md`](./2026-08-24-openapi-nullable-examples.md): OpenAPI 예시에서 사라지던 nullable 필드 복원
- [`2026-08-26-reason-detail-policy.md`](./2026-08-26-reason-detail-policy.md): 분쟁·신고·탈퇴의 사유 선택을 필수로, 상세 사유는 `기타`에서만 필수로 통일
- [`2026-08-26-seed-dispute-survey-questions.md`](./2026-08-26-seed-dispute-survey-questions.md): 분쟁 사유 문항을 신고·탈퇴처럼 마이그레이션으로 시드하고 `requires_detail`을 코드 정본으로 고정
- [`2026-08-26-replace-mysql-enums-with-varchar.md`](./2026-08-26-replace-mysql-enums-with-varchar.md): MySQL native ENUM 컬럼 6개를 VARCHAR로 전환하고, 열거형 컬럼 11개를 non-native Enum 매핑 + 이름 붙인 `CHECK` 제약으로 통일
- [`2026-08-27-withdrawal-open-obligation-rule.md`](./2026-08-27-withdrawal-open-obligation-rule.md): 탈퇴 차단 조건을 종결 상태 화이트리스트 기반 미결 판정 하나로 통일하고 `HOLDING` 자동 취소 제거
- [`2026-08-27-fcm-token-dedup.md`](./2026-08-27-fcm-token-dedup.md): 여러 계정이 같은 FCM 토큰을 공유해 알림이 엉뚱한 기기로 가는 문제 정리 — 로그인 시 dedupe, 로그아웃 시 토큰 삭제, `fcm_token_hash` unique 제약 추가
- [`2026-09-29-rds-to-ec2-mysql.md`](./2026-09-29-rds-to-ec2-mysql.md): RDS를 걷어내고 STAGING·PROD DB를 같은 EC2의 MySQL 컨테이너(별도 compose `orderrun-db`)로 이전, 매시/일일 S3 백업, Docker Hub namespace `orderrun` 전환
- [`2026-11-18-notification-chat-unification.md`](./2026-11-18-notification-chat-unification.md): 지원 전은 요청 상세로 가는 푸시 알림, 지원 후는 채팅방으로 가는 시스템 채팅으로 전달 통합
- [`2026-11-18-nginx-recreate-on-config-change.md`](./2026-11-18-nginx-recreate-on-config-change.md): 배포 때 nginx 설정이 바뀌었으면 `nginx -t` 검사 후 다시 만들기, ssh heredoc stdin 문제 수정
