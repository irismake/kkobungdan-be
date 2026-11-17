"""채팅 통합 테스트 (API + MySQL, tests/conftest.py 의 client/db fixture 사용).

시나리오 정본: docs/domains/chat/test-scenarios.md 의 CHAT-TS-*
TDD 흐름: docs/design-docs/tdd-workflow.md
"""

import pytest


@pytest.mark.scenario("CHAT-TS-002")
@pytest.mark.skip(reason="구현 전")
def test_chat_integration_placeholder() -> None:
    """채팅 테스트 자리. 시나리오 작성 후 실제 테스트로 바꾼다."""
