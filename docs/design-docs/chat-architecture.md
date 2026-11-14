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

## 대안과 결정

| 대안 | 장점 | 단점 | 결정 |
|------|------|------|------|
| TODO | | | |

## 리스크와 후속 작업

- TODO
