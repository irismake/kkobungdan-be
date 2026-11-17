# 채팅 요구사항

> 상태: 초안 (뼈대만 작성됨)
> 관련 문서: [`../domains/chat/test-scenarios.md`](../domains/chat/test-scenarios.md), [`../design-docs/chat-architecture.md`](../design-docs/chat-architecture.md), [`../exec-plans/active/2026-11-14-tdd-harness.md`](../exec-plans/active/2026-11-14-tdd-harness.md)

## 목적

<!-- 채팅 기능이 해결하려는 사용자 문제를 적는다. -->

## 범위

### 포함

- TODO

### 제외

- TODO

## 사용자와 권한

<!-- 누가 채팅방을 열고 채팅을 주고받을 수 있는지 (행님/꼬붕/관리자), 요청(Proposal)·지원(Offer)·임무(Mission) 상태와의 관계 -->

| 역할 | 할 수 있는 일 | 할 수 없는 일 |
|------|---------------|---------------|
| 행님 | TODO | TODO |
| 꼬붕 | TODO | TODO |
| 관리자 | TODO | TODO |

## 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| CHAT-REQ-001 | TODO | TODO |

## 비기능 요구사항

- 성능: TODO
- 신뢰성 (채팅 유실·중복·순서): TODO
- 보안 (참여자 외 접근 차단, 개인정보): TODO

## 테스트 시나리오

테스트 시나리오(`CHAT-TS-*`)는 [`../domains/chat/test-scenarios.md`](../domains/chat/test-scenarios.md)에 둔다. 시나리오마다 연결된 요구사항(`CHAT-REQ-*`)을 적는다.

## 완료 조건

- [ ] 모든 기능 요구사항에 [테스트 시나리오](../domains/chat/test-scenarios.md)가 연결되어 있다.
- [ ] 모든 테스트 시나리오가 `scripts/verify.sh`에서 통과한다.

## 미결정 사항

- TODO
