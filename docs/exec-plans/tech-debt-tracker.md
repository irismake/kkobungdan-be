# 기술 부채 트래커

## 목적

현재 작업을 막지는 않지만 실제로 추적할 가치가 있는 부채를 기록한다.

## 현재 항목

| ID | 영역 | 부채 내용 | 영향 | 다음 단계 |
| --- | --- | --- | --- | --- |
| TD-001 | 인증 | 현재 부트스트랩 방향에서 최종 인증 흐름이 아직 placeholder 수준이다. | 권한 버그와 약한 연동 계약 위험 | 인증 전략 설계 문서와 실행 계획 작성 |
| TD-002 | 결제 | 결제 생명주기는 문서화되었지만 코드에는 구현되지 않았다. | 핵심 루프에서 상태 불일치 위험 | 구현 전 API와 스키마 가정 확정 |
| TD-003 | 테스트 | 도메인 상태 전이에 대한 회귀 검증이 부족하다. | 리팩터링 안전성이 낮아짐 | 서비스 및 API 수준 전이 테스트 추가 |
| TD-004 | 문서 | 기존 아키텍처 문서와 새 하네스 문서는 계속 정렬돼야 한다. | 결정 드리프트 발생 가능 | 모델 변경 시 생성 스키마와 인덱스 갱신 |
| TD-005 | 인프라 | staging 배포 workflow, Dockerfile, EC2 compose flow는 FastAPI env 계약과 계속 정렬돼야 한다. | 배포 실패와 환경 불일치 위험 | env template와 deploy script를 설정 변경 시 함께 갱신 |
| TD-006 | 인증 | 인증번호 발송 제한이 휴대폰 번호 단위라 번호를 바꿔가며 반복 요청하는 남용은 막지 못한다. 클라이언트는 제거된 409 `PHONE_VERIFICATION_ALREADY_SENT` 대신 429 `PHONE_VERIFICATION_SEND_RATE_LIMITED`를 처리해야 한다. | SMS 비용 증가, 앱의 구 에러 코드 처리 미갱신 시 재발송 UX 오작동 | 클라이언트 429 대응 확인 후 IP 기준 제한 도입 검토 |
| TD-007 | 알림 | 시간 기반 알림이 APScheduler 1시간 주기에 묶여 있어 미입금 취소 알림이 최대 1시간 지연된다. 30분 입금 독촉과 만료 전 사전 예고 알림은 아직 미구현이다. | 사용자가 취소 사실을 늦게 인지, 입금 전환율 개선 기회 손실 | 스케줄러 주기 조정 검토, 30분 독촉 알림을 별도 계획으로 설계 |
| TD-008 | 알림 | `NotificationType` 열거형에 코드 참조가 없는 멤버가 남아 있다 (`SYSTEM_ANNOUNCEMENT`, `EXECUTION_STARTED`, `PAYMENT_FAILED` 등). 죽은 디스패처 메서드를 제거하며 참조가 사라졌지만, `notifications.notification_type` 컬럼에 기존 레코드 값이 있을 수 있어 열거형은 그대로 두었다. | 실제로 쓰이는 알림 종류를 코드만 보고 판단하기 어렵다 | 운영 DB에서 각 값의 레코드 수를 확인한 뒤 미사용 멤버 제거 계획 수립 |
| TD-009 | 스키마 | `offers.open_chat_url`(`0008_add_offer_open_chat_url`)에 값을 쓰는 코드 경로가 없다. 오픈채팅방 링크는 입금 확인 때 `proposals.open_chat_url`에만 저장된다. 읽기 폴백은 제거했지만 컬럼은 남겨 두었다. | 미사용 컬럼이 링크 정본을 헷갈리게 한다 | 운영 DB에서 non-null 레코드가 없음을 확인한 뒤, 꼬붕별 채팅방 요구가 없으면 drop 마이그레이션 작성 |
| TD-011 | 알림 | 관리자 운영 알림(Slack)에 재시도와 영속화가 없다. `SlackAdminAlertSender`가 실패하면 `logger.error`만 남기고 메시지는 사라진다. 처리 대기열의 정본은 관리자 웹 목록(분쟁 `PENDING`, 미션 `COMPLETED`)이라 일 자체는 남지만, webhook이 장시간 죽으면 재촉이 통째로 없어진다. | 분쟁 판정과 수행비 입금이 지연돼도 아무도 모를 수 있다 | Slack 발송 실패 로그의 빈도를 먼저 관측한다. 유의미하면 FCM과 같은 outbox 테이블로 승격하고 APScheduler 재시도에 태운다 |
| TD-012 | 인프라 | 배포 중 마이그레이션이 메타데이터 락을 기다린 원인을 특정하지 못했다. 구 앱의 어느 커넥션이 `user_fcm_tokens`의 MDL을 오래 쥐었는지 모른다. `2026-08-28-deploy-migration-lock-resilience`로 무한 대기(365일)는 막았지만 경합 자체는 남아 있다. | 락 경합이 잦아지면 배포가 60초 타임아웃으로 반복 실패할 수 있다 | 타임아웃 실패가 재현되면 `information_schema.innodb_trx`로 먼저 본다. `performance_schema`는 t3.micro 메모리 때문에 꺼 두었으므로(`mysql/conf.d/orderrun.cnf`), `metadata_locks` 추적이 필요하면 잠시 ON으로 바꿔 MySQL을 재시작한다. 잦으면 배포 중 트래픽 차단이나 온라인 DDL 도구를 검토한다 (무한 대기로 되돌리지는 않는다) |
| TD-013 | 인프라 | 앱과 DB가 EC2 한 대에 있다(`2026-09-29-rds-to-ec2-mysql`). EC2가 멈추면 PROD·STAGING과 DB가 같이 멈추고, EBS를 잃으면 마지막 S3 백업 이후 데이터가 사라진다. | 복구 목표가 PROD 약 1시간, STAGING 24시간이다. RDS의 5분 단위 시점 복구보다 약하다 | EBS 일일 스냅샷(DLM) 추가를 검토한다. 실사용자가 늘면 백업 주기 단축이나 호스트 분리를 다시 판단한다 |
| TD-014 | 배포 | GitHub Free(private) 플랜이라 Environment 승인자와 브랜치 보호를 쓸 수 없다. `main` merge가 승인 없는 PROD 자동 배포이고, repository 수준 PROD Secret은 어느 브랜치의 워크플로에서도 읽을 수 있다. | 실수 merge가 곧 운영 배포가 되고, 쓰기 권한자는 PROD Secret을 꺼낼 수 있다 | production 워크플로를 수동 실행(`workflow_dispatch`) 전용으로 바꾸는 안과, PROD Secret을 production Environment로 옮기는 안의 플랜 제약을 확인한다 |
| TD-016 | 테스트 | 테스트 compose는 MySQL 8.0 기본(엄격 `sql_mode`)이고, 운영은 8.4.8에 `NO_ENGINE_SUBSTITUTION`(비엄격)이다. | 테스트에서 통과해도 운영에서 동작이 다를 수 있다(반대도 마찬가지) | `docker-compose.test.yml`을 운영 버전·`sql_mode`에 맞추고 `pytest`로 확인한다 |
| TD-017 | 인프라 | 배포 마이그레이션이 앱 계정으로 돈다. 그래서 앱 계정이 DDL(CREATE/ALTER/DROP) 권한을 가진다. | 앱이 뚫리면 스키마까지 바꿀 수 있다 | 마이그레이션 전용 계정을 두고 앱 계정은 DML만 남기는 안을 설계한다(`deploy.sh`, compose env 변경 필요) |
| TD-018 | 운영 | RDS 이전 뒤 남은 정리: Docker Hub의 옛 `hwangdaesun/orderrun` 저장소(개인 계정이라 계정 소유자가 삭제). 월간 복원 테스트도 아직 수동이다. | 필요 없는 이미지가 남는다. 복원 테스트를 잊을 수 있다 | 계정 소유자가 옛 저장소를 지운다. 복원 테스트를 timer로 자동화할지 결정한다 |
| TD-019 | 인프라 | 비용 때문에 t3.micro(메모리 909MiB)에서 앱 2개·MySQL·nginx를 같이 돌린다. MySQL을 경량 설정(buffer pool 64M, `performance_schema` OFF, 상한 512MiB)으로 줄여 여유는 약 300MiB이고, 안 쓰는 메모리는 swap(2GB)으로 넘긴다. | 사용자·트래픽이 늘거나 배포가 겹치면 swap이 잦아져 응답이 느려지거나 OOM이 날 수 있다 | `free`, `vmstat`의 si/so, `/proc/pressure/memory`를 주기적으로 본다. 부족하면 인스턴스 중지 → t3.small로 변경 → 시작(3~5분 중단)으로 되돌린다 |
| TD-020 | 채팅 | 행님·꼬붕 연락 수단인 카카오톡 오픈채팅방을 앱 내 채팅([`chat-requirements.md`](../product-specs/chat-requirements.md))으로 대체하기로 했다. 앱 채팅 배포 전에 제거하면 연락 수단이 없어지므로 배포 후 제거한다. 대상: 관리자 입금 확인 요청의 `openChatUrl`(`AdminConfirmPaymentRequest`), Proposal·Offer·Mission·관리자 응답의 `openChatUrl`, `proposals.open_chat_url`·`offers.open_chat_url` 컬럼(TD-009), API 스펙 문서 | 오픈채팅과 앱 채팅이 함께 남아 연락 수단 정본이 둘이 된다 | 앱 채팅 배포와 앱 전환을 확인한 뒤, 요청·응답 필드와 컬럼을 제거하는 별도 브랜치·마이그레이션을 작성한다 |
| TD-021 | 요청 | 요청의 마감 시각(`proposals.deadline`)은 생성·수정 때 미래인지만 검사한다(`app/models/proposal.py` `_validate_deadline`). 마감이 지나도 요청·지원을 정리하는 스케줄러가 없어, 마감 후에도 지원 등록·수락(매칭)이 가능하고 홈 목록에도 계속 노출된다. 앱 내 채팅도 이 동작을 따르므로 매칭되지 않은 채팅방이 `WAITING`으로 계속 열려 있다([`chat-requirements.md`](../product-specs/chat-requirements.md)). `error-copy-policy.md`의 `PROPOSAL_NOT_OPEN` 설명("이미 마감됐거나")도 실제 동작과 다르다. | 마감이 지난 요청에 지원·매칭·채팅이 이어져 사용자 기대와 어긋난다 | 마감 후 정책(지원 차단, 대기 지원 자동 정리, 목록 제외, 채팅방 종료)을 제품 스펙으로 정한 뒤 별도 계획으로 구현한다 |
| TD-022 | 품질 | 정적 검사가 `compileall`과 시나리오 연결 검사(`scripts/check_scenarios.py`)뿐이다. ruff 같은 린터가 없어 미사용 import, 정의되지 않은 이름 같은 오류를 테스트 실행 전에 잡지 못한다. | 코드 오류가 리뷰나 런타임까지 늦게 드러난다 | ruff를 dev 의존성에 넣고 오류성 규칙(E, F)부터 켠다. 기존 코드 경고를 함께 정리한 뒤 `verify.sh static`에 추가하고 CLAUDE.md의 "린트 미설정" 문구를 고친다 |
| TD-023 | 문서 | 기존 도메인 `test-scenarios.md`의 "보장 범위" 문장 일부가 테스트와 다르다. 예: Proposal 문서는 공개 목록이 마감이 빠른 순이라고 적지만 테스트(`PROPOSAL-TS-002`)는 최신 생성 순을 보장한다. | 문서만 보고 동작을 잘못 이해할 수 있다 | 시나리오 목록 표를 기준으로 각 도메인의 보장 범위 문장을 다시 쓰거나 지운다 |
| TD-024 | 품질 | 비공개 저장소 요금제라 PR 필수 검사(branch protection)를 걸 수 없다. PR의 `CI 결과`가 실패해도 머지 버튼이 눌린다. staging 배포는 배포 전 CI 성공에 묶였지만(`staging-deploy.yml`이 `test.yml`을 먼저 실행), 실패한 코드가 staging 브랜치에 들어가는 것 자체는 막지 못한다. | 깨진 커밋이 staging에 남아 다음 머지까지 배포가 막힐 수 있다 | 머지 전에 `CI 결과`를 직접 확인한다. 요금제를 올리면 `CI 결과` Job을 필수 검사로 지정한다 |
| TD-025 | 환불 | 신고된 게시글은 환불해야 하지만 환불 경로가 없다. 신고 승인(`POSTED/OFFERED -> REPORTED`, `proposal_report_service.py`)은 입금이 확인된 요청에서만 일어나는데 Refund를 만들지 않는다. `RefundReason`에 신고 원인이 없고, 관리자 요청 취소(`admin_command_service.py` `CANCELLABLE_PROPOSAL_STATUSES`)도 `REPORTED`를 대상으로 하지 않아 관리자가 수동으로 환불을 시작할 방법도 없다. 탈퇴 차단 기준(`WITHDRAWAL_TERMINAL_PROPOSAL_STATUSES`)은 `REPORTED`를 종결로 보므로 행님이 환불 계좌를 지우고 탈퇴할 수도 있다. | 입금한 행님이 환불받지 못하고, 환불 이력도 남지 않는다 | 신고 승인 시 Refund를 만들지(원인 추가, CHECK 제약 마이그레이션 포함) 관리자 처리 흐름을 따로 둘지 정한 뒤 `domain.md`·`refund-lifecycle.md`와 함께 별도 계획으로 고친다 |
