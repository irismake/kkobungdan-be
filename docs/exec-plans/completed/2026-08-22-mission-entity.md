# 미션 엔티티 도입

> 이 문서는 2026-08-22 시점의 기록이다. 2026-08-24
> [환불 수명주기 개편](../../design-docs/refund-lifecycle.md)으로 미션 `REFUNDED` 상태와 미션
> 환불 컬럼·API가 제거되고 환불은 별도 Refund 정본으로 옮겨졌다. 현재 상태 정본은
> [`docs/domain.md`](../../domain.md)다.

## 목표

- 수락된 지원 하나에 대응하는 미션 엔티티를 서버에 도입한다.
- 요청과 지원의 상태 변화를 미션 상태에 반영한다.
- 관리자가 분쟁 판정과 지급·환불 기록으로 미션을 종결할 수 있게 한다.

## 범위와 비범위

- 범위: 미션 모델과 마이그레이션, 미션 상태 파생 규칙, 분쟁 해결 판정 API를 미션 기준으로 재정의,
  관리자 미션 조회 API, 지급·환불 여부 기록, 기존 미션 데이터 백필, 테스트, 문서.
- 비범위: 앱 클라이언트 API 노출, 실제 이체·PG 연동, 기한 만료 자동 처리, 신고 기반 강제 종료,
  부분 환불, 분할 지급.

## 가정

- 미션 상태는 `STARTED`, `DISPUTED`, `COMPLETED`, `PAID`, `FAILED`, `REFUNDED` 여섯 개다.
- 미션 완료는 정산 대기를, 미션 실패는 환불 대기를 겸한다.
- 미션은 수락된 지원과 1:1이며 요청당 최대 하나다.
- 수행비 지급액과 환불액은 모두 요청의 `errand_fee` 전액이다. 금액을 관리자가 입력하지 않는다.
- 미션당 지급 또는 환불은 최대 한 건이므로 별도 지급 테이블 없이 미션 컬럼으로 기록한다.
- 분쟁을 거치지 않는 직접 실패 처리 경로는 만들지 않는다.
- 미션 상태는 요청·지원 상태에서 파생하되 미션 테이블에 실체화해 저장한다. 관리자 목록 조회를
  상태로 필터링해야 하므로 조회 시점 계산으로 두지 않는다.
- CLAUDE.md 규칙에 따라 상태 컬럼은 `String(n)`을 사용하고 MySQL ENUM을 쓰지 않는다.

## 완료 작업

1. `app/models/mission.py`에 `MissionStatus` 열거형과 `Mission` 모델을 추가한다.
   - 식별: `id`, `proposal_id`(유니크), `offer_id`(유니크), `orderer_id`, `runner_id`
   - 상태: `status`(String(20)), `errand_fee`
   - 진행 시각: `started_at`, `disputed_at`, `completed_at`, `failed_at`
   - 분쟁 판정: `resolution`(String(20), nullable), `resolved_at`, `resolved_by_admin_id`
   - 지급 여부: `settlement_paid_at`, `settlement_paid_by_admin_id`
   - 환불 여부: `refunded_at`, `refunded_by_admin_id`
   - 공통: `payout_memo`, `created_at`, `updated_at`
   지급 여부는 별도 boolean을 두지 않고 시각 컬럼의 null 여부로 판정한다.
2. Alembic revision `0022_create_missions`를 작성한다. `missions` 테이블을 생성하고,
   기존에 매칭된 요청·지원에 대해 미션을 백필한다. 백필 상태는 현재 요청·지원 상태에서 파생한다.
   기존 데이터에는 지급·환불 기록이 없으므로 관련 시각은 모두 null로 둔다.
3. `app/services/mission/mission_service.py`를 추가한다.
   - `create_for_accepted_offer`: 지원 수락 시 미션 생성
   - `sync_from_offer_and_proposal`: 요청·지원 상태 변화를 미션에 반영
   - `resolve_dispute`: 관리자 판정으로 `COMPLETED` 또는 `FAILED` 전이. 내부에서 기존
     `OfferService.resolve`가 하던 offer·proposal 동시 해결을 수행한다.
   - `record_settlement`: 수행비 지급 기록과 `COMPLETED` → `PAID` 전이
   - `record_refund`: 환불 기록과 `FAILED` → `REFUNDED` 전이
4. 지원 수락 경로(`OfferService`)와 완료·분쟁 전이 경로에 미션 동기화 호출을 연결한다.
5. 분쟁 해결 엔드포인트를 미션 기준으로 옮긴다.
   - 신설: `POST /api/v1/admin/missions/{mission_id}/resolve`, 본문에 판정 결과(`COMPLETED`/`FAILED`) 필수
   - 기존 `POST /api/v1/admin/offer/{offer_id}/resolve`는 제거한다. 관리자 웹 전용이며 앱이
     사용하지 않으므로 deprecated 기간을 두지 않고 관리자 웹과 동시 배포한다.
   - `OfferService.resolve`는 `MissionService.resolve_dispute` 내부 호출로 흡수한다.
6. 관리자 미션 API를 추가한다.
   - `GET /api/v1/admin/missions`: 상태 필터·페이지네이션 목록. 지급 여부와 환불 여부를 함께 반환한다
   - `GET /api/v1/admin/missions/{mission_id}`: 단건 상세
   - `POST /api/v1/admin/missions/{mission_id}/settlement`: 수행비 지급 기록. 금액 입력 없음
   - `POST /api/v1/admin/missions/{mission_id}/refund`: 환불 기록. 금액 입력 없음
7. `tests/test_mission_integration.py`를 추가한다. 생성, 상태 동기화, 분쟁 판정 양쪽 분기,
   지급·환불 기록, 중복 지급 거절, 종료 상태 재전이 거절, 분쟁 없는 실패 처리 거절을 검증한다.
   `tests/test_admin_integration.py`의 `test_resolve_offer_sets_resolved_from_disputed`를
   미션 기준으로 옮긴다.
8. `ARCHITECTURE.md`의 도메인 목록과 `docs/generated/db-schema.md`를 갱신한다.
9. `CLAUDE.md`의 도메인 설명에서 미션을 현재 정의로 정정한다.

## 검증 기준

- 지원 수락 시 미션이 `STARTED`로 생성된다.
- 요청·지원이 `ALL_COMPLETED`가 되면 미션이 `COMPLETED`로 전이한다.
- 요청 또는 지원이 `DISPUTED`가 되면 미션이 `DISPUTED`로 전이한다.
- 분쟁 판정이 `완료`면 `COMPLETED`, `실패`면 `FAILED`로 전이한다.
- 지급 기록 후 `COMPLETED`는 `PAID`로, `FAILED`는 `REFUNDED`로 전이한다.
- 지급·환불 금액을 요청 본문으로 받지 않으며, 기록된 금액은 `errand_fee` 전액이다.
- `COMPLETED`가 아닌 미션의 지급 기록, `FAILED`가 아닌 미션의 환불 기록은 거절된다.
- 이미 지급·환불된 미션의 중복 기록은 거절된다.
- `PAID`, `REFUNDED`에서의 추가 전이 시도는 거절된다.
- 분쟁을 거치지 않은 미션의 실패 처리 시도는 거절된다.
- 미션 목록·상세 응답에 수행비 지급 여부와 환불 여부가 포함된다.
- 백필 후 기존 매칭 건 수와 미션 수가 일치한다.
- 미션 상태 컬럼이 MySQL ENUM이 아닌 `VARCHAR`로 생성된다.
- 앱 API 응답에 미션 필드가 추가되지 않는다.
- 전체 테스트 통과.

## 확정된 결정

- 환불은 입금액 전액이다. 부분 환불은 지원하지 않는다.
- 분쟁을 거치지 않은 직접 실패 처리는 제공하지 않는다.
- 지급·환불 여부는 별도 테이블 없이 미션의 시각 컬럼으로 기록한다.
- 분쟁 해결 엔드포인트는 offer 기준에서 mission 기준으로 이전한다.

## 리스크

- 5번 엔드포인트 이전은 관리자 웹과 동시 배포가 필요하다. 배포 순서가 어긋나면 분쟁 해결이 중단된다.
- 지급·환불을 미션 컬럼으로 기록하므로 재시도나 이체 실패 이력은 남지 않는다.
  이력 추적이 필요해지면 별도 테이블로 분리한다.
- 백필 로직이 요청·지원 상태 조합을 모두 처리하지 못하면 상태가 어긋난 미션이 생길 수 있다.
  백필 후 상태별 건수를 확인한다.

## 검증 결과

- `pytest`: 207개 통과, 실패 0. 미션 통합 테스트 19개 신규 추가.
- `alembic upgrade head`: fresh DB에서 `0022_create_missions`까지 정상 적용. `alembic heads`가 단일 head다.
- `SHOW COLUMNS FROM missions`: `status`와 `resolution`이 `varchar(20)`으로 생성됨을 확인했다.
  MySQL ENUM을 사용하지 않는다.
- 백필 검증: 레거시 데이터를 넣고 `0021` → `0022`를 실제로 적용해 확인했다.
  `ACCEPTED` → `STARTED`, `ALL_COMPLETED` → `COMPLETED`, `DISPUTED` → `DISPUTED`,
  `RESOLVED` → `DISPUTED`로 파생되고 `WAITING`·`REJECTED`·`CANCELLED` 지원은 제외됐다.
  매칭된 지원 4건에 미션 4건이 1:1로 생성됐다.
- OpenAPI: 미션 5개 엔드포인트가 문서화되고 `/v1/admin/offer/{offer_id}/resolve`는 사라졌다.
  전체 에러 코드가 openapi.json에 노출되는지 검사하는 기존 테스트를 통과한다.

## 산출물

- [요청·지원·미션 상태 지도](https://claude.ai/code/artifact/bf76f755-a2be-4ac9-b9be-71733dc73f1b): 세 축의 통합 상태 흐름도, 전이표, 대응표

## 롤아웃 및 롤백 메모

- 배포 시 `0022_create_missions`가 missions 테이블 생성과 기존 매칭 건 백필을 함께 수행한다.
- 관리자 웹과 동시 배포가 필요하다. `POST /v1/admin/offer/{offerId}/resolve`가 제거되어
  구 관리자 웹은 분쟁 해결이 404가 된다.
- 롤백 시 `downgrade`는 missions 테이블을 통째로 삭제하므로 지급·환불 기록도 함께 사라진다.
  운영에서 지급 기록이 쌓인 뒤에는 코드만 롤백하고 마이그레이션은 되돌리지 않는다.

## 남은 리스크

- 백필된 레거시 `RESOLVED` 건은 판정 결과를 알 수 없어 `DISPUTED`로 되돌려 두었다.
  관리자가 다시 완료/실패를 판정해야 지급 방향이 정해진다. 배포 후 해당 건수를 확인한다.
- 지급·환불을 미션 컬럼으로 기록하므로 이체 재시도나 실패 이력은 남지 않는다.
- 관리자 엔드포인트에 인증·인가 의존성이 없다. 기존 관리자 API와 동일한 상태이며
  별도 과제로 다룬다.
- 기한 만료 미션 자동 처리와 신고 기반 강제 종료는 이번 범위에서 제외했다.
