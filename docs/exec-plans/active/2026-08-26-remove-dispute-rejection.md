# 분쟁 반려 제거

작성일: 2026-08-26 · 상태: 구현·MySQL 통합 검증·문서 갱신 완료

## 배경

`POST /v1/admin/dispute/{disputeId}/reject`는 `DisputeEvidence.status`만 `REJECTED`로 바꾸고
Proposal·Offer·Mission은 건드리지 않았다. 그래서 반려된 분쟁은 어느 경로로도 종결되지
않았다.

- `resolve_dispute`는 `PENDING` 증빙만 받으므로 재판정할 수 없다
- 관리자 요청 취소는 `DISPUTED`를 취소 가능 상태에 넣지 않아 취소할 수 없다
- `raise_dispute`는 `MATCHED`/`ORDER_COMPLETED`에서만 되므로 재접수할 수 없다

즉 반려하면 요청이 `DISPUTED`에 영구히 갇히고, 행님도 꼬붕도 정산을 받지 못한 채 돈이
회사에 남는다.

## 결정 내용

반려를 없앤다. 관리자가 분쟁에서 내릴 수 있는 결론은 꼬붕 책임(`FAILED`, 행님 환불)과 행님
책임(`COMPLETED`, 꼬붕 수행비 지급) 둘뿐이다. "증빙 부족"은 결론이 아니라 판단 보류이고,
보류는 증빙을 더 받아 결국 둘 중 하나로 가야 한다. 보류 상태는 `PENDING`이 이미 표현한다.

- `DisputeProcessStatus.REJECTED`와 `mark_rejected()` 제거
- `AdminCommandService.reject_dispute`와 반려 엔드포인트 제거
- 기존 `REJECTED` 데이터는 결론이 나지 않은 건이므로 `PENDING`으로 되돌린다.
  `resolved_at`과 `resolved_by_admin_id`도 함께 비운다

반려에 "분쟁 사유 불인정 = 정상 완료"라는 의미를 주는 방안도 검토했으나, 결과가
`resolve(COMPLETED)`와 같아져 따로 둘 이유가 없어 제외했다.

## 작업 항목

1. `DisputeProcessStatus`에서 `REJECTED` 제거, `mark_rejected()` 삭제
2. 서비스·라우터·OpenAPI 예시에서 반려 경로 삭제
3. Alembic `0032`: `REJECTED` 데이터를 `PENDING`으로 되돌리고 CHECK 제약 갱신
4. 문서 갱신: `domain.md`, `product-specs/mission.md`, `api-spec/README.md`,
   `generated/db-schema.md`
5. 반려 통합 테스트 제거

## 검증 기준

- `DisputeProcessStatus`에 `REJECTED`가 없다
- `POST /v1/admin/dispute/{id}/reject`가 404다
- 마이그레이션 후 `dispute_evidences.status` CHECK가 `PENDING`, `RESOLVED`만 허용한다
- 기존 판정 흐름(`resolve`)은 회귀 없이 동작한다

## 남는 문제

`0032` downgrade는 허용값만 되돌리며 `PENDING`으로 바꾼 데이터는 복구하지 않는다. 반려는
결론이 아니었으므로 되돌릴 원본 상태가 의미를 갖지 않는다고 봤다.

관리자 웹의 분쟁 상세에서 반려 버튼을 함께 제거해야 한다. 프론트는 별도 저장소다.
