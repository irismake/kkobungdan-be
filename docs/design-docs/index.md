# 설계 문서 인덱스

## 목적

이 폴더는 백엔드의 기술 설계와 장기적으로 유지할 의사결정 근거를 담는다.

## 현재 문서

- [`core-beliefs.md`](./core-beliefs.md): 아키텍처 선택을 이끄는 핵심 신념
- [`object-oriented-principles.md`](./object-oriented-principles.md): 객체지향 설계 원칙과 Python 적용 기준
- [`user-service-boundaries.md`](./user-service-boundaries.md): 인증, 프로필, 전화번호 검증, 회원 탈퇴 서비스의 책임과 트랜잭션 경계
- [`persistence-schema-canonicalization.md`](./persistence-schema-canonicalization.md): 전체 영속성 스키마 정본화와 현재 구현 갭
- [`testing-conventions.md`](./testing-conventions.md): pytest 통합 테스트 작성 규칙 (이름, GWT 구조, 중복 방지)
- [`api-router-organization.md`](./api-router-organization.md): API 라우터의 도메인 패키지, 명명, 버전별 조립 원칙
- [`refund-lifecycle.md`](./refund-lifecycle.md): 환불 정본 테이블과 분쟁 종결·취소 상태 전이 결정
- [`tdd-workflow.md`](./tdd-workflow.md): 저장소 전체 TDD 개발 흐름과 문서·테스트 연결 규칙 (초안)
- [`outbox.md`](./outbox.md): 공통 Transactional Outbox 설계. 기록·발행·전달 처리·재시도·DEAD·재처리·정리, Kafka 확장 (구현됨)
- [`chat-architecture.md`](./chat-architecture.md): 채팅 서버 구성(WebSocket 수신·REST 전송), 데이터 모델, 모듈·의존성 규칙 (설계 확정, 구현 전)
- [`../api-spec/README.md`](../api-spec/README.md): 외부 API 요청/응답 계약 정본
- [`../domain.md`](../domain.md): 도메인 상태와 정책 정본

## 다음 후보 문서

- 인증 전략
- 결제 제공자 추상화
- 운영 감사 로그
- 백그라운드 작업과 비동기 처리
