# User/Auth Test Scenarios

기준 테스트 파일: `tests/test_user_auth_integration.py`, `tests/test_timestamps.py`

## 보장 범위

- 회원가입, 로그인, refresh token 갱신, 로그아웃의 기본 흐름과 회원가입 시 FCM 토큰 저장을 검증한다.
- 일반 회원가입/로그인 인증번호는 보안 난수 기반 6자리 값이고 발송된 값만 확인되는지 검증한다.
- staging과 production의 로그인 데모 `01000000000`만 `123456`을 사용하고 SMS 공급자를 호출하지 않는지 검증한다.
- 로그인 데모 번호의 회원가입 발송 요청도 SMS 없이 거절되는지 검증한다.
- 인증번호 재발송이 이전 코드 유효기간 내에도 허용되고, 마지막 코드만 유효함을 검증한다.
- 인증번호 발송이 5분당 3회로 제한되고, 기간 경과 및 인증 성공 시 다시 허용됨을 검증한다.
- 모든 회원가입 번호와 일반 로그인 번호는 환경과 무관하게 `123456` 고정 우회를 허용하지 않는지 검증한다.
- 존재하지 않는 사용자, pending verification 없음, 코드 불일치 같은 인증 실패를 검증한다.
- 사용자 상세, 알림 설정, 닉네임 변경, FCM 토큰 저장 흐름을 검증한다.
- 회원 탈퇴는 사유 조회, 선택 사유 이력 저장, 기타 상세 사유 필수 검증, 개인정보 hard delete, 탈퇴 사용자 익명 표시, 매칭 전 활동 자동 취소, 진행 중 활동 차단을 검증한다.
- 매칭 전 자동 취소는 `HOLDING`, `POSTED`, `OFFERED` Proposal과 `WAITING` Offer를 대상으로 한다.
- 진행 중 활동 차단은 `MATCHED`, `ORDER_COMPLETED`, `DISPUTED` Proposal과 `ACCEPTED`, `RUNNER_COMPLETED`, `DISPUTED` Offer를 대상으로 한다.
- SMS background 발송 실패가 verification 저장을 깨지 않는지 확인한다.
- 사용자/인증 문서 모델과 ORM timestamp 관리 규칙을 검증한다.
