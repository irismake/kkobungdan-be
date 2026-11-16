# 제품 스펙 인덱스

## 목적

이 폴더는 사용자 관점의 행동, 화면 간 흐름, 완료 조건을 정의한다.
제품 스펙은 구현 정본이 아니라 제품 의도와 사용자 기대 행동의 기준이다.

## 책임 경계

- 사용자 문제, 기대 행동, 완료 조건, 제품 정책을 기록한다.
- API 요청/응답 필드와 에러 코드는 [`../api-spec/README.md`](../api-spec/README.md)를 우선한다.
- 상태 전이와 도메인 정책은 [`../domain.md`](../domain.md)를 우선한다.
- 도메인별 개념과 테스트 보장 범위는 [`../domains/README.md`](../domains/README.md)를 우선한다.
- 영속성 구조에서 파생된 스키마 스냅샷은 [`../generated/db-schema.md`](../generated/db-schema.md)에 둔다.

## 현재 스펙

- [`new-user-onboarding.md`](./new-user-onboarding.md): 첫 세션 계정 생성과 초기 활성화 흐름
- [`notification-policy.md`](./notification-policy.md): 알림 발송 조건과 이벤트별 정책
- [`error-copy-policy.md`](./error-copy-policy.md): 에러 문구와 노출 상황, 문구 변경 절차
- [`proposal-reporting.md`](./proposal-reporting.md): 공개 요청 게시글 신고와 관리자 검토 흐름
- [`production-demo-login.md`](./production-demo-login.md): 실제 SMS 인증번호와 운영 검수용 로그인 데모 정책
- [`mission.md`](./mission.md): 수락된 지원의 수행 단위와 관리자 정산·환불 상태 흐름

## 예정 스펙

- 요청서 생성과 공개
- 지원 등록과 수락
- 수락된 Offer 기반 수행 완료
- 결제 확정과 환불 처리
