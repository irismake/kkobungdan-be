"""채팅 통합 테스트 (API + MySQL, tests/conftest.py 의 client/db fixture 사용).

시나리오 정본: docs/domains/chat/test-scenarios.md 의 CHAT-TS-*
TDD 흐름: docs/design-docs/tdd-workflow.md
"""

import pytest


<<<<<<< HEAD
@pytest.mark.scenario("CHAT-TS-002")
@pytest.mark.skip(reason="구현 전")
def test_chat_integration_placeholder() -> None:
    """채팅 테스트 자리. 시나리오 작성 후 실제 테스트로 바꾼다."""
=======
@pytest.mark.skip(reason="CHAT-TS-001: 구현 전")
def test_chat_integration_placeholder() -> None:
    """CHAT-TS-001"""
>>>>>>> 4b40297 (docs: 채팅 테스트 시나리오 작성과 사용자 표시 용어 정리)
