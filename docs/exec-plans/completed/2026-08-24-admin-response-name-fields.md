# 관리자 응답 계약 분리와 사용자 표시 이름 보정

## 목표

- 앱과 관리자 웹이 wire 필드가 같더라도 서로 다른 응답 DTO를 사용한다.
- 관리자 웹에서 사용자 이름이 삭제된 경우 `"탈퇴한 사용자"`로 표시한다.
- 분쟁과 미션의 연결, 요청 생성과 환불 계좌의 관계를 DB·서비스 수준에서 보강한다.

## 배경

기존에는 앱 신고와 관리자 신고가 `ProposalReportResponse`를 공유했고, 관리자 입금 확인도 앱의
`ProposalResponse`를 사용했다. 필드가 같아도 한쪽 변경이 다른 클라이언트 계약에 영향을 줄 수 있다.
또한 탈퇴 시 이름이 삭제되기 때문에 관리자 응답에 `null`이 노출됐으며, 분쟁은 미션을 조회 시점에
간접 탐색해 `missionId`가 없을 수 있었다.

## 범위와 비범위

- 범위: 관리자 전용 Proposal/신고 DTO, 관리자 이름 표시 보정, 분쟁-Mission FK,
  Mission 정산 상태, 요청 생성 전 계좌 검증, OpenAPI·테스트·문서.
- 비범위: 기존 앱 `ProposalResponse`와 `ProposalReportResponse` 변경, 기존 계좌 데이터 임의 생성.

## 결정

- 당사자가 반드시 존재하는 관리자 이름 필드는 non-null 문자열로 선언한다.
- 관리자 서비스는 이름이 null이거나 사용자 row가 없으면 `"탈퇴한 사용자"`를 반환한다.
- 연관 대상 자체가 없을 수 있는 `acceptedRunnerName`만 nullable로 유지한다.
- `AdminProposalResponse`, `AdminProposalReportResponse`는 앱 DTO와 wire 필드만 같고 타입은 공유하지 않는다.
- `AdminDisputeSummaryResponse.missionId`는 DB의 NOT NULL FK에 맞춰 필수다.
- 목록 조회는 N+1을 만들지 않도록 ID를 모아 한 번에 조회한다.

## 작업

1. 관리자 전용 `AdminProposalResponse`, `AdminProposalReportResponse`를 추가하고 관리자 라우터만 사용한다.
2. 관리자 사용자 이름 조회를 공통화하고 삭제된 이름을 표시 문자열로 보정한다.
3. `dispute_evidences.mission_id`를 기존 staging 데이터 백필 후 NOT NULL FK로 전환한다.
4. Proposal/Offer 분쟁 생성 시 Mission ID를 직접 저장한다.
5. Proposal 생성 전에 행님의 SettlementAccount 존재를 검증한다.
6. 미결 환불·지급이 있으면 계좌 삭제를 동반하는 회원 탈퇴를 차단한다.
7. Offer 생성 전에 러너의 SettlementAccount 존재를 검증한다.
8. `MissionResponse.settlementStatus`를 추가하고 지급 목록에서 `AdminPayoutSummaryResponse`를 제거한다.

## 검증

- `pytest tests/test_openapi.py`
- MySQL 통합 테스트: proposal, proposal-report, mission, admin-web, user-auth 범위.
- staging 배포 전 `0025_link_disputes_to_missions` 백필 결과와 미연결 분쟁 0건을 확인한다.

## 검증 결과

- OpenAPI 계약 및 ORM 모델 테스트 23개 통과.
- `compileall`과 `git diff --check` 통과.
- 관련 MySQL 통합 테스트 145개 수집 성공.
- 현재 실행 환경에는 Docker 명령이 없고 `127.0.0.1:3307` MySQL도 실행 중이지 않아 통합 테스트와
  실제 migration 적용은 실행하지 못했다. 코드 실패가 아니라 테스트 DB 연결 거부다.
- staging DB는 `0024_add_user_admin_columns` 상태이며 분쟁 10건, 미션 25건이 있다. 분쟁 10건 모두
  `offer_id`로 미션을 찾을 수 있고 미연결 건은 0건이다. 현재 `mission_id` 컬럼은 아직 없다.

## 남은 리스크

- staging에 `offer_id`와 연결되는 Mission이 없는 분쟁이 있으면 마이그레이션은 의도적으로 중단한다.
  해당 데이터는 임의 값을 만들 수 없으므로 실제 Offer/Mission 관계를 확인해 먼저 복구한다.
- 레거시 Proposal은 계좌 선등록 규칙 도입 전에 생성됐을 수 있어 관리자 환불 상세 계좌 필드는 당분간
  nullable을 유지한다. staging 정리와 운영 규칙 검증 후 별도 변경으로 non-null 계약을 검토한다.

## 상태

- 완료
