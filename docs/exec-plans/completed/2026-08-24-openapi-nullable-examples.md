# OpenAPI 예시에서 사라지는 nullable 필드 복원

## 목표

- 값이 `null`인 필드가 API 문서 예시에 그대로 보이게 한다. 클라이언트가 응답에 어떤 필드가
  오는지 문서만 보고 알 수 있어야 한다.

## 배경

FastAPI의 `get_openapi()`는 마지막에 스키마를 `jsonable_encoder(..., exclude_none=True)`로
인코딩한다. 그래서 라우터에 선언한 예시에 `None`을 넣어도 문서에서는 그 키가 통째로 사라진다.

영향은 문서 전체다. 예를 들어 `GET /v1/admin/missions`의 `started` 예시에서 `resolution`,
`runnerConfirmedAt`, `ordererConfirmedAt`, `disputedAt`, `completedAt`, `failedAt`,
`resolvedAt`, `payoutMemo` 등 nullable 필드가 전부 빠져 보인다. 클라이언트는 이 필드들이
응답에 없다고 오해하거나, 파싱 모델에서 누락한다.

`app/main.py`의 `custom_openapi()`에는 이미 이 문제의 국소 대응이 들어 있다. 모든 응답 예시를
순회하며 `error.details`가 없으면 `None`을 도로 넣는 코드다. 에러 예시 한 필드만 손으로 되살린
셈이고, 성공 응답의 nullable 필드는 그대로 사라진 상태다.

## 범위와 비범위

- 범위: 생성된 스키마에 라우트 선언 예시를 원본 그대로 되돌리는 후처리, `error.details` 국소
  대응 제거, 회귀 테스트, 문서.
- 비범위: 예시 내용 자체의 개정, 응답 스키마 변경, `apply_global_error_responses`가 스키마 생성
  후에 붙이는 전역 에러 예시(이미 인코딩을 거치지 않아 `null`이 살아 있다).

## 가정

- 라우트에 선언한 예시(`route.responses`)가 정본이다. 인코딩 전 원본이 런타임에 그대로 남아
  있으므로 생성 후 다시 넣으면 된다.
- `example`과 `examples` 두 형태 모두 복원 대상이다.
- 예시를 통째로 교체하지 않고 `content."application/json"`의 해당 키만 덮어쓴다. `schema`
  참조 등 FastAPI가 채운 나머지는 건드리지 않는다.

## 작업

1. `app/core/openapi.py`에 `restore_example_nulls(schema, routes)`를 추가한다.
2. `app/main.py`의 `custom_openapi()`에서 `get_openapi()` 직후에 호출하고,
   `error.details` 국소 대응 루프를 제거한다.
3. `tests/test_openapi.py`에 nullable 필드가 예시에 남는지 검증하는 테스트를 추가한다.
4. 기존 예시 기대값 테스트가 복원된 `null` 때문에 깨지면 실제 응답에 맞춰 갱신한다.
5. `docs/api-spec/README.md`에 예시 읽는 법을 한 줄 남긴다.

## 검증

- `python -m pytest -q`
- `GET /openapi.json`에서 미션 `started` 예시에 `resolution: null`과 시각 필드들이 보이는지
  확인한다.
- 에러 예시의 `details: null`이 그대로 유지되는지 확인한다.

## 검증 결과

- `python -m pytest -q` 272 passed.
- 미션 `started` 예시에 `resolution`, `runnerConfirmedAt`, `payoutMemo` 등 nullable 필드가
  `null`로 복원되는지 회귀 테스트로 고정했다.
- 에러 예시 571건 모두 `details` 키를 유지한다. 국소 대응을 지워도 회귀가 없다.
- 기존 예시 테스트 두 건은 필드 부재를 단언하고 있었다. 인코딩 때문에 사라졌을 뿐 계약에는
  있는 필드라 `is None` 단언으로 고쳤다.

## 후속

- 감싼 라우터를 따라 내려가며 접두사를 모으는 부분은 FastAPI 내부 구조(`original_router`,
  `include_context.prefix`)에 기댄다. 버전이 올라 구조가 바뀌면 복원이 조용히 멈출 수 있어
  `test_nullable_fields_stay_visible_in_examples`로 고정해 두었다.

## 상태

- 완료
