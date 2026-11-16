# 관리자 사용자 목록 조회 API

작성일: 2026-08-25 · 상태: 구현 완료 · 근거 문서: [`2026-08-22-admin-web-api.md`](./2026-08-22-admin-web-api.md)

## 배경

관리자 웹에 사용자 관리 화면이 필요하다. 지금까지 관리자 API는 요청·지원·분쟁·환불·지급만 다뤘고
사용자 자체를 나열하는 경로가 없다. 화면이 요구하는 항목은 이름, 사용자 ID, 회원 가입일,
임무 수행 횟수 네 가지다.

## 결정 사항

| # | 항목 | 결정 |
|---|---|---|
| U1 | 임무 수행 횟수의 정본 | **`users.level`을 그대로 내려준다.** 이 값은 지원이 `ALL_COMPLETED`로 끝날 때 꼬붕에게 1씩 오르는, 이미 존재하는 "성공 완료한 꼬붕 Offer 수"다. `missions`를 다시 집계하지 않는다 |
| U2 | 응답 필드명 | `missionCount`. FE 화면 용어가 "임무 수행 횟수"이고 `level`은 앱 프로필의 레벨 표시와 의미가 겹쳐 혼동된다. 값의 출처는 스키마 설명에 명시한다 |
| U3 | 조회 대상 | **앱 사용자만**(`is_admin = false`). 관리자 콘솔 계정은 사용자 관리 대상이 아니다 |
| U4 | 탈퇴 사용자 | 목록에 **포함**한다. 탈퇴 시 `name`이 비므로 다른 관리자 응답과 같이 `탈퇴한 사용자`로 표시한다 |
| U5 | 정렬 | `created_at DESC, id DESC`. 다른 관리자 목록과 동일하다 |
| U6 | 검색 | `keyword` 하나로 이름 부분 일치 또는 사용자 ID 완전 일치를 찾는다. 사용자 ID는 UUID라 부분 일치가 의미 없다 |
| U7 | 경로 | `GET /v1/admin/user`. 관리자 목록 경로는 단수형(`/proposal`, `/offer`, `/refund`)을 쓴다 |

## 엔드포인트

```
GET /v1/admin/user?keyword={keyword}&page={page}&size={size}
```

응답: `ApiResponse<PageResponse<AdminUserSummaryResponse>>`

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | string | 사용자 ID (UUID) |
| `name` | string | 사용자 이름. 탈퇴·누락 시 `탈퇴한 사용자` |
| `createdAt` | datetime | 회원 가입일 |
| `missionCount` | number | 임무 수행 횟수 (`users.level`) |

## 파일 계획

| 파일 | 작업 |
|---|---|
| `app/schemas/admin.py` | `AdminUserSummaryResponse` 추가 |
| `app/services/admin/admin_query_service.py` | `list_users()` 추가 |
| `app/api/v1/admin/admin_router.py` | `GET /admin/user` 등록 |
| `app/core/openapi.py` | `ADMIN_USER_PAGE_EXAMPLE` 추가 |
| `tests/test_admin_web_api_integration.py` | 목록·검색·필터 통합 테스트 |
| `docs/api-spec/README.md` | Admin Execution API 표에 행 추가 |

스키마 변경 없음 → 마이그레이션 없음.

## 검증 결과 (2026-08-25)

- `pytest tests/test_admin_web_api_integration.py tests/test_openapi.py` 통과
- `pytest` 전체 통과

## 남은 일

- 사용자 상세 조회(`GET /v1/admin/user/{userId}`)는 요구가 없어 만들지 않았다. 화면에 상세가 생기면 추가한다
- `users.level`은 분쟁을 관리자가 완료로 판정한 건은 올리지 않는다. 임무 수행 횟수를 미션 기준으로
  다시 정의해야 하면 U1을 재검토한다
