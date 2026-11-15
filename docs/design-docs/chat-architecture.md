# 채팅 아키텍처

> 상태: 초안 (뼈대만 작성됨)
> 관련 문서: [`../product-specs/chat-requirements.md`](../product-specs/chat-requirements.md), [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md)

## 배경

<!-- 왜 이 구조가 필요한지, 어떤 요구사항(CHAT-REQ-*)을 만족해야 하는지 -->

## 서버 구성

<!-- 전송 방식(REST / WebSocket / 폴링 등), 프로세스 구성, 외부 의존(MySQL, 푸시 등) -->

```
TODO: 구성도
```

## 모듈 구성

| 레이어 | 위치 | 책임 |
|--------|------|------|
| API | `app/api/v1/` | TODO |
| Service | `app/services/` | TODO |
| Model | `app/models/` | TODO |
| Schema | `app/schemas/` | TODO |

## 의존성 규칙

기존 의존 방향 `api → services → models`(`schemas`는 검증용)를 그대로 따른다.

- [ ] TODO: 채팅 모듈이 의존해도 되는 모듈
- [ ] TODO: 채팅 모듈이 의존하면 안 되는 모듈
- [ ] TODO: 다른 도메인이 채팅 모듈을 호출하는 방식 (예: 이벤트)

## 데이터 모델

<!-- 테이블, 상태값(Python Enum + non-native Enum CHECK 제약, CLAUDE.md 규칙 참고), 인덱스 -->

- 채팅방 상태(`ACTIVE`/`INACTIVE`/`CLOSED`)와 `statusReason`은 채팅방마다 저장한다. 요청·지원·분쟁 상태가 바뀔 때 해당 채팅방의 상태를 함께 갱신한다.
- 차단은 채팅방 상태에 반영하지 않는다. 차단·해제는 차단 테이블만 바꾸고, 메시지 전송 시 채팅방 상태와 차단 기록을 함께 검사한다.
- 사용자 차단 기록은 별도 테이블에 저장한다. 차단 구현은 별도 브랜치에서 한다.

## 대안과 결정

| 대안 | 장점 | 단점 | 결정 |
|------|------|------|------|
| TODO | | | |

## 리스크와 후속 작업

- TODO
