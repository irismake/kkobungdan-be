# User/Auth Domain

User/Auth는 전화번호 기반 인증, 토큰 생명주기, 사용자 상세, 알림 설정, FCM 토큰을 담당한다.

## 책임

- 회원가입/로그인 인증 코드 발송과 확인을 처리한다.
- access/refresh token 발급, 갱신, 로그아웃을 처리한다.
- 사용자 상세, 알림 설정, 닉네임 변경, FCM 토큰 저장 API의 사용자 식별 기준을 제공한다.
- 회원 탈퇴 시 종결되지 않은 Proposal·Offer·Mission·Refund가 있으면 차단하고, 대기 Offer만 자동 취소하며 개인정보 hard delete 정책을 적용한다.
- SMS 실패와 일반/데모 전화번호별 인증 코드 정책을 분리한다.
- 인증 코드 발송 횟수를 제한해 SMS 남용을 차단한다.

## 인증 코드 발송 제한

재발송은 이전 코드가 살아있어도 허용한다. 대기 시간 대신 횟수로 남용을 통제한다.

| 항목 | 값 |
|---|---|
| 제한 횟수 | 5분당 3회 (`VERIFICATION_CODE_TTL`과 동일 기간) |
| 카운트 단위 | `purpose`(SIGNUP/LOGIN) + 휴대폰 번호 |
| 초기화 조건 | 해당 번호/purpose의 마지막 인증 성공 이후 발송만 카운트 |
| 초과 응답 | HTTP 429 `PHONE_VERIFICATION_SEND_RATE_LIMITED` |

재발송 시 이전 PENDING 코드는 EXPIRED로 무효화되며, 가장 마지막에 발송된 코드만 확인에 사용할 수 있다.

## 인증번호와 운영 데모

- 일반 전화번호는 보안 난수로 생성한 6자리 인증번호를 SMS로 받는다.
- 로그인 데모 `01000000000`만 공개 검수 코드 `123456`을 사용하며 SMS 발송 작업과 SMS 공급자 호출을 모두 생략한다.
- 데모 번호도 pending verification, 5분 유효시간, 실패 횟수, 발송 횟수 제한을 동일하게 적용한다.
- 회원가입에는 데모 예외가 없고 일반 번호는 실제 SMS 인증번호를 사용한다. 로그인 데모 번호의 회원가입 발송은 SMS 없이 거절한다.
- 상세 사용자 행동은 [`../../product-specs/production-demo-login.md`](../../product-specs/production-demo-login.md)를 따른다.

## 정본 링크

- API 계약: [`../../api-spec/README.md`](../../api-spec/README.md)의 Auth API와 User API
- 사용자 부가 정책: [`../../domain.md`](../../domain.md)의 정책 기준
- 회원 탈퇴 정책: [`withdrawal-policy.md`](./withdrawal-policy.md)
- 테스트 보장: [`test-scenarios.md`](./test-scenarios.md)
- 서비스 책임 경계: [`../../design-docs/user-service-boundaries.md`](../../design-docs/user-service-boundaries.md)
