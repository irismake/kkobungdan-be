# 채팅 요구사항

> 상태: 초안 (뼈대만 작성됨)
> 관련 문서: [`../design-docs/chat-architecture.md`](../design-docs/chat-architecture.md), [`../exec-plans/active/2026-11-14-tdd-harness.md`](../exec-plans/active/2026-11-14-tdd-harness.md)

## 목적

<!-- 채팅 기능이 해결하려는 사용자 문제를 적는다. -->

## 범위

### 포함

- TODO

### 제외

- TODO

## 사용자와 권한

<!-- 누가 채팅방을 열고 메시지를 주고받을 수 있는지 (주문자/러너/관리자), Proposal·Offer·Mission 상태와의 관계 -->

| 역할 | 할 수 있는 일 | 할 수 없는 일 |
|------|---------------|---------------|
| 주문자 | TODO | TODO |
| 러너 | TODO | TODO |
| 관리자 | TODO | TODO |

## 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| CHAT-REQ-001 | TODO | TODO |

## 비기능 요구사항

- 성능: TODO
- 신뢰성 (메시지 유실·중복·순서): TODO
- 보안 (참여자 외 접근 차단, 개인정보): TODO

## 테스트 시나리오

각 시나리오는 테스트와 1:1로 연결한다. 연결 방식은 [`../design-docs/tdd-workflow.md`](../design-docs/tdd-workflow.md)를 따른다.

| ID | 요구사항 | 시나리오 (Given / When / Then) | 종류 | 테스트 위치 |
|----|----------|-------------------------------|------|-------------|
| CHAT-TS-001 | CHAT-REQ-001 | TODO | unit | `tests/test_chat_service.py` |
| CHAT-TS-002 | CHAT-REQ-001 | TODO | integration | `tests/test_chat_integration.py` |

## 완료 조건

- [ ] 모든 기능 요구사항에 테스트 시나리오가 연결되어 있다.
- [ ] 모든 테스트 시나리오가 `scripts/verify.sh`에서 통과한다.

## 미결정 사항

- TODO
