# 환불 수명주기와 분쟁 종결 상태 개편

작성일: 2026-08-24 · 상태: 구현·MySQL 통합 검증·문서 갱신 완료

## 목표

- 분쟁 판정 결과를 요청·지원의 완료/취소 상태에 직접 반영한다.
- 입금 확인 후 매칭 전 취소를 관리자 환불 처리 대상으로 만든다.
- 환불 원인을 코드와 상세 사유로 구분해 응답한다.

## 범위

- Proposal에 `REFUND_PENDING`, `REFUNDED` 상태 추가
- Refund 영속 모델과 마이그레이션 추가
- 앱 취소, 관리자 취소, 분쟁 판정, 환불 완료 전이 통합
- Proposal/Offer `RESOLVED`, Mission `REFUNDED`, 환불 반려 제거
- 관리자 환불 목록·상세·집계 계약 변경
- 도메인/미션 스펙과 OpenAPI 예시 및 통합 테스트 갱신

## 비범위

- PG 자동 환불
- 부분 환불
- 앱의 취소 사유 입력 UI

## 작업 분해

1. 상태 및 Refund 모델과 마이그레이션을 추가한다.
2. 세 환불 생성 경로를 Refund 서비스로 통합한다.
3. 관리자 환불 API를 Refund 정본 조회로 변경한다.
4. 레거시 Mission 환불 API와 환불 전용 상태·컬럼을 제거한다.
5. 통합/OpenAPI 테스트와 기준 문서를 갱신한다.

## 검증 전략

- 분쟁 `COMPLETED`/`FAILED` 각각 Proposal·Offer·Mission 상태를 검증한다.
- `HOLDING` 취소는 환불 없음, `POSTED`/`OFFERED` 취소는 환불 생성을 검증한다.
- 세 환불 원인의 `reason`/`reasonDetail` 응답을 검증한다.
- 환불 완료 후 Proposal은 `REFUNDED`, Mission은 `FAILED` 유지임을 검증한다.
- MySQL 테스트 DB에서 관련 통합 테스트와 OpenAPI 계약 테스트를 실행한다.

## 롤백 메모

Refund 테이블 제거 전 백필된 처리 결과를 확인한다. 새 Proposal
상태는 롤백 시 Mission 결과에 따라 기존 `RESOLVED` 또는 `CANCELLED`로 되돌린다.

## 남은 리스크

- 관리자 프론트와 앱이 새 Proposal 상태 및 환불 ID 의미 변경을 함께 반영해야 한다.

## 현재 검증 결과

- OpenAPI·오류 계약·설정·환불 도메인 테스트 50건 통과
- 로컬 MySQL 9.7(`orderrun_test`)에서 전체 실행: 283 passed, 7 failed
- 실패 7건 중 6건은 이번 개편 이전(`d3d1309`)에도 같은 방식으로 실패하는 기존 부채다.
  분쟁 관련 5건은 `factory.execution()`이 미션을 만들지 않아 분쟁 접수가
  `MISSION_NOT_FOUND`(404)로 끊기고, `test_create_proposal_validation_errors`는 정산 계좌가
  없어 409로 끊긴다.
- 나머지 1건 `test_withdraw_user_rolls_back_all_changes_when_anonymization_fails`는 이번
  개편으로 새로 깨졌다. fixture가 `OFFERED` 요청을 만드는데 입금 확인된 `POSTED`/`OFFERED`가
  탈퇴 차단 상태가 되면서, 롤백 경로에 도달하기 전에 `USER_WITHDRAWAL_BLOCKED`로 막힌다.
  제품 정책은 의도한 대로 동작하며 fixture 상태를 `HOLDING`으로 바꾸면 해소된다.
- Alembic 왕복 검증(`0026` upgrade/downgrade)은 아직 남아 있다.

## 문서 갱신 (2026-08-24)

- `docs/domain.md`: 관리자 취소 전이, Mission 상태·전이·세 축 대응표, Refund 전이표 추가
- `docs/product-specs/mission.md`: 관리자 요청 취소로 인한 `미션 실패` 경로 반영
- `docs/design-docs/refund-lifecycle.md`: 매칭 후 관리자 취소 절 추가
- `docs/api-spec/README.md`: 관리자 웹 엔드포인트 13개와 Mission/Refund/Dispute enum 표 추가
- `docs/domains/*`: 요청·지원·관리자 도메인 책임과 테스트 보장 범위 갱신
- `docs/domains/user-auth/withdrawal-policy.md`: 차단 기준을 Refund `PENDING` 기준으로 정정
- `docs/exec-plans/active/2026-08-18-list-sort-order.md`: 취소 배지 매핑에서 `RESOLVED` 제거
- `ARCHITECTURE.md`, `CLAUDE.md`, `docs/FRONTEND.md`: 핵심 엔티티와 상태 목록 갱신
- [요청·지원·미션 상태 지도](https://claude.ai/code/artifact/bf76f755-a2be-4ac9-b9be-71733dc73f1b)
  아티팩트를 새 상태로 갱신
