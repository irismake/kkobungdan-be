#!/usr/bin/env bash
# 테스트와 정적 검사를 한 번에 실행한다. 로컬과 CI(.github/workflows/test.yml)가 같은 스크립트를 쓴다.
#
# 사용법:
#   scripts/verify.sh            # 정적 검사 + 전체 테스트
#   scripts/verify.sh static     # 정적 검사만
#   scripts/verify.sh unit       # 단위 테스트만 (*_integration.py 제외, DB 불필요)
#   scripts/verify.sh integration  # 전체 테스트 (MySQL 필요, AGENTS.md "테스트 실행 규칙" 참고)
#
# 테스트 분류는 docs/references/testing-guidelines.md 의 파일명 규칙을 따른다.
set -euo pipefail

cd "$(dirname "$0")/.."

# AGENTS.md "테스트 실행 규칙"의 테스트 DB 설정. 이미 지정된 값이 있으면 그대로 쓴다.
# DB_NAME에는 접미사 없는 이름을 준다. tests/conftest.py가 `_test`를 붙여 실제 DB(orderrun_test)에 접속한다.
export DB_HOST="${DB_HOST:-127.0.0.1}"
export DB_PORT="${DB_PORT:-3307}"
export DB_USERNAME="${DB_USERNAME:-orderrun_user}"
export DB_PASSWORD="${DB_PASSWORD:-orderrun_pass}"
export DB_NAME="${DB_NAME:-orderrun}"

PYTHON="${PYTHON:-$(command -v python || command -v python3)}"

target="${1:-all}"

run_static() {
  echo "==> 정적 검사"
  "$PYTHON" -m compileall -q app tests
  # TODO: 정적 검사 도구(ruff, mypy 등)를 도입하면 여기에 추가한다.
}

run_unit() {
  echo "==> 단위 테스트"
  "$PYTHON" -m pytest --ignore-glob='*_integration.py'
}

run_integration() {
  echo "==> 전체 테스트 (통합 포함)"
  "$PYTHON" -m pytest
}

case "$target" in
  static) run_static ;;
  unit) run_unit ;;
  integration) run_integration ;;
  all)
    run_static
    run_integration
    ;;
  *)
    echo "알 수 없는 대상: $target (static | unit | integration | all)" >&2
    exit 2
    ;;
esac

echo "==> 검증 완료: $target"
