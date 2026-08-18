# 홈/내 활동 목록 정렬 정책

## 목표

홈 화면과 내 활동 화면의 목록 정렬을 화면 요구사항에 맞춘다.

- 홈 화면(`GET /api/v1/proposal`): 가장 최신 게시글이 최상단
- 내 활동 - 요청(`GET /api/v1/proposal/own`): 배지 순 → 같은 배지 안에서 최신순
- 내 활동 - 수행 기록(`GET /api/v1/offer/own`): 배지 순 → 같은 배지 안에서 최신순

## 배경

세 목록 모두 `deadline ASC, created_at DESC, id DESC` 또는 `created_at DESC, id DESC`로만 정렬되어 있다.

- 홈은 마감이 임박한 순(`deadline ASC`)이라 방금 올라온 글이 하단에 묻힌다.
- 내 활동은 배지(상태 그룹) 개념 자체가 정렬에 반영되어 있지 않아, 전체 탭에서 취소/완료 건이 진행 중인 건보다 위에 올 수 있다.

배지는 클라이언트가 `status` 쿼리 파라미터로 필터링하는 단위이며, 서버에는 그 그룹 개념이 없었다.

## 범위

- `ProposalService.search_proposals` 정렬을 `created_at DESC, id DESC`로 변경
- `ProposalService.search_owner_proposals`에 배지 순 정렬 추가
- `OfferService.search_runner_offers`에 배지 순 정렬 추가
- 배지 ↔ 상태 매핑을 서버 상수로 정의
- 정렬 회귀 테스트 추가

## 비범위

- 배지 필드를 응답에 노출하는 것 (클라이언트가 status로 이미 판별)
- 배지별 건수 집계 API
- 페이지네이션/필터 계약 변경

## 배지 ↔ 상태 매핑

### 요청 (Proposal)

| 순서 | 배지 | ProposalStatus |
|---|---|---|
| 1 | 미입금 | `HOLDING` |
| 2 | 대기중 | `POSTED`, `OFFERED` |
| 3 | 진행중 | `MATCHED`, `ORDER_COMPLETED` |
| 4 | 분쟁중 | `DISPUTED` |
| 5 | 완료 | `ALL_COMPLETED` |
| 6 | 취소 | `CANCELLED`, `REPORTED`, `RESOLVED` |

`REPORTED`(관리자 신고 승인)와 `RESOLVED`(분쟁 해결)는 별도 배지가 없어 취소 그룹으로 묶는다.
`RESOLVED`는 분쟁 처리로 종결된 건이라 정상 완료(`ALL_COMPLETED`)와 구분해 취소에 넣는다.

### 수행 기록 (Offer)

| 순서 | 배지 | OfferStatus |
|---|---|---|
| 1 | 대기중 | `WAITING` |
| 2 | 진행중 | `ACCEPTED`, `RUNNER_COMPLETED` |
| 3 | 분쟁중 | `DISPUTED` |
| 4 | 완료 | `ALL_COMPLETED` |
| 5 | 취소 | `REJECTED`, `CANCELLED`, `RESOLVED` |

## 정렬 규칙

| 목록 | ORDER BY |
|---|---|
| 홈 | `created_at DESC, id DESC` |
| 내 요청 | `badge_rank ASC, created_at DESC, id DESC` |
| 수행 기록 | `badge_rank ASC, created_at DESC, id DESC` |

`badge_rank`는 SQL `CASE` 식으로 계산한다. 매핑에 없는 상태는 맨 뒤로 보낸다.
"최신순"은 `created_at` 기준이며, 동시각 충돌은 `id DESC`로 깬다.

## 작업 분해

1. `ProposalService`에 `PROPOSAL_BADGE_ORDER`와 `_proposal_badge_rank()` 추가
2. `search_proposals` 정렬 변경
3. `search_owner_proposals` 정렬 변경
4. `OfferService`에 `OFFER_BADGE_ORDER`와 `_offer_badge_rank()` 추가
5. `search_runner_offers` 정렬 변경
6. `tests/test_proposal_integration.py`, `tests/test_offer_integration.py`에 정렬 테스트 추가

## 검증

- 홈 목록에서 나중에 만든 Proposal이 먼저 오는지 확인
- 내 요청 목록에서 배지 순서대로 정렬되고, 같은 배지 안에서는 최신순인지 확인
- 수행 기록 목록에서 동일 조건 확인
- `pytest tests/test_proposal_integration.py tests/test_offer_integration.py`

## 상태

- [x] 구현
- [x] 테스트 작성
- [x] 테스트 실행 — MySQL 9.7 로컬 인스턴스에서 전체 169개 통과
- [x] 문서 갱신 (`docs/api-spec/README.md`)

### 테스트 작성 시 주의

정렬 테스트를 배지 역순으로 생성하면 "최신순"과 배지 순서가 일치해 버려서,
정렬을 고치지 않아도 통과한다. 실제로 처음 작성한 테스트가 이 함정에 빠졌다.
그래서 두 테스트 모두 다음을 지킨다.

- 생성 순서를 배지 순서와 어긋나게 섞는다.
- `created_at`을 명시적으로 지정하되, 일부 쌍은 id 순서와 반대로 둔다
  (id 타이브레이크가 아니라 `created_at`이 최신순을 결정하는지 확인).
- Proposal 테스트는 `deadline`을 전부 같은 값으로 맞춰 정렬에 끼어들지 못하게 한다.

검증 방법: 서비스 코드만 되돌린 상태에서 네 테스트가 모두 실패하는지 확인했다.
